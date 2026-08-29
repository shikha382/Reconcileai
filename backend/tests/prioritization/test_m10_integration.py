"""M11 Phase 13: integration with M10 explainability -- NOT a second
explanation system. `attach_priority` adds a structured `PriorityInfo`
section to the EXISTING `ExplanationReport` and appends one rendered
section to its `human_readable` text, reusing the exact reason codes/action
already computed for the queue -- never a separately-worded explanation.
"""
from app.prioritization.scorer import attach_priority, build_prioritized_exception


def test_attach_priority_sets_the_priority_field_on_the_real_explanation(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("fee_mismatch", 0, not_adversarial=False)
    assert explanation.priority is None  # not set until attach_priority runs

    attach_priority(explanation, prioritized)
    assert explanation.priority is not None
    assert explanation.priority.priority == prioritized.priority
    assert explanation.priority.reason_codes == prioritized.reason_codes
    assert explanation.priority.recommended_action == prioritized.recommended_action


def test_attach_priority_appends_to_the_existing_human_readable_text_not_a_new_one(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("ambiguous_match", 0, not_adversarial=False)
    original_text = explanation.human_readable
    attach_priority(explanation, prioritized)

    assert explanation.human_readable.startswith(original_text)  # appended, not replaced
    assert "PRIORITY" in explanation.human_readable
    assert prioritized.priority in explanation.human_readable
    assert prioritized.recommended_action in explanation.human_readable
    for code in prioritized.reason_codes:
        assert code in explanation.human_readable


def test_attach_priority_reason_codes_reference_the_same_structured_facts(get_prioritized):
    from app.prioritization.schemas import ReasonCode

    prioritized, result, explanation, payment, reference_now = get_prioritized("fee_mismatch", 0, not_adversarial=False)
    attach_priority(explanation, prioritized)

    if ReasonCode.CONTRADICTORY_EVIDENCE in explanation.priority.reason_codes:
        assert explanation.contradictions  # the SAME contradictions already on the explanation, not invented anew


def test_explanation_to_dict_includes_priority_once_attached(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("exact_match", 0)
    assert explanation.to_dict()["priority"] is None
    attach_priority(explanation, prioritized)
    d = explanation.to_dict()
    assert d["priority"]["priority"] == prioritized.priority
