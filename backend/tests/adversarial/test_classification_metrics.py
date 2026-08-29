"""M9 Phase 20: confusion matrix / classification metrics -- computed ONLY
where the underlying task genuinely is classification (exception category
assignment against the real dataset's own ground truth). No metric is
manufactured for a task that isn't actually a classification problem (e.g.
policy decisions are a controlled state machine, not a classifier, so no
precision/recall is computed for them anywhere in this suite).
"""
from collections import defaultdict

from tests.adversarial.helpers import Dataset


def test_exception_category_classification_confusion_matrix(base_dataset: Dataset, ground_truth):
    from app.services.exception_service import run_exception_intelligence

    _, bundles = run_exception_intelligence(
        base_dataset.payments, base_dataset.settlements, base_dataset.bank_transactions,
        base_dataset.refunds, base_dataset.fee_rules,
    )
    by_order = {b.order_id: b for b in bundles}
    gt_by_order = {row["order_id"]: row for row in ground_truth}

    labels = sorted({row["category"] for row in ground_truth if row["category"] is not None})
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    correct = 0
    total_labeled = 0

    for order_id, gt in gt_by_order.items():
        expected_category = gt["category"]
        if expected_category is None:
            continue  # clean matches have no category to classify -- not part of this task
        total_labeled += 1
        actual_category = by_order[order_id].category
        if actual_category == expected_category:
            correct += 1
            tp[expected_category] += 1
        else:
            fn[expected_category] += 1
            if actual_category is not None:
                fp[actual_category] += 1

    accuracy = correct / total_labeled

    precisions, recalls, f1s = [], [], []
    print("\n\nM9 EXCEPTION CATEGORY CLASSIFICATION METRICS")
    print(f"{'category':<28} {'TP':<5} {'FP':<5} {'FN':<5} {'precision':<10} {'recall':<10} {'F1'}")
    for label in labels:
        p = tp[label] / (tp[label] + fp[label]) if (tp[label] + fp[label]) > 0 else 1.0
        r = tp[label] / (tp[label] + fn[label]) if (tp[label] + fn[label]) > 0 else 1.0
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        precisions.append(p); recalls.append(r); f1s.append(f1)
        print(f"{label:<28} {tp[label]:<5} {fp[label]:<5} {fn[label]:<5} {p:<10.4f} {r:<10.4f} {f1:.4f}")

    macro_precision = sum(precisions) / len(precisions)
    macro_recall = sum(recalls) / len(recalls)
    macro_f1 = sum(f1s) / len(f1s)
    print(f"\naccuracy={accuracy:.4f}  macro_precision={macro_precision:.4f}  macro_recall={macro_recall:.4f}  macro_f1={macro_f1:.4f}\n")

    assert accuracy == 1.0, "exception category classification must remain 100% on the real, unmutated dataset (M3's established baseline)"
    assert macro_f1 == 1.0
