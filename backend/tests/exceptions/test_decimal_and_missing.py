"""Scenarios 18, 19: Decimal precision throughout, and graceful handling of
missing source records (no settlement, no bank credit, no candidates at
all)."""
from decimal import Decimal

from app.engines.reconciliation.engine import reconcile_all
from app.engines.root_cause.decomposition import decompose_discrepancy
from app.engines.root_cause.result import UNEXPLAINED, determine_root_cause
from app.engines.risk.scoring import build_financial_exposure, compute_risk_score
from shared.taxonomy import ReconciliationStatus

from .factories import BASE_DATE, CARD_FEE_RULE, ZERO_FEE_RULE, make_bank_txn, make_context, make_payment, make_settlement


def test_all_root_cause_amounts_are_decimal_never_float():
    payment = make_payment(amount="4970.37", method="card")  # not exactly representable in binary float
    settlement = make_settlement(amount="4970.37", fee="91.47", tax="16.46", net_amount="4862.44")
    bank_txn = make_bank_txn(amount="4862.44")
    context = make_context([payment], [settlement], [bank_txn], fee_rules=[CARD_FEE_RULE])
    [result] = reconcile_all([payment], [settlement], [bank_txn], [], [CARD_FEE_RULE])

    root_cause = determine_root_cause(payment, result, context, settlement, [])
    assert isinstance(root_cause.financial_delta, Decimal)
    assert isinstance(root_cause.explained_amount, Decimal)
    assert isinstance(root_cause.unexplained_amount, Decimal)

    decomposition = decompose_discrepancy(payment, settlement, context)
    assert isinstance(decomposition.residual, Decimal)

    exposure = build_financial_exposure(payment, root_cause)
    assert isinstance(exposure.gross_amount, Decimal)

    risk = compute_risk_score(payment, root_cause, BASE_DATE)
    assert isinstance(risk, Decimal)


def test_missing_settlement_produces_unresolved_without_crashing():
    payment = make_payment(amount="1000.00")
    context = make_context([payment], [])
    [result] = reconcile_all([payment], [], [], [], [ZERO_FEE_RULE])

    root_cause = determine_root_cause(payment, result, context, None, [])
    assert root_cause.status == UNEXPLAINED
    assert root_cause.root_cause == "missing_transaction"
    assert root_cause.unexplained_amount == Decimal("1000.00")


def test_settlement_with_no_bank_credit_does_not_crash_decomposition():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    context = make_context([payment], [settlement], [])  # no bank_txn at all

    decomposition = decompose_discrepancy(payment, settlement, context)
    assert decomposition.observed == Decimal("0.00")
    assert isinstance(decomposition.residual, Decimal)


def test_no_refunds_and_no_fee_rule_does_not_crash():
    payment = make_payment(amount="1000.00", method="unknown_method")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(amount="1000.00")
    context = make_context([payment], [settlement], [bank_txn], fee_rules=[])  # no fee rule for this method at all

    decomposition = decompose_discrepancy(payment, settlement, context)
    assert decomposition.components == {}
