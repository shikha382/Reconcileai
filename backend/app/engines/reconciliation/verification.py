"""Stage 3: deterministic financial consistency checks. Decimal only, never
float. Every function here answers one narrow, checkable financial question
and returns a small typed result carrying its own reasoning -- these are the
building blocks matching.py composes into a final status, and the exact
functions the M1 adversarial fee_mismatch cases must fail.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.models import Payment, Refund, Settlement
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.config import FEE_VERIFICATION_TOLERANCE


@dataclass
class FeeCheckResult:
    consistent: bool
    expected_fee: Decimal
    expected_tax: Decimal
    expected_net: Decimal
    actual_net: Decimal
    delta: Decimal
    rule_id: str


def verify_fee_consistency(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> FeeCheckResult | None:
    """Recomputes settlement.net_amount from the payment's applicable
    FeeRule, using Decimal throughout, and compares it against what the
    settlement actually claims. Returns None if there's no applicable fee
    rule for this method (nothing to verify) or if net_amount already equals
    the gross amount exactly (no fee gap exists to explain in the first
    place). This NEVER trusts a natural-language explanation of "there was a
    fee" -- it recomputes the exact number and compares it, which is
    precisely what catches the M1 adversarial fee_mismatch cases: their
    net_amount does not match this computation, by design.
    """
    rule = context.fee_rule_by_method.get(payment.method)
    if rule is None:
        return None
    if settlement.net_amount == settlement.amount:
        return None

    expected_fee = (settlement.amount * rule.mdr_percent + rule.fixed_fee).quantize(Decimal("0.01"))
    expected_tax = (expected_fee * rule.tax_percent).quantize(Decimal("0.01"))
    expected_net = (settlement.amount - expected_fee - expected_tax).quantize(Decimal("0.01"))

    delta = (settlement.net_amount - expected_net).copy_abs()
    consistent = delta <= FEE_VERIFICATION_TOLERANCE

    return FeeCheckResult(
        consistent=consistent,
        expected_fee=expected_fee,
        expected_tax=expected_tax,
        expected_net=expected_net,
        actual_net=settlement.net_amount,
        delta=delta,
        rule_id=rule.fee_rule_id,
    )


@dataclass
class RefundCheckResult:
    refund_ids: list[str]
    debit_bank_txn_ids: list[str]
    consistent: bool
    unexplained_delta: Decimal


def verify_refund_consistency(payment: Payment, context: ReconciliationContext) -> RefundCheckResult | None:
    """If refunds exist for this payment, checks that each refund's amount
    is matched by an equal-amount DEBIT bank transaction. Returns None if no
    refunds exist for this payment at all (nothing to check).

    Each debit transaction can be claimed as evidence by AT MOST ONE refund
    -- `claimed_debit_ids` tracks this across the loop so two refund records
    (e.g. a duplicated/replayed refund row) can never both cite the SAME
    single real debit as if it independently backed each of them. Found via
    the M9 adversarial evaluation's duplicate-refund scenario: without this,
    a duplicated refund record could make `decompose_discrepancy`'s reported
    residual/`fully_explained` look more complete than the real bank
    evidence actually supports -- a real explainability defect (the
    downstream M2 status/policy gate never promotes to VERIFIED from this
    alone, so no unsafe auto-resolution was possible, but the reported
    residual number itself was simply wrong).
    """
    refunds: list[Refund] = context.refunds_by_payment_id.get(payment.payment_id, [])
    if not refunds:
        return None

    all_debits = [b for b in context.bank_transactions if b.direction == "debit"]
    refund_ids: list[str] = []
    debit_ids: list[str] = []
    unexplained = Decimal("0.00")
    claimed_debit_ids: set[str] = set()

    for refund in refunds:
        refund_ids.append(refund.refund_id)
        matching_debit = next(
            (b for b in all_debits
             if b.amount == refund.amount and b.currency == refund.currency and b.bank_txn_id not in claimed_debit_ids),
            None,
        )
        if matching_debit is not None:
            debit_ids.append(matching_debit.bank_txn_id)
            claimed_debit_ids.add(matching_debit.bank_txn_id)
        else:
            unexplained += refund.amount

    return RefundCheckResult(
        refund_ids=refund_ids,
        debit_bank_txn_ids=debit_ids,
        consistent=(unexplained == Decimal("0.00")),
        unexplained_delta=unexplained,
    )


@dataclass
class SettlementSelfConsistencyResult:
    consistent: bool
    stated_net: Decimal
    computed_net: Decimal
    delta: Decimal


def verify_settlement_self_consistency(settlement: Settlement) -> SettlementSelfConsistencyResult:
    """Checks the settlement record's OWN arithmetic: does its stated
    net_amount actually equal amount - fee - tax, using ONLY the figures the
    settlement itself claims (no external FeeRule lookup)? A settlement that
    fails this check has an internal data-integrity problem distinct from
    "the fee doesn't match the rule" -- see data/synthetic/README.md's
    documented distinction between `unexplained_difference` (fails THIS
    check) and `under_settlement` (passes this check, just short relative to
    the payment, per the M1 dataset design)."""
    computed_net = (settlement.amount - settlement.fee - settlement.tax).quantize(Decimal("0.01"))
    delta = (settlement.net_amount - computed_net).copy_abs()
    return SettlementSelfConsistencyResult(
        consistent=(delta <= FEE_VERIFICATION_TOLERANCE),
        stated_net=settlement.net_amount,
        computed_net=computed_net,
        delta=delta,
    )


def bank_credited_amount(settlement: Settlement, context: ReconciliationContext) -> Decimal | None:
    """The actual amount a CREDIT bank transaction confirms was received for
    this settlement, or None if no confirmed credit exists yet. This --not
    settlement.amount or settlement.net_amount alone-- is the figure that
    must ultimately reconcile against payment.amount (net of any verified
    fee), because it's the one number in this dataset that represents money
    that has actually, confirmedly moved."""
    credits = [b for b in context.bank_txns_by_settlement_id.get(settlement.settlement_id, []) if b.direction == "credit"]
    if not credits:
        return None
    return sum((b.amount for b in credits), Decimal("0.00"))
