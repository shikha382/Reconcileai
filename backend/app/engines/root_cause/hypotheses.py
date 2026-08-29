"""Deterministic counterfactual hypothesis testing (H1-H5). NOT an AI
hypothesis -- every one of these is a fixed, hand-written deterministic
check. This is the evidence layer a future LLM-based agent will reason over
(AI PROPOSES -> DETERMINISTIC EVIDENCE CHECKS IT), not something that itself
calls a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import uuid4

from app.db.models import Payment, Settlement
from app.engines.evidence.constraints import ConstraintResult, settlement_window_constraint
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.verification import (
    bank_credited_amount,
    verify_fee_consistency,
    verify_refund_consistency,
)


@dataclass
class HypothesisResult:
    hypothesis_id: str
    hypothesis_type: str
    inputs: dict
    expected_value: Decimal | None
    observed_value: Decimal | None
    residual: Decimal | None
    constraints: list[ConstraintResult] = field(default_factory=list)
    status: str = "REJECTED"  # "VERIFIED" | "REJECTED"
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id, "hypothesis_type": self.hypothesis_type, "inputs": self.inputs,
            "expected_value": str(self.expected_value) if self.expected_value is not None else None,
            "observed_value": str(self.observed_value) if self.observed_value is not None else None,
            "residual": str(self.residual) if self.residual is not None else None,
            "constraints": [c.to_dict() for c in self.constraints], "status": self.status,
            "evidence_ids": self.evidence_ids,
        }


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def test_refund_hypothesis(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> HypothesisResult:
    """H1: 'This is explained by a refund.' expected_settlement = payment -
    refund - valid_fees. If equality holds: VERIFIED."""
    refund_check = verify_refund_consistency(payment, context)
    observed = bank_credited_amount(settlement, context)
    fee_check = verify_fee_consistency(payment, settlement, context)
    fee_amount = (fee_check.expected_fee + fee_check.expected_tax) if (fee_check and fee_check.consistent) else Decimal("0.00")

    if refund_check is None or observed is None:
        return HypothesisResult(_new_id("H1"), "refund", {"payment_id": payment.payment_id}, None, observed, None, status="REJECTED")

    from app.db.models import Refund

    refunds: list[Refund] = context.refunds_by_payment_id.get(payment.payment_id, [])
    refund_total = sum((r.amount for r in refunds), Decimal("0.00"))
    expected = payment.amount - refund_total - fee_amount
    residual = (expected - observed).copy_abs()
    status = "VERIFIED" if residual == Decimal("0.00") else "REJECTED"

    return HypothesisResult(
        _new_id("H1"), "refund",
        {"payment_amount": str(payment.amount), "refund_total": str(refund_total), "fee_amount": str(fee_amount)},
        expected, observed, residual, status=status, evidence_ids=[r.refund_id for r in refunds],
    )


def test_fee_hypothesis(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> HypothesisResult:
    """H2: 'This is explained by a fee.' Runs the exact fee rule via M2's
    verify_fee_consistency -- the same function that rejects the M1
    adversarial fee_mismatch cases."""
    fee_check = verify_fee_consistency(payment, settlement, context)
    if fee_check is None:
        return HypothesisResult(_new_id("H2"), "fee_mismatch", {"method": payment.method}, None, None, None, status="REJECTED")

    status = "VERIFIED" if fee_check.consistent else "REJECTED"
    return HypothesisResult(
        _new_id("H2"), "fee_mismatch",
        {"method": payment.method, "rule_id": fee_check.rule_id},
        fee_check.expected_net, fee_check.actual_net, fee_check.delta,
        status=status, evidence_ids=[fee_check.rule_id],
    )


def test_timing_hypothesis(payment: Payment, settlement: Settlement) -> HypothesisResult:
    """H3: 'This is explained by a timing delay.' Checks the configured
    settlement window (M2's LENIENT_DATE_TOLERANCE_DAYS)."""
    window = settlement_window_constraint(payment, settlement, lenient=True)
    status = "VERIFIED" if window.passed else "REJECTED"
    return HypothesisResult(
        _new_id("H3"), "timing_delay",
        {"payment_captured_at": payment.captured_at.isoformat(), "settlement_settled_at": settlement.settled_at.isoformat()},
        None, None, None, constraints=[window], status=status,
    )


def test_duplicate_hypothesis(payment: Payment, sibling_settlements: list[Settlement]) -> HypothesisResult:
    """H4: 'This is a duplicate.' More than one settlement genuinely linked
    to the same payment, with amounts that don't form a valid split (that's
    H5's job) -- itself is the positive signal for this hypothesis."""
    status = "VERIFIED" if len(sibling_settlements) >= 1 else "REJECTED"
    return HypothesisResult(
        _new_id("H4"), "duplicate",
        {"payment_id": payment.payment_id, "sibling_count": len(sibling_settlements)},
        None, None, None, status=status,
        evidence_ids=[s.settlement_id for s in sibling_settlements],
    )


def test_aggregation_hypothesis(candidate_payments: list[Payment], settlement: Settlement, context: ReconciliationContext) -> HypothesisResult:
    """H5: 'This is an aggregation.' sum(candidate transactions) ==
    settlement amount after valid deductions."""
    observed = bank_credited_amount(settlement, context)
    target = observed if observed is not None else settlement.amount
    total = sum((p.amount for p in candidate_payments), Decimal("0.00"))
    residual = (target - total).copy_abs()
    status = "VERIFIED" if residual == Decimal("0.00") and len(candidate_payments) >= 2 else "REJECTED"
    return HypothesisResult(
        _new_id("H5"), "aggregation",
        {"settlement_id": settlement.settlement_id, "candidate_count": len(candidate_payments)},
        target, total, residual, status=status,
        evidence_ids=[p.payment_id for p in candidate_payments],
    )


def run_all_hypotheses(
    payment: Payment, settlement: Settlement | None, context: ReconciliationContext,
    sibling_settlements: list[Settlement] | None = None,
) -> list[HypothesisResult]:
    """Runs every applicable hypothesis given what evidence is actually
    available (no settlement -> only what can be tested without one)."""
    results: list[HypothesisResult] = []
    if settlement is not None:
        results.append(test_refund_hypothesis(payment, settlement, context))
        results.append(test_fee_hypothesis(payment, settlement, context))
        results.append(test_timing_hypothesis(payment, settlement))
    if sibling_settlements:
        results.append(test_duplicate_hypothesis(payment, sibling_settlements))
    return results
