"""Phase 6/32: money-safety tests at the provider boundary."""
from decimal import Decimal

import pytest

from app.adapters.errors import ProviderResponseError
from app.adapters.money import decimal_to_minor_units, minor_units_to_decimal


def test_paise_converts_to_exact_rupee_decimal():
    assert minor_units_to_decimal(497037, field_name="amount") == Decimal("4970.37")


def test_zero_paise_is_zero_rupees():
    assert minor_units_to_decimal(0, field_name="amount") == Decimal("0.00")


def test_large_amount_survives_without_binary_drift():
    # A value that is a classic float-imprecision trap (e.g. 0.1 + 0.2 != 0.3
    # in binary float) -- proven here to round-trip exactly via Decimal only.
    assert minor_units_to_decimal(1000000007, field_name="amount") == Decimal("10000000.07")


def test_float_minor_units_is_rejected_not_silently_coerced():
    with pytest.raises(ProviderResponseError):
        minor_units_to_decimal(4970.37, field_name="amount")


def test_boolean_is_rejected():
    with pytest.raises(ProviderResponseError):
        minor_units_to_decimal(True, field_name="amount")


def test_non_numeric_string_is_rejected():
    with pytest.raises(ProviderResponseError):
        minor_units_to_decimal("not-a-number", field_name="amount")


def test_decimal_string_minor_units_is_rejected_not_truncated():
    # "4970.37" as a MINOR-UNIT value would silently truncate to 4970 paise
    # (₹49.70) if cast via int() -- must be rejected instead of guessed.
    with pytest.raises(ProviderResponseError):
        minor_units_to_decimal("4970.37", field_name="amount")


def test_round_trip_decimal_to_minor_units_and_back():
    original = Decimal("4970.37")
    paise = decimal_to_minor_units(original)
    assert paise == 497037
    assert minor_units_to_decimal(paise, field_name="amount") == original
