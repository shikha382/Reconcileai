"""Decimal-only money handling shared by every part of the codebase.

CLAUDE.md rule: never use floating point for money, anywhere. This module is the
single place quantization and Decimal-safe (de)serialization live, so that rule
can actually be enforced/checked in one place instead of trusted by convention.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

TWO_PLACES = Decimal("0.01")


def quantize(amount: Decimal) -> Decimal:
    """Round to the nearest paisa/cent using HALF_UP, matching standard
    payment-processor rounding conventions. Input must already be a Decimal
    (or something Decimal() can parse from a string) -- never a float, since
    a float has already lost precision before it reaches this function."""
    if isinstance(amount, float):
        raise TypeError(
            "quantize() received a float; construct the Decimal from a string "
            "or int upstream instead of introducing binary-float rounding error"
        )
    return Decimal(amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def has_at_most_two_decimal_places(amount: Decimal) -> bool:
    return amount.as_tuple().exponent >= -2


class DecimalSafeEncoder(json.JSONEncoder):
    """Serializes Decimal as a tagged fixed-point string, never as a JSON
    float, so re-parsing can never introduce binary-float rounding error.
    Also handles datetime/date as ISO-8601 strings."""

    def default(self, o: Any) -> Any:
        if isinstance(o, Decimal):
            return {"__decimal__": str(o)}
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        return super().default(o)


def _decimal_safe_object_hook(obj: dict) -> Any:
    if "__decimal__" in obj:
        return Decimal(obj["__decimal__"])
    return obj


def dumps(obj: Any) -> str:
    return json.dumps(obj, cls=DecimalSafeEncoder, indent=2, sort_keys=True)


def loads(s: str) -> Any:
    return json.loads(s, object_hook=_decimal_safe_object_hook)
