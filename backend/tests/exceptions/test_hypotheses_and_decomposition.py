"""Scenarios 6, 7, 8, 9, 10, 14, 15: fee explanation (valid/invalid), refund
explanation, partial explanation, timing explanation, residual calculation,
counterfactual hypothesis testing."""
from decimal import Decimal

from app.engines.reconciliation.engine import reconcile_all
from app.engines.root_cause.decomposition import decompose_discrepancy
from app.engines.root_cause.hypotheses import test_fee_hypothesis as run_fee_hypothesis
from app.engines.root_cause.hypotheses import test_refund_hypothesis as run_refund_hypothesis
from app.engines.root_cause.hypotheses import test_timing_hypothesis as run_timing_hypothesis
from app.engines.root_cause.result import (
    CONTRADICTED,
    PARTIALLY_EXPLAINED,
    VERIFIED,
    determine_root_cause,
)

from .factories import CARD_FEE_RULE, ZERO_FEE_RULE, make_bank_txn, make_context, make_payment, make_refund, make_settlement


def test_valid_fee_hypothesis_is_verified():
    payment = make_payment(amount="5000.00", method="card")
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4891.44")
    context = make_context([payment], [settlement], fee_rules=[CARD_FEE_RULE])

    hyp = run_fee_hypothesis(payment, settlement, context)
    assert hyp.status == "VERIFIED"
    assert hyp.residual == Decimal("0.00")


def test_invalid_fee_hypothesis_is_rejected_with_nonzero_residual():
    payment = make_payment(amount="5000.00", method="card")
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4870.00")  # short by 21.44
    context = make_context([payment], [settlement], fee_rules=[CARD_FEE_RULE])

    hyp = run_fee_hypothesis(payment, settlement, context)
    assert hyp.status == "REJECTED"
    assert hyp.residual > 0


def test_refund_hypothesis_verified_when_net_credit_equals_payment_minus_refund():
    """H1's formula is expected = payment - refund - fee, compared against
    the CONFIRMED CREDIT amount -- this models a settlement netted at
    source (single credit already reflecting the refund deduction), a
    distinct real-world shape from M1's own refund_mismatch archetype
    (full credit + a later separate debit, verified instead by
    verify_refund_consistency / the refund_balance constraint)."""
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_credit = make_bank_txn(amount="600.00", direction="credit")  # already net of the Rs 400 refund
    refund = make_refund(amount="400.00")
    context = make_context([payment], [settlement], [bank_credit], [refund])

    hyp = run_refund_hypothesis(payment, settlement, context)
    assert hyp.status == "VERIFIED"
    assert hyp.residual == Decimal("0.00")


def test_partial_settlement_root_cause_is_partially_explained():
    payment = make_payment(amount="10000.00")
    settlement = make_settlement(amount="6000.00", net_amount="6000.00")
    bank_txn = make_bank_txn(amount="6000.00")
    context = make_context([payment], [settlement], [bank_txn])
    [result] = reconcile_all([payment], [settlement], [bank_txn], [], [ZERO_FEE_RULE])

    root_cause = determine_root_cause(payment, result, context, settlement, [])
    assert root_cause.status == PARTIALLY_EXPLAINED
    assert root_cause.explained_amount == Decimal("6000.00")
    assert root_cause.unexplained_amount == Decimal("4000.00")


def test_timing_hypothesis_verified_within_window():
    from datetime import timedelta

    from .factories import BASE_DATE

    payment = make_payment(captured_at=BASE_DATE)
    settlement = make_settlement(settled_at=BASE_DATE + timedelta(days=3))
    hyp = run_timing_hypothesis(payment, settlement)
    assert hyp.status == "VERIFIED"


def test_timing_hypothesis_rejected_outside_window():
    from datetime import timedelta

    from .factories import BASE_DATE

    payment = make_payment(captured_at=BASE_DATE)
    settlement = make_settlement(settled_at=BASE_DATE + timedelta(days=30))
    hyp = run_timing_hypothesis(payment, settlement)
    assert hyp.status == "REJECTED"


def test_discrepancy_decomposition_fully_explained_by_fee():
    payment = make_payment(amount="5000.00", method="card")
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4891.44")
    bank_txn = make_bank_txn(amount="4891.44")
    context = make_context([payment], [settlement], [bank_txn], fee_rules=[CARD_FEE_RULE])

    decomposition = decompose_discrepancy(payment, settlement, context)
    assert decomposition.fully_explained
    assert decomposition.residual == Decimal("0.00")


def test_discrepancy_decomposition_reports_residual_when_not_fully_explained():
    """Payment 10,000; a Rs 2,000 refund fully evidenced by a matching bank
    debit (component correctly explains Rs 2,000); but the settlement's own
    confirmed credit is Rs 7,990, not the fully-explained Rs 8,000 -- a
    genuine Rs 10 residual, matching the spirit of the M3 brief's own
    worked example (expected - deductions - observed = residual).

    Note: this decomposition is verified here with a SINGLE active
    deduction type (refund), matching how M1's own dataset always exercises
    it (refund_mismatch has zero fee; fee_mismatch has zero refund) --
    combining a settlement-level fee deduction with a payment-level refund
    deduction (a separate, later bank debit) in the same record is a known,
    documented limitation of this decomposition; see CLAUDE.md's M3 entry.
    """
    payment = make_payment(amount="10000.00")  # UPI, zero fee rule
    settlement = make_settlement(amount="7990.00", net_amount="7990.00")
    bank_credit = make_bank_txn(amount="7990.00", direction="credit")
    bank_debit = make_bank_txn(bank_txn_id="BANKTXN-00002", amount="2000.00", direction="debit")
    refund = make_refund(amount="2000.00")
    context = make_context([payment], [settlement], [bank_credit, bank_debit], [refund])

    decomposition = decompose_discrepancy(payment, settlement, context)
    assert decomposition.components["refund"] == Decimal("2000.00")
    assert not decomposition.fully_explained
    assert decomposition.residual == Decimal("10.00")


def test_adversarial_fee_mismatch_root_cause_is_contradicted():
    """The exact M1 adversarial trap: a fee WAS deducted, but doesn't match
    the exact rule. Root cause must be CONTRADICTED, never VERIFIED."""
    payment = make_payment(amount="7842.54", method="card")
    correct_fee = Decimal("143.17")
    correct_tax = Decimal("25.77")
    correct_net = payment.amount - correct_fee - correct_tax
    bogus_net = correct_net - Decimal("9.83")
    settlement = make_settlement(amount="7842.54", fee=str(correct_fee), tax=str(correct_tax), net_amount=str(bogus_net))
    bank_txn = make_bank_txn(amount=str(bogus_net))
    context = make_context([payment], [settlement], [bank_txn], fee_rules=[CARD_FEE_RULE])
    [result] = reconcile_all([payment], [settlement], [bank_txn], [], [CARD_FEE_RULE])

    root_cause = determine_root_cause(payment, result, context, settlement, [])
    assert root_cause.status == CONTRADICTED
    assert root_cause.root_cause == "fee_mismatch_unverified"
    assert root_cause.status != VERIFIED
