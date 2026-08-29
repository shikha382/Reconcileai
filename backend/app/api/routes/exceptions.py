"""GET /exceptions, GET /exceptions/{id}, GET /exceptions/{id}/provenance.

Every field returned here comes straight off an existing M3/M5/M6 object
(`EvidenceBundle`, `PolicyDecision`, `ResolutionProposal`, `ContradictionRecord`,
`DecisionProvenance`) -- this module never recomputes a category, a risk
level, a verification result, or a decision; it only shapes what M3-M6
already computed into the public DTOs.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_run_registry, get_session, require_capability
from app.api.run_registry import RunRegistry
from app.api.schemas import (
    ChallengeSummary,
    ExceptionDetailResponse,
    ExceptionListItem,
    ExceptionListResponse,
    ExplanationResponse,
    HypothesisSummary,
    PolicyResultSummary,
    PrioritizedExceptionResponse,
    PriorityInfoResponse,
    ProvenanceResponse,
    QueueResponse,
    QueueSummaryResponse,
    ReviewSummary,
    TimelineEntryResponse,
)
from app.audit.provenance import build_decision_summary, get_decision_provenance
from app.api.errors import ApiError
from app.api.run_registry import RunNotFoundError
from app.db.models import Payment
from app.explainability.builder import build_explanation
from app.policy.schemas import Capability
from app.prioritization.queue import QueueFilters, get_priority_queue, summarize_queue
from app.prioritization.scorer import attach_priority, build_prioritized_exception
from app.services.decision_service import DecisionResult

router = APIRouter(tags=["exceptions"])

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


def _verification_conclusion(decision: DecisionResult) -> str:
    if any(c.status == "CONTRADICTED" for c in decision.contradiction_records):
        return "CONTRADICTED"
    if decision.ai_investigation is not None:
        return "VERIFIED"
    return "NOT_NEEDED"


def _to_list_item(decision: DecisionResult) -> ExceptionListItem:
    bundle = decision.bundle
    return ExceptionListItem(
        exception_id=decision.exception_id, run_id=decision.run_id or "", order_id=bundle.order_id,
        payment_id=bundle.payment_id, category=bundle.category, reconciliation_status=bundle.reconciliation_status,
        financial_exposure=str(decision.proposal.financial_impact), risk_level=decision.policy_decision.risk_level.value,
        decision=decision.policy_decision.decision.value, review_required=decision.policy_decision.required_approval,
        ai_investigated=decision.ai_investigation is not None,
        contradiction_found=any(c.status == "CONTRADICTED" for c in decision.contradiction_records),
    )


def _to_detail(decision: DecisionResult) -> ExceptionDetailResponse:
    bundle = decision.bundle
    hypotheses = []
    if decision.ai_investigation is not None:
        for outcome in decision.ai_investigation.outcomes:
            hypotheses.append(HypothesisSummary(
                hypothesis_id=outcome.hypothesis.hypothesis_id, hypothesis_type=outcome.hypothesis.hypothesis_type.value,
                claim=outcome.hypothesis.claim, confidence=outcome.hypothesis.confidence,
            ))
    challenges = [
        ChallengeSummary(
            hypothesis_id=c.hypothesis_id, hypothesis_type=c.hypothesis_type, status=c.status, reason=c.reason,
            expected_value=c.expected_value, observed_value=c.observed_value, residual=c.residual,
        )
        for c in decision.contradiction_records
    ]
    review = None
    if decision.review is not None:
        review = ReviewSummary(
            review_id=decision.review.review_id, state=decision.review.state.value,
            dual_control_required=decision.review.dual_control_required, created_by=decision.review.created_by,
        )
    return ExceptionDetailResponse(
        exception_id=decision.exception_id, run_id=decision.run_id or "", correlation_id=decision.correlation_id,
        order_id=bundle.order_id, payment_id=bundle.payment_id, category=bundle.category,
        reconciliation_status=bundle.reconciliation_status, financial_exposure=str(decision.proposal.financial_impact),
        risk_level=decision.policy_decision.risk_level.value, risk_score=str(bundle.risk_score),
        ai_investigated=decision.ai_investigation is not None, hypotheses=hypotheses, challenges=challenges,
        verification_conclusion=_verification_conclusion(decision),
        policy=PolicyResultSummary(
            decision=decision.policy_decision.decision.value, policy_id=decision.policy_decision.policy_id,
            policy_version=decision.policy_decision.policy_version, risk_level=decision.policy_decision.risk_level.value,
            required_approval=decision.policy_decision.required_approval, reasons=decision.policy_decision.reasons,
            blocked_reasons=decision.policy_decision.blocked_reasons,
        ),
        decision=decision.policy_decision.decision.value, review=review, provenance_available=True,
    )


@router.get(
    "/exceptions", response_model=ExceptionListResponse,
    summary="List exceptions", description="Lists exceptions from completed runs, with bounded pagination and safe, domain-backed filtering.",
)
def list_exceptions(
    run_id: Optional[str] = Query(default=None, description="Filter to one run's exceptions."),
    category: Optional[str] = Query(default=None, description="Filter by ExceptionCategory value (e.g. fee_mismatch)."),
    risk_level: Optional[str] = Query(default=None, description="Filter by risk level (LOW/MEDIUM/HIGH/CRITICAL)."),
    decision: Optional[str] = Query(default=None, description="Filter by final PolicyDecisionType (e.g. HUMAN_REVIEW)."),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_EXCEPTION)),
) -> ExceptionListResponse:
    decisions = registry.list_exceptions(run_id=run_id)

    if category is not None:
        decisions = [d for d in decisions if d.bundle.category == category]
    if risk_level is not None:
        decisions = [d for d in decisions if d.policy_decision.risk_level.value == risk_level.upper()]
    if decision is not None:
        decisions = [d for d in decisions if d.policy_decision.decision.value == decision.upper()]

    total = len(decisions)
    start = (page - 1) * page_size
    page_items = decisions[start:start + page_size]

    return ExceptionListResponse(
        items=[_to_list_item(d) for d in page_items], page=page, page_size=page_size, total=total,
    )


# NOTE: this route is registered BEFORE /exceptions/{exception_id} (which
# has the same path-segment shape) so "queue" is never captured as an
# exception_id path parameter -- FastAPI/Starlette match routes in
# registration order.
@router.get(
    "/exceptions/queue", response_model=QueueResponse,
    summary="Get the deterministic, prioritized finance work queue",
    description=(
        "Milestone 11: a READ-ONLY operational view over already-decided exceptions for one run. Builds one "
        "PrioritizedException per exception by reusing M5's existing assess_priority/assess_sla (never a second "
        "priority formula) plus the real risk/exposure/decision already computed by M3/M5/M6, and M10's "
        "explanation for contradiction/missing-evidence counts. Ordering is deterministic (same inputs, same "
        "order, every time) -- priority can never change the underlying policy decision, verification result, "
        "or financial record."
    ),
)
def get_exceptions_queue(
    run_id: str = Query(..., description="The run whose exceptions should be prioritized."),
    priority: Optional[str] = Query(default=None, description="Filter by priority (P0/P1/P2/P3)."),
    risk_level: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    decision_status: Optional[str] = Query(default=None),
    sla_status: Optional[str] = Query(default=None),
    min_age_days: Optional[int] = Query(default=None, ge=0),
    min_exposure: Optional[str] = Query(default=None, description="Decimal string, e.g. '1000.00'."),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    session: Session = Depends(get_session),
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_EXCEPTION)),
) -> QueueResponse:
    from decimal import Decimal, InvalidOperation

    run_result = registry.get_run(run_id)  # raises RunNotFoundError -> 404, see app.api.errors
    if run_result.reference_now is None:
        raise ApiError("Run has no reference timestamp available for prioritization.", code="QUEUE_UNAVAILABLE", status_code=409)

    min_exposure_decimal = None
    if min_exposure is not None:
        try:
            min_exposure_decimal = Decimal(min_exposure)
        except InvalidOperation:
            raise ApiError(f"min_exposure {min_exposure!r} is not a valid decimal.", code="INVALID_FILTER", status_code=400)

    decisions = list(run_result.decisions.values())
    payment_ids = {d.bundle.payment_id for d in decisions}
    payments_by_id = {
        p.payment_id: p for p in session.query(Payment).filter(Payment.payment_id.in_(payment_ids)).all()
    }

    prioritized = []
    for decision in decisions:
        payment = payments_by_id.get(decision.bundle.payment_id)
        if payment is None:
            continue  # a payment the registry references but the DB no longer has -- skip, never fabricate
        explanation = build_explanation(decision)
        prioritized.append(build_prioritized_exception(decision, payment, run_result.reference_now, explanation))

    filters = QueueFilters(
        priority=priority, risk_level=risk_level, category=category, decision_status=decision_status,
        sla_status=sla_status, min_age_days=min_age_days, min_exposure=min_exposure_decimal,
    )
    ordered = get_priority_queue(prioritized, filters)
    summary = summarize_queue(ordered)

    total = len(ordered)
    start = (page - 1) * page_size
    page_items = ordered[start:start + page_size]

    return QueueResponse(
        items=[PrioritizedExceptionResponse(**p.to_dict()) for p in page_items],
        summary=QueueSummaryResponse(**summary.to_dict()), page=page, page_size=page_size, total=total,
    )


@router.get(
    "/exceptions/{exception_id}", response_model=ExceptionDetailResponse,
    summary="Get one exception's full safe-to-display summary",
    description=(
        "Returns category, exposure, risk, AI hypotheses (structured summaries, not hidden chain-of-thought), "
        "challenge/contradiction results, the policy decision, and review state -- everything M3-M6 already "
        "computed for this exception, reshaped into the public contract."
    ),
)
def get_exception(
    exception_id: str,
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_EXCEPTION)),
) -> ExceptionDetailResponse:
    decision = registry.get_exception(exception_id)  # raises ExceptionNotFoundError -> 404
    return _to_detail(decision)


@router.get(
    "/exceptions/{exception_id}/provenance", response_model=ProvenanceResponse,
    summary="Get an exception's full decision provenance",
    description=(
        "Calls the existing M6 provenance service (get_decision_provenance/build_decision_summary) directly -- "
        "this route never reconstructs provenance itself. Answers what happened, why, what the AI believed, "
        "what evidence supported/contradicted it, what the verifier proved, what policy applied, and whether "
        "the audit chain is valid."
    ),
)
def get_exception_provenance(
    exception_id: str,
    session: Session = Depends(get_session),
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_PROVENANCE)),
) -> ProvenanceResponse:
    registry.get_exception(exception_id)  # raises ExceptionNotFoundError -> 404 before touching the ledger

    provenance = get_decision_provenance(session, exception_id)
    summary = build_decision_summary(provenance)

    return ProvenanceResponse(
        exception_id=provenance.exception_id, correlation_id=provenance.correlation_id,
        timeline=[
            TimelineEntryResponse(timestamp=t.timestamp, event_type=t.event_type, actor_type=t.actor_type, actor_id=t.actor_id)
            for t in provenance.timeline
        ],
        ai_believed=[b for b in summary["ai_believed"] if b is not None],
        supporting_evidence=[e for e in summary["supporting_evidence"] if e],
        contradicting_evidence=[e for e in summary["contradicting_evidence"] if e],
        verification_conclusion=summary["verification_conclusion"], policy_decision=summary["policy_decision"],
        policy_id=summary["policy_id"], policy_version=summary["policy_version"],
        financial_exposure=summary["financial_exposure"], approval_required=summary["approval_required"],
        review_id=summary["review_id"], audit_chain_valid=summary["audit_chain_valid"],
        audit_events_checked=summary["audit_events_checked"],
    )


@router.get(
    "/exceptions/{exception_id}/explanation", response_model=ExplanationResponse,
    summary="Get an exception's canonical, evidence-first explanation",
    description=(
        "Milestone 10: assembles the canonical structured explanation contract (app.explainability.builder"
        ".build_explanation) directly from the already-computed DecisionResult -- this route performs no "
        "matching, verification, risk, policy, or audit logic of its own, and reruns none of M2-M6's expensive "
        "stages. Distinguishes AI hypotheses from verified fact, represents contradictions and missing evidence "
        "explicitly, and never fabricates a claim not backed by real evidence."
    ),
)
def get_exception_explanation(
    exception_id: str,
    session: Session = Depends(get_session),
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_PROVENANCE)),
) -> ExplanationResponse:
    decision = registry.get_exception(exception_id)  # raises ExceptionNotFoundError -> 404
    explanation = build_explanation(decision)  # no context/payment available via the registry -- still fully evidence-backed, just without the literal FeeRule id

    # M12 addition: attach M11's priority info (reason codes, recommended
    # action) to the canonical explanation when the owning run's
    # reference_now and the payment are both available -- best-effort only,
    # never fabricated. Mirrors exactly what GET /exceptions/queue already
    # does per-item; this just does it for the single-exception explanation
    # too, per Phase 8/13's instruction to surface "why is this prioritized"
    # from the SAME reason codes, not a second explanation.
    try:
        run_result = registry.get_run(decision.run_id) if decision.run_id else None
    except RunNotFoundError:
        run_result = None
    if run_result is not None and run_result.reference_now is not None:
        payment = session.query(Payment).filter(Payment.payment_id == decision.bundle.payment_id).one_or_none()
        if payment is not None:
            prioritized = build_prioritized_exception(decision, payment, run_result.reference_now, explanation)
            attach_priority(explanation, prioritized)

    return ExplanationResponse(**explanation.to_dict())
