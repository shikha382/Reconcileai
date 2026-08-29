"""Phase 7: timestamp normalization at the provider boundary. Razorpay's
real API represents timestamps as Unix epoch seconds (UTC, unambiguous by
construction) -- e.g. `created_at: 1594982616`. Other sources (a bank
export) might send an ISO-8601 string with or without an explicit UTC
offset. This module converts every supported provider representation into
a `datetime` that `app.engines.normalization.normalize_timestamp` (reused
verbatim downstream, never re-derived) can accept -- and REJECTS anything
ambiguous rather than guessing a timezone.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.adapters.errors import ProviderResponseError

# A deliberately generous but bounded sanity window -- rejects obviously
# wrong values (Phase 7's "ancient timestamp"/"future timestamp" adversarial
# cases) without hardcoding a business-specific cutoff. 2000-01-01 to
# 2100-01-01 covers every plausible real or synthetic record without
# silently accepting a clearly-corrupted epoch (e.g. 0, or a millisecond
# value mistaken for seconds).
_EARLIEST_PLAUSIBLE = datetime(2000, 1, 1, tzinfo=timezone.utc)
_LATEST_PLAUSIBLE = datetime(2100, 1, 1, tzinfo=timezone.utc)


def _check_plausible(dt: datetime, *, field_name: str) -> datetime:
    if dt < _EARLIEST_PLAUSIBLE or dt > _LATEST_PLAUSIBLE:
        raise ProviderResponseError(f"{field_name}: {dt.isoformat()} is outside the plausible date range (2000-2100)")
    return dt


def normalize_provider_timestamp(value: object, *, field_name: str) -> datetime:
    """Accepts a Unix epoch integer (seconds, UTC) or an ISO-8601 string
    that carries an explicit UTC offset. Returns a naive-UTC datetime
    (matching app.engines.normalization.normalize_timestamp's own output
    convention) -- NEVER assumes local time for an ambiguous input."""
    if isinstance(value, bool):
        raise ProviderResponseError(f"{field_name}: received a boolean where a timestamp was expected")

    if isinstance(value, int):
        try:
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise ProviderResponseError(f"{field_name}: {value!r} is not a valid Unix epoch timestamp")
        return _check_plausible(dt, field_name=field_name).replace(tzinfo=None)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ProviderResponseError(f"{field_name}: empty timestamp string")
        # Pure-digit strings are almost always a JSON-encoded epoch int --
        # handle them the same way as a real int, rather than letting
        # fromisoformat reject them uninformatively.
        if stripped.lstrip("-").isdigit():
            return normalize_provider_timestamp(int(stripped), field_name=field_name)
        try:
            dt = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            raise ProviderResponseError(f"{field_name}: {value!r} is not a recognized ISO-8601 timestamp or Unix epoch")
        if dt.tzinfo is None:
            # Phase 7's own explicit instruction: never silently assume
            # local time for an ambiguous (no-offset) timestamp -- reject
            # and let the caller supply an explicit offset instead.
            raise ProviderResponseError(f"{field_name}: {value!r} has no timezone offset -- ambiguous, refusing to guess")
        dt_utc = dt.astimezone(timezone.utc)
        return _check_plausible(dt_utc, field_name=field_name).replace(tzinfo=None)

    raise ProviderResponseError(f"{field_name}: {value!r} is not a supported timestamp representation (expected int epoch or ISO-8601 string)")
