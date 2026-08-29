"""Scenarios 14, 15 (similar references, different references) plus
candidate-generation blocking correctness. CANDIDATE MATCH != FINANCIAL
RECONCILIATION is asserted explicitly: a high fuzzy-reference similarity
must never, by itself, produce a MATCHED status without the amount/date/fee
checks also agreeing."""
from decimal import Decimal

from app.engines.reconciliation.candidate_generation import build_context
from app.engines.reconciliation.scoring import score_reference

from .factories import ZERO_FEE_RULE, make_payment, make_settlement


def test_similar_reference_scores_high():
    payment = make_payment(payment_id="PAY-00123")
    # "payment-ABC-123"-style near match: same digits, different formatting/prefix noise
    settlement = make_settlement(utr_reference="UTR00001-PAY-00123-REF")
    score = score_reference(payment, settlement)
    assert score == Decimal("1.00")  # contains the payment's id token


def test_different_reference_scores_low():
    payment = make_payment(payment_id="PAY-00123")
    # Same-length, similarly-formatted, but a genuinely different id ("999" not "123")
    settlement = make_settlement(utr_reference="UTR00001-PAY-00999-REF")
    score = score_reference(payment, settlement)
    assert score < Decimal("0.80"), "a different id must not score as if it were the same reference"


def test_candidate_match_alone_never_declares_reconciliation():
    """A settlement with a very similar-looking reference but a WRONG amount
    must not be matched -- candidate generation only produces candidates,
    matching.py/relationships.py still require amount/date/fee agreement."""
    from app.engines.reconciliation.relationships import resolve_unlinked_payment

    payment = make_payment(payment_id="PAY-00123", amount="1000.00")
    look_alike = make_settlement(
        settlement_id="STL-LOOKALIKE", payment_id=None, amount="1.00",  # wildly different amount
        utr_reference="UTR00001-PAY-00123-REF",
    )
    ctx = build_context([payment], [look_alike], [], [], [ZERO_FEE_RULE])

    result = resolve_unlinked_payment(payment, ctx)

    from shared.taxonomy import ReconciliationStatus

    assert result.status != ReconciliationStatus.MATCHED


def test_candidate_generation_uses_blocking_not_full_cross_product():
    """Documents and checks the actual blocking behavior: a settlement far
    outside the payment's currency/date/amount block is never returned as a
    candidate, even though a naive O(N*M) scan would still find it."""
    from datetime import timedelta

    from .factories import BASE_DATE

    payment = make_payment(amount="1000.00", captured_at=BASE_DATE)
    far_settlement = make_settlement(
        settlement_id="STL-FAR", payment_id=None, amount="999999.00",  # very different amount band
        settled_at=BASE_DATE + timedelta(days=400),  # very different date bucket
    )
    ctx = build_context([payment], [far_settlement], [], [], [ZERO_FEE_RULE])

    candidates = ctx.candidates_for(payment)
    assert far_settlement not in candidates
