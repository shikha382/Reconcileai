"""POST /runs, GET /runs/{run_id} -- the ONLY place the API touches the M7
pipeline. This route does not perform ingestion, matching, AI reasoning,
verification, risk, or policy itself; it translates HTTP input into a call
to `run_reconciliation_pipeline` (M7, unchanged) and translates the
resulting `PipelineRunResult` into the public `RunResponse` DTO.
"""
from __future__ import annotations

from pathlib import Path
from threading import Lock

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.ai.provider import LLMProvider
from app.api.dependencies import get_approval_store, get_ledger, get_provider, get_run_registry, get_session, require_capability
from app.api.errors import InvalidDatasetError
from app.api.run_registry import RunRegistry
from app.api.schemas import RunCreateRequest, RunListResponse, RunResponse, SafetyMetricsResponse, StageTimingResponse
from app.audit.ledger import AuditLedger
from app.config import settings
from app.policy.approval import ApprovalWorkflowStore
from app.policy.schemas import Capability
from app.services.reconciliation_pipeline import PipelineRunResult, run_reconciliation_pipeline
from app.services.safety_metrics import compute_safety_metrics

router = APIRouter(tags=["runs"])

# The audit ledger deliberately derives each hash-linked sequence number from
# the previous committed event.  SQLite cannot make that read-then-append
# operation safe across two simultaneous writers by itself, so the demo API
# serializes its only write-heavy operation: starting a complete run.  This is
# a process-local release safeguard for the documented single-process demo,
# not a distributed lock or a production scalability claim.
_run_execution_lock = Lock()


def _to_run_response(result: PipelineRunResult) -> RunResponse:
    return RunResponse(
        run_id=result.run_id, status=result.status, started_at=result.started_at, completed_at=result.completed_at,
        duration_seconds=result.duration_seconds, records_processed=result.records_processed, matched=result.matched,
        exceptions=result.exceptions, auto_resolved=result.auto_resolved, human_review=result.human_review,
        blocked=result.blocked, rejected=result.rejected, unresolved=result.unresolved, escalated=result.escalated,
        audit_event_count=result.audit_events, audit_chain_valid=result.provenance_available,
        stage_timings=[StageTimingResponse(stage=t.stage, seconds=t.seconds) for t in result.stage_timings],
        errors=result.errors, warnings=result.warnings,
    )


def _resolve_dataset_dir(name: str) -> Path:
    # Path-traversal safe (Phase 22): `name` may only be a bare directory
    # name resolving to somewhere INSIDE settings.dataset_base_dir, never an
    # absolute path or a "../" escape -- checked by containment, not by
    # string-matching "..".
    base = settings.dataset_base_dir.resolve()
    candidate = (base / name).resolve()
    if candidate != base and base not in candidate.parents:
        raise InvalidDatasetError(f"dataset {name!r} is not a recognized dataset directory.")
    if not candidate.is_dir():
        raise InvalidDatasetError(f"dataset {name!r} was not found.")
    return candidate


@router.post(
    "/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED,
    summary="Start a reconciliation run",
    description=(
        "Runs the complete M7 pipeline end-to-end (ingest -> normalize -> deterministic reconciliation -> "
        "exception intelligence -> per exception: AI investigation -> self-challenge -> deterministic "
        "verification -> risk -> policy -> resolution/human review -> audit) against a supported dataset "
        "directory. This route calls run_reconciliation_pipeline exactly once; it never re-implements any "
        "matching, verification, policy, or audit logic itself."
    ),
)
def create_run(
    body: RunCreateRequest,
    session: Session = Depends(get_session),
    ledger: AuditLedger = Depends(get_ledger),
    approval_store: ApprovalWorkflowStore = Depends(get_approval_store),
    provider: LLMProvider = Depends(get_provider),
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.START_RECONCILIATION)),
) -> RunResponse:
    dataset_dir = _resolve_dataset_dir(body.dataset)
    with _run_execution_lock:
        result = run_reconciliation_pipeline(session, dataset_dir, provider, ledger, approval_store)
        registry.add(result)
    return _to_run_response(result)


@router.get(
    "/runs", response_model=RunListResponse,
    summary="List reconciliation runs",
    description=(
        "M12 addition: lists every run this API process has completed, most-recent first. Reuses "
        "RunRegistry.list_runs() (M8, unchanged) and the same _to_run_response shaping GET /runs/{id} already "
        "uses -- never re-runs or recomputes anything."
    ),
)
def list_runs(
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_RUN)),
) -> RunListResponse:
    results = sorted(registry.list_runs(), key=lambda r: r.started_at, reverse=True)
    return RunListResponse(items=[_to_run_response(r) for r in results], total=len(results))


@router.get(
    "/runs/{run_id}", response_model=RunResponse,
    summary="Get a reconciliation run's summary",
    description="Returns the STORED summary of a previously-completed run. Never re-runs the pipeline.",
)
def get_run(
    run_id: str,
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_RUN)),
) -> RunResponse:
    result = registry.get_run(run_id)  # raises RunNotFoundError -> handled as 404, see app.api.errors
    return _to_run_response(result)


@router.get(
    "/runs/{run_id}/safety-metrics", response_model=SafetyMetricsResponse,
    summary="Get a run's ground-truth-based safety metrics",
    description=(
        "Milestone 15: the unsafe (false) auto-resolution rate and match rate, computed by comparing this run's "
        "REAL decisions against a REAL ground_truth.json for the dataset it used -- ONLY when one exists. "
        "Reports `available=false` (never a fabricated number) when the run's dataset has no graded ground "
        "truth to compare against. Calls app.services.safety_metrics.compute_safety_metrics directly; performs "
        "no matching/verification/policy logic of its own."
    ),
)
def get_run_safety_metrics(
    run_id: str,
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_RUN)),
) -> SafetyMetricsResponse:
    result = registry.get_run(run_id)  # raises RunNotFoundError -> 404
    metrics = compute_safety_metrics(result)
    return SafetyMetricsResponse(
        available=metrics.available, total=metrics.total, graded=metrics.graded,
        false_auto_resolutions=metrics.false_auto_resolutions, false_auto_resolution_rate=metrics.false_auto_resolution_rate,
        match_rate=metrics.match_rate, reason_unavailable=metrics.reason_unavailable,
    )
