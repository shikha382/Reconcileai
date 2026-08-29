from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.engines.validation import DataValidationError, validate_batch, validate_record


def _good_order() -> dict:
    return {
        "order_id": "ORD-00001",
        "customer_ref": "CUST-0001",
        "amount": Decimal("100.00"),
        "currency": "INR",
        "created_at": datetime(2026, 6, 1),
        "status": "paid",
        "metadata": {},
    }


def test_valid_order_passes():
    model = validate_record("order", _good_order())
    assert model.order_id == "ORD-00001"


def test_negative_amount_is_rejected():
    bad = _good_order()
    bad["amount"] = Decimal("-5.00")
    with pytest.raises(ValidationError):
        validate_record("order", bad)


def test_unsupported_currency_is_rejected():
    bad = _good_order()
    bad["currency"] = "USD"
    with pytest.raises(ValidationError):
        validate_record("order", bad)


def test_malformed_order_id_is_rejected():
    bad = _good_order()
    bad["order_id"] = "not-an-id"
    with pytest.raises(ValidationError):
        validate_record("order", bad)


def test_too_many_decimal_places_is_rejected():
    bad = _good_order()
    bad["amount"] = Decimal("100.123")
    with pytest.raises(ValidationError):
        validate_record("order", bad)


def test_validate_batch_collects_every_failure_not_just_the_first():
    good = _good_order()
    bad_currency = _good_order()
    bad_currency["order_id"] = "ORD-00002"
    bad_currency["currency"] = "USD"
    bad_amount = _good_order()
    bad_amount["order_id"] = "ORD-00003"
    bad_amount["amount"] = Decimal("-1.00")

    report = validate_batch("order", [good, bad_currency, bad_amount])
    assert len(report.valid_records) == 1
    assert len(report.failures) == 2
    assert {f.record_ref for f in report.failures} == {"ORD-00002", "ORD-00003"}


def test_validate_batch_raises_data_validation_error_when_requested():
    bad_amount = _good_order()
    bad_amount["amount"] = Decimal("-1.00")
    with pytest.raises(DataValidationError) as excinfo:
        validate_batch("order", [bad_amount], raise_on_error=True)
    assert "ORD-00001" in str(excinfo.value)
