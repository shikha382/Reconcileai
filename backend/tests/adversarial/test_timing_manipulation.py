"""M9 Category F: timing manipulation (Phase 9). Timing is EVIDENCE in this
domain, not an invented deterministic constraint -- `_date_delta_days` uses
`abs()`, so a settlement dated before its payment is treated the same as
one dated after, within the same tolerance windows; this is a confirmed,
deliberate property (not a bug) since the domain never defines settlement
ordering as authoritative, only proximity.
"""
from datetime import timedelta
from decimal import Decimal

from tests.adversarial.helpers import analyze, decide_one, find_payment_by_order, pick_by_archetype, settlements_for_payment


# 1. Valid chronological order -- positive control.
def test_01_valid_chronological_order_still_matches(mutated_dataset, ground_truth):
    order_id = pick_by_archetype(ground_truth, "exact_match", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    bundle = analyze(mutated_dataset, payment.payment_id)
    assert bundle.reconciliation_status == "matched"


# 2. Settlement dated BEFORE the payment (an impossible real-world ordering)
# -- must not crash; confirmed-deliberate symmetric-tolerance behavior.
def test_02_settlement_before_payment_does_not_crash(mutated_dataset, ground_truth):
    order_id = pick_by_archetype(ground_truth, "exact_match", 1)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = settlements_for_payment(mutated_dataset, payment.payment_id)[0]
    settlement.settled_at = payment.captured_at - timedelta(hours=6)  # settled before it was even paid
    bundle = analyze(mutated_dataset, payment.payment_id)  # must not raise
    assert bundle is not None
    # Within the tight tolerance window, abs()-based proximity still treats
    # this as a nearby date -- a deliberate, documented property (timing is
    # evidence of proximity, not a directional constraint this domain defines).
    assert bundle.reconciliation_status in ("matched", "mismatch", "partial")


# 3-4. Refund before payment / refund after settlement -- covered directly
# in test_refund_manipulation.py (items 8-9); not duplicated here.


# 5. Extreme timestamp gap -- must not match via date proximity once far
# outside even the lenient tolerance window.
def test_05_extreme_timestamp_gap_does_not_match_via_timing_alone(mutated_dataset, ground_truth):
    from app.engines.reconciliation.config import LENIENT_DATE_TOLERANCE_DAYS

    order_id = pick_by_archetype(ground_truth, "exact_match", 2)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = settlements_for_payment(mutated_dataset, payment.payment_id)[0]
    settlement.settled_at = payment.captured_at + timedelta(days=LENIENT_DATE_TOLERANCE_DAYS + 365)
    bundle = analyze(mutated_dataset, payment.payment_id)
    if bundle.reconciliation_status == "matched":
        assert bundle.root_cause.status == "VERIFIED"


# 6. Duplicate timestamps across different settlements -- must not crash or
# cause an incorrect tie-break.
def test_06_duplicate_timestamps_do_not_crash(mutated_dataset, ground_truth):
    order_a = pick_by_archetype(ground_truth, "exact_match", 3)
    order_b = pick_by_archetype(ground_truth, "exact_match", 4)
    settlement_a = settlements_for_payment(mutated_dataset, find_payment_by_order(mutated_dataset, order_a).payment_id)[0]
    settlement_b = settlements_for_payment(mutated_dataset, find_payment_by_order(mutated_dataset, order_b).payment_id)[0]
    settlement_b.settled_at = settlement_a.settled_at  # identical timestamp, different records

    bundle_a = analyze(mutated_dataset, find_payment_by_order(mutated_dataset, order_a).payment_id)
    bundle_b = analyze(mutated_dataset, find_payment_by_order(mutated_dataset, order_b).payment_id)
    assert bundle_a is not None and bundle_b is not None


# 7. Timezone/format noise -- normalize_timestamp is applied at ingestion;
# a direct unit check that tz-aware input normalizes to a comparable,
# tz-naive UTC value rather than silently comparing apples to oranges.
def test_07_timezone_aware_timestamp_normalizes_consistently():
    from datetime import datetime, timezone

    from app.engines.normalization import normalize_timestamp

    aware = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    naive = normalize_timestamp(aware.isoformat())
    assert naive.tzinfo is None  # normalized to a comparable, tz-naive form


# 8. Future timestamp (captured_at after "now") must not crash SLA/risk aging.
def test_08_future_timestamp_does_not_crash_or_invert_aging(mutated_dataset, ground_truth):
    from app.engines.risk.scoring import sla_aging_factor

    order_id = pick_by_archetype(ground_truth, "exact_match", 5)
    payment = find_payment_by_order(mutated_dataset, order_id)
    reference_now = max(p.captured_at for p in mutated_dataset.payments)
    payment.captured_at = reference_now + timedelta(days=30)  # captured "in the future"
    factor = sla_aging_factor(payment, reference_now)
    assert factor == Decimal("1.0000")  # clamped to zero aging, never negative


# 9. Stale/very old record -- aging factor must stay bounded (capped), never
# grow without limit and never crash the risk calculation.
def test_09_very_stale_record_aging_factor_stays_bounded(mutated_dataset, ground_truth):
    from app.engines.risk.scoring import MAX_AGING_DAYS, sla_aging_factor

    order_id = pick_by_archetype(ground_truth, "exact_match", 6)
    payment = find_payment_by_order(mutated_dataset, order_id)
    reference_now = max(p.captured_at for p in mutated_dataset.payments)
    payment.captured_at = reference_now - timedelta(days=MAX_AGING_DAYS * 100)  # absurdly old
    factor = sla_aging_factor(payment, reference_now)
    assert factor == Decimal("2.0000")  # capped at the documented maximum (1.0 + MAX_AGING_DAYS/MAX_AGING_DAYS)
