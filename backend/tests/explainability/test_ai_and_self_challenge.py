"""M10 Phase 7/8: AI hypotheses must always be presented as hypotheses,
never as established fact, and self-challenge results must be exposed
explicitly. AI confidence must never appear as if it settled anything."""
from app.explainability.builder import build_explanation


def test_ai_hypothesis_carries_confidence_as_advisory_only(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    assert explanation.ai_investigation_status == "INVESTIGATED"
    assert explanation.ai_hypotheses, "expected at least one AI hypothesis for an AI-routed case"
    for h in explanation.ai_hypotheses:
        assert 0.0 <= h.ai_confidence <= 1.0
        assert h.final_disposition in ("ACCEPTED", "REJECTED", "NOT_ACCEPTED")
    assert "advisory" in explanation.confidence_note.lower()
    assert "never" in explanation.confidence_note.lower()


def test_rejected_hypothesis_is_never_labeled_accepted(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    fee_hyp = next((h for h in explanation.ai_hypotheses if h.hypothesis_type == "FEE_EXPLAINS_DIFFERENCE"), None)
    assert fee_hyp is not None
    assert fee_hyp.verification_result == "FAILED"
    assert fee_hyp.final_disposition != "ACCEPTED"


def test_verified_hypothesis_is_labeled_accepted_only_when_policy_actually_allowed_it(get_decision):
    # Find a case where AI investigation genuinely succeeds (residual case
    # that resolves safely) -- unexplained_difference archetype cases are
    # AI-routed and some legitimately verify.
    result, payment, settlement, context = get_decision("timing_mismatch", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    for h in explanation.ai_hypotheses:
        if h.final_disposition == "ACCEPTED":
            assert h.verification_result == "PASSED"
            assert explanation.decision == "SAFE_TO_RESOLVE"


def test_ai_not_needed_case_shows_not_needed_never_fabricated_hypotheses(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.ai_investigation_status == "NOT_NEEDED"
    assert explanation.ai_hypotheses == []


def test_self_challenge_trace_exists_for_every_tested_hypothesis(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    assert len(explanation.self_challenge) == len(result.contradiction_records)
    for sc in explanation.self_challenge:
        assert sc.verification_result in ("SUPPORTED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE")
        assert sc.challenge_question  # a real, non-empty question was generated
        assert sc.final_result  # a real, non-empty final result was generated


def test_self_challenge_contradiction_blocks_auto_resolve_and_is_reflected_in_contradictions(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    contradicted_challenges = [s for s in explanation.self_challenge if s.verification_result == "CONTRADICTED"]
    assert contradicted_challenges
    assert explanation.decision != "SAFE_TO_RESOLVE"
    assert explanation.contradictions  # explicitly represented, not hidden inside the self-challenge prose
