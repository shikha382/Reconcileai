"""M9 Category C: fee manipulation (Phase 6) -- "especially important" per
the brief. The system must never accept "the difference looks approximately
like a fee"; it must accept only "the configured fee rule mathematically
explains the difference" (`app.engines.reconciliation.verification
.verify_fee_consistency`, which recomputes the exact expected fee/tax/net
from the payment's FeeRule and compares to a tight Decimal tolerance --
FEE_VERIFICATION_TOLERANCE = 0.01 -- never a fuzzy "close enough").
"""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype, settlements_for_payment


def _clean_fee_case(dataset, ground_truth, index):
    order_id = pick_by_archetype(ground_truth, "fee_mismatch", index, not_adversarial=True)
    payment = find_payment_by_order(dataset, order_id)
    settlement = settlements_for_payment(dataset, payment.payment_id)[0]
    return payment, settlement


# 1. Correct fee -- positive control: a genuinely, exactly-verified card fee auto-resolves.
def test_01_correct_fee_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, _ = _clean_fee_case(mutated_dataset, ground_truth, 0)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE


# 2. Fee one currency unit wrong -- beyond the 0.01 tolerance -- must not auto-resolve.
def test_02_fee_one_unit_wrong_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 1)
    settlement.fee += Decimal("1.00")
    settlement.net_amount -= Decimal("1.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 3. Fee percentage slightly wrong (net_amount computed off a different MDR%
# than the configured rule) must not auto-resolve.
def test_03_fee_percentage_slightly_wrong_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 2)
    # Shift net_amount as if a slightly different (but plausible-looking) MDR% had been applied.
    wrong_extra_fee = (payment.amount * Decimal("0.002")).quantize(Decimal("0.01"))
    settlement.net_amount -= wrong_extra_fee
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 4. Tax component wrong -- same principle, isolated to the tax portion.
def test_04_tax_component_wrong_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 3)
    settlement.tax += Decimal("2.00")
    settlement.net_amount -= Decimal("2.00")
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 5. Fee calculated against the wrong base (e.g. against net instead of
# gross amount) produces a different number than the rule's real formula --
# must not auto-resolve just because SOME fee-shaped deduction occurred.
def test_05_fee_calculated_against_wrong_base_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.verification import verify_fee_consistency
    from app.engines.reconciliation.candidate_generation import build_context

    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 4)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    rule = context.fee_rule_by_method["card"]
    # Compute a fee against (amount - existing fee) instead of amount -- a
    # subtly wrong base a careless implementation could plausibly produce.
    wrong_base = settlement.amount - settlement.fee
    wrong_fee = (wrong_base * rule.mdr_percent + rule.fixed_fee).quantize(Decimal("0.01"))
    settlement.net_amount = settlement.amount - wrong_fee - settlement.tax
    settlement.fee = wrong_fee

    check = verify_fee_consistency(payment, settlement, context)
    assert check is None or check.consistent is False
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 6. Fee deducted twice -- net_amount reflects double the real fee.
def test_06_fee_deducted_twice_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 5)
    settlement.net_amount -= settlement.fee  # subtract the real fee a second time
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 7. Fee omitted entirely (net_amount == amount, but the bank actually
# credited less) -- verify_fee_consistency intentionally does not fire when
# net_amount == amount (no gap to explain); the shortfall must still surface
# via the bank-credited-amount check, never be silently absorbed.
def test_07_fee_omitted_but_bank_credited_less_still_surfaces(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 6)
    settlement.fee = Decimal("0.00")
    settlement.tax = Decimal("0.00")
    settlement.net_amount = settlement.amount  # claims no fee was taken at all
    for txn in mutated_dataset.bank_transactions:
        if txn.matched_settlement_id == settlement.settlement_id and txn.direction == "credit":
            txn.amount = settlement.amount - Decimal("120.00")  # but less money actually arrived
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 8. A fee that appears to explain the residual but does not (off by an
# amount smaller than a human might notice, but outside Decimal tolerance).
def test_08_plausible_but_wrong_fee_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 7)
    settlement.net_amount -= Decimal("0.05")  # small, very plausible-looking, still outside the 0.01 tolerance
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 9. No fee rule exists for the payment's method -- verify_fee_consistency
# returns None (nothing to verify against); a genuine gap must still be
# reported, never silently treated as "no fee, so it's fine".
def test_09_no_applicable_fee_rule_does_not_silently_explain_a_gap(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 8)
    payment.method = "totally_unconfigured_method"  # no FeeRule exists for this
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 10. Wrong fee rule selected (payment claims a method whose rule doesn't
# match what was actually deducted) -- the mismatch between the configured
# rule for the claimed method and the settlement's real numbers must surface.
def test_10_wrong_fee_rule_selected_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    payment, settlement = _clean_fee_case(mutated_dataset, ground_truth, 9)
    # Settlement's fee/net_amount were computed for "card"; relabel the
    # payment as a different method (assumed to exist with a different rate,
    # e.g. "upi", per data/synthetic FEE_RULES_BY_METHOD) without touching
    # the settlement's real (still card-rate) numbers.
    payment.method = "upi"
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# --- Regression re-confirmation: the real M1 adversarial fee_mismatch cases
# (ground truth's own ADVERSARIAL_INDICES, not a new mutation) must still be
# correctly blocked -- reusing existing ground truth per the brief's "use
# existing synthetic records as the base" instruction, not re-deriving it. ---

def test_11_real_adversarial_fee_mismatch_cases_still_blocked(mutated_dataset, ground_truth, decision_env):
    adversarial_orders = [row["order_id"] for row in ground_truth if row["archetype"] == "fee_mismatch" and row.get("is_adversarial")]
    assert len(adversarial_orders) >= 1
    for order_id in adversarial_orders:
        payment = find_payment_by_order(mutated_dataset, order_id)
        result = decide_one(mutated_dataset, payment.payment_id, decision_env)
        assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
