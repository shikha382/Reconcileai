"""Phase 7/32: timestamp normalization tests at the provider boundary."""
from datetime import datetime

import pytest

from app.adapters.errors import ProviderResponseError
from app.adapters.timestamps import normalize_provider_timestamp


def test_unix_epoch_int_converts_to_naive_utc():
    dt = normalize_provider_timestamp(1785574800, field_name="created_at")
    assert dt == datetime(2026, 8, 1, 9, 0, 0)
    assert dt.tzinfo is None


def test_epoch_as_digit_string_is_accepted():
    dt = normalize_provider_timestamp("1785574800", field_name="created_at")
    assert dt == datetime(2026, 8, 1, 9, 0, 0)


def test_iso8601_with_explicit_offset_converts_to_utc():
    dt = normalize_provider_timestamp("2026-08-01T09:00:00+05:30", field_name="value_date")
    assert dt == datetime(2026, 8, 1, 3, 30, 0)


def test_iso8601_with_z_suffix_is_accepted():
    dt = normalize_provider_timestamp("2026-08-01T09:00:00Z", field_name="value_date")
    assert dt == datetime(2026, 8, 1, 9, 0, 0)


def test_missing_timezone_is_rejected_not_assumed_local():
    with pytest.raises(ProviderResponseError, match="ambiguous"):
        normalize_provider_timestamp("2026-08-01T09:00:00", field_name="value_date")


def test_malformed_string_is_rejected():
    with pytest.raises(ProviderResponseError):
        normalize_provider_timestamp("not-a-date", field_name="value_date")


def test_empty_string_is_rejected():
    with pytest.raises(ProviderResponseError):
        normalize_provider_timestamp("", field_name="value_date")


def test_ancient_timestamp_is_rejected():
    with pytest.raises(ProviderResponseError, match="plausible"):
        normalize_provider_timestamp(0, field_name="created_at")  # 1970-01-01


def test_far_future_timestamp_is_rejected():
    with pytest.raises(ProviderResponseError, match="plausible"):
        normalize_provider_timestamp(32503680000, field_name="created_at")  # year 3000 -- a valid but implausible epoch


def test_boolean_is_rejected():
    with pytest.raises(ProviderResponseError):
        normalize_provider_timestamp(True, field_name="created_at")


def test_unsupported_type_is_rejected():
    with pytest.raises(ProviderResponseError):
        normalize_provider_timestamp(3.14, field_name="created_at")


def test_boundary_timestamp_2000_is_accepted():
    dt = normalize_provider_timestamp("2000-01-01T00:00:00+00:00", field_name="created_at")
    assert dt == datetime(2000, 1, 1, 0, 0, 0)
