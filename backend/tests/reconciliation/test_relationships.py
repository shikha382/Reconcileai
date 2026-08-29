"""Scenarios 9, 10, 11 (partial settlement, split settlement, aggregated
settlement)."""
from decimal import Decimal

from app.engines.reconciliation.candidate_generation import build_context
from app.engines.reconciliation.matching import resolve_single_linked_settlement
from app.engines.reconciliation.relationships import find_aggregations, resolve_multiple_linked_settlements
from shared.taxonomy import ReconciliationStatus, RelationshipType

from .factories import ZERO_FEE_RULE, make_bank_txn, make_payment, make_settlement


def test_partial_settlement_is_partial_not_matched():
    payment = make_payment(amount="10000.00")
    settlement = make_settlement(amount="6000.00", net_amount="6000.00")  # 60% settled, remainder outstanding
    bank_txn = make_bank_txn(amount="6000.00")
    ctx = build_context([payment], [settlement], [bank_txn], [], [ZERO_FEE_RULE])

    result = resolve_single_linked_settlement(payment, settlement, ctx)

    assert result.status == ReconciliationStatus.PARTIAL
    assert result.financial_impact == Decimal("4000.00")


def test_split_settlement_sums_exactly_and_matches():
    payment = make_payment(amount="5000.00")
    settlement_1 = make_settlement(settlement_id="STL-00001", amount="2000.00", net_amount="2000.00")
    settlement_2 = make_settlement(settlement_id="STL-00002", amount="3000.00", net_amount="3000.00")
    bank_1 = make_bank_txn(bank_txn_id="BANKTXN-00001", settlement_id="STL-00001", amount="2000.00")
    bank_2 = make_bank_txn(bank_txn_id="BANKTXN-00002", settlement_id="STL-00002", amount="3000.00")
    ctx = build_context([payment], [settlement_1, settlement_2], [bank_1, bank_2], [], [ZERO_FEE_RULE])

    result = resolve_multiple_linked_settlements(payment, [settlement_1, settlement_2], ctx)

    assert result.status == ReconciliationStatus.MATCHED
    assert result.method == "split_settlement_sum"
    assert result.relationship == RelationshipType.ONE_TO_MANY
    assert set(result.matched_settlement_ids) == {"STL-00001", "STL-00002"}
    assert result.financial_impact == Decimal("0.00")


def test_split_settlement_that_does_not_sum_exactly_is_not_matched():
    payment = make_payment(amount="5000.00")
    settlement_1 = make_settlement(settlement_id="STL-00001", amount="2000.00", net_amount="2000.00")
    settlement_2 = make_settlement(settlement_id="STL-00002", amount="2500.00", net_amount="2500.00")  # sums to 4500, not 5000
    bank_1 = make_bank_txn(bank_txn_id="BANKTXN-00001", settlement_id="STL-00001", amount="2000.00")
    bank_2 = make_bank_txn(bank_txn_id="BANKTXN-00002", settlement_id="STL-00002", amount="2500.00")
    ctx = build_context([payment], [settlement_1, settlement_2], [bank_1, bank_2], [], [ZERO_FEE_RULE])

    result = resolve_multiple_linked_settlements(payment, [settlement_1, settlement_2], ctx)

    assert result.status != ReconciliationStatus.MATCHED


def test_aggregated_settlement_two_payments_one_settlement():
    payment_a = make_payment(payment_id="PAY-00001", order_id="ORD-00001", amount="2000.00")
    payment_b = make_payment(payment_id="PAY-00002", order_id="ORD-00002", amount="3000.00")
    settlement = make_settlement(
        settlement_id="STL-00001", payment_id=None, amount="5000.00", net_amount="5000.00",
    )
    bank_txn = make_bank_txn(amount="5000.00")
    ctx = build_context([payment_a, payment_b], [settlement], [bank_txn], [], [ZERO_FEE_RULE])

    aggregations = find_aggregations(ctx)

    assert set(aggregations.keys()) == {"PAY-00001", "PAY-00002"}
    for result in aggregations.values():
        assert result.status == ReconciliationStatus.MATCHED
        assert result.method == "aggregated_settlement_sum"
        assert result.relationship == RelationshipType.MANY_TO_ONE
        assert result.matched_settlement_ids == ["STL-00001"]
