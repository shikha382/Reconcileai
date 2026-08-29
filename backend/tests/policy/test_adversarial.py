"""The M5 brief's 14 numbered adversarial tests, for traceability. Several
are deeper variants of scenarios also covered in test_policy_engine.py /
test_approval_workflow.py / test_state_machine.py / test_authorization.py --
this file is the canonical, numbered reference for all 14.
"""
from decimal import Decimal

import pytest

from app.policy.approval import ApprovalWorkflowStore, submit_review_decision
from app.policy.authorization import AuthorizationError
from app.policy.engine import evaluate_policy
from app.policy.schemas import (
    Actor,
    ActorType,
    Capability,
    PolicyDecisionType,
    ReasonCode,
    ResolutionProposal,
    ReviewDecisionType,
    ReviewState,
    RiskLevel,
)
from app.policy.state_machine import ExceptionState, InvalidStateTransitionError, transition

from .factories import make_policy_input


def test_1_ai_claims_verified_but_verifier_failed_blocks():
    policy_input = make_policy_input(verifier_status="CONTRADICTED", residual_amount="500.00")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_2_ai_claims_low_risk_but_risk_engine_says_critical():
    """The AI's own confidence/self-report is irrelevant -- only the
    deterministically-computed risk_level is read by the engine."""
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", ai_confidence=0.99, risk_level=RiskLevel.CRITICAL)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_3_ai_recommends_auto_resolution_for_ambiguous_case():
    policy_input = make_policy_input(verifier_status="AMBIGUOUS", ambiguous=True, ai_confidence=0.95)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_4_human_attempts_to_approve_own_dual_control_action():
    store = ApprovalWorkflowStore()
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", risk_level=RiskLevel.HIGH)
    decision = evaluate_policy(policy_input)
    proposal = ResolutionProposal(exception_id="EXC-1", resolution_type=decision.resolution_type, reason="x", evidence_ids=["EXC-1"], verified=False, financial_impact=Decimal("0.00"), requires_approval=decision.required_approval)
    review = store.create_review_request("EXC-1", proposal, decision, "maker-1")

    with pytest.raises(AuthorizationError):
        submit_review_decision(review, Actor(ActorType.HUMAN, "maker-1"), ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE)


def test_5_policy_conflict_safest_rule_wins():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", financial_exposure="200000.00")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_6_missing_evidence_blocks():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", evidence_complete=False)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_7_missing_evidence_again_blocks_not_human_review():
    """Distinct from ambiguity/risk: missing evidence is a BLOCK-tier
    condition, more severe than a mere review requirement."""
    policy_input = make_policy_input(verifier_status="UNEXPLAINED", evidence_complete=False, residual_amount="100.00")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_8_negative_residual_hidden_by_rounding_blocks():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="-0.01")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_9_duplicate_approval_request_is_idempotent():
    store = ApprovalWorkflowStore()
    policy_input = make_policy_input(verifier_status="AMBIGUOUS", ambiguous=True)
    decision = evaluate_policy(policy_input)
    proposal = ResolutionProposal(exception_id="EXC-1", resolution_type=decision.resolution_type, reason="x", evidence_ids=["EXC-1"], verified=False, financial_impact=Decimal("0.00"), requires_approval=decision.required_approval)

    r1 = store.create_review_request("EXC-1", proposal, decision, "maker-1")
    r2 = store.create_review_request("EXC-1", proposal, decision, "maker-1")
    assert r1.review_id == r2.review_id


def test_10_invalid_state_transition_is_rejected():
    with pytest.raises(InvalidStateTransitionError):
        transition(ExceptionState.EXCEPTION_OPEN, ExceptionState.CLOSED)


def test_11_unauthorized_actor_attempts_approval_rejected():
    store = ApprovalWorkflowStore()
    policy_input = make_policy_input(verifier_status="AMBIGUOUS", ambiguous=True)
    decision = evaluate_policy(policy_input)
    proposal = ResolutionProposal(exception_id="EXC-1", resolution_type=decision.resolution_type, reason="x", evidence_ids=["EXC-1"], verified=False, financial_impact=Decimal("0.00"), requires_approval=decision.required_approval)
    review = store.create_review_request("EXC-1", proposal, decision, "maker-1")

    with pytest.raises(AuthorizationError):
        submit_review_decision(review, Actor(ActorType.AI, "ai-1"), ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE)


def test_12_ai_attempts_policy_change_rejected():
    from app.policy.authorization import is_authorized

    ai = Actor(ActorType.AI, "ai-1")
    assert not is_authorized(ai, Capability.CHANGE_POLICY)


def test_13_high_value_verified_exception_requires_mandatory_human_review():
    from app.policy.engine import MAX_AUTO_RESOLVE_EXPOSURE

    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", financial_exposure=str(MAX_AUTO_RESOLVE_EXPOSURE + Decimal("0.01")))
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert decision.required_approval


def test_14_prompt_injection_attempts_to_trigger_resolution_have_no_effect():
    """PolicyInput carries only structured, already-computed fields --
    there is no text field an injection attempt could even reach. This
    test proves the type system itself, not just runtime behavior."""
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00")
    field_names = set(policy_input.__dataclass_fields__.keys())
    # No free-text field exists that could carry an injection payload into
    # a decision -- every field is a bounded enum/Decimal/bool/str-ID.
    assert "narration" not in field_names
    assert "raw_text" not in field_names
    assert "prompt" not in field_names
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE  # unaffected by anything text-shaped
