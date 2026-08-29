"""Milestone 3 — reusable constraint/evidence abstraction.

A ConstraintResult is the machine-readable atom every piece of evidence in
M3 is built from: one narrowly-scoped, deterministic check, with its
expected/observed/delta and a reason_code -- never just prose. This is
intentionally a thin wrapper around M2's existing deterministic checks
(app.engines.reconciliation.verification / .matching) rather than a
reimplementation: M2 is COMPLETE and must be preserved, so every number here
is computed by the exact same function M2 already uses, not a parallel copy
that could silently drift from it.

Positive vs. negative evidence is not a separate field -- it's simply
`passed`. Callers building an EvidenceBundle split constraints into
positive_evidence = [c for c in constraints if c.passed] and
negative_evidence = [c for c in constraints if not c.passed].
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.models import Payment, Settlement
from app.engines.normalization import normalize_reference
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.config import LENIENT_DATE_TOLERANCE_DAYS, TIGHT_DATE_TOLERANCE_DAYS
from app.engines.reconciliation.verification import (
    bank_credited_amount,
    verify_fee_consistency,
    verify_refund_consistency,
    verify_settlement_self_consistency,
)


@dataclass
class ConstraintResult:
    constraint: str
    passed: bool
    expected: str | None
    observed: str | None
    delta: str | None
    reason_code: str | None

    def to_dict(self) -> dict:
        return {
            "constraint": self.constraint,
            "expected": self.expected,
            "observed": self.observed,
            "delta": self.delta,
            "passed": self.passed,
            "reason_code": self.reason_code,
        }


def reference_match_constraint(payment: Payment, settlement: Settlement) -> ConstraintResult:
    """Untouched-text comparison only -- narration/reference content is
    treated purely as data to compare, never interpreted or executed (see
    backend/tests/exceptions/test_adversarial.py's malicious-memo-text case:
    this function does string containment/normalization only, nothing else)."""
    pid_token_raw = payment.payment_id.replace("-", "")
    raw_match = pid_token_raw in settlement.utr_reference
    normalized_match = normalize_reference(payment.payment_id) in normalize_reference(settlement.utr_reference)

    if raw_match:
        return ConstraintResult("reference_match", True, pid_token_raw, settlement.utr_reference, None, None)
    if normalized_match:
        return ConstraintResult("reference_match", True, pid_token_raw, settlement.utr_reference, None, "NORMALIZED_MATCH")
    return ConstraintResult(
        "reference_match", False, pid_token_raw, settlement.utr_reference, None, "REFERENCE_NOT_FOUND"
    )


def amount_balance_constraint(payment: Payment, observed_amount: Decimal | None) -> ConstraintResult:
    if observed_amount is None:
        return ConstraintResult("amount_balance", False, str(payment.amount), None, None, "NO_CONFIRMED_AMOUNT")
    delta = (payment.amount - observed_amount).copy_abs()
    passed = delta == Decimal("0.00")
    return ConstraintResult(
        "amount_balance", passed, str(payment.amount), str(observed_amount), str(delta),
        None if passed else "AMOUNT_RESIDUAL",
    )


def fee_rule_constraint(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> ConstraintResult:
    fee_check = verify_fee_consistency(payment, settlement, context)
    if fee_check is None:
        return ConstraintResult("fee_rule", True, None, None, None, "NO_FEE_RULE_APPLICABLE")
    return ConstraintResult(
        "fee_rule", fee_check.consistent, str(fee_check.expected_net), str(fee_check.actual_net),
        str(fee_check.delta), None if fee_check.consistent else "FEE_RULE_RESIDUAL",
    )


def refund_balance_constraint(payment: Payment, context: ReconciliationContext) -> ConstraintResult:
    refund_check = verify_refund_consistency(payment, context)
    if refund_check is None:
        return ConstraintResult("refund_balance", True, None, None, None, "NO_REFUND_ON_RECORD")
    return ConstraintResult(
        "refund_balance", refund_check.consistent, "0.00", str(refund_check.unexplained_delta),
        str(refund_check.unexplained_delta), None if refund_check.consistent else "REFUND_RESIDUAL",
    )


def settlement_window_constraint(payment: Payment, settlement: Settlement, *, lenient: bool = True) -> ConstraintResult:
    delta_days = abs((settlement.settled_at.date() - payment.captured_at.date()).days)
    tolerance = LENIENT_DATE_TOLERANCE_DAYS if lenient else TIGHT_DATE_TOLERANCE_DAYS
    passed = delta_days <= tolerance
    return ConstraintResult(
        "settlement_window", passed, f"<= {tolerance}d", f"{delta_days}d", str(delta_days - tolerance),
        None if passed else "SETTLEMENT_WINDOW_VIOLATION",
    )


def currency_match_constraint(payment: Payment, settlement: Settlement) -> ConstraintResult:
    passed = payment.currency == settlement.currency
    return ConstraintResult(
        "currency_match", passed, payment.currency, settlement.currency, None,
        None if passed else "CURRENCY_MISMATCH",
    )


def relationship_consistency_constraint(settlement: Settlement) -> ConstraintResult:
    self_check = verify_settlement_self_consistency(settlement)
    return ConstraintResult(
        "relationship_consistency", self_check.consistent, str(self_check.computed_net), str(self_check.stated_net),
        str(self_check.delta), None if self_check.consistent else "SETTLEMENT_SELF_INCONSISTENT",
    )


def duplicate_check_constraint(settlement: Settlement, sibling_settlement_ids: list[str]) -> ConstraintResult:
    passed = len(sibling_settlement_ids) == 0
    return ConstraintResult(
        "duplicate_check", passed, "1 settlement", f"{len(sibling_settlement_ids) + 1} settlements", None,
        None if passed else "DUPLICATE_SETTLEMENT_CANDIDATES",
    )


def aggregation_balance_constraint(target: Decimal, component_amounts: list[Decimal]) -> ConstraintResult:
    total = sum(component_amounts, Decimal("0.00"))
    delta = (target - total).copy_abs()
    passed = delta == Decimal("0.00")
    return ConstraintResult(
        "aggregation_balance", passed, str(target), str(total), str(delta),
        None if passed else "AGGREGATION_RESIDUAL",
    )


def evaluate_all_constraints(payment: Payment, settlement: Settlement, context: ReconciliationContext, observed_amount: Decimal | None) -> list[ConstraintResult]:
    """Runs the full constraint battery for one (payment, settlement)
    candidate pair -- this is what the "Why NOT Matched" engine
    (evidence/candidates.py) runs per candidate, not just a single field."""
    return [
        currency_match_constraint(payment, settlement),
        reference_match_constraint(payment, settlement),
        amount_balance_constraint(payment, observed_amount),
        settlement_window_constraint(payment, settlement),
        fee_rule_constraint(payment, settlement, context),
        refund_balance_constraint(payment, context),
        relationship_consistency_constraint(settlement),
    ]
