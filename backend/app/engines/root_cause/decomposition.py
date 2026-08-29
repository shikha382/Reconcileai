"""Discrepancy decomposition: for every amount mismatch, don't just compute
`difference = expected - observed` -- attempt to explain the difference as
the sum of known, verifiable deductions (refund, fee+tax), and report
whatever residual is left over. Decimal throughout; never float.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.db.models import Payment, Settlement
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.verification import (
    bank_credited_amount,
    verify_fee_consistency,
    verify_refund_consistency,
)


@dataclass
class DecompositionResult:
    expected: Decimal
    observed: Decimal
    difference: Decimal  # expected - observed, signed
    components: dict[str, Decimal] = field(default_factory=dict)  # {"refund": ..., "fee": ..., "tax": ...}
    residual: Decimal = Decimal("0.00")
    fully_explained: bool = False

    def to_dict(self) -> dict:
        return {
            "expected": str(self.expected), "observed": str(self.observed), "difference": str(self.difference),
            "components": {k: str(v) for k, v in self.components.items()},
            "residual": str(self.residual), "fully_explained": self.fully_explained,
        }


def decompose_discrepancy(payment: Payment, settlement: Settlement | None, context: ReconciliationContext) -> DecompositionResult:
    """expected = payment.amount. observed = the confirmed bank-credited
    amount for `settlement`, if any. Known deduction components (refund
    total, fee+tax per the applicable FeeRule) are subtracted from expected;
    whatever is left after that is the residual.

    Known limitation: refund and fee are verified independently and summed
    additively. This is correct for every case in M1's actual dataset
    (refund_mismatch always has zero fee; fee_mismatch always has zero
    refund), but a record with BOTH a genuine settlement-level fee
    deduction AND a payment-level refund (a separate, later bank debit) at
    once has not been validated end-to-end -- see
    backend/tests/exceptions/test_hypotheses_and_decomposition.py's
    docstring for the specific arithmetic tension (the refund's debit isn't
    netted into `observed`, which is credit-only) and CLAUDE.md's M3 entry.
    """
    expected = payment.amount
    observed = bank_credited_amount(settlement, context) if settlement is not None else None
    if observed is None:
        observed = Decimal("0.00")

    difference = expected - observed
    components: dict[str, Decimal] = {}

    refund_check = verify_refund_consistency(payment, context)
    refund_total = Decimal("0.00")
    if refund_check is not None:
        # verify_refund_consistency reports the UNEXPLAINED delta; the
        # explained portion is refund total minus that unexplained residual.
        from app.db.models import Refund

        refunds: list[Refund] = context.refunds_by_payment_id.get(payment.payment_id, [])
        refund_total = sum((r.amount for r in refunds), Decimal("0.00"))
        components["refund"] = refund_total - refund_check.unexplained_delta

    fee_total = Decimal("0.00")
    if settlement is not None:
        fee_check = verify_fee_consistency(payment, settlement, context)
        if fee_check is not None and fee_check.consistent:
            fee_total = fee_check.expected_fee + fee_check.expected_tax
            components["fee_and_tax"] = fee_total

    explained = sum(components.values(), Decimal("0.00"))
    residual = (difference - explained).copy_abs()
    fully_explained = residual == Decimal("0.00")

    return DecompositionResult(
        expected=expected, observed=observed, difference=difference,
        components=components, residual=residual, fully_explained=fully_explained,
    )
