"""The deterministic policy gate -- the AI cannot override any of this."""
from decimal import Decimal

from app.ai.policy import MAX_AUTO_RESOLVE_AMOUNT, decide_final_outcome, decide_hypothesis_outcome
from app.ai.schemas import AIHypothesis, HypothesisType, RecommendedAction, TestHypothesisOutput


def _hypothesis(hyp_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE) -> AIHypothesis:
    return AIHypothesis(
        hypothesis_id="H-1", exception_id="EXC-1", hypothesis_type=hyp_type, claim="x",
        record_ids=["PAY-00001"], evidence_ids=["PAY-00001"], confidence=0.9,
        recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
    )


def test_verified_and_zero_residual_is_safe_to_resolve():
    verifier_result = TestHypothesisOutput(hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=True, residual="0.00", reason="ok")
    outcome = decide_hypothesis_outcome(_hypothesis(), verifier_result, [], Decimal("500.00"))
    assert outcome.decision == RecommendedAction.SAFE_TO_RESOLVE


def test_failed_verification_is_rejected_not_auto_resolved():
    """AI confidence is irrelevant here -- the verifier has authority."""
    verifier_result = TestHypothesisOutput(hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=False, reason="residual unexplained")
    hypothesis = _hypothesis()
    hypothesis.confidence = 0.99  # a very "confident" AI -- must not matter
    outcome = decide_hypothesis_outcome(hypothesis, verifier_result, [], Decimal("500.00"))
    assert outcome.decision == RecommendedAction.REJECTED


def test_low_confidence_but_verifier_passed_is_still_safe():
    """AI confidence is ALSO irrelevant in the other direction -- a
    "low confidence" hypothesis that the verifier fully confirms is safe."""
    verifier_result = TestHypothesisOutput(hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=True, residual="0.00", reason="ok")
    hypothesis = _hypothesis()
    hypothesis.confidence = 0.1
    outcome = decide_hypothesis_outcome(hypothesis, verifier_result, [], Decimal("500.00"))
    assert outcome.decision == RecommendedAction.SAFE_TO_RESOLVE


def test_grounding_violation_forces_rejected_regardless_of_verifier():
    verifier_result = TestHypothesisOutput(hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=True, residual="0.00", reason="ok")
    outcome = decide_hypothesis_outcome(_hypothesis(), verifier_result, ["hallucinated id"], Decimal("500.00"))
    assert outcome.decision == RecommendedAction.REJECTED


def test_never_auto_resolve_categories_always_human_review_even_when_verified():
    for hyp_type in (HypothesisType.DUPLICATE, HypothesisType.AMBIGUOUS, HypothesisType.UNEXPLAINED_RESIDUAL, HypothesisType.PARTIAL_SETTLEMENT):
        verifier_result = TestHypothesisOutput(hypothesis_type=hyp_type, passed=True, reason="confirmed")
        outcome = decide_hypothesis_outcome(_hypothesis(hyp_type), verifier_result, [], Decimal("500.00"))
        assert outcome.decision == RecommendedAction.HUMAN_REVIEW, f"{hyp_type} must never auto-resolve"


def test_missing_record_maps_to_unresolved_not_human_review():
    verifier_result = TestHypothesisOutput(hypothesis_type=HypothesisType.MISSING_RECORD, passed=True, reason="confirmed missing")
    outcome = decide_hypothesis_outcome(_hypothesis(HypothesisType.MISSING_RECORD), verifier_result, [], Decimal("500.00"))
    assert outcome.decision == RecommendedAction.UNRESOLVED


def test_nonzero_residual_forces_human_review():
    verifier_result = TestHypothesisOutput(hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=True, residual="9.83", reason="close but not exact")
    outcome = decide_hypothesis_outcome(_hypothesis(), verifier_result, [], Decimal("500.00"))
    assert outcome.decision == RecommendedAction.HUMAN_REVIEW


def test_amount_above_risk_threshold_forces_human_review():
    verifier_result = TestHypothesisOutput(hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=True, residual="0.00", reason="ok")
    outcome = decide_hypothesis_outcome(_hypothesis(), verifier_result, [], MAX_AUTO_RESOLVE_AMOUNT + Decimal("1.00"))
    assert outcome.decision == RecommendedAction.HUMAN_REVIEW


def test_final_outcome_picks_safe_to_resolve_if_any_hypothesis_achieved_it():
    from app.ai.policy import HypothesisOutcome

    rejected = HypothesisOutcome(_hypothesis(), TestHypothesisOutput(hypothesis_type=HypothesisType.REFUND_EXPLAINS_DIFFERENCE, passed=False, reason="x"), True, RecommendedAction.REJECTED, "x")
    safe = HypothesisOutcome(_hypothesis(), TestHypothesisOutput(hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=True, residual="0.00", reason="x"), True, RecommendedAction.SAFE_TO_RESOLVE, "x")
    final, _ = decide_final_outcome([rejected, safe])
    assert final == RecommendedAction.SAFE_TO_RESOLVE


def test_final_outcome_defaults_to_human_review_when_all_rejected():
    from app.ai.policy import HypothesisOutcome

    rejected = HypothesisOutcome(_hypothesis(), TestHypothesisOutput(hypothesis_type=HypothesisType.REFUND_EXPLAINS_DIFFERENCE, passed=False, reason="x"), True, RecommendedAction.REJECTED, "x")
    final, _ = decide_final_outcome([rejected, rejected])
    assert final == RecommendedAction.HUMAN_REVIEW


def test_final_outcome_with_no_hypotheses_tested_is_human_review_not_safe():
    final, reason = decide_final_outcome([])
    assert final == RecommendedAction.HUMAN_REVIEW
