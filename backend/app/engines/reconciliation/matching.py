"""Stages 1-3 for the common case: exactly one settlement is directly linked
to a payment (via settlement.payment_id). Multiple-linked-settlement and
zero-linked-settlement cases are relationships.py's job (splits,
aggregations, and candidate-scored/ambiguous cases) -- kept separate per the
project's file-size/separation-of-concerns rule.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.models import Payment, Settlement
from app.engines.normalization import normalize_reference
from app.engines.reconciliation import explanation
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.config import (
    ENGINE_VERSION,
    LENIENT_DATE_TOLERANCE_DAYS,
    TIGHT_DATE_TOLERANCE_DAYS,
)
from app.engines.reconciliation.types import ReconciliationResult
from app.engines.reconciliation.verification import (
    bank_credited_amount,
    verify_fee_consistency,
    verify_refund_consistency,
    verify_settlement_self_consistency,
)
from shared.taxonomy import ReconciliationStatus, RelationshipType


def _date_delta_days(settlement: Settlement, payment: Payment) -> int:
    return abs((settlement.settled_at.date() - payment.captured_at.date()).days)


def _reference_evidence(payment: Payment, settlement: Settlement) -> tuple[bool, bool]:
    """(raw_exact, normalized_match): whether the settlement's reference
    contains this payment's id token, checked both on the untouched raw
    string (must be a literal, contiguous substring) and on the normalized
    string (whitespace/case/punctuation-insensitive). See
    data/synthetic/generator.py's `messify()` -- this is precisely the
    distinction that separates a clean exact_match from a messified one."""
    pid_token_raw = payment.payment_id.replace("-", "")
    raw_exact = pid_token_raw in settlement.utr_reference
    normalized_match = normalize_reference(payment.payment_id) in normalize_reference(settlement.utr_reference)
    return raw_exact, normalized_match


def _apply_refund_enrichment(result: ReconciliationResult, payment: Payment, context: ReconciliationContext) -> ReconciliationResult:
    refund_check = verify_refund_consistency(payment, context)
    line = explanation.refund_line(refund_check)
    if line is None:
        return result
    if refund_check.consistent:
        result.why_matched.append(line)
        result.matched_refund_ids = refund_check.refund_ids
    else:
        # Safety override: an unexplained refund conflict is never silently
        # left inside a MATCHED result, regardless of what stages 1-3 found.
        result.why_not_matched.append(line)
        result.differences.append(line)
        result.status = ReconciliationStatus.MISMATCH
        result.financial_impact += refund_check.unexplained_delta
    return result


def resolve_single_linked_settlement(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> ReconciliationResult:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Deliberately excludes matched_bank_txn_ids -- some branches below have
    # a confirmed credit to report, others don't, so each passes it
    # explicitly rather than relying on (and sometimes colliding with) a
    # shared default.
    base = dict(
        reconciliation_id=str(uuid4()),
        payment_id=payment.payment_id,
        order_id=payment.order_id,
        matched_refund_ids=[],
        candidates=[],
        created_at=now,
        engine_version=ENGINE_VERSION,
        relationship=RelationshipType.ONE_TO_ONE,
    )

    currency_ok = payment.currency == settlement.currency
    currency_line = explanation.currency_line(currency_ok, payment.currency, settlement.currency)
    if not currency_ok:
        result = ReconciliationResult(
            **base, status=ReconciliationStatus.MISMATCH, method="currency_mismatch",
            matched_settlement_ids=[settlement.settlement_id], matched_bank_txn_ids=[], score=None,
            why_matched=[], why_not_matched=[currency_line], differences=[currency_line],
            financial_impact=payment.amount,
        )
        return _apply_refund_enrichment(result, payment, context)

    if settlement.status == "reversed":
        result = ReconciliationResult(
            **base, status=ReconciliationStatus.MISMATCH, method="none",
            matched_settlement_ids=[settlement.settlement_id],
            matched_bank_txn_ids=[b.bank_txn_id for b in context.bank_txns_by_settlement_id.get(settlement.settlement_id, [])],
            score=None,
            why_matched=[currency_line],
            why_not_matched=["✗ settlement status is 'reversed' -- the credit was reversed by an equal debit and requires human confirmation of cause"],
            differences=["settlement reversed"], financial_impact=payment.amount,
        )
        return _apply_refund_enrichment(result, payment, context)

    bank_amount = bank_credited_amount(settlement, context)
    raw_ref_exact, normalized_ref_match = _reference_evidence(payment, settlement)
    delta_days = _date_delta_days(settlement, payment)
    tight_ok = delta_days <= TIGHT_DATE_TOLERANCE_DAYS
    lenient_ok = delta_days <= LENIENT_DATE_TOLERANCE_DAYS

    ref_line_exact = explanation.reference_line(raw_ref_exact, "exact")
    ref_line_norm = explanation.reference_line(normalized_ref_match, "normalized")
    date_line = explanation.date_line(tight_ok, delta_days, TIGHT_DATE_TOLERANCE_DAYS)
    date_line_lenient = explanation.date_line(lenient_ok, delta_days, LENIENT_DATE_TOLERANCE_DAYS)

    if bank_amount is None:
        result = ReconciliationResult(
            **base, status=ReconciliationStatus.UNRESOLVED, method="none",
            matched_settlement_ids=[settlement.settlement_id], matched_bank_txn_ids=[], score=None,
            why_matched=[currency_line],
            why_not_matched=["✗ no confirmed bank credit exists yet for this settlement"],
            differences=["no confirmed bank credit yet"], financial_impact=payment.amount,
        )
        return _apply_refund_enrichment(result, payment, context)

    amount_exact = bank_amount == payment.amount
    amount_line = explanation.amount_line(amount_exact, payment.amount, bank_amount)

    if amount_exact:
        if raw_ref_exact and tight_ok:
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.MATCHED, method="exact_reference",
                matched_settlement_ids=[settlement.settlement_id],
                matched_bank_txn_ids=[b.bank_txn_id for b in context.bank_txns_by_settlement_id.get(settlement.settlement_id, []) if b.direction == "credit"],
                score=Decimal("1.00"),
                why_matched=[currency_line, ref_line_exact, amount_line, date_line],
                why_not_matched=[], differences=[], financial_impact=Decimal("0.00"),
            )
        elif normalized_ref_match and tight_ok:
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.MATCHED, method="normalized_reference",
                matched_settlement_ids=[settlement.settlement_id],
                matched_bank_txn_ids=[b.bank_txn_id for b in context.bank_txns_by_settlement_id.get(settlement.settlement_id, []) if b.direction == "credit"],
                score=Decimal("0.98"),
                why_matched=[currency_line, ref_line_norm, amount_line, date_line],
                why_not_matched=[], differences=[], financial_impact=Decimal("0.00"),
            )
        elif lenient_ok:
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.MATCHED, method="financial_consistency",
                matched_settlement_ids=[settlement.settlement_id],
                matched_bank_txn_ids=[b.bank_txn_id for b in context.bank_txns_by_settlement_id.get(settlement.settlement_id, []) if b.direction == "credit"],
                score=Decimal("0.90"),
                why_matched=[currency_line, amount_line, date_line_lenient],
                why_not_matched=[ref_line_norm] if not normalized_ref_match else [],
                differences=[], financial_impact=Decimal("0.00"),
            )
        else:
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.MISMATCH, method="none",
                matched_settlement_ids=[settlement.settlement_id], matched_bank_txn_ids=[], score=None,
                why_matched=[currency_line, amount_line],
                why_not_matched=[date_line_lenient],
                differences=[date_line_lenient], financial_impact=Decimal("0.00"),
            )
        return _apply_refund_enrichment(result, payment, context)

    # Amounts differ -- check whether a fee rule explains the gap.
    fee_check = verify_fee_consistency(payment, settlement, context)
    fee_line = explanation.fee_line(fee_check)

    if fee_check is not None:
        # `fee_check.consistent` only proves the settlement's OWN claimed
        # fields (amount/fee/tax/net_amount) are internally, mathematically
        # consistent with the configured FeeRule -- it says nothing about
        # whether the money that was ACTUALLY, confirmedly credited
        # (`bank_amount`) matches that claimed net figure. Trusting
        # fee-math self-consistency alone would let a settlement whose
        # fee arithmetic is correct on paper, but whose real bank credit
        # was separately altered/shortchanged, still verify as MATCHED with
        # financial_impact=0.00 -- found via M9's seeded fuzz testing
        # (backend/tests/adversarial/test_fuzz.py), a genuine false
        # auto-resolution, not a theoretical one.
        bank_amount_matches_net = bank_amount == settlement.net_amount
        if fee_check.consistent and lenient_ok and bank_amount_matches_net:
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.MATCHED, method="fee_verified",
                matched_settlement_ids=[settlement.settlement_id],
                matched_bank_txn_ids=[b.bank_txn_id for b in context.bank_txns_by_settlement_id.get(settlement.settlement_id, []) if b.direction == "credit"],
                score=Decimal("0.95"),
                why_matched=[currency_line, fee_line, date_line_lenient],
                why_not_matched=[], differences=[], financial_impact=Decimal("0.00"),
            )
            return _apply_refund_enrichment(result, payment, context)
        elif fee_check.consistent and lenient_ok and not bank_amount_matches_net:
            # The fee math checks out, but the confirmed bank credit itself
            # does not match what that math implies was actually paid out --
            # a real, unexplained residual in what money arrived, never
            # silently absorbed into a "fee explains it" story.
            credit_residual = (bank_amount - settlement.net_amount).copy_abs()
            credit_mismatch_line = (
                f"✗ confirmed bank credit ({bank_amount}) does not match the fee-verified net amount ({settlement.net_amount})"
            )
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.MISMATCH, method="none",
                matched_settlement_ids=[settlement.settlement_id], matched_bank_txn_ids=[], score=None,
                why_matched=[currency_line, fee_line],
                why_not_matched=[credit_mismatch_line],
                differences=[credit_mismatch_line], financial_impact=credit_residual,
            )
            return _apply_refund_enrichment(result, payment, context)
        else:
            # This is exactly the case the M1 adversarial fee_mismatch cases
            # are designed to hit: a fee WAS deducted, but the deterministic
            # recomputation shows it does not explain the actual gap. Must
            # NOT be matched, regardless of how plausible it looks.
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.MISMATCH, method="none",
                matched_settlement_ids=[settlement.settlement_id], matched_bank_txn_ids=[], score=None,
                why_matched=[currency_line],
                why_not_matched=[amount_line, fee_line],
                differences=[fee_line], financial_impact=fee_check.delta,
            )
            return _apply_refund_enrichment(result, payment, context)

    # No fee rule explains it either -- check the settlement's own internal
    # arithmetic before deciding partial vs. mismatch.
    self_check = verify_settlement_self_consistency(settlement)
    self_line = explanation.self_consistency_line(self_check.consistent, self_check.delta)

    if bank_amount < payment.amount:
        shortfall = payment.amount - bank_amount
        if not self_check.consistent:
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.MISMATCH, method="none",
                matched_settlement_ids=[settlement.settlement_id], matched_bank_txn_ids=[], score=None,
                why_matched=[currency_line],
                why_not_matched=[amount_line, self_line],
                differences=[amount_line, self_line], financial_impact=shortfall,
            )
        else:
            result = ReconciliationResult(
                **base, status=ReconciliationStatus.PARTIAL, method="none",
                matched_settlement_ids=[settlement.settlement_id], matched_bank_txn_ids=[], score=None,
                why_matched=[currency_line],
                why_not_matched=[amount_line],
                differences=[amount_line], financial_impact=shortfall,
            )
    else:
        excess = bank_amount - payment.amount
        result = ReconciliationResult(
            **base, status=ReconciliationStatus.MISMATCH, method="none",
            matched_settlement_ids=[settlement.settlement_id], matched_bank_txn_ids=[], score=None,
            why_matched=[currency_line],
            why_not_matched=[amount_line],
            differences=[amount_line], financial_impact=excess,
        )

    return _apply_refund_enrichment(result, payment, context)
