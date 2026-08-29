"""Financial exposure and risk-priority scoring.

The project's own documented intent (RECONCILEAI_CONTEXT_PACK.md's Value-at-
Risk prioritization, PROJECT_PLAN.md's M15) names amount, confidence,
severity/frequency, and business impact as the inputs -- but does not fix an
exact formula. Per the M3 brief's own instruction ("do not hard-code a
made-up business metric without documenting it"), the formula used here is
made explicit and named:

    risk_score = |financial_delta| x confidence_deficit x sla_aging_factor

- confidence_deficit in [0, 1]: 0 for a fully-verified MATCHED result (no
  risk left), rising for statuses where less is actually known about
  whether the exception is safe.
- sla_aging_factor in [1.0, 2.0]: how long the record has been outstanding
  relative to the dataset's own latest record (a synthetic batch has no real
  "now", so the latest captured_at in the batch stands in for it), linearly
  scaled and capped at 30 days so a single very old record can't dominate
  the ranking unboundedly.

This deliberately keeps financial amount from being the sole determinant: a
Rs 50 issue with a confidently-diagnosed cause should not automatically
outrank a Rs 5,00,000 issue just because it's newer, and vice versa -- see
backend/tests/exceptions/test_risk.py for a case exercising exactly this.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.db.models import Payment
from app.engines.root_cause.result import (
    AMBIGUOUS,
    CONTRADICTED,
    PARTIALLY_EXPLAINED,
    UNEXPLAINED,
    VERIFIED,
    RootCauseResult,
)
MAX_AGING_DAYS = 30

_CONFIDENCE_DEFICIT_BY_STATUS = {
    VERIFIED: Decimal("0.00"),
    PARTIALLY_EXPLAINED: Decimal("0.40"),
    CONTRADICTED: Decimal("0.60"),
    AMBIGUOUS: Decimal("0.80"),
    UNEXPLAINED: Decimal("1.00"),
}


@dataclass
class FinancialExposure:
    gross_amount: Decimal
    expected_amount: Decimal
    observed_amount: Decimal
    explained_amount: Decimal
    unexplained_amount: Decimal
    currency: str

    def to_dict(self) -> dict:
        return {
            "gross_amount": str(self.gross_amount), "expected_amount": str(self.expected_amount),
            "observed_amount": str(self.observed_amount), "explained_amount": str(self.explained_amount),
            "unexplained_amount": str(self.unexplained_amount), "currency": self.currency,
        }


def build_financial_exposure(payment: Payment, root_cause: RootCauseResult, actual_observed_amount: Decimal | None = None) -> FinancialExposure:
    # Prefer the ACTUAL bank-confirmed amount when the caller has one (avoids
    # a derived figure that could read inconsistently next to a constraint's
    # own expected/observed pair in the same narrative); fall back to
    # (expected - unexplained) only when nothing was observed at all (e.g. no
    # settlement/candidate exists for this payment).
    observed = actual_observed_amount if actual_observed_amount is not None else (payment.amount - root_cause.unexplained_amount)
    return FinancialExposure(
        gross_amount=payment.amount, expected_amount=payment.amount, observed_amount=observed,
        explained_amount=root_cause.explained_amount, unexplained_amount=root_cause.unexplained_amount,
        currency=payment.currency,
    )


def confidence_deficit_for(root_cause: RootCauseResult) -> Decimal:
    return _CONFIDENCE_DEFICIT_BY_STATUS.get(root_cause.status, Decimal("1.00"))


def sla_aging_factor(payment: Payment, reference_now: datetime) -> Decimal:
    aging_days = max((reference_now.date() - payment.captured_at.date()).days, 0)
    capped = min(aging_days, MAX_AGING_DAYS)
    return (Decimal("1.00") + Decimal(capped) / Decimal(MAX_AGING_DAYS)).quantize(Decimal("0.0001"))


def compute_risk_score(payment: Payment, root_cause: RootCauseResult, reference_now: datetime) -> Decimal:
    deficit = confidence_deficit_for(root_cause)
    aging = sla_aging_factor(payment, reference_now)
    amount_at_risk = root_cause.unexplained_amount if root_cause.status != VERIFIED else Decimal("0.00")
    return (amount_at_risk * deficit * aging).quantize(Decimal("0.01"))
