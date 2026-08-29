"""Deterministic explanation strings -- NOT LLM explanation. Every function
here turns an already-computed, already-typed check result into a plain
"✓ ..." / "✗ ..." sentence. Nothing here decides anything; it only describes
what matching.py/verification.py already decided, so the reasoning is
readable without recomputation.
"""
from __future__ import annotations

from decimal import Decimal

from app.engines.reconciliation.verification import FeeCheckResult, RefundCheckResult


def reference_line(matched: bool, method: str) -> str:
    if matched:
        return f"✓ reference matched ({method})"
    return "✗ reference did not match"


def amount_line(matched: bool, payment_amount: Decimal, other_amount: Decimal) -> str:
    if matched:
        return "✓ amount matched exactly"
    diff = (payment_amount - other_amount).copy_abs()
    return f"✗ amount differs by ₹{diff}"


def date_line(within_tolerance: bool, delta_days: int, tolerance_days: int) -> str:
    if delta_days == 0:
        return "✓ same-day settlement"
    if within_tolerance:
        return f"✓ date within allowed tolerance ({delta_days}d ≤ {tolerance_days}d)"
    return f"✗ date difference of {delta_days}d exceeds the {tolerance_days}d tolerance"


def fee_line(fee_result: FeeCheckResult | None) -> str | None:
    if fee_result is None:
        return None
    if fee_result.consistent:
        return f"✓ settlement balance matched fee rule {fee_result.rule_id} (net {fee_result.expected_net})"
    return (
        f"✗ fee rule {fee_result.rule_id} does not explain the difference "
        f"(expected net {fee_result.expected_net}, actual {fee_result.actual_net}, "
        f"unexplained by ₹{fee_result.delta})"
    )


def refund_line(refund_result: RefundCheckResult | None) -> str | None:
    if refund_result is None:
        return None
    if refund_result.consistent:
        return f"✓ refund evidence consistent ({len(refund_result.refund_ids)} refund(s) matched to bank debits)"
    return f"✗ refund evidence conflicts (₹{refund_result.unexplained_delta} unexplained)"


def currency_line(matched: bool, payment_currency: str, other_currency: str) -> str:
    if matched:
        return "✓ currency matched"
    return f"✗ currency mismatch ({payment_currency} vs {other_currency})"


def duplicate_candidates_line(count: int) -> str:
    return f"✗ {count} plausible settlement candidates found for this payment -- not safe to auto-select one"


def self_consistency_line(consistent: bool, delta: Decimal) -> str | None:
    if consistent:
        return None
    return f"✗ settlement's own net_amount does not reconcile against its stated fee/tax (off by ₹{delta})"
