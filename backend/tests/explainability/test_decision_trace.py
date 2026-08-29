"""M10 Phase 11: one canonical decision summary -- structured data first,
human-readable text is a presentation of that structure, never a separate
source of truth."""
from app.explainability.builder import build_explanation
from app.explainability.completeness import check_explanation_completeness


def test_final_decision_matches_the_authoritative_policy_decision(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.decision == result.policy_decision.decision.value


def test_decision_status_reflects_review_state_when_a_review_exists(get_decision):
    result, payment, settlement, context = get_decision("ambiguous_match", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    if result.review is not None:
        assert explanation.decision_status == result.review.state.value
    else:
        assert explanation.decision_status == result.policy_decision.decision.value


def test_human_readable_text_contains_the_key_structured_facts(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    text = explanation.human_readable
    assert explanation.decision in text
    assert explanation.payment_id in text
    assert explanation.audit_references.correlation_id in text


def test_audit_references_carry_the_real_correlation_and_exception_ids(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.audit_references.exception_id == result.exception_id
    assert explanation.audit_references.correlation_id == result.correlation_id


def test_explanation_is_complete_for_every_decision_type(get_decision):
    for archetype, kwargs in [
        ("exact_match", {}), ("ambiguous_match", {"not_adversarial": False}),
        ("missing_transaction", {}), ("fee_mismatch", {"not_adversarial": False}),
    ]:
        result, payment, settlement, context = get_decision(archetype, 0, **kwargs)
        explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
        completeness = check_explanation_completeness(explanation)
        assert completeness.explanation_complete, f"{archetype}: missing {completeness.missing_sections}"
