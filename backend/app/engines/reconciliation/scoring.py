"""Stage 5: transparent, deterministic multi-field candidate scoring.

Used specifically for candidates discovered WITHOUT a direct payment_id link
(the unlinked/blocked settlement pool -- see candidate_generation.py) where
no other stage has already produced a deterministic answer. Direct-link
candidates are resolved by stages 1-3 (see matching.py) without ever going
through this scorer, on the principle that a real payment_id/bank-confirmed
link is stronger evidence than a computed similarity score.

Every component is stored, never just the total -- "a developer must be able
to understand exactly why the score is 0.94" (explicit project requirement).
No signal is included to look sophisticated; each one is documented with why
it's there and why it's weighted the way it is (config.py).
"""
from __future__ import annotations

from decimal import Decimal

from rapidfuzz import fuzz

from app.db.models import Payment, Settlement
from app.engines.normalization import normalize_reference
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.config import (
    LENIENT_DATE_TOLERANCE_DAYS,
    SCORE_WEIGHTS,
)
from app.engines.reconciliation.types import ScoreBreakdown

assert sum(SCORE_WEIGHTS.values()) == Decimal("1.00"), "SCORE_WEIGHTS must sum to 1.0"


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def score_reference(payment: Payment, settlement: Settlement) -> Decimal:
    """1.0 if the settlement is directly linked to this payment, or if its
    (normalized) reference contains this payment's own id token -- the
    convention data/synthetic/generator.py actually uses when it derives a
    settlement's utr_reference from a payment. Otherwise, falls back to a
    RapidFuzz partial-ratio similarity as partial credit for a genuinely
    similar-but-not-identical reference, rather than an all-or-nothing 0."""
    if settlement.payment_id == payment.payment_id:
        return Decimal("1.00")

    pid_token = normalize_reference(payment.payment_id)
    normalized_ref = normalize_reference(settlement.utr_reference)
    if pid_token in normalized_ref:
        return Decimal("1.00")

    similarity = fuzz.partial_ratio(normalized_ref, pid_token) / 100.0
    return _round2(Decimal(str(similarity)))


def score_amount(payment: Payment, settlement: Settlement) -> Decimal:
    """1.0 for an exact gross-amount match; partial credit decaying with the
    relative difference otherwise (never negative, floors at 0)."""
    if payment.amount == Decimal("0"):
        return Decimal("0.00")
    diff_ratio = abs(payment.amount - settlement.amount) / payment.amount
    score = Decimal("1.00") - diff_ratio
    return _round2(max(score, Decimal("0.00")))


def score_date(payment: Payment, settlement: Settlement) -> Decimal:
    """1.0 for same-day settlement, decaying linearly to 0 at
    LENIENT_DATE_TOLERANCE_DAYS -- settlement lag is expected and should only
    mildly penalize a candidate, not disqualify it outright (that's what the
    tolerance WINDOW in matching.py is for; this score is a softer signal for
    ranking candidates within the window)."""
    delta_days = abs((settlement.settled_at.date() - payment.captured_at.date()).days)
    if delta_days >= LENIENT_DATE_TOLERANCE_DAYS:
        return Decimal("0.00")
    score = Decimal("1.00") - (Decimal(delta_days) / Decimal(LENIENT_DATE_TOLERANCE_DAYS))
    return _round2(score)


def score_fee(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> Decimal:
    """1.0 if the settlement's net_amount is exactly explained by the
    payment's applicable FeeRule (or if there's no fee gap to explain at
    all); 0 if a fee rule exists but does NOT explain the gap. This is the
    signal the M1 adversarial fee_mismatch cases are specifically designed
    to drive to 0 -- see verification.verify_fee_consistency, which this
    delegates to so there is exactly one fee-checking implementation."""
    from app.engines.reconciliation.verification import verify_fee_consistency

    result = verify_fee_consistency(payment, settlement, context)
    if result is None:
        # No fee rule for this method, or amounts already match exactly --
        # neither for nor against a fee-based explanation.
        return Decimal("1.00") if payment.amount == settlement.net_amount else Decimal("0.50")
    return Decimal("1.00") if result.consistent else Decimal("0.00")


def score_merchant(payment: Payment, settlement: Settlement) -> Decimal:
    """Compares an optional 'merchant' key in each record's metadata dict, if
    present on both sides -- a secondary corroborating signal (weight 0.05),
    never decisive alone. Returns a neutral 0.5 (neither for nor against)
    when the data doesn't carry merchant metadata at all, since most
    archetypes don't populate it."""
    import json

    p_meta = json.loads(payment.metadata_json or "{}")
    s_meta = json.loads(settlement.metadata_json or "{}")
    p_merchant = p_meta.get("merchant")
    s_merchant = s_meta.get("merchant")
    if p_merchant is None or s_merchant is None:
        return Decimal("0.50")
    return Decimal("1.00") if p_merchant == s_merchant else Decimal("0.00")


def score_link(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> Decimal:
    """Small bonus (weight 0.05) for a settlement that has a confirmed
    CREDIT bank transaction -- evidence that money actually moved, not just
    that a settlement record exists. This is evidence attached to the
    candidate, not an auto-resolving tiebreaker (see relationships.py's
    explicit non-negotiable-ambiguity handling for records with multiple
    plausible candidates)."""
    bank_txns = context.bank_txns_by_settlement_id.get(settlement.settlement_id, [])
    has_confirmed_credit = any(b.direction == "credit" for b in bank_txns)
    return Decimal("1.00") if has_confirmed_credit else Decimal("0.00")


def score_candidate(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> ScoreBreakdown:
    reference = score_reference(payment, settlement)
    amount = score_amount(payment, settlement)
    date = score_date(payment, settlement)
    fee = score_fee(payment, settlement, context)
    merchant = score_merchant(payment, settlement)
    link = score_link(payment, settlement, context)

    total = (
        reference * SCORE_WEIGHTS["reference"]
        + amount * SCORE_WEIGHTS["amount"]
        + date * SCORE_WEIGHTS["date"]
        + fee * SCORE_WEIGHTS["fee"]
        + merchant * SCORE_WEIGHTS["merchant"]
        + link * SCORE_WEIGHTS["link"]
    )

    return ScoreBreakdown(
        reference=reference, amount=amount, date=date, fee=fee, merchant=merchant, link=link,
        total=_round2(total),
    )
