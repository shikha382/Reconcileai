"""Milestone 15, Phase 2: computes the one metric the M15 brief insists be
"impossible to miss" on the Overview screen -- the unsafe (false)
auto-resolution rate -- from a completed run's REAL decisions, compared
against a REAL ground_truth.json, when one exists for the dataset that run
used. Never fabricated, never hardcoded: if no ground truth is available
for a run's dataset (e.g. a hypothetical future live-provider run with no
graded expected outcome), this reports `available=False` rather than
inventing a number.

This is the SAME comparison `tests/audit/test_evaluation_m6.py` already
performs inline for its own test assertions -- factored out here so the
API route and that test call one shared, single implementation rather than
two independently-maintained copies of the same logic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.policy.schemas import PolicyDecisionType
from app.services.reconciliation_pipeline import PipelineRunResult


@dataclass
class SafetyMetrics:
    available: bool
    total: int = 0
    graded: int = 0  # how many of `total` had a ground-truth row to compare against
    false_auto_resolutions: int = 0
    false_auto_resolution_rate: float = 0.0
    match_rate: float = 0.0  # matched / records_processed -- always computable, ground-truth-independent
    reason_unavailable: str | None = None


def _load_ground_truth(dataset_dir: Path) -> list[dict] | None:
    gt_path = dataset_dir / "ground_truth.json"
    if not gt_path.exists():
        return None
    try:
        data = json.loads(gt_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, list) else None


def compute_safety_metrics(result: PipelineRunResult) -> SafetyMetrics:
    match_rate = (result.matched / result.records_processed) if result.records_processed else 0.0

    if result.dataset_dir is None:
        return SafetyMetrics(available=False, reason_unavailable="This run did not record its source dataset directory.", match_rate=match_rate)

    ground_truth = _load_ground_truth(result.dataset_dir)
    if ground_truth is None:
        return SafetyMetrics(available=False, reason_unavailable="No ground_truth.json exists for this run's dataset -- this metric requires a graded reference dataset.", match_rate=match_rate)

    gt_by_order = {row["order_id"]: row for row in ground_truth}
    total = len(result.decisions)
    graded = 0
    false_auto_resolutions = 0

    for order_id, decision in result.decisions.items():
        gt = gt_by_order.get(order_id)
        if gt is None:
            continue
        graded += 1
        expected_action = gt.get("expected_action")
        if decision.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE and expected_action != "auto_resolve":
            false_auto_resolutions += 1

    rate = (false_auto_resolutions / graded) if graded else 0.0
    return SafetyMetrics(
        available=True, total=total, graded=graded, false_auto_resolutions=false_auto_resolutions,
        false_auto_resolution_rate=rate, match_rate=match_rate,
    )
