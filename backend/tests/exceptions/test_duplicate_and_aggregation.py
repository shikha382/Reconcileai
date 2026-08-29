"""Scenarios 11, 12: duplicate detection, aggregation explanation."""
from decimal import Decimal

from app.engines.exceptions.classifier import classify_exception
from app.engines.reconciliation.engine import reconcile_all
from app.engines.root_cause.hypotheses import test_aggregation_hypothesis as run_aggregation_hypothesis
from app.engines.root_cause.hypotheses import test_duplicate_hypothesis as run_duplicate_hypothesis
from shared.taxonomy import ExceptionCategory, ReconciliationStatus

from .factories import ZERO_FEE_RULE, make_bank_txn, make_context, make_payment, make_settlement


def test_duplicate_hypothesis_verified_when_siblings_exist():
    payment = make_payment(amount="1000.00")
    sibling = make_settlement(settlement_id="STL-00002", amount="1000.00", net_amount="1000.00")
    hyp = run_duplicate_hypothesis(payment, [sibling])
    assert hyp.status == "VERIFIED"
    assert hyp.evidence_ids == ["STL-00002"]


def test_duplicate_hypothesis_rejected_with_no_siblings():
    payment = make_payment(amount="1000.00")
    hyp = run_duplicate_hypothesis(payment, [])
    assert hyp.status == "REJECTED"


def test_duplicate_settlements_classify_as_duplicate_and_stay_ambiguous():
    payment = make_payment(amount="1000.00")
    settlement_1 = make_settlement(settlement_id="STL-00001", amount="1000.00", net_amount="1000.00")
    settlement_2 = make_settlement(settlement_id="STL-00002", amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(settlement_id="STL-00001", amount="1000.00")
    context = make_context([payment], [settlement_1, settlement_2], [bank_txn])
    [result] = reconcile_all([payment], [settlement_1, settlement_2], [bank_txn], [], [ZERO_FEE_RULE])

    assert result.status == ReconciliationStatus.AMBIGUOUS
    category = classify_exception(payment, settlement_1, result, context)
    assert category == ExceptionCategory.DUPLICATE


def test_aggregation_hypothesis_verified_when_sum_matches():
    payment_a = make_payment(payment_id="PAY-00001", amount="2000.00")
    payment_b = make_payment(payment_id="PAY-00002", amount="3000.00")
    settlement = make_settlement(settlement_id="STL-00001", payment_id=None, amount="5000.00", net_amount="5000.00")
    bank_txn = make_bank_txn(amount="5000.00")
    context = make_context([payment_a, payment_b], [settlement], [bank_txn])

    hyp = run_aggregation_hypothesis([payment_a, payment_b], settlement, context)
    assert hyp.status == "VERIFIED"
    assert hyp.residual == Decimal("0.00")


def test_aggregation_hypothesis_rejected_when_sum_does_not_match():
    payment_a = make_payment(payment_id="PAY-00001", amount="2000.00")
    payment_b = make_payment(payment_id="PAY-00002", amount="2500.00")  # sums to 4500, not 5000
    settlement = make_settlement(settlement_id="STL-00001", payment_id=None, amount="5000.00", net_amount="5000.00")
    bank_txn = make_bank_txn(amount="5000.00")
    context = make_context([payment_a, payment_b], [settlement], [bank_txn])

    hyp = run_aggregation_hypothesis([payment_a, payment_b], settlement, context)
    assert hyp.status == "REJECTED"


def test_aggregated_settlement_classifies_correctly_for_each_payment():
    from app.engines.reconciliation.relationships import find_aggregations

    payment_a = make_payment(payment_id="PAY-00001", order_id="ORD-00001", amount="2000.00")
    payment_b = make_payment(payment_id="PAY-00002", order_id="ORD-00002", amount="3000.00")
    settlement = make_settlement(settlement_id="STL-00001", payment_id=None, amount="5000.00", net_amount="5000.00")
    bank_txn = make_bank_txn(amount="5000.00")
    context = make_context([payment_a, payment_b], [settlement], [bank_txn])

    aggregations = find_aggregations(context)
    assert set(aggregations.keys()) == {"PAY-00001", "PAY-00002"}

    for payment in (payment_a, payment_b):
        category = classify_exception(payment, settlement, aggregations[payment.payment_id], context)
        assert category == ExceptionCategory.AGGREGATED_SETTLEMENT
