"""Scenarios 3, 4, 5: positive evidence, negative evidence, candidate
rejection -- the "Why NOT Matched" engine, evaluated on hand-built cases."""
from decimal import Decimal

from app.engines.evidence.candidates import evaluate_candidate, why_not_matched
from app.engines.evidence.constraints import amount_balance_constraint, currency_match_constraint

from .factories import ZERO_FEE_RULE, make_bank_txn, make_context, make_payment, make_settlement


def test_positive_evidence_recorded_for_a_clean_candidate():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(amount="1000.00")
    context = make_context([payment], [settlement], [bank_txn])

    evidence = evaluate_candidate(payment, settlement, context, [])

    assert evidence.verdict == "ACCEPTED"
    assert len(evidence.positive_evidence) > 0
    assert all(e.passed for e in evidence.positive_evidence)


def test_negative_evidence_recorded_for_a_bad_candidate():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1200.00", net_amount="1200.00")  # Rs 200 unexplained
    bank_txn = make_bank_txn(amount="1200.00")
    context = make_context([payment], [settlement], [bank_txn])

    evidence = evaluate_candidate(payment, settlement, context, [])

    assert evidence.verdict == "REJECTED"
    assert len(evidence.negative_evidence) > 0
    failing = [e for e in evidence.negative_evidence if e.constraint == "amount_balance"]
    assert failing and failing[0].delta == "200.00"


def test_evidence_bundle_preserves_both_positive_and_negative():
    """A candidate can have SOME passing and SOME failing constraints at
    once -- both lists must be preserved, not just the failure that decided
    the verdict."""
    payment = make_payment(amount="1000.00", currency="INR")
    settlement = make_settlement(amount="1200.00", net_amount="1200.00", currency="INR")  # currency ok, amount not
    bank_txn = make_bank_txn(amount="1200.00", currency="INR")
    context = make_context([payment], [settlement], [bank_txn])

    evidence = evaluate_candidate(payment, settlement, context, [])
    passed_constraints = {e.constraint for e in evidence.positive_evidence}
    failed_constraints = {e.constraint for e in evidence.negative_evidence}

    assert "currency_match" in passed_constraints
    assert "amount_balance" in failed_constraints


def test_candidate_rejection_reason_is_machine_readable():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1200.00", net_amount="1200.00")
    bank_txn = make_bank_txn(amount="1200.00")
    context = make_context([payment], [settlement], [bank_txn])

    evidence = evaluate_candidate(payment, settlement, context, [])
    assert evidence.reason_code == "AMOUNT_RESIDUAL"  # not free-form prose


def test_why_not_matched_ranks_multiple_candidates_and_rejects_all():
    # Amounts close enough to the payment to fall within candidate_generation's
    # blocking window (a real Rs 700/1300 candidate for a Rs 1000 payment
    # would correctly never surface at all -- that's blocking working as
    # intended, not a bug; this test is about ranking+rejecting REAL candidates).
    payment = make_payment(amount="1000.00")
    bad_candidate_1 = make_settlement(settlement_id="STL-A", payment_id=None, amount="950.00")
    bad_candidate_2 = make_settlement(settlement_id="STL-B", payment_id=None, amount="1040.00")
    context = make_context([payment], [bad_candidate_1, bad_candidate_2])

    report = why_not_matched(payment, context)

    assert report.verdict == "NO_VALID_CANDIDATE"
    assert len(report.candidates) == 2
    assert all(c.verdict == "REJECTED" for c in report.candidates)


def test_why_not_matched_returns_no_valid_candidate_when_nothing_exists():
    payment = make_payment(amount="1000.00")
    context = make_context([payment], [])
    report = why_not_matched(payment, context)
    assert report.verdict == "NO_VALID_CANDIDATE"
    assert report.candidates == []
