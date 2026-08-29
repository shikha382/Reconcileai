"""Scenarios 5, 6, 7, 16, 17 (valid fee, invalid fee, refund, currency
mismatch, Decimal precision)."""
from decimal import Decimal

from app.db.models import Refund
from app.engines.reconciliation.candidate_generation import build_context
from app.engines.reconciliation.matching import resolve_single_linked_settlement
from app.engines.reconciliation.verification import verify_fee_consistency
from shared.taxonomy import ReconciliationStatus

from .factories import BASE_DATE, CARD_FEE_RULE, ZERO_FEE_RULE, make_bank_txn, make_payment, make_settlement


def test_valid_fee_is_matched_and_verified_exactly():
    payment = make_payment(amount="5000.00", method="card")
    # Correct: fee = 5000*0.018 + 2.00 = 92.00, tax = 92.00*0.18 = 16.56, net = 4891.44
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4891.44")
    bank_txn = make_bank_txn(amount="4891.44")
    ctx = build_context([payment], [settlement], [bank_txn], [], [CARD_FEE_RULE])

    fee_check = verify_fee_consistency(payment, settlement, ctx)
    assert fee_check.consistent
    assert fee_check.expected_net == Decimal("4891.44")

    result = resolve_single_linked_settlement(payment, settlement, ctx)
    assert result.status == ReconciliationStatus.MATCHED
    assert result.method == "fee_verified"
    assert result.financial_impact == Decimal("0.00")


def test_invalid_fee_is_rejected_not_matched():
    """The exact scenario the M1 adversarial fee_mismatch cases are built
    around: a fee WAS deducted, but not the one the rule prescribes."""
    payment = make_payment(amount="5000.00", method="card")
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4870.00")  # ~21.44 short of correct
    bank_txn = make_bank_txn(amount="4870.00")
    ctx = build_context([payment], [settlement], [bank_txn], [], [CARD_FEE_RULE])

    fee_check = verify_fee_consistency(payment, settlement, ctx)
    assert not fee_check.consistent

    result = resolve_single_linked_settlement(payment, settlement, ctx)
    assert result.status != ReconciliationStatus.MATCHED
    assert result.status == ReconciliationStatus.MISMATCH
    assert any("does not explain" in line for line in result.why_not_matched)


def test_refund_consistent_enriches_matched_result_without_downgrading():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_credit = make_bank_txn(amount="1000.00", direction="credit")
    bank_debit = make_bank_txn(bank_txn_id="BANKTXN-00002", amount="400.00", direction="debit")
    refund = Refund(
        refund_id="REF-00001", payment_id="PAY-00001", amount=Decimal("400.00"), currency="INR",
        initiated_at=BASE_DATE, processed_at=BASE_DATE, status="processed", reference="RFND00001",
        metadata_json="{}",
    )
    ctx = build_context([payment], [settlement], [bank_credit, bank_debit], [refund], [ZERO_FEE_RULE])

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.MATCHED
    assert result.matched_refund_ids == ["REF-00001"]
    assert any("refund evidence consistent" in line for line in result.why_matched)


def test_refund_inconsistent_forces_mismatch_even_if_settlement_matched():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_credit = make_bank_txn(amount="1000.00", direction="credit")
    # Refund exists but NO matching debit anywhere -- unexplained.
    refund = Refund(
        refund_id="REF-00001", payment_id="PAY-00001", amount=Decimal("400.00"), currency="INR",
        initiated_at=BASE_DATE, processed_at=BASE_DATE, status="processed", reference="RFND00001",
        metadata_json="{}",
    )
    ctx = build_context([payment], [settlement], [bank_credit], [refund], [ZERO_FEE_RULE])

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.MISMATCH
    assert result.financial_impact == Decimal("400.00")


def test_currency_mismatch_is_never_matched():
    payment = make_payment(currency="INR")
    settlement = make_settlement(currency="USD")
    bank_txn = make_bank_txn(currency="USD")
    ctx = build_context([payment], [settlement], [bank_txn], [], [ZERO_FEE_RULE])

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.MISMATCH
    assert result.method == "currency_mismatch"
    assert any("currency mismatch" in line for line in result.why_not_matched)


def test_all_financial_computations_use_decimal_never_float():
    payment = make_payment(amount="4970.37", method="card")  # not exactly representable in binary float
    settlement = make_settlement(amount="4970.37", fee="91.47", tax="16.46", net_amount="4862.44")
    bank_txn = make_bank_txn(amount="4862.44")
    ctx = build_context([payment], [settlement], [bank_txn], [], [CARD_FEE_RULE])

    fee_check = verify_fee_consistency(payment, settlement, ctx)
    assert isinstance(fee_check.expected_fee, Decimal)
    assert isinstance(fee_check.expected_net, Decimal)
    assert isinstance(fee_check.delta, Decimal)

    result = resolve_single_linked_settlement(payment, settlement, ctx)
    assert isinstance(result.financial_impact, Decimal)
