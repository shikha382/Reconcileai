"""Evaluation harness: runs the engine's output against ground_truth.json
and reports every metric honestly -- including, and especially, the safety
metric (incorrect auto-resolutions), which must never be hidden or averaged
away. Ground truth is NEVER modified to make the engine look better; if the
engine's output disagrees with it, that's investigated and documented (see
PROJECT_PLAN.md / CLAUDE.md's M2 entry), not patched around here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.db.models import Payment
from app.engines.reconciliation.types import ReconciliationResult
from shared.taxonomy import ReconciliationStatus

STATUS_TO_EXPECTED_ACTION = {
    ReconciliationStatus.MATCHED: "auto_resolve",
    ReconciliationStatus.PARTIAL: "human_review",
    ReconciliationStatus.MISMATCH: "human_review",
    ReconciliationStatus.AMBIGUOUS: "human_review",
    ReconciliationStatus.UNRESOLVED: "unresolved",
}


@dataclass
class RecordEvaluation:
    order_id: str
    archetype: str
    expected_action: str
    predicted_action: str
    status: str
    method: str
    is_adversarial: bool
    correct_action: bool
    correct_settlement_match: bool | None  # None when status isn't MATCHED (not applicable)
    payment_amount: Decimal
    notes: str = ""


@dataclass
class EvaluationReport:
    total_records: int
    precision: Decimal
    recall: Decimal
    f1: Decimal
    false_match_rate: Decimal
    incorrect_auto_resolution_rate: Decimal
    auto_resolution_rate: Decimal
    human_review_rate: Decimal
    unresolved_rate: Decimal
    ambiguous_rate: Decimal
    exact_match_rate: Decimal
    candidate_match_rate: Decimal
    incorrect_match_count: int
    action_accuracy: Decimal  # fraction where predicted_action == expected_action

    total_transaction_amount: Decimal
    correctly_reconciled_amount: Decimal
    incorrectly_reconciled_amount: Decimal
    unresolved_amount: Decimal
    ambiguous_amount: Decimal

    adversarial_total: int
    adversarial_correctly_blocked: int  # adversarial cases NOT incorrectly auto-resolved

    per_record: list[RecordEvaluation] = field(default_factory=list)
    disagreements: list[RecordEvaluation] = field(default_factory=list)  # engine action != ground truth action


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator == 0:
        return Decimal("0.00")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))


def evaluate(payments: list[Payment], results: list[ReconciliationResult], ground_truth: list[dict]) -> EvaluationReport:
    payments_by_order_id = {p.order_id: p for p in payments}
    results_by_order_id = {r.order_id: r for r in results}
    gt_by_order_id = {g["order_id"]: g for g in ground_truth}

    assert set(gt_by_order_id) == set(results_by_order_id), "results and ground truth must cover the same order set"

    per_record: list[RecordEvaluation] = []

    true_positive = false_positive = false_negative = true_negative = 0
    exact_method_count = candidate_method_count = 0
    total_transaction_amount = Decimal("0.00")
    correctly_reconciled_amount = Decimal("0.00")
    incorrectly_reconciled_amount = Decimal("0.00")
    unresolved_amount = Decimal("0.00")
    ambiguous_amount = Decimal("0.00")
    adversarial_total = 0
    adversarial_correctly_blocked = 0

    for order_id, gt in gt_by_order_id.items():
        result = results_by_order_id[order_id]
        payment = payments_by_order_id[order_id]
        expected_action = gt["expected_action"]
        predicted_action = STATUS_TO_EXPECTED_ACTION[result.status]
        # Precision/recall are scoped to "should this have been safely
        # auto-resolved", NOT "does ground truth happen to know a true
        # settlement id" -- most human_review archetypes (duplicate,
        # over/under_settlement, reversed_transaction, ambiguous_match, ...)
        # DO have a knowable true settlement in ground truth, but the engine
        # correctly declining to auto-resolve them is CORRECT behavior, not
        # a missed match. Counting those as recall-reducing false negatives
        # would make a safety-correct engine look worse than a reckless one.
        should_auto_resolve = expected_action == "auto_resolve"
        total_transaction_amount += payment.amount

        correct_settlement_match: bool | None = None
        if result.status == ReconciliationStatus.MATCHED:
            predicted_ids = set(result.matched_settlement_ids)
            true_ids = set(gt["true_matches"]["settlement_ids"])
            correct_settlement_match = predicted_ids == true_ids

            if should_auto_resolve and correct_settlement_match:
                true_positive += 1
                correctly_reconciled_amount += payment.amount
            else:
                false_positive += 1
                incorrectly_reconciled_amount += payment.amount
        else:
            if should_auto_resolve:
                false_negative += 1
            else:
                true_negative += 1
            if result.status == ReconciliationStatus.UNRESOLVED:
                unresolved_amount += payment.amount
            elif result.status == ReconciliationStatus.AMBIGUOUS:
                ambiguous_amount += payment.amount

        if result.method == "exact_reference":
            exact_method_count += 1
        elif result.method == "candidate_scoring":
            candidate_method_count += 1

        is_incorrect_auto_resolution = (
            result.status == ReconciliationStatus.MATCHED
            and not (should_auto_resolve and correct_settlement_match)
        )

        if gt["is_adversarial"]:
            adversarial_total += 1
            if not is_incorrect_auto_resolution:
                adversarial_correctly_blocked += 1

        record_eval = RecordEvaluation(
            order_id=order_id, archetype=gt["archetype"], expected_action=expected_action,
            predicted_action=predicted_action, status=result.status.value, method=result.method,
            is_adversarial=gt["is_adversarial"], correct_action=(predicted_action == expected_action),
            correct_settlement_match=correct_settlement_match, payment_amount=payment.amount,
            notes=gt.get("notes", ""),
        )
        per_record.append(record_eval)

    total = len(per_record)
    disagreements = [r for r in per_record if not r.correct_action]
    incorrect_match_count = false_positive

    report = EvaluationReport(
        total_records=total,
        precision=_rate(true_positive, true_positive + false_positive),
        recall=_rate(true_positive, true_positive + false_negative),
        f1=Decimal("0.00"),
        false_match_rate=_rate(false_positive, total),
        incorrect_auto_resolution_rate=_rate(false_positive, total),
        auto_resolution_rate=_rate(sum(1 for r in per_record if r.status == "matched"), total),
        human_review_rate=_rate(sum(1 for r in per_record if r.status in ("partial", "mismatch", "ambiguous")), total),
        unresolved_rate=_rate(sum(1 for r in per_record if r.status == "unresolved"), total),
        ambiguous_rate=_rate(sum(1 for r in per_record if r.status == "ambiguous"), total),
        exact_match_rate=_rate(exact_method_count, total),
        candidate_match_rate=_rate(candidate_method_count, total),
        incorrect_match_count=incorrect_match_count,
        action_accuracy=_rate(sum(1 for r in per_record if r.correct_action), total),
        total_transaction_amount=total_transaction_amount,
        correctly_reconciled_amount=correctly_reconciled_amount,
        incorrectly_reconciled_amount=incorrectly_reconciled_amount,
        unresolved_amount=unresolved_amount,
        ambiguous_amount=ambiguous_amount,
        adversarial_total=adversarial_total,
        adversarial_correctly_blocked=adversarial_correctly_blocked,
        per_record=per_record,
        disagreements=disagreements,
    )
    if report.precision + report.recall > 0:
        report.f1 = (2 * report.precision * report.recall / (report.precision + report.recall)).quantize(Decimal("0.0001"))
    return report
