"""M6's 3 new audit capabilities (VIEW_AUDIT/VERIFY_AUDIT/APPEND_AUDIT) --
AI can never APPEND_AUDIT, and no actor type has UPDATE_AUDIT/DELETE_AUDIT
because those values don't exist in the Capability enum at all."""
import pytest

from app.policy.authorization import is_authorized, require_authorization, AuthorizationError
from app.policy.schemas import Actor, ActorType, Capability


def test_capability_enum_has_no_update_or_delete_audit_value():
    values = {c.value for c in Capability}
    assert "UPDATE_AUDIT" not in values
    assert "DELETE_AUDIT" not in values


def test_ai_can_view_audit_but_not_append():
    ai = Actor(ActorType.AI, "ai-1")
    assert is_authorized(ai, Capability.VIEW_AUDIT) is True
    assert is_authorized(ai, Capability.APPEND_AUDIT) is False
    assert is_authorized(ai, Capability.VERIFY_AUDIT) is False


def test_ai_cannot_approve_or_change_policy():
    ai = Actor(ActorType.AI, "ai-1")
    assert is_authorized(ai, Capability.APPROVE) is False
    assert is_authorized(ai, Capability.CHANGE_POLICY) is False


def test_human_can_view_and_verify_but_not_append_audit():
    human = Actor(ActorType.HUMAN, "reviewer-1")
    assert is_authorized(human, Capability.VIEW_AUDIT) is True
    assert is_authorized(human, Capability.VERIFY_AUDIT) is True
    assert is_authorized(human, Capability.APPEND_AUDIT) is False


def test_system_has_full_audit_capability_set():
    system = Actor(ActorType.SYSTEM, "reconcileai-decision-service")
    assert is_authorized(system, Capability.VIEW_AUDIT) is True
    assert is_authorized(system, Capability.VERIFY_AUDIT) is True
    assert is_authorized(system, Capability.APPEND_AUDIT) is True


def test_verifier_can_append_audit_but_not_change_policy():
    verifier = Actor(ActorType.VERIFIER, "deterministic-verifier")
    assert is_authorized(verifier, Capability.APPEND_AUDIT) is True
    assert is_authorized(verifier, Capability.CHANGE_POLICY) is False


def test_policy_engine_can_only_view_audit():
    policy_engine = Actor(ActorType.POLICY_ENGINE, "policy-engine")
    assert is_authorized(policy_engine, Capability.VIEW_AUDIT) is True
    assert is_authorized(policy_engine, Capability.APPEND_AUDIT) is False
    assert is_authorized(policy_engine, Capability.VERIFY_AUDIT) is False


def test_require_authorization_raises_for_unauthorized_capability():
    ai = Actor(ActorType.AI, "ai-1")
    with pytest.raises(AuthorizationError):
        require_authorization(ai, Capability.APPEND_AUDIT)


def test_require_authorization_silent_for_authorized_capability():
    human = Actor(ActorType.HUMAN, "reviewer-1")
    require_authorization(human, Capability.VIEW_AUDIT)  # must not raise
