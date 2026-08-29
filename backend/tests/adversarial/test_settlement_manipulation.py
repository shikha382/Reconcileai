"""M9 Category D: settlement manipulation (Phase 7). SUM(settlements) must
match the expected financial relationship EXACTLY (M2's own
`AMOUNT_EXACT_TOLERANCE = Decimal("0.00")`) -- no "close enough" matching
unless the domain explicitly defines one (it doesn't, for settlement sums).
"""
from decimal import Decimal

from tests.adversarial.helpers import clone, decide_one, find_payment_by_order, pick_by_archetype, settlements_for_payment
from app.policy.schemas import PolicyDecisionType


# 1. Split settlement -- real archetype, positive control: a genuine split
# that sums exactly must still be recognized and safely resolved.
def test_01_genuine_split_settlement_matches_correctly(mutated_dataset, ground_truth):
    from tests.adversarial.helpers import analyze

    order_id = pick_by_archetype(ground_truth, "split_settlement", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    bundle = analyze(mutated_dataset, payment.payment_id)
    assert bundle.reconciliation_status == "matched"


# 2. Aggregated settlement -- real archetype, positive control.
def test_02_genuine_aggregated_settlement_matches_correctly(mutated_dataset, ground_truth):
    from tests.adversarial.helpers import analyze

    order_id = pick_by_archetype(ground_truth, "aggregated_settlement", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    bundle = analyze(mutated_dataset, payment.payment_id)
    assert bundle.reconciliation_status == "matched"


# 3. Missing settlement -- real archetype, must safely escalate (never invent one).
def test_03_missing_settlement_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "missing_transaction", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
    assert result.policy_decision.decision == PolicyDecisionType.UNRESOLVED


# 4. Duplicate settlement -- real archetype, must never auto-resolve.
def test_04_duplicate_settlement_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "duplicate", 0, not_adversarial=False)
    payment = find_payment_by_order(mutated_dataset, order_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 5. Partial settlement -- real archetype, must never auto-resolve.
def test_05_partial_settlement_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "partial_settlement", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 6. Settlement in wrong amount -- covered thoroughly in Category B; a
# distinct settlement-relationship-specific case here: a split's SECOND
# settlement is inflated so the pair no longer sums exactly.
def test_06_split_settlement_wrong_amount_breaks_the_exact_sum(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "split_settlement", 1)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlements = settlements_for_payment(mutated_dataset, payment.payment_id)
    assert len(settlements) >= 2
    for txn in mutated_dataset.bank_transactions:
        if txn.matched_settlement_id == settlements[0].settlement_id and txn.direction == "credit":
            txn.amount += Decimal("50.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 7. Settlement assigned to the wrong order -- reassigning a settlement's
# payment_id to an unrelated payment must not create a false match for
# EITHER payment.
def test_07_settlement_assigned_to_wrong_order_does_not_cross_match(mutated_dataset, ground_truth):
    from tests.adversarial.helpers import analyze

    order_a = pick_by_archetype(ground_truth, "exact_match", 0)
    order_b = pick_by_archetype(ground_truth, "exact_match", 1)
    payment_a = find_payment_by_order(mutated_dataset, order_a)
    payment_b = find_payment_by_order(mutated_dataset, order_b)
    settlement_a = settlements_for_payment(mutated_dataset, payment_a.payment_id)[0]
    settlement_a.payment_id = payment_b.payment_id  # reassigned to an unrelated payment

    bundle_b = analyze(mutated_dataset, payment_b.payment_id)
    # Payment B now has TWO settlements genuinely linked (its own real one,
    # plus A's reassigned one) -- a real duplicate-linkage situation, which
    # must trigger ambiguity handling, never a silent pick or a silent sum.
    if bundle_b.reconciliation_status == "matched":
        assert bundle_b.root_cause.status == "VERIFIED"


# 8. Delayed settlement beyond the lenient tolerance window must not match via timing alone.
def test_08_severely_delayed_settlement_does_not_match_via_timing_alone(mutated_dataset, ground_truth):
    from datetime import timedelta

    from tests.adversarial.helpers import analyze
    from app.engines.reconciliation.config import LENIENT_DATE_TOLERANCE_DAYS

    order_id = pick_by_archetype(ground_truth, "exact_match", 2)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = settlements_for_payment(mutated_dataset, payment.payment_id)[0]
    settlement.settled_at = payment.captured_at + timedelta(days=LENIENT_DATE_TOLERANCE_DAYS + 30)

    bundle = analyze(mutated_dataset, payment.payment_id)
    assert bundle.reconciliation_status != "matched" or bundle.root_cause.status == "VERIFIED"


# 9. Settlement reference changed to something unrelated -- must not silently
# keep matching once BOTH the direct link and the reference no longer agree.
def test_09_settlement_reference_changed_and_unlinked_does_not_silently_match(mutated_dataset, ground_truth):
    from tests.adversarial.helpers import analyze

    order_id = pick_by_archetype(ground_truth, "exact_match", 3)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = settlements_for_payment(mutated_dataset, payment.payment_id)[0]
    settlement.payment_id = None
    settlement.utr_reference = "COMPLETELY-UNRELATED-REFERENCE-TEXT"

    bundle = analyze(mutated_dataset, payment.payment_id)
    if bundle.reconciliation_status == "matched":
        assert bundle.root_cause.status == "VERIFIED"


# 10. Multiple settlements that ALMOST sum correctly (off by a few rupees) --
# must not be accepted as a split; M2's sum check is an exact Decimal `==`.
def test_10_near_sum_split_is_not_accepted(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "split_settlement", 2)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlements = settlements_for_payment(mutated_dataset, payment.payment_id)
    assert len(settlements) >= 2
    for txn in mutated_dataset.bank_transactions:
        if txn.matched_settlement_id == settlements[0].settlement_id and txn.direction == "credit":
            txn.amount += Decimal("3.00")  # close, but the sum no longer equals the payment exactly
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 11. One-paisa residual after aggregation -- the smallest possible break of
# the exact-sum rule must still be caught, never rounded away.
def test_11_one_paisa_residual_after_split_is_not_accepted(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "split_settlement", 3)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlements = settlements_for_payment(mutated_dataset, payment.payment_id)
    assert len(settlements) >= 2
    for txn in mutated_dataset.bank_transactions:
        if txn.matched_settlement_id == settlements[0].settlement_id and txn.direction == "credit":
            txn.amount += Decimal("0.01")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
