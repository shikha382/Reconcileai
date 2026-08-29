"""Scenario 20: evidence bundle serialization/deserialization. The
EvidenceBundle is the controlled boundary a future AI layer will consume --
it must round-trip through JSON without loss (Decimal-safe, per
shared.money), since a real system would persist/transmit it.
"""
from datetime import datetime
from decimal import Decimal

from app.services.exception_service import build_evidence_bundle
from app.engines.evidence.graph import build_graph
from app.engines.reconciliation.candidate_generation import build_context
from app.engines.reconciliation.engine import reconcile_all
from shared.money import loads

from .factories import ZERO_FEE_RULE, make_bank_txn, make_payment, make_settlement


def _build_one_bundle(payment, settlements, bank_txns):
    context = build_context([payment], settlements, bank_txns, [], [ZERO_FEE_RULE])
    graph = build_graph([payment], settlements, bank_txns, [])
    [result] = reconcile_all([payment], settlements, bank_txns, [], [ZERO_FEE_RULE])
    return build_evidence_bundle(payment, result, context, graph, datetime(2026, 6, 1))


def test_evidence_bundle_serializes_to_valid_json():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(amount="1000.00")
    bundle = _build_one_bundle(payment, [settlement], [bank_txn])

    raw_json = bundle.to_json()
    parsed = loads(raw_json)

    assert parsed["payment_id"] == "PAY-00001"
    assert parsed["order_id"] == "ORD-00001"
    assert parsed["reconciliation_status"] == "matched"


def test_evidence_bundle_decimal_fields_round_trip_exactly():
    payment = make_payment(amount="4970.37")  # not exactly representable in binary float
    settlement = make_settlement(amount="4970.00", net_amount="4970.00")  # deliberately Rs 0.37 short
    bank_txn = make_bank_txn(amount="4970.00")
    bundle = _build_one_bundle(payment, [settlement], [bank_txn])

    parsed = loads(bundle.to_json())
    assert Decimal(parsed["financial_exposure"]["gross_amount"]) == Decimal("4970.37")
    assert isinstance(Decimal(parsed["risk_score"]), Decimal)


def test_evidence_bundle_to_dict_matches_to_json_content():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(amount="1000.00")
    bundle = _build_one_bundle(payment, [settlement], [bank_txn])

    as_dict = bundle.to_dict()
    as_json_then_parsed = loads(bundle.to_json())
    assert as_dict["exception_id"] == as_json_then_parsed["exception_id"]
    assert as_dict["category"] == as_json_then_parsed["category"]


def test_negative_evidence_report_nested_structure_survives_serialization():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1200.00", net_amount="1200.00")
    bank_txn = make_bank_txn(amount="1200.00")
    bundle = _build_one_bundle(payment, [settlement], [bank_txn])

    parsed = loads(bundle.to_json())
    candidates = parsed["negative_evidence_report"]["candidates"]
    assert len(candidates) >= 1
    assert "positive_evidence" in candidates[0]
    assert "negative_evidence" in candidates[0]
