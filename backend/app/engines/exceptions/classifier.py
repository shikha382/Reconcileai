"""Exception classification into the CANONICAL taxonomy already established
in M1 (shared.taxonomy.ExceptionCategory) -- no second taxonomy is created
here. A record can carry a category even when M2 successfully auto-resolved
it (e.g. `fee_mismatch` + status=MATCHED is a normal, safely-explained
outcome): category describes WHAT kind of discrepancy occurred, which is
independent of whether it needed human review (that's M2's `status`).

Note on scope: this doubles as PROJECT_PLAN.md's originally-planned M5
("category-level exception taxonomy"), pulled forward into M3 at the user's
explicit direction -- see CLAUDE.md's M3 architectural decision.

One category in the M3 brief's own example list -- "currency mismatch" --
has no corresponding value in M1's canonical ExceptionCategory enum. Per
explicit instruction not to invent a second taxonomy, currency-mismatch
records are classified as `unexplained_difference` (the closest existing
fit: a genuine data inconsistency with no dedicated category) and this
mapping is called out explicitly wherever it's used, not silently applied.
"""
from __future__ import annotations

from decimal import Decimal

from app.db.models import Payment, Settlement
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.types import ReconciliationResult
from shared.taxonomy import ExceptionCategory, ReconciliationStatus

_MATCHED_METHOD_TO_CATEGORY: dict[str, ExceptionCategory | None] = {
    "exact_reference": None,
    "normalized_reference": None,
    "fee_verified": ExceptionCategory.FEE_MISMATCH,
    "split_settlement_sum": ExceptionCategory.SPLIT_SETTLEMENT,
    "aggregated_settlement_sum": ExceptionCategory.AGGREGATED_SETTLEMENT,
    "candidate_scoring": ExceptionCategory.REFERENCE_MISMATCH,
}


def classify_exception(
    payment: Payment, settlement: Settlement | None, m2_result: ReconciliationResult, context: ReconciliationContext,
) -> ExceptionCategory | None:
    """Returns None for a genuinely clean match (not an exception at all);
    otherwise the single best-fitting ExceptionCategory. Re-derives the
    same signals M2's own matching.py used (date delta, reference
    containment) rather than parsing M2's evidence strings, so this stays
    correct even if M2's wording ever changes."""
    if m2_result.status == ReconciliationStatus.MATCHED:
        # Refund evidence takes priority over the underlying match method:
        # a cleanly-matched settlement that also has a consistent refund on
        # record (refund_mismatch archetype) is still a refund story, not a
        # plain exact/normalized match, even though M2 resolved the
        # payment<->settlement pair via exact_reference/normalized_reference.
        if context.refunds_by_payment_id.get(payment.payment_id):
            return ExceptionCategory.REFUND_MISMATCH
        if m2_result.method == "financial_consistency" and settlement is not None:
            # Disambiguate the one method M2 uses for two different
            # archetypes: date exceeded the tight window (timing_mismatch)
            # vs. reference genuinely didn't match within the tight window
            # (reference_mismatch). Both pass via the same code path in
            # matching.py; the classifier re-derives which one actually
            # happened using the same primitives matching.py itself uses.
            from app.engines.reconciliation.config import TIGHT_DATE_TOLERANCE_DAYS
            from app.engines.reconciliation.matching import _date_delta_days, _reference_evidence

            delta_days = _date_delta_days(settlement, payment)
            _, normalized_ref_match = _reference_evidence(payment, settlement)
            if delta_days > TIGHT_DATE_TOLERANCE_DAYS:
                return ExceptionCategory.TIMING_MISMATCH
            if not normalized_ref_match:
                return ExceptionCategory.REFERENCE_MISMATCH
            return ExceptionCategory.TIMING_MISMATCH
        return _MATCHED_METHOD_TO_CATEGORY.get(m2_result.method)

    if m2_result.status == ReconciliationStatus.PARTIAL:
        # M1's dataset does not encode a structural difference between
        # "partial_settlement" (more is genuinely expected later) and
        # "under_settlement" (a smaller, likely-final shortfall) -- both are
        # a single settlement covering less than the payment, zero-fee,
        # confirmed by bank credit. The only real signal available is
        # magnitude: data/synthetic/generator.py's partial_settlement cases
        # cover 55-75% of the payment (25-45% shortfall) while its
        # under_settlement cases cover 92-96% (4-8% shortfall) -- a clean,
        # non-overlapping gap. 85% is used as the dividing line, documented
        # here rather than silently guessed. See CLAUDE.md's M3 decision.
        from app.engines.reconciliation.verification import bank_credited_amount

        observed = bank_credited_amount(settlement, context) if settlement is not None else None
        if observed is not None and payment.amount > 0 and (observed / payment.amount) >= Decimal("0.85"):
            return ExceptionCategory.UNDER_SETTLEMENT
        return ExceptionCategory.PARTIAL_SETTLEMENT

    if m2_result.status == ReconciliationStatus.AMBIGUOUS:
        linked = context.settlements_by_payment_id.get(payment.payment_id, [])
        if len(linked) > 1:
            return ExceptionCategory.DUPLICATE
        return ExceptionCategory.AMBIGUOUS_MATCH

    if m2_result.status == ReconciliationStatus.UNRESOLVED:
        return ExceptionCategory.MISSING_TRANSACTION

    # MISMATCH
    if settlement is not None and settlement.status == "reversed":
        return ExceptionCategory.REVERSED_TRANSACTION
    if settlement is not None and payment.currency != settlement.currency:
        # No dedicated "currency_mismatch" value exists in M1's taxonomy --
        # mapped explicitly to the closest existing category rather than
        # inventing a new one (see module docstring).
        return ExceptionCategory.UNEXPLAINED_DIFFERENCE
    if settlement is not None:
        from app.engines.reconciliation.verification import bank_credited_amount, verify_fee_consistency, verify_settlement_self_consistency

        observed = bank_credited_amount(settlement, context)
        fee_check = verify_fee_consistency(payment, settlement, context)
        rule = context.fee_rule_by_method.get(payment.method)
        # A failing fee_check only means "fee_mismatch" if the applicable
        # rule actually prescribes a non-trivial deduction (e.g. card MDR).
        # Under a zero-rate rule (UPI in this dataset), fee_check "fails"
        # for exactly the same arithmetic reason relationship_consistency
        # does (both derive the same expected value from a zero fee), which
        # would otherwise misclassify unexplained_difference cases as
        # fee_mismatch. See CLAUDE.md's M3 decision.
        rule_is_nontrivial = rule is not None and (rule.mdr_percent > 0 or rule.fixed_fee > 0)
        if fee_check is not None and not fee_check.consistent and rule_is_nontrivial:
            return ExceptionCategory.FEE_MISMATCH
        refund_check_flag = bool(context.refunds_by_payment_id.get(payment.payment_id))
        if refund_check_flag:
            return ExceptionCategory.REFUND_MISMATCH
        self_check = verify_settlement_self_consistency(settlement)
        if not self_check.consistent:
            return ExceptionCategory.UNEXPLAINED_DIFFERENCE
        if observed is not None and observed > payment.amount:
            return ExceptionCategory.OVER_SETTLEMENT
        if observed is not None and observed < payment.amount:
            return ExceptionCategory.UNDER_SETTLEMENT
    return ExceptionCategory.UNEXPLAINED_DIFFERENCE
