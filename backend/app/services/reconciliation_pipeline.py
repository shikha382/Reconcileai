"""Milestone 7: the single, application-level orchestrator that runs the
whole ReconcileAI pipeline end-to-end --

    INGEST + NORMALIZE (M1)
    -> DETERMINISTIC RECONCILIATION (M2)
    -> EXCEPTION INTELLIGENCE / NEGATIVE EVIDENCE (M3)
    -> per exception: AI INVESTIGATION (M4) -> SELF-CHALLENGE (M6)
       -> DETERMINISTIC VERIFICATION (M4/M2) -> RISK (M3) -> POLICY (M5)
       -> RESOLUTION / HUMAN REVIEW (M5)
    -> AUDIT (M6)
    -> PROVENANCE-READY RESULT (M6)

This module contains NO duplicated business logic and does not create a
second matching engine, verifier, policy engine, or audit system. Every
stage below is a call into an existing M1-M6 component (`ingest_source_directory`,
`run_exception_intelligence`, `run_decision_pipeline`, `AuditLedger`,
`verify_chain`); this file's only job is sequencing, run/correlation-id
bookkeeping, per-stage timing, result aggregation, and fail-safe error
handling at each stage boundary -- exactly the M7 brief's "orchestration
only" boundary.

Before M7, running the full pipeline meant separately calling
`run_exception_intelligence` and then `run_decision_pipeline` once per
bundle from a test/benchmark script -- correct, but requiring a caller to
know the wiring. `run_reconciliation_pipeline` is that wiring, done once,
reusably, with a `run_id` threaded through so a whole run (not just one
exception) is auditable and reconstructable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.ai.provider import LLMProvider
from app.audit.ledger import AuditLedger
from app.audit.verify import verify_chain
from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement
from app.engines.evidence.graph import build_graph
from app.engines.reconciliation.candidate_generation import build_context
from app.ingestion.pipeline import ingest_source_directory
from app.policy.approval import ApprovalWorkflowStore
from app.policy.schemas import PolicyDecisionType
from app.services.decision_service import DecisionResult, run_decision_pipeline
from app.services.exception_service import run_exception_intelligence


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class StageTiming:
    stage: str
    seconds: float

    def to_dict(self) -> dict:
        return {"stage": self.stage, "seconds": round(self.seconds, 4)}


@dataclass
class PipelineRunResult:
    """Phase 3's structured pipeline contract. Every count here is computed
    from real per-exception `PolicyDecision`s, never hard-coded."""

    run_id: str
    status: str  # "completed" | "failed"
    started_at: datetime
    completed_at: datetime | None = None
    records_processed: int = 0
    matched: int = 0
    exceptions: int = 0
    auto_resolved: int = 0
    human_review: int = 0
    rejected: int = 0
    # This codebase's actual PolicyDecisionType taxonomy (app.policy.schemas)
    # has no separate BLOCKED value -- the BLOCK tier's rules (e.g.
    # POLICY-VERIFIER-FAIL-001) produce PolicyDecisionType.REJECTED. `blocked`
    # is kept as an explicit alias of `rejected` (not a second, competing
    # status) purely so this result's shape matches the brief's own example
    # output without inventing a status the policy engine doesn't have.
    blocked: int = 0
    unresolved: int = 0
    escalated: int = 0  # PolicyDecisionType.ESCALATED exists in the enum but is not reachable from the current evaluate_policy logic -- kept for completeness/forward-compat, expected to stay 0
    audit_events: int = 0
    provenance_available: bool = False
    stage_timings: list[StageTiming] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decisions: dict[str, DecisionResult] = field(default_factory=dict)  # keyed by order_id -- programmatic access for golden tests/demo output, not part of the JSON contract below
    # M11 addition: the SAME reference_now every bundle's risk_score/SLA was
    # actually computed against (not wall-clock "now" at some later query
    # time) -- so a caller (the prioritization queue) can rebuild SLA/aging
    # assessments consistent with the numbers already baked into each
    # DecisionResult, instead of silently drifting from them. Not part of
    # the JSON contract (an internal timestamp, not a public API field).
    reference_now: datetime | None = None
    # M15 addition: the exact source directory this run ingested from, so a
    # caller (the new GET /runs/{run_id}/safety-metrics route) can look
    # for a sibling ground_truth.json to compute real, non-fabricated
    # safety metrics -- WITHOUT this run result claiming any metric itself.
    # Not part of the public JSON contract (an internal path, never returned
    # over HTTP directly -- see app.api.routes.runs's own path-safety
    # reasoning for why a raw filesystem path is never exposed to a caller).
    dataset_dir: Path | None = None

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id, "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "records_processed": self.records_processed, "matched": self.matched, "exceptions": self.exceptions,
            "auto_resolved": self.auto_resolved, "human_review": self.human_review,
            "blocked": self.blocked, "rejected": self.rejected, "unresolved": self.unresolved,
            "escalated": self.escalated,
            "audit_events": self.audit_events, "provenance_available": self.provenance_available,
            "stage_timings": [t.to_dict() for t in self.stage_timings],
            "errors": self.errors, "warnings": self.warnings,
        }


class _StageTimer:
    """Records wall-clock time for one pipeline stage (Phase 23). Never
    swallows an exception -- the caller decides fail-safe behavior at each
    stage boundary; this is observability only, not error handling."""

    def __init__(self, result: PipelineRunResult, stage: str):
        self._result = result
        self._stage = stage
        self._t0 = 0.0

    def __enter__(self) -> "_StageTimer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._result.stage_timings.append(StageTiming(self._stage, time.perf_counter() - self._t0))
        return False


def _record_run_event(ledger: AuditLedger, run_id: str, event_type: str, payload: dict) -> None:
    # entity_type="run" alongside M6's existing entity_type="exception"
    # events -- both share the same audit_events table and hash chain, no
    # second audit system. correlation_id=run_id ties every run-level event
    # together the same way M6 already ties one exception's events together.
    ledger.append(event_type, "run", run_id, "SYSTEM", "reconciliation_pipeline", payload, run_id)


def _tally(result: PipelineRunResult, decision: DecisionResult) -> None:
    d = decision.policy_decision.decision
    if d == PolicyDecisionType.SAFE_TO_RESOLVE:
        result.auto_resolved += 1
    elif d == PolicyDecisionType.HUMAN_REVIEW:
        result.human_review += 1
    elif d == PolicyDecisionType.REJECTED:
        result.rejected += 1
        result.blocked += 1  # see PipelineRunResult.blocked's docstring -- REJECTED *is* this system's block outcome
    elif d == PolicyDecisionType.UNRESOLVED:
        result.unresolved += 1
    elif d == PolicyDecisionType.ESCALATED:
        result.escalated += 1


def run_reconciliation_pipeline(
    session: Session, source_dir: Path, provider: LLMProvider,
    ledger: AuditLedger | None = None, approval_store: ApprovalWorkflowStore | None = None,
) -> PipelineRunResult:
    """The ONE end-to-end entry point (Phase 2/24). Ingests `source_dir`
    (M1), runs deterministic reconciliation + exception intelligence (M2/M3),
    then runs M6's existing `run_decision_pipeline` (AI investigation ->
    self-challenge -> deterministic verification -> risk -> policy ->
    resolution/review -> audit) once per exception, all under one `run_id`.

    Fail-safe (Phase 19): a failure in ingestion or matching fails the whole
    run explicitly (`status="failed"`) rather than returning a partially
    populated "completed" result. A failure processing one exception is
    caught, rolled back, and recorded as a warning -- that exception is
    simply absent from `decisions`, never silently counted as resolved.
    """
    run_id = f"RUN-{uuid4().hex[:12]}"
    started_at = _now()
    ledger = ledger if ledger is not None else AuditLedger(session)
    approval_store = approval_store if approval_store is not None else ApprovalWorkflowStore()

    result = PipelineRunResult(run_id=run_id, status="running", started_at=started_at, dataset_dir=source_dir)

    # --- Stage 1+2: INGEST + NORMALIZE (M1, reused as-is; normalization is
    # already an inseparable part of ingestion itself -- there is no
    # separate downstream normalization step to call). ---
    try:
        with _StageTimer(result, "ingestion"):
            ingest_source_directory(session, source_dir)
            session.commit()
    except Exception as exc:
        session.rollback()
        result.status, result.completed_at = "failed", _now()
        result.errors.append(f"ingestion failed: {exc}")
        try:
            _record_run_event(ledger, run_id, "RUN_FAILED", {"stage": "ingestion", "error": str(exc)})
            session.commit()
        except Exception:
            session.rollback()  # audit-fail-safe (M6 Phase 15): never let a failed audit write mask the real failure
        return result

    payments = session.query(Payment).all()
    settlements = session.query(Settlement).all()
    bank_txns = session.query(BankTransaction).all()
    refunds = session.query(Refund).all()
    fee_rules = session.query(FeeRule).all()
    result.records_processed = len(payments)

    # --- Stage 3+4: DETERMINISTIC RECONCILIATION (M2) + EXCEPTION
    # INTELLIGENCE / NEGATIVE EVIDENCE (M3) -- one call, exactly the wiring
    # M3 already established (`run_exception_intelligence`). ---
    try:
        with _StageTimer(result, "reconciliation_and_exception_intelligence"):
            m2_results, bundles = run_exception_intelligence(payments, settlements, bank_txns, refunds, fee_rules)
    except Exception as exc:
        result.status, result.completed_at = "failed", _now()
        result.errors.append(f"reconciliation/exception-intelligence failed: {exc}")
        try:
            _record_run_event(ledger, run_id, "RUN_FAILED", {"stage": "reconciliation", "error": str(exc)})
            session.commit()
        except Exception:
            session.rollback()
        return result

    result.matched = sum(1 for r in m2_results if r.status.value == "matched")
    result.exceptions = len(bundles)

    context = build_context(payments, settlements, bank_txns, refunds, fee_rules)
    graph = build_graph(payments, settlements, bank_txns, refunds)
    payments_by_id = {p.payment_id: p for p in payments}
    reference_now = max((p.captured_at for p in payments), default=started_at)
    result.reference_now = reference_now

    _record_run_event(ledger, run_id, "RUN_STARTED", {
        "source_dir": str(source_dir), "records_processed": result.records_processed, "exceptions": result.exceptions,
    })
    session.commit()

    # --- Stage 5-11: per exception -- AI INVESTIGATION (M4) ->
    # SELF-CHALLENGE (M6) -> DETERMINISTIC VERIFICATION -> RISK (M3) ->
    # POLICY (M5, the single decision authority) -> RESOLUTION/REVIEW (M5),
    # every step audited (M6) -- all via M6's own existing orchestrator,
    # `run_decision_pipeline`. Nothing here re-decides anything itself. ---
    with _StageTimer(result, "decision_pipeline"):
        for bundle in bundles:
            payment = payments_by_id[bundle.payment_id]
            try:
                decision = run_decision_pipeline(
                    payment, bundle, context, graph, provider, ledger, reference_now, approval_store, run_id=run_id,
                )
                session.commit()
            except Exception as exc:
                # Fail-safe (Phase 19): never let a crash mid-decision be
                # mistaken for a resolved exception. Roll back whatever this
                # attempt partially staged; the exception is simply absent
                # from `decisions` -- the safe outcome, not a silent
                # auto-resolve or a fabricated success.
                session.rollback()
                result.warnings.append(f"{bundle.exception_id} ({bundle.order_id}): decision pipeline failed safely, skipped: {exc}")
                continue

            result.decisions[bundle.order_id] = decision
            _tally(result, decision)

    # --- Stage 12: AUDIT + PROVENANCE READINESS (M6) ---
    result.audit_events = ledger.count()
    chain_result = verify_chain(session)
    result.provenance_available = chain_result.valid
    if not chain_result.valid:
        result.warnings.append(f"audit chain invalid at run completion: {chain_result.reason} (event {chain_result.first_invalid_event_id})")

    result.status, result.completed_at = "completed", _now()

    _record_run_event(ledger, run_id, "RUN_COMPLETED", {
        k: v for k, v in result.to_dict().items() if k not in ("stage_timings",)
    })
    session.commit()

    return result
