"""Scenarios 8, 12 (duplicate, ambiguous candidates) -- the non-negotiable
ambiguity rule: never auto-pick a candidate just because it has the highest
score, or because it happens to have a confirmed bank credit, when a genuine
rival exists."""
from decimal import Decimal

from app.engines.reconciliation.candidate_generation import build_context
from app.engines.reconciliation.relationships import resolve_multiple_linked_settlements, resolve_unlinked_payment
from shared.taxonomy import ReconciliationStatus

from .factories import make_bank_txn, make_payment, make_settlement, ZERO_FEE_RULE


def test_duplicate_settlements_are_ambiguous_even_with_one_confirmed_credit():
    """Two settlements linked to the same payment, same amount -- only one
    has a confirmed bank credit. Must NOT be silently resolved to the
    confirmed one: the existence of an unexplained duplicate record is
    itself something a human should look at."""
    payment = make_payment(amount="1000.00")
    settlement_1 = make_settlement(settlement_id="STL-00001", amount="1000.00", net_amount="1000.00")
    settlement_2 = make_settlement(settlement_id="STL-00002", amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(settlement_id="STL-00001", amount="1000.00")  # only settlement_1 confirmed
    ctx = build_context([payment], [settlement_1, settlement_2], [bank_txn], [], [ZERO_FEE_RULE])

    result = resolve_multiple_linked_settlements(payment, [settlement_1, settlement_2], ctx)

    assert result.status == ReconciliationStatus.AMBIGUOUS
    assert result.matched_settlement_ids == []
    assert len(result.candidates) == 2


def test_duplicate_with_slightly_different_amounts_is_still_ambiguous():
    """The M1 adversarial duplicate variant: amounts differ by only Rs 1,
    which could tempt a naive system into treating them as two distinct
    legitimate settlements."""
    payment = make_payment(amount="1000.00")
    settlement_1 = make_settlement(settlement_id="STL-00001", amount="1000.00", net_amount="1000.00")
    settlement_2 = make_settlement(settlement_id="STL-00002", amount="1001.00", net_amount="1001.00")
    bank_txn = make_bank_txn(settlement_id="STL-00001", amount="1000.00")
    ctx = build_context([payment], [settlement_1, settlement_2], [bank_txn], [], [ZERO_FEE_RULE])

    result = resolve_multiple_linked_settlements(payment, [settlement_1, settlement_2], ctx)

    assert result.status == ReconciliationStatus.AMBIGUOUS


def test_ambiguous_unlinked_candidates_do_not_auto_resolve_to_top_score():
    """Two unlinked candidates for one payment: B is clearly better (closer
    date, matching merchant, confirmed credit) but not overwhelmingly so --
    must land as AMBIGUOUS (human review), never auto-picked."""
    import json

    payment = make_payment(amount="1000.00")
    payment.metadata_json = json.dumps({"merchant": "Merchant-A"})

    candidate_a = make_settlement(settlement_id="STL-A", payment_id=None, amount="1000.00")
    candidate_a.utr_reference = "UTRUNRELATED999999"
    candidate_a.metadata_json = json.dumps({"merchant": "Merchant-B"})

    candidate_b = make_settlement(settlement_id="STL-B", payment_id=None, amount="1000.00")
    candidate_b.metadata_json = json.dumps({"merchant": "Merchant-A"})
    bank_txn = make_bank_txn(settlement_id="STL-B", amount="1000.00")

    ctx = build_context([payment], [candidate_a, candidate_b], [bank_txn], [], [ZERO_FEE_RULE])

    result = resolve_unlinked_payment(payment, ctx)

    assert result.status == ReconciliationStatus.AMBIGUOUS
    assert result.matched_settlement_ids == []
    assert len(result.candidates) == 2


def test_weak_lone_candidate_is_unresolved_not_ambiguous():
    """A single, weakly-scoring candidate (no shared reference, no merchant
    match, no bank confirmation, amount off) has no real rival, but also
    isn't strong enough to act on -- correctly UNRESOLVED, not AMBIGUOUS."""
    import json

    payment = make_payment(amount="1000.00")
    weak_candidate = make_settlement(settlement_id="STL-WEAK", payment_id=None, amount="700.00")
    weak_candidate.utr_reference = "UTRUNRELATED000000"
    ctx = build_context([payment], [weak_candidate], [], [], [ZERO_FEE_RULE])

    result = resolve_unlinked_payment(payment, ctx)

    assert result.status == ReconciliationStatus.UNRESOLVED
