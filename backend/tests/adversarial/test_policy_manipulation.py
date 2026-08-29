"""M9 Category L: policy manipulation (Phase 15). No combination of "AI
looks confident, amount is low, records look similar" can substitute for
policy authority -- `ai_confidence` is carried on `PolicyInput` for audit
only and is never read by `evaluate_policy` (app.policy.engine) at all.
"""
from decimal import Decimal

import pytest

from app.policy.engine import evaluate_policy
from app.policy.schemas import PolicyDecisionType, PolicyInput, RiskLevel
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype


def _eligible_input(**overrides) -> PolicyInput:
    defaults = dict(
        exception_id="EXC-manip", exception_type="fee_mismatch", verifier_status="VERIFIED",
        residual_amount=Decimal("0.00"), financial_exposure=Decimal("50.00"),
        ai_confidence=0.5, evidence_complete=True, conflicting_evidence=False, ambiguous=False,
        risk_score=Decimal("1.00"), risk_level=RiskLevel.LOW, auto_resolution_eligible_category=True,
    )
    defaults.update(overrides)
    return PolicyInput(**defaults)


@pytest.mark.parametrize("confidence", [0.0, 0.5, 0.99, 1.0])
def test_ai_confidence_never_affects_the_policy_decision(confidence):
    baseline = evaluate_policy(_eligible_input(ai_confidence=confidence))
    other = evaluate_policy(_eligible_input(ai_confidence=1.0 - confidence))
    assert baseline.decision == other.decision == PolicyDecisionType.SAFE_TO_RESOLVE


def test_high_ai_confidence_plus_low_amount_plus_conflicting_evidence_still_reviews():
    # Exactly the brief's own attempted attack shape: high AI confidence +
    # low amount + everything else looking eligible -- but conflicting
    # evidence must still force HUMAN_REVIEW.
    decision = evaluate_policy(_eligible_input(ai_confidence=0.99, financial_exposure=Decimal("1.00"), conflicting_evidence=True))
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-CONFLICT-001" in decision.rules_passed


def test_high_risk_forces_review_regardless_of_everything_else_looking_eligible():
    decision = evaluate_policy(_eligible_input(ai_confidence=0.99, risk_level=RiskLevel.HIGH))
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_high_exposure_forces_review_regardless_of_everything_else_looking_eligible():
    decision = evaluate_policy(_eligible_input(ai_confidence=0.99, financial_exposure=Decimal("200000.00")))
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-EXPOSURE-001" in decision.rules_passed


def test_contradiction_forces_review_regardless_of_everything_else_looking_eligible():
    decision = evaluate_policy(_eligible_input(ai_confidence=0.99, conflicting_evidence=True))
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_missing_evidence_blocks_outright_regardless_of_everything_else_looking_eligible():
    decision = evaluate_policy(_eligible_input(ai_confidence=0.99, evidence_complete=False))
    assert decision.decision == PolicyDecisionType.REJECTED
    assert "POLICY-EVIDENCE-001" in decision.rules_passed


def test_unauthorized_actor_cannot_approve_via_the_policy_authorization_layer():
    from app.policy.authorization import AuthorizationError, require_authorization
    from app.policy.schemas import Actor, ActorType, Capability

    ai_actor = Actor(ActorType.AI, "ai-1")
    with pytest.raises(AuthorizationError):
        require_authorization(ai_actor, Capability.APPROVE)


def test_end_to_end_low_exposure_high_confidence_ambiguous_case_still_reviews(mutated_dataset, ground_truth, decision_env):
    # An end-to-end reconfirmation using the real pipeline, not just the
    # unit-level PolicyInput -- a real ambiguous_match case (inherently
    # low-exposure-looking, MockAIProvider will report reasonably high
    # confidence on whichever hypothesis it tries) must still review.
    order_id = pick_by_archetype(ground_truth, "ambiguous_match", 0, not_adversarial=False)
    payment = find_payment_by_order(mutated_dataset, order_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
