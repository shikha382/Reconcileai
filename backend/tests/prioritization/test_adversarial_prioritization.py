"""M11 Phase 12: adversarial prioritization testing. Priority must remain
deterministic, bounded, explainable, and safe under every constructed edge
case -- and a manipulated priority score must never modify the underlying
decision.
"""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.prioritization.queue import QueueFilters, get_priority_queue, summarize_queue
from app.prioritization.schemas import PrioritizedException
from app.prioritization.scorer import build_prioritized_exception
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype


def _bogus(exception_id="EXC-bogus", **overrides):
    defaults = dict(
        exception_id=exception_id, order_id="ORD-bogus", payment_id="PAY-bogus", priority="P1",
        priority_score="0.00", risk_level="LOW", risk_score="0.00", financial_exposure="0.00", currency="INR",
        age_days=0, sla_status="WITHIN_SLA", exception_category=None, decision_status="HUMAN_REVIEW",
        contradiction_count=0, missing_evidence_count=0, recommended_action="REVIEW_EVIDENCE", reason_codes=[],
    )
    defaults.update(overrides)
    return PrioritizedException(**defaults)


# 1. Huge amount with low (VERIFIED) risk -- a clean, high-value auto-resolve
# must not be inflated to a high priority merely because the amount is large.
def test_01_huge_amount_low_risk_stays_low_priority(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    # Large relative to the dataset's typical range, but kept under M5's own
    # MAX_AUTO_RESOLVE_EXPOSURE (100000.00) so the case can still genuinely
    # auto-resolve -- a figure ABOVE that cap correctly requires human
    # review regardless of verification certainty (POLICY-EXPOSURE-001),
    # which is exactly the safety behavior this test must not contradict.
    payment.amount = Decimal("90000.00")  # huge, but the case is still cleanly, fully verified
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    for txn in mutated_dataset.bank_transactions:
        if txn.matched_settlement_id == settlement.settlement_id and txn.direction == "credit":
            txn.amount = payment.amount
    settlement.amount = payment.amount
    settlement.net_amount = payment.amount
    # Pin SLA to WITHIN_SLA too -- isolating the "amount alone" factor from
    # M5's separate, independent SLA-urgency driver (a record that's simply
    # old relative to the dataset's own reference point correctly still
    # gets bumped to HIGH by that OTHER, unrelated signal -- not a bug).
    reference_now = max(p.captured_at for p in mutated_dataset.payments)
    payment.captured_at = reference_now
    settlement.settled_at = reference_now
    for txn in mutated_dataset.bank_transactions:
        if txn.matched_settlement_id == settlement.settlement_id:
            txn.value_date = reference_now

    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision.value == "SAFE_TO_RESOLVE"
    prioritized = build_prioritized_exception(result, payment, reference_now)
    assert Decimal(prioritized.risk_score) == Decimal("0.00")
    assert prioritized.sla_status == "WITHIN_SLA"
    assert prioritized.priority in ("P2", "P3")  # low risk, no urgency signal -- not automatically P0/P1 from amount alone


# 2. Tiny amount with a critical contradiction -- must still surface as contradictory.
def test_02_tiny_amount_critical_contradiction_still_flagged(mutated_dataset, ground_truth, decision_env):
    order_id = next(r["order_id"] for r in ground_truth if r["archetype"] == "fee_mismatch" and r.get("is_adversarial"))
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    scale = Decimal("1.00") / payment.amount
    payment.amount = (payment.amount * scale).quantize(Decimal("0.01"))
    settlement.amount = payment.amount
    for txn in mutated_dataset.bank_transactions:
        if txn.matched_settlement_id == settlement.settlement_id and txn.direction == "credit":
            txn.amount = (txn.amount * scale).quantize(Decimal("0.01"))

    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    reference_now = max(p.captured_at for p in mutated_dataset.payments)
    prioritized = build_prioritized_exception(result, payment, reference_now)
    from app.prioritization.schemas import ReasonCode

    if any(c.status == "CONTRADICTED" for c in result.contradiction_records):
        assert ReasonCode.CONTRADICTORY_EVIDENCE in prioritized.reason_codes


# 3. Expired (breached) SLA -- already covered by test_scorer.py's real
# dataset cases (most records are breached relative to reference_now);
# explicitly re-confirmed here for completeness.
def test_03_expired_sla_is_flagged(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 6)
    payment = find_payment_by_order(mutated_dataset, order_id)
    reference_now = max(p.captured_at for p in mutated_dataset.payments)
    payment.captured_at = reference_now - timedelta(days=60)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    prioritized = build_prioritized_exception(result, payment, reference_now)
    assert prioritized.sla_status == "BREACHED"
    from app.prioritization.schemas import ReasonCode
    assert ReasonCode.SLA_BREACHED in prioritized.reason_codes


# 4. Future SLA (captured_at after reference_now) -- must not crash or go negative.
def test_04_future_sla_does_not_crash_or_go_negative(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 7)
    payment = find_payment_by_order(mutated_dataset, order_id)
    reference_now = max(p.captured_at for p in mutated_dataset.payments)
    payment.captured_at = reference_now + timedelta(days=30)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    prioritized = build_prioritized_exception(result, payment, reference_now)  # must not raise
    assert prioritized.age_days >= 0
    assert prioritized.sla_status == "WITHIN_SLA"


# 5. Missing evidence -- covered directly in test_scorer.py; not duplicated here.


# 6. Fabricated exposure fed directly into the queue/summary layer -- these
# are pure display functions over whatever list they're given; they must
# not crash, and must not silently "correct" or validate the value away.
def test_06_fabricated_exposure_does_not_crash_the_queue_or_summary():
    item = _bogus(financial_exposure="999999999999.99")
    ordered = get_priority_queue([item])
    summary = summarize_queue(ordered)
    assert Decimal(summary.total_financial_exposure) == Decimal("999999999999.99")


# 7. Negative exposure -- legitimate Decimal arithmetic, must not crash;
# real bundle exposures are never negative (see test_scorer.py), so this
# tests the display layer's robustness to malformed upstream data only.
def test_07_negative_exposure_does_not_crash():
    item = _bogus(financial_exposure="-500.00")
    ordered = get_priority_queue([item])
    summary = summarize_queue(ordered)
    assert Decimal(summary.total_financial_exposure) == Decimal("-500.00")


# 8. Duplicate exception_id in the same list -- deterministic handling, no crash.
def test_08_duplicate_exception_id_is_handled_deterministically():
    a = _bogus("EXC-dup", financial_exposure="10.00")
    b = _bogus("EXC-dup", financial_exposure="10.00")
    ordered = get_priority_queue([a, b])
    assert len(ordered) == 2  # queue does not silently deduplicate -- that's a caller/data-integrity concern, not this layer's job
    assert ordered[0].exception_id == ordered[1].exception_id == "EXC-dup"


# 9. Malformed exception (None category, empty reason codes) -- no crash.
def test_09_malformed_exception_fields_do_not_crash():
    item = _bogus(exception_category=None, reason_codes=[])
    ordered = get_priority_queue([item])
    summary = summarize_queue(ordered)
    assert summary.most_common_category is None


# 10. Contradictory priority inputs (P0 but LOW risk, WITHIN_SLA) -- the
# queue/summary trust whatever priority field is present (a pure sort/
# aggregation layer); the REAL builder never produces such a combination.
def test_10_contradictory_manual_inputs_still_sort_deterministically():
    item = _bogus("EXC-contra", priority="P0", risk_level="LOW", sla_status="WITHIN_SLA")
    ordered = get_priority_queue([item, _bogus("EXC-other", priority="P3")])
    assert ordered[0].exception_id == "EXC-contra"  # sorts on its OWN stated priority field, nothing re-derived


# 11. Manipulated risk value fed manually -- queue/summary treat it as data, no crash.
def test_11_manipulated_risk_value_does_not_crash():
    item = _bogus(risk_score="99999999.99")
    ordered = get_priority_queue([item])
    assert Decimal(ordered[0].risk_score) == Decimal("99999999.99")


# 12. Manipulated SLA status string -- an unrecognized value must not crash sorting.
def test_12_unrecognized_sla_status_does_not_crash_sorting():
    item = _bogus(sla_status="NOT_A_REAL_STATUS")
    ordered = get_priority_queue([item, _bogus("EXC-other")])
    assert len(ordered) == 2  # falls back to the queue's own default urgency rank, never raises


# 13. Extreme Decimal values -- very large and very precise, no crash.
def test_13_extreme_decimal_values_do_not_crash():
    item = _bogus(financial_exposure="1" + "0" * 20 + ".00", risk_score="0.0000000001")
    ordered = get_priority_queue([item])
    summary = summarize_queue(ordered)
    assert summary.total == 1


# 14. Missing optional fields (None category/references) -- no crash, to_dict works.
def test_14_missing_optional_fields_still_serialize():
    item = _bogus(exception_category=None, explanation_reference=None, provenance_reference=None)
    d = item.to_dict()
    assert d["exception_category"] is None
    assert d["explanation_reference"] is None


# 15. Deterministic tie situations -- already covered exhaustively in
# test_queue.py::test_tie_break_order_sla_then_exposure_then_risk_then_age_then_id;
# reconfirmed here with a larger, real-data-derived tie set.
def test_15_large_tie_set_is_still_a_total_deterministic_order(mutated_dataset, ground_truth, decision_env):
    items = []
    for i in range(5):
        order_id = pick_by_archetype(ground_truth, "exact_match", 10 + i)
        payment = find_payment_by_order(mutated_dataset, order_id)
        result = decide_one(mutated_dataset, payment.payment_id, decision_env)
        reference_now = max(p.captured_at for p in mutated_dataset.payments)
        items.append(build_prioritized_exception(result, payment, reference_now))

    ordered_a = [i.exception_id for i in get_priority_queue(items)]
    ordered_b = [i.exception_id for i in get_priority_queue(list(reversed(items)))]
    assert ordered_a == ordered_b
    assert len(set(ordered_a)) == len(items)  # a total order over all items, no ties silently dropped
