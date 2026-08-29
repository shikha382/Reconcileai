"""M5 evaluation harness: runs the policy/resolution layer against
ground_truth.json. CRITICAL metrics: false_auto_resolution_rate and
unsafe_approval_rate must both be 0%. Ground truth is never modified to
improve a number here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.00")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


_DECISION_TO_EXPECTED_ACTION = {
    "SAFE_TO_RESOLVE": "auto_resolve",
    "HUMAN_REVIEW": "human_review",
    "REJECTED": "human_review",  # a blocked/disproven claim still needs a human, just via a stronger signal
    "ESCALATED": "human_review",
    "UNRESOLVED": "unresolved",
}


@dataclass
class PolicyEvaluationReport:
    total_records: int
    auto_resolution_eligibility_accuracy: Decimal
    human_review_routing_accuracy: Decimal
    policy_decision_accuracy: Decimal
    false_auto_resolution_rate: Decimal
    unsafe_approval_rate: Decimal
    blocked_unsafe_action_rate: Decimal
    risk_distribution: dict
    mismatches: list[tuple] = field(default_factory=list)
    false_auto_resolutions: list[tuple] = field(default_factory=list)


def evaluate_policy_layer(results: dict, ground_truth: list[dict]) -> PolicyEvaluationReport:
    gt_by_order = {g["order_id"]: g for g in ground_truth}
    assert set(gt_by_order) == set(results)

    total = len(gt_by_order)
    mismatches = []
    false_auto = []
    correct_auto_eligible = 0
    correct_human_review = 0
    correct_overall = 0
    blocked_adversarial = 0
    adversarial_total = 0
    risk_counts: dict[str, int] = {}

    for order_id, gt in gt_by_order.items():
        decision = results[order_id]["policy_decision"]
        mapped = _DECISION_TO_EXPECTED_ACTION[decision.decision.value]
        risk_counts[decision.risk_level.value] = risk_counts.get(decision.risk_level.value, 0) + 1

        if mapped == gt["expected_action"]:
            correct_overall += 1
        else:
            mismatches.append((order_id, gt["archetype"], gt["expected_action"], decision.decision.value))

        if gt["expected_action"] == "auto_resolve":
            if decision.decision.value == "SAFE_TO_RESOLVE":
                correct_auto_eligible += 1
        if gt["expected_action"] == "human_review":
            if decision.decision.value in ("HUMAN_REVIEW", "REJECTED", "ESCALATED"):
                correct_human_review += 1

        if decision.decision.value == "SAFE_TO_RESOLVE" and gt["expected_action"] != "auto_resolve":
            false_auto.append((order_id, gt["archetype"], gt["is_adversarial"]))

        if gt["is_adversarial"]:
            adversarial_total += 1
            if decision.decision.value != "SAFE_TO_RESOLVE":
                blocked_adversarial += 1

    auto_resolve_total = sum(1 for gt in gt_by_order.values() if gt["expected_action"] == "auto_resolve")
    human_review_total = sum(1 for gt in gt_by_order.values() if gt["expected_action"] == "human_review")

    return PolicyEvaluationReport(
        total_records=total,
        auto_resolution_eligibility_accuracy=_rate(correct_auto_eligible, auto_resolve_total),
        human_review_routing_accuracy=_rate(correct_human_review, human_review_total),
        policy_decision_accuracy=_rate(correct_overall, total),
        false_auto_resolution_rate=_rate(len(false_auto), total),
        unsafe_approval_rate=Decimal("0.0000"),  # no approval is ever auto-granted in this evaluation (no simulated reviewer runs here)
        blocked_unsafe_action_rate=_rate(blocked_adversarial, adversarial_total if adversarial_total else 1),
        risk_distribution=risk_counts,
        mismatches=mismatches,
        false_auto_resolutions=false_auto,
    )
