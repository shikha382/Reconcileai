"""Policy dry-run / what-if simulation -- the same input must be evaluable
against a different policy version without affecting the real decision."""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from app.policy.simulation import simulate

from .factories import make_policy_input


def test_current_policy_version_auto_resolves_a_moderate_case():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", financial_exposure="5000.00")
    result = simulate(policy_input, "1.0.0")
    assert result.decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE


def test_stricter_draft_policy_requires_review_for_the_same_input():
    """The brief's own worked example: Rs 5,000 verified fee mismatch is
    SAFE under v1.0.0 but HUMAN_REVIEW under a stricter draft version --
    the policy difference must be visible, not silently absorbed."""
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", financial_exposure="5000.00")
    result = simulate(policy_input, "2.0.0-stricter-draft")
    assert result.decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert result.would_change_from_current


def test_simulation_never_mutates_the_live_policy_afterward():
    from app.policy.engine import MAX_AUTO_RESOLVE_EXPOSURE, POLICY_VERSION

    original_threshold = MAX_AUTO_RESOLVE_EXPOSURE
    original_version = POLICY_VERSION
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", financial_exposure="5000.00")
    simulate(policy_input, "2.0.0-stricter-draft")

    import app.policy.engine as engine_module

    assert engine_module.MAX_AUTO_RESOLVE_EXPOSURE == original_threshold
    assert engine_module.POLICY_VERSION == original_version


def test_unknown_policy_version_raises():
    import pytest

    policy_input = make_policy_input()
    with pytest.raises(ValueError):
        simulate(policy_input, "9.9.9-does-not-exist")
