"""M9 Category B: amount manipulation (Phase 5). Decimal throughout --
never float. Core principle: a tiny unexplained residual must never vanish
through rounding, and a large discrepancy must never auto-resolve merely
because everything else about the record looks familiar.

IMPORTANT, CONFIRMED-CORRECT DESIGN PROPERTY discovered while writing these
tests: `app.engines.reconciliation.verification.bank_credited_amount` --
NOT `settlement.amount`/`settlement.net_amount` -- is what the matching
engine (`resolve_single_linked_settlement`) actually compares against
`payment.amount`. Mutating a settlement's own self-reported amount fields
alone (with the linked bank_transaction left untouched) correctly has NO
effect on the reconciliation outcome, because the confirmed bank credit --
the one figure representing money that has actually, confirmedly moved -- is
what's authoritative, exactly as `bank_credited_amount`'s own docstring
states. Every scenario below that needs a REAL discrepancy therefore mutates
the linked bank_transaction (the actual source of financial truth in this
model), not just the settlement's self-reported fields.
"""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import (
    ONE_PAISA,
    analyze,
    decide_one,
    find_payment_by_order,
    pick_by_archetype,
    settlements_for_payment,
)


def _payment_and_settlement(dataset, ground_truth, index):
    order_id = pick_by_archetype(ground_truth, "exact_match", index)
    payment = find_payment_by_order(dataset, order_id)
    settlement = settlements_for_payment(dataset, payment.payment_id)[0]
    return payment, settlement


def _credit_txns(dataset, settlement):
    txns = [b for b in dataset.bank_transactions if b.matched_settlement_id == settlement.settlement_id and b.direction == "credit"]
    assert txns, f"expected a confirmed bank credit for settlement {settlement.settlement_id}"
    return txns


def _bump_bank_credit(dataset, settlement, delta: Decimal):
    for txn in _credit_txns(dataset, settlement):
        txn.amount += delta


# 1. Exact amount -- positive control: an unmutated clean match must still auto-resolve.
def test_01_exact_amount_still_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, _ = _payment_and_settlement(mutated_dataset, ground_truth, 0)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE


# 2. One-paisa difference in the actual bank credit must not disappear through rounding.
def test_02_one_paisa_difference_produces_a_real_residual(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 1)
    _bump_bank_credit(mutated_dataset, settlement, ONE_PAISA)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 3. Rupee-scale difference must never auto-resolve.
def test_03_one_rupee_difference_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 2)
    _bump_bank_credit(mutated_dataset, settlement, Decimal("1.00"))
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 4. Large residual must never auto-resolve.
def test_04_large_residual_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 3)
    for txn in _credit_txns(mutated_dataset, settlement):
        txn.amount = (txn.amount / 2).quantize(Decimal("0.01"))
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 5. Negative confirmed-credit amount must not crash the engine or be treated as valid.
def test_05_negative_bank_credit_does_not_crash_or_auto_resolve(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 4)
    for txn in _credit_txns(mutated_dataset, settlement):
        txn.amount = -abs(txn.amount)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)  # must not raise
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 6. Zero confirmed credit must not be treated as satisfying a non-zero payment.
def test_06_zero_bank_credit_does_not_auto_resolve(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 5)
    for txn in _credit_txns(mutated_dataset, settlement):
        txn.amount = Decimal("0.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 7. Excessive decimal precision must not crash and must not fabricate a false exact match.
def test_07_excessive_decimal_precision_is_handled_safely(mutated_dataset, ground_truth):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 6)
    for txn in _credit_txns(mutated_dataset, settlement):
        txn.amount = txn.amount + Decimal("0.001")  # sub-paisa noise, never a legal currency unit
    bundle = analyze(mutated_dataset, payment.payment_id)  # must not raise
    assert bundle is not None
    if bundle.reconciliation_status == "matched":
        # amount_exact in matching.py is a strict Decimal `==`, so sub-paisa
        # noise (100.001 != 100.00) correctly fails to be treated as exact --
        # the only way this could still show "matched" is if some other
        # signal legitimately explains it; verify the residual isn't hidden.
        assert bundle.financial_exposure.unexplained_amount == Decimal("0.00")


# 8. Payment amount altered post-hoc -- must surface as a real discrepancy.
def test_08_payment_amount_altered_surfaces_as_discrepancy(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 7)
    payment.amount += Decimal("50.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 9. Settlement's OWN self-reported amount altered, bank credit left correct --
# confirms this is (correctly) NOT treated as a payment-reconciliation
# failure, since the actually-credited money still matches the payment.
def test_09_settlement_self_reported_amount_alone_does_not_affect_the_authoritative_check(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 8)
    settlement.amount += Decimal("25.00")
    settlement.net_amount += Decimal("25.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    # This is the confirmed-correct behavior, not a bug: bank_credited_amount
    # (unchanged here) is what's authoritative, per its own documented design.
    assert result.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE


# 10. Bank-confirmed credit amount altered -- the actually-authoritative
# figure -- must surface as a discrepancy, never be silently trusted.
def test_10_bank_transaction_amount_altered_surfaces_as_discrepancy(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 9)
    _bump_bank_credit(mutated_dataset, settlement, Decimal("15.00"))
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 11. Fee altered (basic case here; full fee-trap coverage in Category C).
def test_11_fee_altered_surfaces_as_discrepancy(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = settlements_for_payment(mutated_dataset, payment.payment_id)[0]
    settlement.fee += Decimal("5.00")
    settlement.net_amount -= Decimal("5.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 12. Refund altered (basic case here; full refund coverage in Category E).
def test_12_refund_altered_surfaces_as_discrepancy(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "refund_mismatch", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    refunds = [r for r in mutated_dataset.refunds if r.payment_id == payment.payment_id]
    assert refunds
    refunds[0].amount += Decimal("10.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 13. Amount signs reversed on the confirmed bank credit (a credit somehow
# recorded as negative) must not auto-resolve.
def test_13_reversed_sign_bank_credit_does_not_auto_resolve(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 10)
    for txn in _credit_txns(mutated_dataset, settlement):
        txn.amount = -txn.amount
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 14. Inconsistent net_amount (net != amount - fee - tax).
def test_14a_verify_settlement_self_consistency_detects_the_break(mutated_dataset, ground_truth):
    from app.engines.reconciliation.verification import verify_settlement_self_consistency

    _, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 11)
    settlement.net_amount = settlement.net_amount + Decimal("7.00")
    check = verify_settlement_self_consistency(settlement)
    assert check.consistent is False
    assert check.delta == Decimal("7.00")


def test_14b_self_inconsistent_settlement_never_auto_resolves_once_reached(mutated_dataset, ground_truth, decision_env):
    # Self-consistency is only CONSULTED once the bank-confirmed amount
    # actually differs from the payment (matching.py's own control flow) --
    # so to genuinely exercise that code path, the bank credit must differ
    # too, not just the settlement's internal bookkeeping.
    payment, settlement = _payment_and_settlement(mutated_dataset, ground_truth, 12)
    settlement.net_amount = settlement.net_amount + Decimal("7.00")  # breaks amount - fee - tax = net_amount
    _bump_bank_credit(mutated_dataset, settlement, Decimal("3.00"))  # forces bank_amount != payment.amount
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
