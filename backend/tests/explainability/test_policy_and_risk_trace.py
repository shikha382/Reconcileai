"""M10 Phase 9/10: policy and risk traces must come FROM the actual policy
engine and risk score -- the explanation layer describes policy, it does
not recompute or become policy."""
from app.explainability.builder import build_explanation


def test_policy_trace_matches_the_real_policy_decision_exactly(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    real = result.policy_decision
    assert explanation.policy.decision == real.decision.value
    assert explanation.policy.policy_id == real.policy_id
    assert explanation.policy.policy_version == real.policy_version
    assert explanation.policy.rules_evaluated == real.rules_evaluated
    assert explanation.policy.rules_passed == real.rules_passed
    assert explanation.policy.rules_failed == real.rules_failed
    assert explanation.policy.reasons == real.reasons
    assert explanation.policy.blocked_reasons == real.blocked_reasons
    assert explanation.policy.required_approval == real.required_approval
    assert explanation.policy.risk_level == real.risk_level.value


def test_risk_trace_uses_the_real_risk_score_and_level(get_decision):
    result, payment, settlement, context = get_decision("ambiguous_match", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    assert explanation.risk.risk_score == str(result.bundle.risk_score)
    assert explanation.risk.risk_level == result.policy_decision.risk_level.value
    assert explanation.risk.reasons  # never an empty, unexplained risk classification


def test_risk_reasons_are_derived_from_real_conditions_not_invented(get_decision):
    # A clean auto-resolved case must show a real, honest "nothing wrong" reason.
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.decision == "SAFE_TO_RESOLVE"
    assert explanation.risk.reasons == ["none -- within normal parameters"]


def test_policy_reasons_reflect_a_genuine_block_when_verifier_contradicted(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.policy.decision == "REJECTED"
    assert explanation.policy.blocked_reasons or explanation.policy.reasons
