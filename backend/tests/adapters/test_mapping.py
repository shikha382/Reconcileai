"""Phase 5/11/25/32: canonical mapping correctness, schema-drift protection,
and adversarial provider payloads. Every mapper must either produce a valid
canonical dict or a `rejection_reason` -- never a silent guess, and never
a crash on malformed input.
"""
from decimal import Decimal

import pytest

from app.adapters.razorpay_mapping import (
    map_bank_transaction,
    map_internal_order,
    map_razorpay_payment,
    map_razorpay_refund,
    map_razorpay_settlement,
)

VALID_PAYMENT = {
    "id": "pay_RAZ0000001AA", "entity": "payment", "amount": 497037, "currency": "INR",
    "status": "captured", "order_id": "order_RAZ0000001AA", "method": "upi",
    "captured": True, "created_at": 1785574800, "notes": {},
}

VALID_SETTLEMENT = {
    "id": "setl_RAZ0000001AA", "entity": "settlement", "payment_id": "pay_RAZ0000001AA",
    "amount": 497037, "fees": 0, "tax": 0, "utr": "UTR0000001AA", "status": "processed", "created_at": 1785575100,
}

VALID_BANK_TXN = {
    "txn_id": "TXN0000001AA", "value_date": "2026-08-01T09:10:00+05:30",
    "narration": "NEFT-UTR0000001AA-SETTLEMENT", "type": "CR", "amount": "4970.37",
    "currency": "INR", "linked_reference": "setl_RAZ0000001AA",
}

VALID_ORDER = {
    "order_ref": "order_RAZ0000001AA", "customer_ref": "cust_0000001",
    "created_at": "2026-08-01T09:00:00+05:30", "status": "created", "amount": "4970.37", "currency": "INR",
}

VALID_REFUND = {
    "id": "rfnd_RAZ0000002BB", "entity": "refund", "amount": 50000, "currency": "INR",
    "payment_id": "pay_RAZ0000002BB", "status": "processed", "created_at": 1785672000, "notes": {},
}


# --- Happy path: every mapper produces the right canonical shape -----------

def test_payment_maps_correctly():
    result = map_razorpay_payment(VALID_PAYMENT)
    assert result.ok
    assert result.canonical["amount"] == Decimal("4970.37")
    assert result.canonical["currency"] == "INR"
    assert result.canonical["gateway_ref"] == "pay_RAZ0000001AA"
    assert result.canonical["metadata"]["external_id"] == "pay_RAZ0000001AA"
    assert len(result.field_mappings) > 0


def test_settlement_maps_correctly_and_computes_net_amount():
    result = map_razorpay_settlement(VALID_SETTLEMENT)
    assert result.ok
    assert result.canonical["net_amount"] == Decimal("4970.37")
    assert result.canonical["fee"] == Decimal("0.00")


def test_settlement_missing_currency_defaults_to_inr_documented():
    raw = dict(VALID_SETTLEMENT)
    assert "currency" not in raw
    result = map_razorpay_settlement(raw)
    assert result.ok
    assert result.canonical["currency"] == "INR"


def test_bank_transaction_maps_correctly():
    result = map_bank_transaction(VALID_BANK_TXN)
    assert result.ok
    assert result.canonical["direction"] == "credit"
    assert result.canonical["amount"] == Decimal("4970.37")


def test_internal_order_maps_correctly():
    result = map_internal_order(VALID_ORDER)
    assert result.ok
    assert result.canonical["amount"] == Decimal("4970.37")


def test_refund_maps_correctly_and_sets_processed_at_when_processed():
    result = map_razorpay_refund(VALID_REFUND)
    assert result.ok
    assert result.canonical["processed_at"] is not None
    assert result.canonical["amount"] == Decimal("500.00")


def test_refund_not_yet_processed_leaves_processed_at_null():
    raw = dict(VALID_REFUND, status="created")
    result = map_razorpay_refund(raw)
    assert result.ok
    assert result.canonical["processed_at"] is None


# --- Schema drift (Phase 11) -------------------------------------------------

def test_missing_required_field_is_a_safe_rejection_not_a_crash():
    raw = dict(VALID_PAYMENT)
    del raw["amount"]
    result = map_razorpay_payment(raw)
    assert not result.ok
    assert "amount" in result.rejection_reason


def test_additional_unknown_field_is_ignored_safely():
    raw = dict(VALID_PAYMENT, some_new_field_from_a_future_api_version="whatever")
    result = map_razorpay_payment(raw)
    assert result.ok


def test_renamed_field_is_a_safe_rejection():
    raw = dict(VALID_PAYMENT)
    raw["amt"] = raw.pop("amount")  # provider renamed the field
    result = map_razorpay_payment(raw)
    assert not result.ok


def test_wrong_type_for_amount_is_a_safe_rejection():
    raw = dict(VALID_PAYMENT, amount="not-a-number")
    result = map_razorpay_payment(raw)
    assert not result.ok


def test_null_amount_is_a_safe_rejection():
    raw = dict(VALID_PAYMENT, amount=None)
    result = map_razorpay_payment(raw)
    assert not result.ok


def test_invalid_currency_is_caught_downstream_by_existing_schema_not_silently_accepted():
    # The mapper itself only requires *a* currency string; USD (or anything
    # not in ALLOWED_CURRENCIES) is correctly rejected by the EXISTING M1
    # Pydantic schema validation this record flows into next -- proven in
    # test_end_to_end_fixture_pipeline.py, not re-implemented here. This is
    # the correct division of labor (Phase 9: do not bypass, and do not
    # duplicate, existing validation) -- the mapper translates fields, the
    # existing schema enforces the currency allowlist.
    result = map_razorpay_payment(dict(VALID_PAYMENT, currency="USD"))
    assert result.ok
    assert result.canonical["currency"] == "USD"


def test_empty_string_id_is_a_safe_rejection_not_a_crash():
    # id_mapping.external_id_to_canonical raises ValueError on an empty
    # external id -- the mapper must catch that too (not just its own
    # ProviderResponseError), never letting it escape as an unhandled crash.
    raw = dict(VALID_PAYMENT, id="")
    result = map_razorpay_payment(raw)
    assert not result.ok
    assert result.canonical is None


def test_malformed_id_type_never_crashes_the_mapper():
    raw = dict(VALID_PAYMENT, id=12345)  # id should be a string
    result = map_razorpay_payment(raw)
    # int(str(12345)) still produces a valid (if odd) canonical id -- this
    # is intentionally permissive at the mapper layer (str() on any
    # scalar is safe); the point is it never crashes.
    assert result.ok or result.rejection_reason is not None


def test_unexpected_nested_object_where_a_scalar_was_expected_is_a_safe_rejection():
    raw = dict(VALID_PAYMENT, amount={"unexpected": "nested_object"})
    result = map_razorpay_payment(raw)
    assert not result.ok


def test_unknown_status_value_is_passed_through_not_rejected():
    # Canonical PaymentRecord.status is a plain string (no enum constraint)
    # -- an unexpected status from the provider is preserved, not guessed
    # into a known value.
    result = map_razorpay_payment(dict(VALID_PAYMENT, status="some_future_status_value"))
    assert result.ok
    assert result.canonical["status"] == "some_future_status_value"


# --- Adversarial provider payloads (Phase 25) -------------------------------

@pytest.mark.parametrize(
    "mutation",
    [
        {"amount": -497037},  # negative amount
        {"amount": 4970.37},  # float where paise int expected
        {"amount": "497037.5"},  # fractional paise
        {"created_at": "not-a-timestamp"},
        {"created_at": None},
        {"order_id": ""},
        {"id": ""},
    ],
)
def test_adversarial_payment_mutations_are_safely_rejected(mutation):
    raw = dict(VALID_PAYMENT, **mutation)
    result = map_razorpay_payment(raw)
    assert not result.ok
    assert result.rejection_reason is not None


def test_negative_amount_is_never_silently_made_positive():
    result = map_razorpay_payment(dict(VALID_PAYMENT, amount=-497037))
    assert not result.ok
    assert result.canonical is None  # never a guessed/coerced positive value
