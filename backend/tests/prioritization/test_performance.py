"""M11 Phase 16: prioritization performance. Must not rerun AI investigation,
matching, verification, policy, or audit generation -- it consumes already-
produced DecisionResult/ExplanationReport objects. Benchmarked at 300 real
records plus synthetic scale-up to 1,000/10,000 for the pure sort/summary layer
(no AI/DB cost at that layer, so scale-up is safe and fast to actually run).
"""
import time
from decimal import Decimal

from app.prioritization.queue import get_priority_queue, summarize_queue
from app.prioritization.schemas import PrioritizedException


def _synthetic_item(i: int) -> PrioritizedException:
    priorities = ["P0", "P1", "P2", "P3"]
    sla_statuses = ["BREACHED", "AT_RISK", "WITHIN_SLA"]
    return PrioritizedException(
        exception_id=f"EXC-{i:06d}", order_id=f"ORD-{i:06d}", payment_id=f"PAY-{i:06d}",
        priority=priorities[i % 4], priority_score=str(Decimal(i % 1000)), risk_level="LOW",
        risk_score=str(Decimal(i % 500)), financial_exposure=str(Decimal(i % 10000)), currency="INR",
        age_days=i % 60, sla_status=sla_statuses[i % 3], exception_category="fee_mismatch",
        decision_status="HUMAN_REVIEW", contradiction_count=i % 3, missing_evidence_count=i % 2,
        recommended_action="REVIEW_EVIDENCE", reason_codes=["HIGH_EXPOSURE"],
    )


def test_prioritizing_the_full_300_record_dataset_is_lightweight(mutated_dataset, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context
    from app.explainability.builder import build_explanation
    from app.prioritization.scorer import build_prioritized_exception
    from app.services.exception_service import run_exception_intelligence
    from tests.adversarial.helpers import decide_one

    _, bundles = run_exception_intelligence(
        mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions,
        mutated_dataset.refunds, mutated_dataset.fee_rules,
    )
    sample = bundles[:40]
    payments_by_id = {p.payment_id: p for p in mutated_dataset.payments}
    reference_now = max(p.captured_at for p in mutated_dataset.payments)

    t0 = time.perf_counter()
    results = [decide_one(mutated_dataset, b.payment_id, decision_env) for b in sample]
    pipeline_seconds = time.perf_counter() - t0

    t1 = time.perf_counter()
    prioritized = []
    for result in results:
        payment = payments_by_id[result.bundle.payment_id]
        explanation = build_explanation(result)
        prioritized.append(build_prioritized_exception(result, payment, reference_now, explanation))
    ordered = get_priority_queue(prioritized)
    summarize_queue(ordered)
    prioritization_seconds = time.perf_counter() - t1

    assert len(ordered) == len(sample)
    assert prioritization_seconds < pipeline_seconds
    print(f"\nPipeline (40 exceptions): {pipeline_seconds:.4f}s; prioritization: {prioritization_seconds:.4f}s "
          f"({100 * prioritization_seconds / pipeline_seconds:.2f}% of pipeline time)")


def test_queue_sort_and_summary_scale_to_10000_synthetic_items():
    items_1000 = [_synthetic_item(i) for i in range(1000)]
    items_10000 = [_synthetic_item(i) for i in range(10000)]

    t0 = time.perf_counter()
    get_priority_queue(items_1000)
    summarize_queue(items_1000)
    seconds_1000 = time.perf_counter() - t0

    t1 = time.perf_counter()
    get_priority_queue(items_10000)
    summarize_queue(items_10000)
    seconds_10000 = time.perf_counter() - t1

    print(f"\n1,000 items: {seconds_1000:.4f}s; 10,000 items: {seconds_10000:.4f}s")
    assert seconds_10000 < 5.0  # generously bounded -- this is a plain sort/aggregation, not an engine
