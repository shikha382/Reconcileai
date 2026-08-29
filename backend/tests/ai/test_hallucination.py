"""Hallucination defense: the AI must not be able to manufacture financial
facts. Every scenario here injects a reference to something that does not
exist and confirms the system rejects it rather than acting on it."""
from app.ai.controller import investigate
from app.ai.provider import MockAIProvider
from app.ai.schemas import HypothesisType, RecommendedAction, TestHypothesisInput
from app.ai.verifier import verify_hypothesis

from .factories import make_bank_txn, make_investigation_context, make_payment, make_settlement


def test_hallucinated_settlement_id_never_reaches_safe_to_resolve():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment, [])  # no real settlement at all

    result = investigate("EXC-1", ctx, MockAIProvider(hallucinate_record_id="STL-99999", hallucinate_hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE))

    assert result.final_decision != RecommendedAction.SAFE_TO_RESOLVE
    rejected = [o for o in result.outcomes if o.hypothesis.hypothesis_type == HypothesisType.FEE_EXPLAINS_DIFFERENCE]
    assert rejected and rejected[0].decision == RecommendedAction.REJECTED


def test_referenced_fee_rule_does_not_exist():
    payment = make_payment(amount="1000.00", method="nonexistent_method")
    settlement = make_settlement(amount="900.00", net_amount="900.00")
    bank_txn = make_bank_txn(amount="900.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn], fee_rules=[])  # no rule for this method

    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, settlement_id="STL-00001"), ctx)
    assert not result.passed


def test_referenced_refund_does_not_exist():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="800.00", net_amount="800.00")
    bank_txn = make_bank_txn(amount="800.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn], refunds=[])  # no refund on record at all

    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.REFUND_EXPLAINS_DIFFERENCE, settlement_id="STL-00001"), ctx)
    assert not result.passed


def test_amount_missing_does_not_crash_and_is_rejected():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment, [])
    # No settlement_id at all -- the AI didn't even name a candidate.
    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, settlement_id=None), ctx)
    assert not result.passed


def test_invalid_candidate_id_is_rejected_not_crashed():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment, [])
    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.DUPLICATE, candidate_settlement_ids=["STL-DOES-NOT-EXIST"]), ctx)
    assert not result.passed


def test_ai_proposes_nonexistent_payment_id():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(amount="1000.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = verify_hypothesis(TestHypothesisInput(
        exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.AGGREGATED_SETTLEMENT,
        settlement_id="STL-00001", candidate_payment_ids=["PAY-00001", "PAY-NONEXISTENT"],
    ), ctx)
    assert not result.passed
    assert "do not exist" in result.reason
