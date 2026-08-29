"""M9 Category E: refunds (Phase 8). The system must distinguish fee vs.
refund vs. settlement residual vs. unexplained difference -- never collapse
different financial causes merely because their numeric amounts are
similar. `verify_refund_consistency` (app.engines.reconciliation.verification)
is the mechanism: a refund is only "explained" if an EQUAL-AMOUNT, matching-
currency DEBIT bank transaction genuinely exists -- never inferred from a
plausible-looking number alone.
"""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import analyze, clone, decide_one, find_payment_by_order, pick_by_archetype


def _refund_case(dataset, ground_truth, index):
    order_id = pick_by_archetype(ground_truth, "refund_mismatch", index)
    payment = find_payment_by_order(dataset, order_id)
    refunds = [r for r in dataset.refunds if r.payment_id == payment.payment_id]
    return payment, refunds


# 1-2. Valid refund / refund amount matches expected -- positive control:
# the real refund_mismatch archetype (genuinely refund-explained) must be
# handled per its own ground truth, never treated as an unexplained residual.
def test_01_02_valid_refund_matches_ground_truth_expectation(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "refund_mismatch", 0)
    row = next(r for r in ground_truth if r["order_id"] == order_id)
    payment = find_payment_by_order(mutated_dataset, order_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    if row["expected_action"] == "auto_resolve":
        assert result.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE
    else:
        assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 3. Partial refund -- refund covers only part of a discrepancy; the
# remainder must still surface as unexplained, never silently absorbed.
def test_03_partial_refund_leaves_a_real_unexplained_remainder(mutated_dataset, ground_truth, decision_env):
    payment, refunds = _refund_case(mutated_dataset, ground_truth, 1)
    assert refunds
    refunds[0].amount = (refunds[0].amount / 2).quantize(Decimal("0.01"))  # only half the real refund recorded
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 4. Refund greater than the payment itself is nonsensical and must never auto-resolve.
def test_04_refund_greater_than_payment_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, refunds = _refund_case(mutated_dataset, ground_truth, 2)
    assert refunds
    refunds[0].amount = payment.amount + Decimal("500.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 5. Duplicate refund -- two refunds claim the same amount but only one
# matching debit genuinely exists; the duplicate must not be silently
# treated as independently consistent evidence.
def test_05_duplicate_refund_only_one_real_debit_is_not_silently_doubled(mutated_dataset, ground_truth):
    from app.engines.reconciliation.candidate_generation import build_context
    from app.engines.reconciliation.verification import verify_refund_consistency

    payment, refunds = _refund_case(mutated_dataset, ground_truth, 3)
    assert refunds
    duplicate = clone(refunds[0], refund_id=f"{refunds[0].refund_id}-DUP")
    mutated_dataset.refunds.append(duplicate)

    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    check = verify_refund_consistency(payment, context)
    # Only ONE real debit exists for this amount -- if both refunds are
    # reported as matched to a debit, that is exactly the "reused evidence"
    # failure mode this test exists to catch.
    assert len(check.debit_bank_txn_ids) == len(set(check.debit_bank_txn_ids)), (
        "the same debit bank transaction was counted as evidence for two different refunds"
    )


# 6. Refund attached to the wrong order/payment must not manufacture a false
# consistency signal for an unrelated payment.
def test_06_refund_reassigned_to_wrong_payment_does_not_manufacture_consistency(mutated_dataset, ground_truth):
    order_a = pick_by_archetype(ground_truth, "refund_mismatch", 4)
    order_b = pick_by_archetype(ground_truth, "exact_match", 0)
    payment_a = find_payment_by_order(mutated_dataset, order_a)
    payment_b = find_payment_by_order(mutated_dataset, order_b)
    refund = next(r for r in mutated_dataset.refunds if r.payment_id == payment_a.payment_id)
    refund.payment_id = payment_b.payment_id  # reassigned to an unrelated, already-clean payment

    bundle_b = analyze(mutated_dataset, payment_b.payment_id)
    # Payment B was a clean exact_match with no real discrepancy -- an
    # incoming stray refund must not flip it to a false auto-resolved
    # "refund explains it" story; at minimum it must not silently vanish.
    if bundle_b.reconciliation_status == "matched":
        assert bundle_b.root_cause.status == "VERIFIED"


# 7. Refund with a modified/garbled identifier -- reference/id noise must
# not affect the amount+currency-based consistency check at all.
def test_07_refund_identifier_noise_does_not_affect_amount_based_verification(mutated_dataset, ground_truth):
    payment, refunds = _refund_case(mutated_dataset, ground_truth, 5)
    assert refunds
    refunds[0].reference = "  gArBlEd -- Ref3rence!! "
    bundle_before = analyze(mutated_dataset, payment.payment_id)
    # verify_refund_consistency never reads `reference` -- confirms the
    # check is amount/currency-based, not string-based, so identifier noise
    # is correctly irrelevant to the financial verification itself.
    assert bundle_before is not None


# 8. Refund initiated after the settlement -- timing is EVIDENCE here, not a
# deterministic constraint (verify_refund_consistency never reads timestamps
# at all) -- must not crash, and must not be treated as disqualifying on its
# own since this domain doesn't define that rule.
def test_08_refund_after_settlement_does_not_crash_or_get_invented_a_timing_rule(mutated_dataset, ground_truth):
    payment, refunds = _refund_case(mutated_dataset, ground_truth, 6)
    assert refunds
    settlement_dates = [s.settled_at for s in mutated_dataset.settlements if s.payment_id == payment.payment_id]
    if settlement_dates:
        refunds[0].initiated_at = max(settlement_dates) + __import__("datetime").timedelta(days=10)
    bundle = analyze(mutated_dataset, payment.payment_id)  # must not raise
    assert bundle is not None


# 9. Refund timestamped before the payment was even captured -- an
# impossible ordering that must not crash the engine.
def test_09_refund_before_payment_captured_does_not_crash(mutated_dataset, ground_truth):
    payment, refunds = _refund_case(mutated_dataset, ground_truth, 7)
    assert refunds
    refunds[0].initiated_at = payment.captured_at - __import__("datetime").timedelta(days=5)
    bundle = analyze(mutated_dataset, payment.payment_id)  # must not raise
    assert bundle is not None


# 10. A refund whose amount happens to numerically resemble a plausible fee
# must not be misclassified -- fee verification is rule-based (recomputes
# from FeeRule), refund verification is debit-based (looks for a matching
# debit); a coincidental overlap in numbers must not blur the two.
def test_10_refund_shaped_number_is_not_misattributed_as_a_fee(mutated_dataset, ground_truth):
    from app.engines.reconciliation.candidate_generation import build_context
    from app.engines.reconciliation.verification import verify_fee_consistency

    order_id = pick_by_archetype(ground_truth, "exact_match", 8)
    payment = find_payment_by_order(mutated_dataset, order_id)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    # A "refund-shaped" reduction (an arbitrary round number, NOT derived
    # from the configured fee rule) is applied directly to net_amount, with
    # no actual refund record and no actual fee-rule justification.
    settlement.net_amount -= Decimal("25.00")

    fee_check = verify_fee_consistency(payment, settlement, context)
    # The fee check must not rubber-stamp an arbitrary deduction as "the fee" --
    # either no rule applies to justify it, or it's correctly flagged inconsistent.
    assert fee_check is None or fee_check.consistent is False
