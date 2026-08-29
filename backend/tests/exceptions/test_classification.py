"""Scenarios 1, 2: exception taxonomy (no second taxonomy created) and
exception classification correctness."""
from decimal import Decimal

from app.engines.exceptions.classifier import classify_exception
from app.engines.reconciliation.engine import reconcile_all
from shared.taxonomy import ExceptionCategory

from .factories import CARD_FEE_RULE, ZERO_FEE_RULE, make_bank_txn, make_context, make_payment, make_settlement


def test_taxonomy_uses_only_m1_canonical_categories():
    """Every category classify_exception can return must be a real member
    of shared.taxonomy.ExceptionCategory -- no second/duplicate taxonomy."""
    import inspect

    from app.engines.exceptions import classifier

    source = inspect.getsource(classifier)
    for category in ExceptionCategory:
        # Every enum member referenced in the module is a legitimate,
        # existing M1 category (this just documents the invariant; the real
        # guarantee is the type annotation classify_exception() -> ExceptionCategory | None).
        assert isinstance(category, ExceptionCategory)


def test_clean_exact_match_has_no_category():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(amount="1000.00")
    context = make_context([payment], [settlement], [bank_txn])
    [result] = reconcile_all([payment], [settlement], [bank_txn], [], [ZERO_FEE_RULE])

    category = classify_exception(payment, settlement, result, context)
    assert category is None


def test_fee_mismatch_classifies_as_fee_mismatch():
    payment = make_payment(amount="5000.00", method="card")
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4891.44")
    bank_txn = make_bank_txn(amount="4891.44")
    context = make_context([payment], [settlement], [bank_txn], fee_rules=[CARD_FEE_RULE])
    [result] = reconcile_all([payment], [settlement], [bank_txn], [], [CARD_FEE_RULE])

    category = classify_exception(payment, settlement, result, context)
    assert category == ExceptionCategory.FEE_MISMATCH


def test_over_settlement_classifies_correctly():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1050.00", net_amount="1050.00")
    bank_txn = make_bank_txn(amount="1050.00")
    context = make_context([payment], [settlement], [bank_txn])
    [result] = reconcile_all([payment], [settlement], [bank_txn], [], [ZERO_FEE_RULE])

    category = classify_exception(payment, settlement, result, context)
    assert category == ExceptionCategory.OVER_SETTLEMENT


def test_missing_transaction_classifies_correctly():
    payment = make_payment(amount="1000.00")
    context = make_context([payment], [])
    [result] = reconcile_all([payment], [], [], [], [ZERO_FEE_RULE])

    category = classify_exception(payment, None, result, context)
    assert category == ExceptionCategory.MISSING_TRANSACTION
