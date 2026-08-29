"""Scenario 13: cross-source, multi-source traversal -- "given this
unmatched settlement, show me every connected financial record that could
explain it"."""
from app.engines.evidence.graph import build_graph, connected_records

from .factories import make_bank_txn, make_payment, make_refund, make_settlement


def test_traversal_from_settlement_reaches_payment_order_and_bank_txn():
    payment = make_payment(payment_id="PAY-00001", order_id="ORD-00001")
    settlement = make_settlement(settlement_id="STL-00001", payment_id="PAY-00001")
    bank_txn = make_bank_txn(bank_txn_id="BANKTXN-00001", settlement_id="STL-00001")
    graph = build_graph([payment], [settlement], [bank_txn], [])

    result = connected_records("settlement", "STL-00001", graph)

    assert result["order_id"] == "ORD-00001"
    assert result["payment_id"] == "PAY-00001"
    assert "STL-00001" in result["settlements"]
    assert "BANKTXN-00001" in result["bank_transactions"]


def test_traversal_from_order_reaches_refund():
    payment = make_payment(payment_id="PAY-00001", order_id="ORD-00001")
    refund = make_refund(refund_id="REF-00001", payment_id="PAY-00001")
    graph = build_graph([payment], [], [], [refund])

    result = connected_records("order", "ORD-00001", graph)

    assert result["payment_id"] == "PAY-00001"
    assert "REF-00001" in result["refunds"]


def test_traversal_from_payment_reaches_fee_rule_method():
    payment = make_payment(payment_id="PAY-00001", method="card")
    graph = build_graph([payment], [], [], [])

    result = connected_records("payment", "PAY-00001", graph)
    assert result["fee_rule_method"] == "card"


def test_traversal_across_split_settlement_reaches_both_settlements_and_bank_txns():
    payment = make_payment(payment_id="PAY-00001", order_id="ORD-00001")
    settlement_1 = make_settlement(settlement_id="STL-00001", payment_id="PAY-00001")
    settlement_2 = make_settlement(settlement_id="STL-00002", payment_id="PAY-00001")
    bank_1 = make_bank_txn(bank_txn_id="BANKTXN-00001", settlement_id="STL-00001")
    bank_2 = make_bank_txn(bank_txn_id="BANKTXN-00002", settlement_id="STL-00002")
    graph = build_graph([payment], [settlement_1, settlement_2], [bank_1, bank_2], [])

    result = connected_records("payment", "PAY-00001", graph)

    assert set(result["settlements"]) == {"STL-00001", "STL-00002"}
    assert set(result["bank_transactions"]) == {"BANKTXN-00001", "BANKTXN-00002"}


def test_traversal_from_unknown_entity_type_raises():
    import pytest

    graph = build_graph([], [], [], [])
    with pytest.raises(ValueError):
        connected_records("bogus", "X", graph)
