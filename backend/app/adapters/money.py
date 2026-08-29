"""Phase 6: money safety at the provider boundary. Razorpay's real API
represents amounts in integer minor units (paise) -- e.g. 497037 paise for
₹4,970.37. This module converts that integer representation into the
project's canonical Decimal rupee amount, WITHOUT ever passing through a
Python float at any point (float(497037) / 100 would already be exact here,
but the point is this module never risks it for any amount, ever -- see
shared.money's own `quantize`, reused verbatim, never re-derived).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.adapters.errors import ProviderResponseError
from shared.money import quantize

_MINOR_UNITS_PER_RUPEE = Decimal(100)


def minor_units_to_decimal(paise: object, *, field_name: str) -> Decimal:
    """Converts an integer minor-unit amount (paise) into a canonical
    Decimal rupee amount. Only accepts `int` (or a base-10 integer string)
    -- never a float, and never a value that isn't a whole number of paise,
    since anything else means the provider's own representation is already
    ambiguous and must not be guessed at."""
    if isinstance(paise, float):
        raise ProviderResponseError(f"{field_name}: received a float minor-unit amount ({paise!r}); this is unsafe and unsupported")
    if isinstance(paise, bool):  # bool is an int subclass in Python -- reject explicitly, it is never a real amount
        raise ProviderResponseError(f"{field_name}: received a boolean where a minor-unit amount was expected")
    try:
        paise_int = int(str(paise))
    except (ValueError, TypeError):
        raise ProviderResponseError(f"{field_name}: {paise!r} is not a valid integer minor-unit amount")

    if str(paise_int) != str(paise).strip():
        # Defends against a string like "4970.37" being silently truncated
        # by int() into 4970 -- if it doesn't round-trip exactly, reject
        # rather than guess.
        raise ProviderResponseError(f"{field_name}: {paise!r} is not a whole number of minor units")

    if paise_int < 0:
        # Defense in depth (Phase 25 adversarial testing): no monetary
        # amount this project handles is ever legitimately negative --
        # rejected here, at the boundary, rather than relying solely on
        # the downstream Pydantic schema's own (correct, but later) check.
        raise ProviderResponseError(f"{field_name}: {paise!r} is negative; no monetary amount here is ever legitimately negative")

    return quantize(Decimal(paise_int) / _MINOR_UNITS_PER_RUPEE)


def decimal_to_minor_units(amount: Decimal, *, field_name: str = "amount") -> int:
    """The inverse conversion -- used only by fixtures/tests that need to
    round-trip a canonical amount back into a provider-shaped payload.
    Never used on the ingestion path itself."""
    if isinstance(amount, float):
        raise ProviderResponseError(f"{field_name}: received a float, not a Decimal")
    try:
        d = Decimal(amount)
    except InvalidOperation:
        raise ProviderResponseError(f"{field_name}: {amount!r} is not a valid Decimal amount")
    return int((d * _MINOR_UNITS_PER_RUPEE).to_integral_exact())
