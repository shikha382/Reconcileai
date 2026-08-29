"""Human approval workflow -- dual control, idempotency, authorization."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.policy.approval import ApprovalWorkflowStore, submit_review_decision
from app.policy.authorization import AuthorizationError
from app.policy.engine import evaluate_policy
from app.policy.schemas import (
    Actor,
    ActorType,
    ReasonCode,
    ReviewDecisionType,
    ReviewState,
)

from .factories import make_policy_input


def _make_review(store: ApprovalWorkflowStore, risk_level, created_by="ai-controller-1"):
    from app.policy.schemas import RiskLevel

    policy_input = make_policy_input(verifier_status="AMBIGUOUS", ambiguous=True, risk_level=risk_level)
    decision = evaluate_policy(policy_input)
    proposal = build_resolution_proposal_stub(decision)
    return store.create_review_request("EXC-1", proposal, decision, created_by)


def build_resolution_proposal_stub(decision):
    from app.policy.schemas import ResolutionProposal

    return ResolutionProposal(
        exception_id="EXC-1", resolution_type=decision.resolution_type, reason="test",
        evidence_ids=["EXC-1"], verified=False, financial_impact=Decimal("1000.00"),
        requires_approval=decision.required_approval,
    )


def test_dual_control_blocks_maker_approving_own_proposal():
    from app.policy.schemas import RiskLevel

    store = ApprovalWorkflowStore()
    review = _make_review(store, RiskLevel.HIGH, created_by="ai-controller-1")
    assert review.dual_control_required

    maker = Actor(ActorType.HUMAN, "ai-controller-1")
    with pytest.raises(AuthorizationError):
        submit_review_decision(review, maker, ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE)
    assert review.state == ReviewState.PENDING_REVIEW


def test_dual_control_allows_a_different_authorized_reviewer():
    from app.policy.schemas import RiskLevel

    store = ApprovalWorkflowStore()
    review = _make_review(store, RiskLevel.HIGH, created_by="maker-1")

    checker = Actor(ActorType.HUMAN, "checker-2")
    decision = submit_review_decision(review, checker, ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE)
    assert decision.decision == ReviewDecisionType.APPROVE
    assert review.state == ReviewState.APPROVED


def test_low_risk_review_does_not_require_dual_control():
    from app.policy.schemas import RiskLevel

    store = ApprovalWorkflowStore()
    review = _make_review(store, RiskLevel.LOW, created_by="maker-1")
    assert not review.dual_control_required

    maker_as_reviewer = Actor(ActorType.HUMAN, "maker-1")
    decision = submit_review_decision(review, maker_as_reviewer, ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE)
    assert decision.decision == ReviewDecisionType.APPROVE


def test_unauthorized_actor_cannot_approve():
    from app.policy.schemas import RiskLevel

    store = ApprovalWorkflowStore()
    review = _make_review(store, RiskLevel.LOW)
    ai_actor = Actor(ActorType.AI, "ai-controller-1")
    with pytest.raises(AuthorizationError):
        submit_review_decision(review, ai_actor, ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE)


def test_idempotent_review_creation_does_not_duplicate():
    from app.policy.schemas import RiskLevel

    store = ApprovalWorkflowStore()
    policy_input = make_policy_input(verifier_status="AMBIGUOUS", ambiguous=True, risk_level=RiskLevel.LOW)
    decision = evaluate_policy(policy_input)
    proposal = build_resolution_proposal_stub(decision)

    r1 = store.create_review_request("EXC-1", proposal, decision, "maker-1")
    r2 = store.create_review_request("EXC-1", proposal, decision, "maker-1")
    assert r1.review_id == r2.review_id


def test_duplicate_approval_decision_is_idempotent_not_a_new_transition():
    from app.policy.schemas import RiskLevel

    store = ApprovalWorkflowStore()
    review = _make_review(store, RiskLevel.LOW, created_by="maker-1")
    reviewer = Actor(ActorType.HUMAN, "checker-1")

    first = submit_review_decision(review, reviewer, ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE)
    assert review.state == ReviewState.APPROVED
    second = submit_review_decision(review, reviewer, ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE)
    assert review.state == ReviewState.APPROVED  # unchanged
    assert "no-op" in second.comment


def test_request_more_evidence_leaves_review_pending():
    from app.policy.schemas import RiskLevel

    store = ApprovalWorkflowStore()
    review = _make_review(store, RiskLevel.LOW, created_by="maker-1")
    reviewer = Actor(ActorType.HUMAN, "checker-1")
    submit_review_decision(review, reviewer, ReviewDecisionType.REQUEST_MORE_EVIDENCE, ReasonCode.EVIDENCE_INSUFFICIENT)
    assert review.state == ReviewState.PENDING_REVIEW


def test_review_expiry():
    from app.policy.schemas import RiskLevel

    store = ApprovalWorkflowStore()
    now = datetime(2026, 1, 1)
    policy_input = make_policy_input(verifier_status="AMBIGUOUS", ambiguous=True, risk_level=RiskLevel.LOW)
    decision = evaluate_policy(policy_input)
    proposal = build_resolution_proposal_stub(decision)
    review = store.create_review_request("EXC-1", proposal, decision, "maker-1", reference_now=now, expiry_hours=1)

    expired = store.expire_overdue(now + timedelta(hours=2))
    assert review in expired
    assert review.state == ReviewState.EXPIRED
