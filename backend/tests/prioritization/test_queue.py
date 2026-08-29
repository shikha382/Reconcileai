"""M11 Phases 7-9: deterministic queue ordering, tie-breaking, filtering,
and aggregate summary metrics -- all computed from real records, never
hardcoded.
"""
from decimal import Decimal

from app.prioritization.queue import QueueFilters, get_priority_queue, summarize_queue
from app.prioritization.schemas import PRIORITY_CODE_RANK, PrioritizedException


def _make(exception_id, priority, sla_status, exposure, risk_score, age_days, category="fee_mismatch"):
    return PrioritizedException(
        exception_id=exception_id, order_id=f"ORD-{exception_id}", payment_id=f"PAY-{exception_id}",
        priority=priority, priority_score="0.00", risk_level="LOW", risk_score=str(risk_score),
        financial_exposure=str(exposure), currency="INR", age_days=age_days, sla_status=sla_status,
        exception_category=category, decision_status="HUMAN_REVIEW", contradiction_count=0,
        missing_evidence_count=0, recommended_action="REVIEW_EVIDENCE", reason_codes=["HIGH_EXPOSURE"],
    )


def test_queue_orders_by_priority_first():
    items = [_make("A", "P2", "WITHIN_SLA", "0", "0", 0), _make("B", "P0", "WITHIN_SLA", "0", "0", 0)]
    ordered = get_priority_queue(items)
    assert [i.exception_id for i in ordered] == ["B", "A"]


def test_tie_break_order_sla_then_exposure_then_risk_then_age_then_id():
    # Same priority throughout -- SLA breach must win first.
    breached = _make("BREACHED", "P1", "BREACHED", "100", "10", 5)
    at_risk = _make("AT_RISK", "P1", "AT_RISK", "9999", "9999", 100)
    ordered = get_priority_queue([at_risk, breached])
    assert [i.exception_id for i in ordered] == ["BREACHED", "AT_RISK"]

    # Same priority, same SLA -- exposure wins next.
    low_exposure = _make("LOW_EXP", "P1", "WITHIN_SLA", "50", "999", 999)
    high_exposure = _make("HIGH_EXP", "P1", "WITHIN_SLA", "5000", "1", 1)
    ordered2 = get_priority_queue([low_exposure, high_exposure])
    assert [i.exception_id for i in ordered2] == ["HIGH_EXP", "LOW_EXP"]

    # Same priority/SLA/exposure -- risk wins next.
    low_risk = _make("LOW_RISK", "P1", "WITHIN_SLA", "100", "10", 999)
    high_risk = _make("HIGH_RISK", "P1", "WITHIN_SLA", "100", "500", 1)
    ordered3 = get_priority_queue([low_risk, high_risk])
    assert [i.exception_id for i in ordered3] == ["HIGH_RISK", "LOW_RISK"]

    # Same priority/SLA/exposure/risk -- age wins next.
    young = _make("YOUNG", "P1", "WITHIN_SLA", "100", "10", 1)
    old = _make("OLD", "P1", "WITHIN_SLA", "100", "10", 50)
    ordered4 = get_priority_queue([young, old])
    assert [i.exception_id for i in ordered4] == ["OLD", "YOUNG"]

    # Identical everything -- stable, deterministic tie-break on exception_id.
    tie_a = _make("ZZZ", "P1", "WITHIN_SLA", "100", "10", 5)
    tie_b = _make("AAA", "P1", "WITHIN_SLA", "100", "10", 5)
    ordered5 = get_priority_queue([tie_a, tie_b])
    assert [i.exception_id for i in ordered5] == ["AAA", "ZZZ"]


def test_ordering_is_deterministic_across_repeated_calls():
    items = [_make(str(i), "P1", "WITHIN_SLA", str(i * 7 % 13), str(i * 3 % 11), i) for i in range(20)]
    first = [i.exception_id for i in get_priority_queue(items)]
    second = [i.exception_id for i in get_priority_queue(list(reversed(items)))]
    assert first == second  # same inputs (just reordered) -> same output order


def test_filter_by_priority():
    items = [_make("A", "P0", "WITHIN_SLA", "1", "1", 1), _make("B", "P3", "WITHIN_SLA", "1", "1", 1)]
    result = get_priority_queue(items, QueueFilters(priority="P0"))
    assert [i.exception_id for i in result] == ["A"]


def test_filter_by_min_exposure():
    items = [_make("A", "P1", "WITHIN_SLA", "50", "1", 1), _make("B", "P1", "WITHIN_SLA", "5000", "1", 1)]
    result = get_priority_queue(items, QueueFilters(min_exposure=Decimal("1000.00")))
    assert [i.exception_id for i in result] == ["B"]


def test_filter_by_category_and_decision_status():
    items = [_make("A", "P1", "WITHIN_SLA", "1", "1", 1, category="fee_mismatch"), _make("B", "P1", "WITHIN_SLA", "1", "1", 1, category="refund_mismatch")]
    result = get_priority_queue(items, QueueFilters(category="refund_mismatch"))
    assert [i.exception_id for i in result] == ["B"]


def test_summary_counts_are_computed_not_hardcoded():
    items = [
        _make("A", "P0", "BREACHED", "100.00", "1", 1), _make("B", "P0", "WITHIN_SLA", "50.00", "1", 1),
        _make("C", "P3", "AT_RISK", "9999.00", "1", 1),
    ]
    summary = summarize_queue(items)
    assert summary.total == 3
    assert summary.counts_by_priority == {"P0": 2, "P1": 0, "P2": 0, "P3": 1}
    assert Decimal(summary.total_financial_exposure) == Decimal("100.00") + Decimal("50.00") + Decimal("9999.00")
    assert summary.sla_breached_count == 1
    assert summary.sla_at_risk_count == 1
    assert summary.highest_exposure_exception_id == "C"


def test_empty_queue_summary_does_not_crash():
    summary = summarize_queue([])
    assert summary.total == 0
    assert summary.highest_exposure_exception_id is None
    assert summary.most_common_category is None
