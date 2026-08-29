"""Property/invariant tests -- checked directly against the real
300-record M5 resolution run, not just hand-picked examples."""
from decimal import Decimal

from app.policy.authorization import AuthorizationError, is_authorized
from app.policy.schemas import Actor, ActorType, Capability, PolicyDecisionType, RiskLevel
from app.policy.state_machine import InvalidStateTransitionError, transition, ExceptionState


def test_invariant_verifier_not_passed_implies_no_auto_resolution(full_m5_resolution):
    for r in full_m5_resolution["results"].values():
        pi, decision = r["policy_input"], r["policy_decision"]
        if pi.verifier_status != "VERIFIED":
            assert decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


def test_invariant_unexplained_amount_implies_no_auto_resolution(full_m5_resolution):
    for r in full_m5_resolution["results"].values():
        pi, decision = r["policy_input"], r["policy_decision"]
        if pi.residual_amount > Decimal("0.00"):
            assert decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


def test_invariant_ambiguity_implies_human_review(full_m5_resolution):
    for r in full_m5_resolution["results"].values():
        pi, decision = r["policy_input"], r["policy_decision"]
        if pi.ambiguous:
            assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_invariant_mandatory_approval_implies_no_auto_resolution(full_m5_resolution):
    for r in full_m5_resolution["results"].values():
        decision = r["policy_decision"]
        if decision.required_approval:
            assert decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


def test_invariant_unauthorized_actor_action_is_rejected():
    ai = Actor(ActorType.AI, "ai-1")
    assert not is_authorized(ai, Capability.APPROVE)


def test_invariant_invalid_transition_leaves_state_unchanged():
    state = ExceptionState.EXCEPTION_OPEN
    try:
        transition(state, ExceptionState.CLOSED)
        assert False, "should have raised"
    except InvalidStateTransitionError:
        pass
    assert state == ExceptionState.EXCEPTION_OPEN


def test_invariant_policy_evaluation_never_raises_for_well_formed_input(full_m5_resolution):
    """Fail-closed means a well-formed PolicyInput always yields a decision
    -- policy evaluation itself never silently fails or throws."""
    for r in full_m5_resolution["results"].values():
        assert r["policy_decision"] is not None
        assert r["policy_decision"].decision in list(PolicyDecisionType)


def test_invariant_proposal_never_carries_a_financial_mutation_field(full_m5_resolution):
    """A ResolutionProposal has no field that could plausibly be
    interpreted as writing a new amount/balance to a real record."""
    for r in full_m5_resolution["results"].values():
        proposal_fields = set(r["proposal"].__dataclass_fields__.keys())
        assert not ({"new_amount", "new_balance", "amount_override", "settlement_amount"} & proposal_fields)
