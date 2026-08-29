"""Scenarios 1, 2, 4, 13 (exact match, normalized match, date mismatch,
missing candidate). Amount mismatch is scenario 3, covered here too since
it's part of the same single-linked-settlement path."""
from datetime import timedelta
from decimal import Decimal

from app.engines.reconciliation.candidate_generation import build_context
from app.engines.reconciliation.matching import resolve_single_linked_settlement
from app.engines.reconciliation.relationships import resolve_unlinked_payment
from shared.taxonomy import ReconciliationStatus

from .factories import BASE_DATE, ZERO_FEE_RULE, make_bank_txn, make_payment, make_settlement


def _ctx(payments, settlements, bank_txns=(), refunds=(), fee_rules=(ZERO_FEE_RULE,)):
    return build_context(list(payments), list(settlements), list(bank_txns), list(refunds), list(fee_rules))


def test_exact_match_clean_reference():
    payment = make_payment()
    settlement = make_settlement()  # utr_reference default already contains "PAY00001"
    bank_txn = make_bank_txn()
    ctx = _ctx([payment], [settlement], [bank_txn])

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.MATCHED
    assert result.method == "exact_reference"
    assert result.matched_settlement_ids == ["STL-00001"]
    assert result.financial_impact == Decimal("0.00")
    assert any("reference matched" in line for line in result.why_matched)


def test_normalized_reference_match_messy_but_recoverable():
    payment = make_payment()
    settlement = make_settlement(utr_reference="utr 000 01P AY0 000 1")  # noisy but same content
    bank_txn = make_bank_txn()
    ctx = _ctx([payment], [settlement], [bank_txn])

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.MATCHED
    assert result.method == "normalized_reference"


def test_amount_mismatch_with_no_explanation_is_mismatch_not_matched():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1200.00", net_amount="1200.00")  # unexplained overpayment
    bank_txn = make_bank_txn(amount="1200.00")
    ctx = _ctx([payment], [settlement], [bank_txn])

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.MISMATCH
    assert result.financial_impact == Decimal("200.00")
    assert any("amount differs" in line for line in result.why_not_matched)


def test_date_beyond_lenient_tolerance_is_mismatch():
    payment = make_payment(captured_at=BASE_DATE)
    settlement = make_settlement(settled_at=BASE_DATE + timedelta(days=30))  # far beyond any tolerance
    bank_txn = make_bank_txn(value_date=BASE_DATE + timedelta(days=31))
    ctx = _ctx([payment], [settlement], [bank_txn])

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.MISMATCH
    assert any("exceeds" in line for line in result.why_not_matched)


def test_missing_candidate_is_unresolved_not_forced_match():
    payment = make_payment()  # no settlement at all anywhere
    ctx = _ctx([payment], [])

    result = resolve_unlinked_payment(payment, ctx)

    assert result.status == ReconciliationStatus.UNRESOLVED
    assert result.matched_settlement_ids == []
    assert "no candidate settlement found" in result.differences[0]


def test_no_confirmed_bank_credit_is_unresolved():
    payment = make_payment()
    settlement = make_settlement()
    ctx = _ctx([payment], [settlement], bank_txns=[])  # settlement exists, but nothing confirms it

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.UNRESOLVED
