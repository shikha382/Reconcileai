"""Minimal authorization -- actor TYPE alone never implies permission."""
import pytest

from app.policy.authorization import AuthorizationError, is_authorized, require_authorization
from app.policy.schemas import Actor, ActorType, Capability


def test_ai_cannot_approve():
    ai = Actor(ActorType.AI, "ai-controller-1")
    assert not is_authorized(ai, Capability.APPROVE)


def test_ai_cannot_change_policy():
    ai = Actor(ActorType.AI, "ai-controller-1")
    assert not is_authorized(ai, Capability.CHANGE_POLICY)


def test_ai_can_propose_resolution():
    ai = Actor(ActorType.AI, "ai-controller-1")
    assert is_authorized(ai, Capability.PROPOSE_RESOLUTION)


def test_human_can_approve():
    human = Actor(ActorType.HUMAN, "reviewer-1")
    assert is_authorized(human, Capability.APPROVE)


def test_no_actor_can_change_policy_in_this_mvp():
    for actor_type in ActorType:
        actor = Actor(actor_type, "x")
        assert not is_authorized(actor, Capability.CHANGE_POLICY)


def test_policy_engine_actor_is_not_a_human_actor():
    """The policy engine itself must not be treated as authorized to
    approve -- it decides, it doesn't review."""
    policy_engine_actor = Actor(ActorType.POLICY_ENGINE, "policy-engine")
    assert not is_authorized(policy_engine_actor, Capability.APPROVE)


def test_require_authorization_raises_for_unauthorized_actor():
    ai = Actor(ActorType.AI, "ai-controller-1")
    with pytest.raises(AuthorizationError):
        require_authorization(ai, Capability.APPROVE)


def test_require_authorization_passes_silently_for_authorized_actor():
    human = Actor(ActorType.HUMAN, "reviewer-1")
    require_authorization(human, Capability.APPROVE)  # must not raise
