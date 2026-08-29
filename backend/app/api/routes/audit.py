"""GET /runs/{run_id}/audit -- calls M6's existing `AuditLedger`/`verify_chain`
directly. No second audit mechanism, no independent tamper-check logic here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_ledger, get_run_registry, get_session, require_capability
from app.api.run_registry import RunRegistry
from app.api.schemas import AuditEventDetailResponse, AuditEventListResponse, AuditEventSummary, AuditStatusResponse
from app.audit.ledger import AuditLedger
from app.audit.verify import verify_chain
from app.policy.schemas import Capability

router = APIRouter(tags=["audit"])

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


@router.get(
    "/runs/{run_id}/audit", response_model=AuditStatusResponse,
    summary="Get a run's audit status",
    description=(
        "Reports the tamper-evident audit trail status for one run -- event count (this run's own "
        "RUN_STARTED/RUN_COMPLETED bracket plus every one of its exceptions' events, via M6's indexed "
        "correlation-id lookups), whole-chain validity (M6's verify_chain, unchanged), and the run's "
        "first/last bracket events. Never reconstructs or re-verifies the chain independently of M6."
    ),
)
def get_run_audit_status(
    run_id: str,
    session: Session = Depends(get_session),
    ledger: AuditLedger = Depends(get_ledger),
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_AUDIT)),
) -> AuditStatusResponse:
    result = registry.get_run(run_id)  # raises RunNotFoundError -> 404 -- confirms the run exists before querying audit data

    run_events = ledger.events_for_correlation(run_id)
    event_count = len(run_events)
    for decision in result.decisions.values():
        event_count += len(ledger.events_for_correlation(decision.correlation_id))

    chain_result = verify_chain(session)

    first_event = None
    last_event = None
    if run_events:
        first_event = AuditEventSummary(event_id=run_events[0].event_id, event_type=run_events[0].event_type, timestamp=run_events[0].timestamp)
        last_event = AuditEventSummary(event_id=run_events[-1].event_id, event_type=run_events[-1].event_type, timestamp=run_events[-1].timestamp)

    return AuditStatusResponse(
        run_id=run_id, event_count=event_count, chain_valid=chain_result.valid,
        invalid_reason=chain_result.reason if not chain_result.valid else None,
        first_event=first_event, last_event=last_event,
    )


@router.get(
    "/runs/{run_id}/audit/events", response_model=AuditEventListResponse,
    summary="List a run's audit events",
    description=(
        "M12 addition: the smallest additive change for a real audit-log viewer. Reuses the exact same "
        "correlation-id aggregation as GET /runs/{run_id}/audit (this run's own bracket events plus every one of "
        "its exceptions' events, via M6's indexed AuditLedger.events_for_correlation), sorted by sequence -- the "
        "ledger's own tamper-evident, gap-free ordering. No second audit mechanism, no independent event store."
    ),
)
def list_run_audit_events(
    run_id: str,
    ledger: AuditLedger = Depends(get_ledger),
    registry: RunRegistry = Depends(get_run_registry),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    actor=Depends(require_capability(Capability.VIEW_AUDIT)),
) -> AuditEventListResponse:
    result = registry.get_run(run_id)  # raises RunNotFoundError -> 404

    records = list(ledger.events_for_correlation(run_id))
    for decision in result.decisions.values():
        records.extend(ledger.events_for_correlation(decision.correlation_id))
    records.sort(key=lambda r: r.sequence)

    total = len(records)
    start = (page - 1) * page_size
    page_records = records[start:start + page_size]

    return AuditEventListResponse(
        run_id=run_id,
        items=[
            AuditEventDetailResponse(
                event_id=r.event_id, sequence=r.sequence, event_type=r.event_type, timestamp=r.timestamp,
                actor_type=r.actor_type, actor_id=r.actor_id, entity_type=r.entity_type, entity_id=r.entity_id,
                correlation_id=r.correlation_id, details=r.payload_json,
            )
            for r in page_records
        ],
        page=page, page_size=page_size, total=total,
    )
