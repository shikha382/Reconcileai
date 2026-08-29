"""Milestone 11: builds one `PrioritizedException` per already-decided
exception. Read-only assembly -- reuses M5's existing `assess_priority`/
`assess_sla` (`app.policy.risk`) for the priority level/score and SLA
status (never a second priority formula), and reads risk/exposure straight
from the real `DecisionResult`/`EvidenceBundle` (M3/M6) and, when supplied,
the real `ExplanationReport` (M10) for contradiction/missing-evidence
counts. Nothing here recomputes risk, verifies anything, or evaluates
policy -- see `docs/prioritization.md`'s "relationship to M5/M10" sections.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.db.models import Payment
from app.explainability.schemas import ExplanationReport, PriorityInfo
from app.policy.risk import assess_priority, assess_sla
from app.prioritization.schemas import PrioritizedException, ReasonCode, RecommendedAction
from app.prioritization.schemas import PRIORITY_LEVEL_TO_CODE
from app.services.decision_service import DecisionResult

# Documented thresholds (Phase 5's own instruction: "only create codes
# actually supported by project data" / "do not invent arbitrary weights
# without documenting why"):
#
# HIGH_VALUE_REFUND_THRESHOLD: data/synthetic/generator.py's own
# gen_refund_mismatch generates order amounts uniformly in [500, 10000] for
# the refund_mismatch archetype -- 5000 is that range's own midpoint, not an
# arbitrary number invented here.
HIGH_VALUE_REFUND_THRESHOLD = Decimal("5000.00")

# OLD_EXCEPTION_AGE_DAYS reuses app.engines.risk.scoring.MAX_AGING_DAYS (the
# existing aging-factor cap M3's own risk_score formula already uses) rather
# than inventing a second age threshold -- an exception this old has already
# hit the maximum aging multiplier M3's risk score can apply.
from app.engines.risk.scoring import MAX_AGING_DAYS

_SETTLEMENT_CATEGORIES = frozenset({
    "split_settlement", "aggregated_settlement", "partial_settlement", "over_settlement", "under_settlement",
})


def _reason_codes(
    *, risk_level: str, sla_status: str, age_days: int, contradiction_count: int, missing_evidence_count: int,
    decision_status: str, category: Optional[str], unexplained_amount: Decimal, gross_amount: Decimal,
) -> list[str]:
    codes: list[str] = []
    if risk_level == "CRITICAL":
        codes.append(ReasonCode.CRITICAL_RISK)
    elif risk_level == "HIGH":
        codes.append(ReasonCode.HIGH_EXPOSURE)
    if sla_status == "BREACHED":
        codes.append(ReasonCode.SLA_BREACHED)
    elif sla_status == "AT_RISK":
        codes.append(ReasonCode.SLA_AT_RISK)
    if age_days >= MAX_AGING_DAYS:
        codes.append(ReasonCode.OLD_EXCEPTION)
    if contradiction_count > 0:
        codes.append(ReasonCode.CONTRADICTORY_EVIDENCE)
    if missing_evidence_count > 0:
        codes.append(ReasonCode.MISSING_EVIDENCE)
    if decision_status in ("HUMAN_REVIEW", "REJECTED"):
        codes.append(ReasonCode.AUTO_RESOLUTION_BLOCKED)
    if category == "refund_mismatch" and gross_amount > HIGH_VALUE_REFUND_THRESHOLD:
        codes.append(ReasonCode.HIGH_VALUE_REFUND)
    if unexplained_amount > Decimal("0.00"):
        codes.append(ReasonCode.UNRESOLVED_FINANCIAL_DIFFERENCE)
    if not codes:
        codes.append(ReasonCode.CLEAN_LOW_PRIORITY)
    return codes


def recommend_action(
    *, decision_status: str, category: Optional[str], reason_codes: list[str], priority: str,
) -> str:
    """Advisory only (Phase 6): this function returns a STRING recommendation.
    It never calls an approval/resolution API, never mutates a financial
    record, and never influences `evaluate_policy`'s own decision -- it is
    read strictly AFTER the real decision already exists."""
    if decision_status == "SAFE_TO_RESOLVE":
        return RecommendedAction.NONE_REQUIRED
    if decision_status == "UNRESOLVED" or category == "missing_transaction":
        return RecommendedAction.REQUEST_MISSING_EVIDENCE
    if category == "fee_mismatch":
        return RecommendedAction.CHECK_FEE_RULE
    if category == "refund_mismatch":
        return RecommendedAction.INVESTIGATE_REFUND
    if category in _SETTLEMENT_CATEGORIES:
        return RecommendedAction.VERIFY_SETTLEMENT
    if priority == "P0" or ReasonCode.CONTRADICTORY_EVIDENCE in reason_codes:
        return RecommendedAction.ESCALATE_FINANCE_CONTROLLER
    return RecommendedAction.REVIEW_EVIDENCE


def build_prioritized_exception(
    decision: DecisionResult, payment: Payment, reference_now: datetime,
    explanation: Optional[ExplanationReport] = None,
) -> PrioritizedException:
    bundle = decision.bundle
    root_cause = bundle.root_cause
    policy_decision = decision.policy_decision
    exposure = bundle.financial_exposure

    # REUSE M5's existing priority/SLA formulas verbatim -- never a second
    # priority/SLA calculation. `assess_priority` internally recomputes the
    # SAME risk_score formula bundle.risk_score already used (a pure,
    # deterministic function of payment+root_cause+reference_now, so calling
    # it again reproduces the identical number -- see
    # backend/tests/prioritization/test_scorer.py's own direct assertion of this).
    priority_assessment = assess_priority(payment, root_cause, reference_now)
    sla = assess_sla(payment, reference_now)
    priority_code = PRIORITY_LEVEL_TO_CODE[priority_assessment.priority_level]

    contradiction_count = sum(1 for c in decision.contradiction_records if c.status == "CONTRADICTED")
    missing_evidence_count = len(explanation.missing_evidence) if explanation is not None else 0

    reason_codes = _reason_codes(
        risk_level=policy_decision.risk_level.value, sla_status=sla.sla_status.value, age_days=sla.age_days,
        contradiction_count=contradiction_count, missing_evidence_count=missing_evidence_count,
        decision_status=policy_decision.decision.value, category=bundle.category,
        unexplained_amount=root_cause.unexplained_amount, gross_amount=exposure.gross_amount,
    )
    action = recommend_action(
        decision_status=policy_decision.decision.value, category=bundle.category,
        reason_codes=reason_codes, priority=priority_code,
    )

    return PrioritizedException(
        exception_id=decision.exception_id, order_id=bundle.order_id, payment_id=bundle.payment_id,
        priority=priority_code, priority_score=str(priority_assessment.priority_score),
        risk_level=policy_decision.risk_level.value, risk_score=str(bundle.risk_score),
        financial_exposure=str(exposure.gross_amount), currency=exposure.currency, age_days=sla.age_days,
        sla_status=sla.sla_status.value, exception_category=bundle.category,
        decision_status=policy_decision.decision.value, contradiction_count=contradiction_count,
        missing_evidence_count=missing_evidence_count, recommended_action=action, reason_codes=reason_codes,
        explanation_reference=decision.exception_id, provenance_reference=decision.correlation_id,
    )


def attach_priority(explanation: ExplanationReport, prioritized) -> ExplanationReport:
    """Phase 13: integrates M11 into M10's existing explanation contract --
    NOT a second explanation system. Sets `explanation.priority` (a small
    `PriorityInfo` summary defined in `app.explainability.schemas` itself, to
    avoid a circular import) and appends one rendered "PRIORITY" section to
    the existing `human_readable` text, reusing the same reason codes/action
    already computed by `build_prioritized_exception` -- never a second,
    independently-worded explanation.
    """
    explanation.priority = PriorityInfo(
        priority=prioritized.priority, priority_score=prioritized.priority_score,
        reason_codes=list(prioritized.reason_codes), recommended_action=prioritized.recommended_action,
    )
    lines = [
        "", "PRIORITY", "--------", f"{prioritized.priority}", "", "Why:",
        *[f"- {code}" for code in prioritized.reason_codes], "",
        f"Recommended action: {prioritized.recommended_action}",
    ]
    explanation.human_readable = explanation.human_readable + "\n" + "\n".join(lines)
    return explanation
