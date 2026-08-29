"""M9 Category I: missing data (Phase 12). Missing evidence is NOT evidence
of correctness. The system must never "fill in" a missing financial fact --
uncertainty must lead to safe escalation, never AUTO_RESOLVE.
"""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import analyze, decide_one, find_payment_by_order, pick_by_archetype


# 1. Missing settlement -- covered by the real missing_transaction archetype
# in test_settlement_manipulation.py (item 3); not duplicated here.


# 2. Missing bank transaction (settlement exists, but nothing confirms the
# credit actually arrived) -- must be UNRESOLVED, never invented as matched.
def test_02_missing_bank_transaction_is_unresolved_not_fabricated(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    mutated_dataset.bank_transactions = [
        b for b in mutated_dataset.bank_transactions if b.matched_settlement_id != settlement.settlement_id
    ]

    bundle = analyze(mutated_dataset, payment.payment_id)
    assert bundle.reconciliation_status == "unresolved"
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 3. Missing fee rule for the payment's method, on a genuine fee-shaped gap
# -- the gap must not be silently accepted just because nothing could be
# verified against.
def test_03_missing_fee_rule_does_not_silently_accept_the_gap(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    mutated_dataset.fee_rules = [f for f in mutated_dataset.fee_rules if f.method != payment.method]

    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 4. Missing refund record on a genuine refund-shortfall case -- the
# resulting shortfall must surface as unexplained, never silently matched.
#
# NOTE on methodology (a real finding, not a bug): the real refund_mismatch
# archetype's settlement bank-credit already equals payment.amount exactly,
# INDEPENDENT of the refund (the refund is a wholly separate, later debit --
# see data/synthetic/generator.py's gen_refund_mismatch and its own ground-
# truth rationale: "Full settlement... followed by a refund debit; refund
# record fully explains the net position" -- i.e. the refund is not
# load-bearing evidence for the payment<->settlement match at all). Removing
# that refund record correctly leaves the match untouched, because it was
# never what justified the match in the first place. To genuinely test
# "missing refund leaves a real shortfall", the shortfall must be
# constructed so the refund IS load-bearing (the bank credit is reduced by
# the refund amount), which is what this test does instead.
def test_04_missing_refund_record_leaves_a_real_unexplained_shortfall(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 3)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    credit_txn = next(
        b for b in mutated_dataset.bank_transactions
        if b.matched_settlement_id == settlement.settlement_id and b.direction == "credit"
    )
    refund_amount = (payment.amount / 4).quantize(Decimal("0.01"))
    credit_txn.amount = payment.amount - refund_amount  # bank credit reduced as if a refund had been netted

    # Confirm the (correct, expected) shortfall shows up once the refund is missing.
    result_without_refund = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result_without_refund.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 5. Missing/blank reference -- covered in test_identifier_manipulation.py
# (item 10); not duplicated here.


# 6. Degenerate/placeholder timestamp (e.g. an unset "epoch" date standing
# in for "timestamp truly unknown") must not crash and must not fabricate
# a confident match via coincidental date proximity to anything.
def test_06_degenerate_placeholder_timestamp_does_not_crash_or_fabricate_certainty(mutated_dataset, ground_truth):
    from datetime import datetime

    order_id = pick_by_archetype(ground_truth, "exact_match", 1)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    settlement.settled_at = datetime(1970, 1, 1)  # a common "unset" placeholder value

    bundle = analyze(mutated_dataset, payment.payment_id)  # must not raise
    if bundle.reconciliation_status == "matched":
        assert bundle.root_cause.status == "VERIFIED"


# 7. Total absence of evidence (no settlement, no bank transaction, no
# refund at all linked to this payment) -- the only honest outcome is safe
# escalation, never an invented resolution.
def test_07_total_absence_of_evidence_is_safely_escalated(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 2)
    payment = find_payment_by_order(mutated_dataset, order_id)
    linked_settlement_ids = {s.settlement_id for s in mutated_dataset.settlements if s.payment_id == payment.payment_id}
    mutated_dataset.settlements = [s for s in mutated_dataset.settlements if s.payment_id != payment.payment_id]
    mutated_dataset.bank_transactions = [
        b for b in mutated_dataset.bank_transactions if b.matched_settlement_id not in linked_settlement_ids
    ]
    mutated_dataset.refunds = [r for r in mutated_dataset.refunds if r.payment_id != payment.payment_id]

    bundle = analyze(mutated_dataset, payment.payment_id)
    assert bundle.reconciliation_status == "unresolved"
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
    assert result.policy_decision.decision == PolicyDecisionType.UNRESOLVED
