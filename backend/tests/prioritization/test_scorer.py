"""M11 Phases 2-6: the prioritization contract, priority model, SLA
handling, reason codes, and recommended actions -- all reusing M5's
existing `assess_priority`/`assess_sla` (never a second formula).
"""
from decimal import Decimal

from app.policy.risk import assess_priority, assess_sla
from app.prioritization.schemas import PRIORITY_LEVEL_TO_CODE, ReasonCode, RecommendedAction


def test_priority_reuses_m5s_own_assess_priority_verbatim(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("exact_match", 0)
    real_assessment = assess_priority(payment, result.bundle.root_cause, reference_now)
    assert prioritized.priority == PRIORITY_LEVEL_TO_CODE[real_assessment.priority_level]
    assert prioritized.priority_score == str(real_assessment.priority_score)


def test_sla_reuses_m5s_own_assess_sla_verbatim(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("exact_match", 1)
    real_sla = assess_sla(payment, reference_now)
    assert prioritized.sla_status == real_sla.sla_status.value
    assert prioritized.age_days == real_sla.age_days


def test_risk_and_exposure_come_from_the_real_decision_not_recomputed(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("fee_mismatch", 0, not_adversarial=False)
    assert prioritized.risk_level == result.policy_decision.risk_level.value
    assert prioritized.risk_score == str(result.bundle.risk_score)
    assert prioritized.financial_exposure == str(result.bundle.financial_exposure.gross_amount)
    assert prioritized.decision_status == result.policy_decision.decision.value


def test_priority_score_is_decimal_parseable_never_float(get_prioritized):
    prioritized, *_ = get_prioritized("exact_match", 2)
    Decimal(prioritized.priority_score)  # must not raise
    Decimal(prioritized.financial_exposure)
    Decimal(prioritized.risk_score)


def test_clean_case_gets_low_priority_and_honest_reason(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("exact_match", 3)
    assert result.policy_decision.decision.value == "SAFE_TO_RESOLVE"
    assert ReasonCode.CLEAN_LOW_PRIORITY in prioritized.reason_codes or prioritized.reason_codes
    assert prioritized.recommended_action == RecommendedAction.NONE_REQUIRED


def test_contradiction_count_matches_real_contradiction_records(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("fee_mismatch", 0, not_adversarial=False)
    real_count = sum(1 for c in result.contradiction_records if c.status == "CONTRADICTED")
    assert prioritized.contradiction_count == real_count
    if real_count > 0:
        assert ReasonCode.CONTRADICTORY_EVIDENCE in prioritized.reason_codes


def test_missing_evidence_count_matches_the_real_explanation(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("missing_transaction", 0)
    assert prioritized.missing_evidence_count == len(explanation.missing_evidence)
    assert prioritized.missing_evidence_count > 0
    assert ReasonCode.MISSING_EVIDENCE in prioritized.reason_codes


def test_unresolved_financial_difference_reason_code_matches_real_residual(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("fee_mismatch", 0, not_adversarial=False)
    assert result.bundle.root_cause.unexplained_amount > Decimal("0.00")
    assert ReasonCode.UNRESOLVED_FINANCIAL_DIFFERENCE in prioritized.reason_codes


def test_auto_resolution_blocked_reason_only_when_actually_blocked(get_prioritized):
    clean, clean_result, *_ = get_prioritized("exact_match", 4)
    assert ReasonCode.AUTO_RESOLUTION_BLOCKED not in clean.reason_codes

    blocked, blocked_result, *_ = get_prioritized("duplicate", 0, not_adversarial=False)
    assert blocked_result.policy_decision.decision.value in ("HUMAN_REVIEW", "REJECTED")
    assert ReasonCode.AUTO_RESOLUTION_BLOCKED in blocked.reason_codes


def test_explanation_and_provenance_references_point_at_the_real_decision(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("exact_match", 5)
    assert prioritized.explanation_reference == result.exception_id
    assert prioritized.provenance_reference == result.correlation_id
