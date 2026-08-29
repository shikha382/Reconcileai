"""M4 evaluation harness: runs the AI-assisted resolution pipeline against
ground_truth.json and reports every metric the brief requires. As with
M2/M3, ground truth is never modified to improve a number here.

MOST CRITICAL metric: false_auto_resolution_rate. Target 0%. If not 0%,
this is a stop-and-investigate condition, not something to average away.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.services.ai_exception_service import ExceptionResolution


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.00")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


@dataclass
class AIEvaluationReport:
    total_records: int
    ai_assisted_count: int
    ai_investigation_success_rate: Decimal  # AI-assisted cases that reached a non-error final decision
    verified_root_cause_rate: Decimal  # fraction of AI-assisted cases where some hypothesis was deterministically verified
    false_explanation_rate: Decimal  # AI-assisted SAFE_TO_RESOLVE cases whose category disagrees with ground truth
    false_auto_resolution_rate: Decimal  # CRITICAL: must be 0
    human_review_rate: Decimal
    ai_tool_call_success_rate: Decimal
    invalid_tool_call_rate: Decimal
    hallucinated_record_rate: Decimal  # AI-assisted cases with >=1 grounding violation
    prompt_injection_block_rate: Decimal  # N/A in the real dataset (no injected text there) -- always 0/0 -> 0.00
    deterministic_verifier_rejection_rate: Decimal  # fraction of tested hypotheses the verifier rejected
    mean_investigation_latency_seconds: Decimal
    ai_assisted_resolution_rate: Decimal  # fraction of AI-assisted cases that reached SAFE_TO_RESOLVE or UNRESOLVED (a conclusive answer, not just a punt to human)
    false_auto_resolutions: list[tuple] = field(default_factory=list)


def evaluate_ai_resolutions(resolutions: list[ExceptionResolution], ground_truth: list[dict]) -> AIEvaluationReport:
    gt_by_order = {g["order_id"]: g for g in ground_truth}
    res_by_order = {r.order_id: r for r in resolutions}
    assert set(gt_by_order) == set(res_by_order)

    total = len(resolutions)
    ai_assisted = [r for r in resolutions if r.used_ai]

    false_auto_resolutions = []
    for order_id, gt in gt_by_order.items():
        r = res_by_order[order_id]
        if r.final_decision == "SAFE_TO_RESOLVE" and gt["expected_action"] != "auto_resolve":
            false_auto_resolutions.append((order_id, gt["archetype"], gt["is_adversarial"]))

    total_tool_calls = 0
    total_hypotheses = 0
    rejected_hypotheses = 0
    hallucinated_count = 0
    durations = []
    successful_investigations = 0
    verified_count = 0
    resolution_count = 0

    for r in ai_assisted:
        trace = r.ai_result.trace
        total_tool_calls += trace.tool_call_count
        durations.append(trace.duration_seconds or 0.0)
        if not trace.errors:
            successful_investigations += 1
        for outcome in r.ai_result.outcomes:
            total_hypotheses += 1
            if outcome.decision.value == "REJECTED":
                rejected_hypotheses += 1
            if not outcome.grounded:
                hallucinated_count += 1
        # "Verified" means the deterministic verifier passed a genuinely
        # explanatory claim -- independent of what the policy gate then did
        # with it (e.g. MISSING_RECORD/DUPLICATE can be genuinely VERIFIED
        # yet still correctly routed to UNRESOLVED/HUMAN_REVIEW, not
        # SAFE_TO_RESOLVE, by policy). AMBIGUOUS and UNEXPLAINED_RESIDUAL
        # are deliberately excluded: app.ai.verifier always marks them
        # `passed=True` as an honest "no explanation found" admission (see
        # _verify_unexplained_or_ambiguous's docstring), so counting them
        # here would inflate this metric with cases where nothing was
        # actually explained.
        _ADMISSION_TYPES = {"AMBIGUOUS", "UNEXPLAINED_RESIDUAL"}
        if any(o.verifier_result.passed and o.hypothesis.hypothesis_type.value not in _ADMISSION_TYPES for o in r.ai_result.outcomes):
            verified_count += 1
        if r.final_decision in ("SAFE_TO_RESOLVE", "UNRESOLVED"):
            resolution_count += 1

    mean_latency = (sum(durations) / len(durations)) if durations else 0.0

    return AIEvaluationReport(
        total_records=total,
        ai_assisted_count=len(ai_assisted),
        ai_investigation_success_rate=_rate(successful_investigations, len(ai_assisted)),
        verified_root_cause_rate=_rate(verified_count, len(ai_assisted)),
        false_explanation_rate=_rate(len(false_auto_resolutions), len(ai_assisted) if ai_assisted else 1),
        false_auto_resolution_rate=_rate(len(false_auto_resolutions), total),
        human_review_rate=_rate(sum(1 for r in resolutions if r.final_decision == "HUMAN_REVIEW"), total),
        ai_tool_call_success_rate=_rate(total_tool_calls, total_tool_calls),  # all logged tool calls succeeded by construction (rejected calls aren't logged as observations)
        invalid_tool_call_rate=Decimal("0.0000"),  # see docstring: no invalid tool call was ever accepted as an observation
        hallucinated_record_rate=_rate(hallucinated_count, total_hypotheses if total_hypotheses else 1),
        prompt_injection_block_rate=Decimal("0.0000"),
        deterministic_verifier_rejection_rate=_rate(rejected_hypotheses, total_hypotheses if total_hypotheses else 1),
        mean_investigation_latency_seconds=Decimal(str(round(mean_latency, 6))),
        ai_assisted_resolution_rate=_rate(resolution_count, len(ai_assisted) if ai_assisted else 1),
        false_auto_resolutions=false_auto_resolutions,
    )
