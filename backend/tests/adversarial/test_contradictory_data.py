"""M9 Category J: contradictory data (Phase 13). Payment, settlement,
configured fee, and bank credit all disagree with each other by different,
systematically-generated amounts. A single plausible explanation must never
erase contradicting evidence -- contradiction -> challenge -> verification
-> policy -> review/block is the only safe path.
"""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype


def _contradict(mutated_dataset, ground_truth, index, *, settlement_delta, fee_delta, bank_delta):
    order_id = pick_by_archetype(ground_truth, "fee_mismatch", index, not_adversarial=True)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    credit_txn = next(
        b for b in mutated_dataset.bank_transactions
        if b.matched_settlement_id == settlement.settlement_id and b.direction == "credit"
    )
    settlement.amount += settlement_delta
    settlement.fee += fee_delta
    settlement.net_amount = settlement.amount - settlement.fee - settlement.tax
    credit_txn.amount += bank_delta
    return payment


# Systematically generated contradiction matrix: payment, settlement, fee,
# and bank all disagree by different (non-cancelling) deltas.
_CONTRADICTION_DELTAS = [
    (Decimal("20.00"), Decimal("5.00"), Decimal("-8.00")),
    (Decimal("-15.00"), Decimal("3.00"), Decimal("12.00")),
    (Decimal("50.00"), Decimal("-10.00"), Decimal("30.00")),
    (Decimal("0.50"), Decimal("0.25"), Decimal("-0.75")),
]


def test_systematically_generated_contradictions_never_auto_resolve(mutated_dataset, ground_truth, decision_env):
    unsafe = []
    for i, (settlement_delta, fee_delta, bank_delta) in enumerate(_CONTRADICTION_DELTAS):
        dataset = mutated_dataset.clone_all()
        payment = _contradict(dataset, ground_truth, i, settlement_delta=settlement_delta, fee_delta=fee_delta, bank_delta=bank_delta)
        result = decide_one(dataset, payment.payment_id, decision_env)
        if result.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE:
            unsafe.append((i, settlement_delta, fee_delta, bank_delta))
    assert unsafe == [], f"contradictory scenarios incorrectly auto-resolved: {unsafe}"


def test_contradiction_reaches_the_challenge_layer_and_blocks_resolution(mutated_dataset, ground_truth, decision_env):
    payment = _contradict(
        mutated_dataset, ground_truth, 0,
        settlement_delta=Decimal("20.00"), fee_delta=Decimal("5.00"), bank_delta=Decimal("-8.00"),
    )
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
    # If AI investigation ran, at least one hypothesis must have been
    # challenged and found wanting -- a single plausible story never erases
    # contradicting evidence in this architecture.
    if result.ai_investigation is not None:
        assert len(result.contradiction_records) > 0


def test_a_single_plausible_fee_explanation_does_not_erase_a_real_contradiction(mutated_dataset, ground_truth, decision_env):
    # Even though a fee rule genuinely applies to this payment's method, the
    # combination of settlement/fee/bank deltas here means NO single fee
    # number can explain all three simultaneously -- the plausible existence
    # of "a fee" must not paper over the residual contradiction.
    payment = _contradict(
        mutated_dataset, ground_truth, 1,
        settlement_delta=Decimal("-15.00"), fee_delta=Decimal("3.00"), bank_delta=Decimal("12.00"),
    )
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
    assert result.policy_decision.risk_level.value in ("LOW", "MEDIUM", "HIGH", "CRITICAL")  # a real risk level was computed, not skipped
