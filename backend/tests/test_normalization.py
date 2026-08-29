from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.engines.normalization import (
    normalize_amount,
    normalize_currency,
    normalize_record,
    normalize_reference,
    normalize_timestamp,
)


def test_normalize_currency_strips_and_uppercases():
    assert normalize_currency(" inr ") == "INR"
    assert normalize_currency("Inr") == "INR"


def test_normalize_amount_quantizes_to_two_places():
    assert normalize_amount("100.1") == Decimal("100.10")
    assert normalize_amount(Decimal("100")) == Decimal("100.00")


def test_normalize_amount_rejects_float_input():
    with pytest.raises(TypeError):
        normalize_amount(100.5)


def test_normalize_timestamp_converts_offset_to_naive_utc():
    from datetime import timedelta

    aware = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    result = normalize_timestamp(aware)
    assert result.tzinfo is None
    assert result == datetime(2026, 6, 1, 6, 30, 0)


def test_normalize_timestamp_parses_iso_strings():
    result = normalize_timestamp("2026-06-01T10:00:00")
    assert result == datetime(2026, 6, 1, 10, 0, 0)


def test_normalize_reference_collapses_whitespace_and_case_noise():
    canonical = normalize_reference("UTR007123")
    assert normalize_reference("utr 007 123") == canonical
    assert normalize_reference("UTR-007-123") == canonical
    assert normalize_reference(" utr007123 ") == canonical


def test_normalize_reference_does_not_collapse_genuinely_different_references():
    assert normalize_reference("UTR007123") != normalize_reference("UTRUNRELATED999999")


def test_normalize_record_does_not_mutate_input():
    raw = {"currency": " inr ", "amount": "100.5", "created_at": "2026-06-01T10:00:00"}
    raw_copy = dict(raw)
    normalize_record("order", raw)
    assert raw == raw_copy


def test_normalize_record_leaves_primary_ids_untouched():
    raw = {"order_id": "ORD-00001", "currency": "inr"}
    normalized = normalize_record("order", raw)
    assert normalized["order_id"] == "ORD-00001"
