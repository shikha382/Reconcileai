"""Performance benchmark for the M3 exception-intelligence layer at scale.

Reuses scripts/benchmark_reconciliation.py's synthetic data generator (not
M1's locked 300-record dataset generator) so the same mixed load (70% clean
matches, 20% fee-consistent, 10% unlinked/candidate-scored) stresses
classification, evidence, and root-cause code paths together.

Run: python scripts/benchmark_exception_intelligence.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from benchmark_reconciliation import FEE_RULES, generate_benchmark_batch  # noqa: E402

from app.engines.evidence.graph import build_graph  # noqa: E402
from app.engines.reconciliation.candidate_generation import build_context  # noqa: E402
from app.engines.reconciliation.engine import reconcile_all  # noqa: E402
from app.services.exception_service import build_evidence_bundle  # noqa: E402


def run_benchmark(sizes: list[int]) -> None:
    print(f"{'records':>10} {'reconcile(s)':>13} {'evidence(s)':>13} {'total(s)':>10} {'records/sec':>13}")
    for n in sizes:
        payments, settlements, bank_txns = generate_benchmark_batch(n)

        t0 = time.perf_counter()
        results = reconcile_all(payments, settlements, bank_txns, [], FEE_RULES)
        t1 = time.perf_counter()

        context = build_context(payments, settlements, bank_txns, [], FEE_RULES)
        graph = build_graph(payments, settlements, bank_txns, [])
        reference_now = max(p.captured_at for p in payments)

        t2 = time.perf_counter()
        bundles = [
            build_evidence_bundle(payment, result, context, graph, reference_now)
            for payment, result in zip(payments, results)
        ]
        t3 = time.perf_counter()

        reconcile_time = t1 - t0
        evidence_time = t3 - t2
        total_time = reconcile_time + evidence_time
        rate = n / total_time if total_time > 0 else float("inf")

        assert len(bundles) == n
        print(f"{n:>10} {reconcile_time:>13.3f} {evidence_time:>13.3f} {total_time:>10.3f} {rate:>13.1f}")


if __name__ == "__main__":
    run_benchmark([300, 1000, 5000, 10000])
