"""Milestone 6 orchestrator: the SINGLE unified trust chain for one
exception, regardless of whether AI investigation was needed.

    M3 EvidenceBundle -> (M4 AI investigation, only if M3 left it
    unverified) -> challenge/contradiction classification (M6) -> M5
    PolicyEngine (the one authority for the final decision, always) ->
    ResolutionProposal -> (ReviewRequest if required) -> every step
    recorded on the audit ledger under one correlation_id.

Before M6, `app.services.ai_exception_service.resolve_one` computed its own
final decision independently of `app.policy.engine.evaluate_policy` for
AI-assisted exceptions -- two separate authorities reaching what happened to
be the same answer on this dataset, but not architecturally unified. This
module is the fix: M5's PolicyEngine decides EVERY exception's fate, AI or
not; the AI layer's job is strictly to propose and gather evidence, per the
project's core principle. `ai_exception_service`/`resolution_service`
themselves are unchanged and still independently correct/tested -- this is
an additive integration layer, not a rewrite of either.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from app.ai.provider import LLMProvider
from app.ai.tools import InvestigationContext
from app.challenge.contradiction import ContradictionRecord, build_contradiction_record, has_unresolved_contradiction
from app.engines.evidence.bundle import EvidenceBundle
from app.engines.evidence.candidates import why_not_matched
from app.ai.controller import investigate
from app.ai.routing import needs_ai_investigation
from app.ai.verifier import validate_grounding
from app.audit.ledger import AuditLedger
from app.policy.approval import ApprovalWorkflowStore
from app.policy.engine import evaluate_policy
from app.policy.schemas import Actor, ActorType, PolicyDecision, ResolutionProposal, ReviewRequest
from app.services.resolution_service import build_policy_input, build_resolution_proposal

SYSTEM_ACTOR = Actor(ActorType.SYSTEM, "reconcileai-decision-service")


@dataclass
class DecisionResult:
    correlation_id: str
    exception_id: str
    bundle: EvidenceBundle
    ai_investigation: object | None
    contradiction_records: list[ContradictionRecord]
    policy_decision: PolicyDecision
    proposal: ResolutionProposal
    review: ReviewRequest | None
    run_id: str | None = None


def run_decision_pipeline(
    payment, bundle: EvidenceBundle, reconciliation_context, graph, provider: LLMProvider,
    ledger: AuditLedger, reference_now: datetime, approval_store: ApprovalWorkflowStore | None = None,
    *, run_id: str | None = None,
) -> DecisionResult:
    """Per-exception decision authority (M6). `run_id` is an optional M7
    addition only -- when a caller (e.g. app.services.reconciliation_pipeline)
    is orchestrating a full batch run, it's threaded into the
    EXCEPTION_CREATED payload so `run -> exception` stays reconstructable
    from the audit trail alone, without adding a new ledger column or
    changing anything about this function's own decision logic."""
    correlation_id = f"CORR-{uuid4().hex[:12]}"

    exception_created_payload = {
        "payment_id": bundle.payment_id, "order_id": bundle.order_id, "category": bundle.category,
        "reconciliation_status": bundle.reconciliation_status,
    }
    if run_id is not None:
        exception_created_payload["run_id"] = run_id

    ledger.append(
        "EXCEPTION_CREATED", "exception", bundle.exception_id, SYSTEM_ACTOR.actor_type.value, "decision_service",
        exception_created_payload, correlation_id, SYSTEM_ACTOR.actor_id,
    )

    ai_result = None
    contradiction_records: list[ContradictionRecord] = []
    ai_confidence = None

    if needs_ai_investigation(bundle.root_cause):
        ledger.append("AI_INVESTIGATION_STARTED", "exception", bundle.exception_id, SYSTEM_ACTOR.actor_type.value,
                      "decision_service", {}, correlation_id, SYSTEM_ACTOR.actor_id)

        report = why_not_matched(payment, reconciliation_context)
        ctx = InvestigationContext(
            exception_id=bundle.exception_id, payment=payment, reconciliation_context=reconciliation_context,
            graph=graph, negative_evidence_report=report,
        )
        ai_result = investigate(bundle.exception_id, ctx, provider)

        ledger.append(
            "AI_INVESTIGATION_COMPLETED", "exception", bundle.exception_id, "AI", "decision_service",
            {"provider": ai_result.trace.provider, "model": ai_result.trace.model,
             "tool_call_count": ai_result.trace.tool_call_count, "hypotheses_tested": ai_result.trace.hypotheses_tested,
             "duration_seconds": ai_result.trace.duration_seconds},
            correlation_id, "ai-controller",
        )

        for outcome in ai_result.outcomes:
            ai_confidence = outcome.hypothesis.confidence  # last-tested hypothesis's self-report, audit-only
            grounding_violations = [] if outcome.grounded else ["ungrounded"]
            record = build_contradiction_record(outcome, grounding_violations)
            contradiction_records.append(record)

            ledger.append(
                "HYPOTHESIS_CREATED", "exception", bundle.exception_id, "AI", "decision_service",
                {"hypothesis_id": outcome.hypothesis.hypothesis_id, "hypothesis_type": outcome.hypothesis.hypothesis_type.value,
                 "claim": outcome.hypothesis.claim, "confidence": outcome.hypothesis.confidence},
                correlation_id, "ai-controller",
            )
            ledger.append(
                "HYPOTHESIS_CHALLENGED", "exception", bundle.exception_id, "VERIFIER", "decision_service",
                record.to_dict(), correlation_id, "deterministic-verifier",
            )
            if record.status == "CONTRADICTED":
                ledger.append("CONTRADICTION_FOUND", "exception", bundle.exception_id, "VERIFIER", "decision_service",
                              record.to_dict(), correlation_id, "deterministic-verifier")
                ledger.append("HYPOTHESIS_REJECTED", "exception", bundle.exception_id, "VERIFIER", "decision_service",
                              {"hypothesis_id": outcome.hypothesis.hypothesis_id, "reason": outcome.reason},
                              correlation_id, "deterministic-verifier")
            elif record.status == "SUPPORTED":
                ledger.append("HYPOTHESIS_VERIFIED", "exception", bundle.exception_id, "VERIFIER", "decision_service",
                              {"hypothesis_id": outcome.hypothesis.hypothesis_id, "reason": outcome.reason},
                              correlation_id, "deterministic-verifier")

    # --- Self-challenge rule (Phase 11): a known contradiction is fed to
    # the policy engine as structured evidence (`conflicting_evidence`),
    # which already has a dedicated rule (POLICY-CONFLICT-001) blocking
    # auto-resolution on it. The challenge layer never decides the outcome
    # itself -- it only ever enriches PolicyInput.
    policy_input = build_policy_input(bundle, ai_confidence)
    if has_unresolved_contradiction(contradiction_records):
        policy_input.conflicting_evidence = True

    policy_decision = evaluate_policy(policy_input)
    ledger.append("POLICY_EVALUATED", "exception", bundle.exception_id, "POLICY_ENGINE", "decision_service",
                  policy_decision.to_dict(), correlation_id, "policy-engine")

    proposal = build_resolution_proposal(bundle, policy_decision)
    ledger.append("RESOLUTION_PROPOSED", "exception", bundle.exception_id, SYSTEM_ACTOR.actor_type.value,
                  "decision_service", proposal.to_dict(), correlation_id, SYSTEM_ACTOR.actor_id)

    review = None
    if policy_decision.required_approval and approval_store is not None:
        rejected_alternatives = [
            {"settlement_id": c.settlement_id, "verdict": c.verdict, "score": str(c.score)}
            for c in bundle.negative_evidence_report.candidates if c.verdict == "REJECTED"
        ]
        review = approval_store.create_review_request(
            bundle.exception_id, proposal, policy_decision, SYSTEM_ACTOR.actor_id,
            rejected_alternatives=rejected_alternatives, reference_now=reference_now,
        )
        ledger.append("REVIEW_REQUESTED", "exception", bundle.exception_id, SYSTEM_ACTOR.actor_type.value,
                      "decision_service", {"review_id": review.review_id, "dual_control_required": review.dual_control_required},
                      correlation_id, SYSTEM_ACTOR.actor_id)

    return DecisionResult(
        correlation_id=correlation_id, exception_id=bundle.exception_id, bundle=bundle,
        ai_investigation=ai_result, contradiction_records=contradiction_records,
        policy_decision=policy_decision, proposal=proposal, review=review, run_id=run_id,
    )
