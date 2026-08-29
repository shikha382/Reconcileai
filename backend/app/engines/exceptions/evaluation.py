"""M3 evaluation harness: runs the exception-intelligence layer against
ground_truth.json and reports every metric honestly. As with M2, ground
truth is never modified to improve a number here -- if the engine disagrees
with it, that's investigated and documented (see CLAUDE.md's M3 entry for
the one confirmed, intentional case: reversed_transaction correctly reaches
VERIFIED root-cause status even though ground truth's `expected_action`
says human_review -- those are different questions, see below).

MOST IMPORTANT metric: false_explanation_rate -- the percentage of VERIFIED
exceptions whose claimed category does not match ground truth's category.
Target: 0%.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.engines.evidence.bundle import EvidenceBundle
from app.engines.root_cause.result import AMBIGUOUS, CONTRADICTED, PARTIALLY_EXPLAINED, UNEXPLAINED, VERIFIED


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.00")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


@dataclass
class ExceptionEvaluationReport:
    total_records: int
    exception_classification_accuracy: Decimal
    root_cause_status_accuracy: Decimal
    verified_explanation_rate: Decimal
    unexplained_residual_rate: Decimal
    partially_explained_rate: Decimal
    ambiguous_rate: Decimal
    contradicted_rate: Decimal
    false_explanation_rate: Decimal
    false_root_cause_rate: Decimal
    average_candidates_evaluated: Decimal
    average_evidence_records_generated: Decimal
    category_mismatches: list[tuple] = field(default_factory=list)
    false_explanations: list[tuple] = field(default_factory=list)


# What root-cause STATUS is expected for each archetype, independent of
# ground_truth.expected_action (a policy question M3 does not answer --
# see module docstring). Adversarial cases are handled separately (they
# must never be VERIFIED, regardless of archetype).
_EXPECTED_STATUS_BY_ARCHETYPE = {
    "exact_match": VERIFIED,
    "timing_mismatch": VERIFIED,
    "fee_mismatch": VERIFIED,  # non-adversarial only; adversarial handled separately
    "refund_mismatch": VERIFIED,
    "split_settlement": VERIFIED,
    "aggregated_settlement": VERIFIED,
    "reversed_transaction": VERIFIED,  # the reversal ITSELF is a verified fact -- see docstring
    "partial_settlement": PARTIALLY_EXPLAINED,
    "under_settlement": PARTIALLY_EXPLAINED,
    "over_settlement": UNEXPLAINED,
    "unexplained_difference": UNEXPLAINED,
    "missing_transaction": UNEXPLAINED,
    "reference_mismatch": VERIFIED,
    "duplicate": AMBIGUOUS,
    "ambiguous_match": AMBIGUOUS,
}


def evaluate_exceptions(bundles: list[EvidenceBundle], ground_truth: list[dict]) -> ExceptionEvaluationReport:
    gt_by_order = {g["order_id"]: g for g in ground_truth}
    bundles_by_order = {b.order_id: b for b in bundles}
    assert set(gt_by_order) == set(bundles_by_order)

    total = len(bundles)
    category_correct = 0
    root_cause_status_correct = 0
    status_counts = {VERIFIED: 0, PARTIALLY_EXPLAINED: 0, UNEXPLAINED: 0, CONTRADICTED: 0, AMBIGUOUS: 0}
    false_explanations: list[tuple] = []
    category_mismatches: list[tuple] = []
    candidate_counts: list[int] = []
    evidence_counts: list[int] = []

    for order_id, gt in gt_by_order.items():
        bundle = bundles_by_order[order_id]
        rc = bundle.root_cause
        status_counts[rc.status] = status_counts.get(rc.status, 0) + 1

        if bundle.category == gt["category"]:
            category_correct += 1
        else:
            category_mismatches.append((order_id, gt["archetype"], gt["category"], bundle.category))

        if rc.status == VERIFIED and bundle.category != gt["category"]:
            false_explanations.append((order_id, gt["archetype"], gt["category"], bundle.category))

        expected_status = AMBIGUOUS if gt["is_adversarial"] else _EXPECTED_STATUS_BY_ARCHETYPE.get(gt["archetype"])
        if gt["is_adversarial"]:
            # Adversarial cases must never be VERIFIED -- any non-VERIFIED
            # status (AMBIGUOUS or CONTRADICTED, both seen in practice) is
            # correct here.
            if rc.status != VERIFIED:
                root_cause_status_correct += 1
        elif rc.status == expected_status:
            root_cause_status_correct += 1

        n_candidates = len(bundle.negative_evidence_report.candidates)
        candidate_counts.append(n_candidates)
        evidence_counts.append(sum(len(c.constraints) for c in bundle.negative_evidence_report.candidates))

    verified_count = status_counts.get(VERIFIED, 0)
    false_root_cause = [m for m in category_mismatches]  # every mismatch is a wrong root-cause label, not just VERIFIED ones

    return ExceptionEvaluationReport(
        total_records=total,
        exception_classification_accuracy=_rate(category_correct, total),
        root_cause_status_accuracy=_rate(root_cause_status_correct, total),
        verified_explanation_rate=_rate(status_counts.get(VERIFIED, 0), total),
        unexplained_residual_rate=_rate(status_counts.get(UNEXPLAINED, 0), total),
        partially_explained_rate=_rate(status_counts.get(PARTIALLY_EXPLAINED, 0), total),
        ambiguous_rate=_rate(status_counts.get(AMBIGUOUS, 0), total),
        contradicted_rate=_rate(status_counts.get(CONTRADICTED, 0), total),
        false_explanation_rate=_rate(len(false_explanations), verified_count if verified_count else 1),
        false_root_cause_rate=_rate(len(false_root_cause), total),
        average_candidates_evaluated=(sum(candidate_counts) / Decimal(len(candidate_counts))).quantize(Decimal("0.01")) if candidate_counts else Decimal("0"),
        average_evidence_records_generated=(sum(evidence_counts) / Decimal(len(evidence_counts))).quantize(Decimal("0.01")) if evidence_counts else Decimal("0"),
        category_mismatches=category_mismatches,
        false_explanations=false_explanations,
    )
