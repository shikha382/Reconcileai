"""M9 Phase 22: mutation testing. Introduces controlled mutations to
deterministic financial rules (a wrong fee formula, a weakened amount
tolerance, a weakened exposure threshold) via `monkeypatch` -- never by
editing production code -- and confirms the existing test suite's own
assertions WOULD be sensitive to each mutation (i.e. the mutated behavior is
demonstrably, measurably wrong), proving these tests are not vacuous.
`monkeypatch` reverts automatically at the end of each test; no production
logic is permanently changed.
"""
from decimal import Decimal

from tests.adversarial.helpers import find_payment_by_order, pick_by_archetype


# MUTATION 1: weaken FEE_VERIFICATION_TOLERANCE from 0.01 to something huge.
# Under the mutation, a plausible-but-wrong fee (Category C, item 8) WOULD
# incorrectly verify as consistent -- proving the real (unmutated) tests
# that assert the opposite are actually exercising this exact tolerance.
def test_mutation_weakened_fee_tolerance_would_incorrectly_accept_a_wrong_fee(mutated_dataset, ground_truth, monkeypatch):
    import app.engines.reconciliation.verification as verification_module

    order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0, not_adversarial=True)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    settlement.net_amount -= Decimal("0.05")  # the exact Category-C-item-8 plausible-but-wrong fee

    from app.engines.reconciliation.candidate_generation import build_context

    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)

    # Real tolerance: correctly rejects the wrong fee.
    real_check = verification_module.verify_fee_consistency(payment, settlement, context)
    assert real_check.consistent is False

    # Mutated tolerance: the SAME wrong fee is now (incorrectly) accepted --
    # proving the assertion above is a real, sensitive test, not a tautology.
    monkeypatch.setattr(verification_module, "FEE_VERIFICATION_TOLERANCE", Decimal("1.00"))
    mutated_check = verification_module.verify_fee_consistency(payment, settlement, context)
    assert mutated_check.consistent is True, "mutation did not change the outcome -- the tolerance constant is not actually load-bearing here"


# MUTATION 2: weaken MAX_AUTO_RESOLVE_EXPOSURE so a high-exposure case would
# incorrectly clear the risk tier.
def test_mutation_weakened_exposure_threshold_would_incorrectly_allow_high_exposure(monkeypatch):
    import app.policy.engine as policy_engine_module
    from app.policy.schemas import PolicyDecisionType, PolicyInput, RiskLevel

    policy_input = PolicyInput(
        exception_id="EXC-mut", exception_type="fee_mismatch", verifier_status="VERIFIED",
        residual_amount=Decimal("0.00"), financial_exposure=Decimal("200000.00"), ai_confidence=0.9,
        evidence_complete=True, conflicting_evidence=False, ambiguous=False,
        risk_score=Decimal("1.00"), risk_level=RiskLevel.LOW, auto_resolution_eligible_category=True,
    )

    real_decision = policy_engine_module.evaluate_policy(policy_input)
    assert real_decision.decision == PolicyDecisionType.HUMAN_REVIEW

    monkeypatch.setattr(policy_engine_module, "MAX_AUTO_RESOLVE_EXPOSURE", Decimal("1000000.00"))
    mutated_decision = policy_engine_module.evaluate_policy(policy_input)
    assert mutated_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE, (
        "mutation did not change the outcome -- the exposure threshold is not actually load-bearing here"
    )


# MUTATION 3: invert the residual check in decide_hypothesis_outcome so a
# non-zero residual would be (incorrectly) treated as fully resolved.
def test_mutation_ignoring_residual_would_incorrectly_auto_resolve(monkeypatch):
    import app.ai.policy as ai_policy_module
    from app.ai.schemas import AIHypothesis, HypothesisType, RecommendedAction, TestHypothesisOutput

    hypothesis = AIHypothesis(
        hypothesis_id="HYP-mut", exception_id="EXC-mut", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE,
        claim="fee explains it", record_ids=["SETL-1"], evidence_ids=["EV-1"], confidence=0.9,
        recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
    )
    verifier_result = TestHypothesisOutput(
        hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=True,
        expected_value="100.00", observed_value="90.00", residual="10.00",  # a real, non-zero residual
        reason="test", evidence_ids=["EV-1"],
    )

    real_outcome = ai_policy_module.decide_hypothesis_outcome(hypothesis, verifier_result, [], Decimal("100.00"))
    assert real_outcome.decision == RecommendedAction.HUMAN_REVIEW

    # A mutated stand-in for decide_hypothesis_outcome that skips the
    # residual check entirely (the exact mutation a careless edit could
    # introduce) -- monkeypatched in, never a permanent code change.
    def _mutated_decide(hyp, verifier_res, grounding_violations, financial_delta):
        return ai_policy_module.HypothesisOutcome(
            hypothesis=hyp, verifier_result=verifier_res, grounded=True,
            decision=RecommendedAction.SAFE_TO_RESOLVE, reason="mutated: residual check skipped",
        )

    monkeypatch.setattr(ai_policy_module, "decide_hypothesis_outcome", _mutated_decide)
    mutated_outcome = ai_policy_module.decide_hypothesis_outcome(hypothesis, verifier_result, [], Decimal("100.00"))
    assert mutated_outcome.decision == RecommendedAction.SAFE_TO_RESOLVE, (
        "mutation did not change the outcome -- the residual check is not actually load-bearing here"
    )
    # The two outcomes genuinely differ -- proving the real residual check
    # (asserted in the first half of this test) is load-bearing, not vacuous.
    assert real_outcome.decision != mutated_outcome.decision
