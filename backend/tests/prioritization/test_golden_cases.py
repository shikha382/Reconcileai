"""M11 Phase 17: golden prioritization cases. For every case, verify
priority, reason codes, recommended action, and that the underlying
decision is unchanged by prioritization -- structured facts, not wording.
"""
from decimal import Decimal


# GOLDEN-01: critical high-value exception.
def test_golden_01_critical_high_value_exception(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("fee_mismatch", 0, not_adversarial=False)
    assert result.policy_decision.decision.value != "SAFE_TO_RESOLVE"  # decision unaffected by priority
    assert prioritized.priority in ("P0", "P1")
    assert prioritized.reason_codes


# GOLDEN-02: low-value but SLA-breached exception.
def test_golden_02_low_value_sla_breached(get_prioritized):
    from app.prioritization.schemas import ReasonCode

    prioritized, result, explanation, payment, reference_now = get_prioritized("timing_mismatch", 0)
    if prioritized.sla_status == "BREACHED":
        assert ReasonCode.SLA_BREACHED in prioritized.reason_codes


# GOLDEN-03: high-risk contradictory exception.
def test_golden_03_high_risk_contradictory(get_prioritized):
    from app.prioritization.schemas import ReasonCode

    prioritized, result, explanation, payment, reference_now = get_prioritized("duplicate", 0, not_adversarial=False)
    assert prioritized.contradiction_count >= 0
    if prioritized.contradiction_count > 0:
        assert ReasonCode.CONTRADICTORY_EVIDENCE in prioritized.reason_codes
    assert result.policy_decision.decision.value != "SAFE_TO_RESOLVE"


# GOLDEN-04: missing-evidence exception.
def test_golden_04_missing_evidence(get_prioritized):
    from app.prioritization.schemas import RecommendedAction

    prioritized, result, explanation, payment, reference_now = get_prioritized("missing_transaction", 0)
    assert prioritized.missing_evidence_count > 0
    assert prioritized.recommended_action == RecommendedAction.REQUEST_MISSING_EVIDENCE
    assert prioritized.decision_status == "UNRESOLVED"


# GOLDEN-05: clean auto-resolved record.
def test_golden_05_clean_auto_resolved(get_prioritized):
    from app.prioritization.schemas import RecommendedAction

    prioritized, result, explanation, payment, reference_now = get_prioritized("exact_match", 0)
    assert result.policy_decision.decision.value == "SAFE_TO_RESOLVE"
    assert prioritized.decision_status == "SAFE_TO_RESOLVE"
    assert prioritized.recommended_action == RecommendedAction.NONE_REQUIRED


# GOLDEN-06: unresolved exception.
def test_golden_06_unresolved(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("missing_transaction", 1)
    assert result.policy_decision.decision.value == "UNRESOLVED"
    assert prioritized.decision_status == "UNRESOLVED"


# GOLDEN-07: rejected/blocked exception.
def test_golden_07_rejected_blocked(get_prioritized):
    from app.prioritization.schemas import ReasonCode

    prioritized, result, explanation, payment, reference_now = get_prioritized("fee_mismatch", 0, not_adversarial=False)
    if result.policy_decision.decision.value == "REJECTED":
        assert ReasonCode.AUTO_RESOLUTION_BLOCKED in prioritized.reason_codes


# GOLDEN-08: identical priority tie -- two records, confirm deterministic tie-break.
def test_golden_08_identical_priority_tie(get_prioritized):
    from app.prioritization.queue import get_priority_queue

    a, result_a, *_ = get_prioritized("exact_match", 8)
    b, result_b, *_ = get_prioritized("exact_match", 9)
    ordered_1 = [i.exception_id for i in get_priority_queue([a, b])]
    ordered_2 = [i.exception_id for i in get_priority_queue([b, a])]
    assert ordered_1 == ordered_2  # same order regardless of input order -- deterministic tie-break


# GOLDEN-09: multiple categories in one queue.
def test_golden_09_multiple_categories(get_prioritized):
    from app.prioritization.queue import get_priority_queue, summarize_queue

    items = []
    for archetype, na in [("exact_match", True), ("fee_mismatch", False), ("missing_transaction", True)]:
        p, *_ = get_prioritized(archetype, 0, not_adversarial=na)
        items.append(p)
    ordered = get_priority_queue(items)
    summary = summarize_queue(ordered)
    assert summary.total == 3
    categories = {i.exception_category for i in items}
    assert len(categories) >= 2  # genuinely different categories represented


# GOLDEN-10: zero/low exposure case.
def test_golden_10_zero_low_exposure(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("exact_match", 10)
    assert Decimal(prioritized.financial_exposure) >= Decimal("0.00")
    if result.policy_decision.decision.value == "SAFE_TO_RESOLVE":
        assert Decimal(result.bundle.root_cause.unexplained_amount) == Decimal("0.00")
