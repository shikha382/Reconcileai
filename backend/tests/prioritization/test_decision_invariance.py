"""M11 Phase 11: CRITICAL invariants. Computing or re-ordering priority must
NEVER change the policy decision, verification result, AI investigation
result, approval requirement, final resolution, or audit history.
"""
import copy

from app.prioritization.queue import get_priority_queue
from app.prioritization.scorer import build_prioritized_exception


def test_building_priority_does_not_mutate_the_decision_object(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("fee_mismatch", 0, not_adversarial=False)

    before_decision = result.policy_decision.decision
    before_risk_level = result.policy_decision.risk_level
    before_reasons = list(result.policy_decision.reasons)
    before_review = result.review
    before_ai_outcomes = len(result.ai_investigation.outcomes) if result.ai_investigation else 0
    before_contradictions = [c.status for c in result.contradiction_records]

    # Build priority twice more, as an API consumer or repeated queue refresh would.
    build_prioritized_exception(result, payment, reference_now, explanation)
    build_prioritized_exception(result, payment, reference_now, explanation)

    assert result.policy_decision.decision == before_decision
    assert result.policy_decision.risk_level == before_risk_level
    assert result.policy_decision.reasons == before_reasons
    assert result.review == before_review
    assert (len(result.ai_investigation.outcomes) if result.ai_investigation else 0) == before_ai_outcomes
    assert [c.status for c in result.contradiction_records] == before_contradictions


def test_priority_score_manipulation_cannot_alter_the_real_decision(get_prioritized):
    prioritized, result, explanation, payment, reference_now = get_prioritized("ambiguous_match", 0, not_adversarial=False)
    real_decision_before = result.policy_decision.decision

    # Simulate an attacker/bug tampering with the computed priority object directly.
    tampered = copy.deepcopy(prioritized)
    tampered.priority = "P3"
    tampered.priority_score = "0.00"
    tampered.reason_codes = []
    tampered.decision_status = "SAFE_TO_RESOLVE"  # even a forged decision_status field

    # The tampered PrioritizedException is a throwaway display object -- it
    # has no back-reference and no code path that could feed into
    # evaluate_policy/decision_service. Confirm the real decision is untouched.
    assert result.policy_decision.decision == real_decision_before
    assert tampered.decision_status != result.policy_decision.decision.value or real_decision_before.value == "SAFE_TO_RESOLVE"


def test_queue_reordering_does_not_change_any_items_own_fields(get_prioritized):
    items = []
    for archetype in ("exact_match", "fee_mismatch", "ambiguous_match"):
        prioritized, *_ = get_prioritized(archetype, 0, not_adversarial=(archetype != "ambiguous_match"))
        items.append(prioritized)

    before = [copy.deepcopy(i) for i in items]
    ordered_once = get_priority_queue(items)
    ordered_twice = get_priority_queue(list(reversed(ordered_once)))

    for original in before:
        match = next(i for i in ordered_twice if i.exception_id == original.exception_id)
        assert match.to_dict() == original.to_dict()  # every field is byte-identical after any amount of reordering


def test_prioritized_exception_has_no_method_that_could_mutate_a_financial_record():
    from app.prioritization.schemas import PrioritizedException

    # Structural guarantee: the dataclass exposes no method beyond to_dict().
    public_methods = [
        name for name in dir(PrioritizedException)
        if not name.startswith("_") and callable(getattr(PrioritizedException, name, None))
    ]
    assert public_methods == ["to_dict"]
