"""Deterministic normalization -- no LLM, no matching, just field cleanup.

Runs on a raw ingested dict BEFORE schema validation, so that messy-but-
recoverable input (extra whitespace, inconsistent casing, non-UTC timestamps)
doesn't get rejected outright when it's exactly the kind of thing normalization
exists to fix. The untouched original is preserved separately by the ingestion
pipeline (app.ingestion.pipeline) regardless of what normalization does here --
this module never mutates its input, it returns a new dict.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from shared.money import quantize

_REFERENCE_STRIP_RE = re.compile(r"[^A-Za-z0-9]+")


def normalize_currency(code: str) -> str:
    return code.strip().upper()


def normalize_amount(value: Any) -> Decimal:
    """Accepts a Decimal, int, or numeric string -- never a float (a float
    has already lost precision before it reaches here; callers must pass the
    original string/Decimal representation, per shared.money.quantize)."""
    if isinstance(value, float):
        raise TypeError("normalize_amount received a float; pass a str or Decimal instead")
    return quantize(Decimal(value))


def normalize_timestamp(value: Any) -> datetime:
    """Parses an ISO-8601 string (or passes through a datetime), and
    standardizes to naive UTC -- i.e. any timezone offset is converted to UTC
    and then the tzinfo is dropped, so all stored timestamps are directly
    comparable without further conversion."""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def normalize_reference(value: str) -> str:
    """Collapses whitespace/case/punctuation variance in human-entered
    reference fields (e.g. UTRs, narrations) so that "ord 00001", "ORD-00001",
    and "ord_00001" all normalize to the same canonical token. This is
    intentionally aggressive -- it is meant to close the gap that would
    otherwise require fuzzy matching (a later milestone) for the merely-messy
    cases, leaving fuzzy matching to handle genuine ambiguity instead.
    """
    return _REFERENCE_STRIP_RE.sub("", value).upper()


def normalize_record(source_type: str, raw: dict) -> dict:
    """Applies the appropriate field-level normalizers to a raw record dict
    based on its source type, returning a new dict. Does not validate --
    that's app.engines.validation's job, run after this."""
    out = dict(raw)

    if "currency" in out:
        out["currency"] = normalize_currency(out["currency"])

    for amount_field in ("amount", "fee", "tax", "net_amount", "fixed_fee"):
        if amount_field in out and out[amount_field] is not None:
            out[amount_field] = normalize_amount(out[amount_field])

    for ts_field in (
        "created_at",
        "captured_at",
        "settled_at",
        "value_date",
        "initiated_at",
        "processed_at",
        "effective_from",
        "effective_to",
    ):
        if ts_field in out and out[ts_field] is not None:
            out[ts_field] = normalize_timestamp(out[ts_field])

    # Only human-entered reference-ish fields are normalized this way -- the
    # deterministic primary IDs (order_id, payment_id, ...) are never touched
    # here; they're either exactly right or the record is genuinely invalid.
    for ref_field in ("utr_reference", "narration", "reference"):
        if ref_field in out and out[ref_field] is not None:
            out[ref_field] = normalize_reference(out[ref_field])

    return out
