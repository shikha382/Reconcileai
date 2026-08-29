"""Milestone 16, Phase 5: a consolidated, honestly-labeled performance
benchmark across the full stack -- ingestion-adjacent deterministic stages
(reconciliation + exception intelligence) at 300/1,000/5,000/10,000
records, and the full AI-investigation + self-challenge + verification +
risk + policy + audit decision pipeline at a smaller range (300/1,000/2,000)
where per-exception AI/audit overhead makes 10,000 impractical to run
repeatedly in a demo environment (each exception's decision pipeline does
real work -- MockAIProvider investigation, Decimal verification, an audit-
ledger append -- unlike the cheap, purely-in-memory reconciliation stage).

ALL data here is synthetic (scripts/benchmark_reconciliation.py's own
generator, reused unchanged, never duplicated), this runs entirely locally,
and every AI-involving number uses MockAIProvider (zero network latency) --
never presented as production-scale or as real-LLM-vendor latency. No
production SLA is implied anywhere in this output.

Run: python scripts/benchmark_full_pipeline_m16.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark_reconciliation import FEE_RULES, generate_benchmark_batch  # noqa: E402

from app.ai.provider import MockAIProvider  # noqa: E402
from app.audit.ledger import AuditLedger  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.engines.reconciliation.engine import reconcile_all  # noqa: E402
from app.policy.approval import ApprovalWorkflowStore  # noqa: E402
from app.services.decision_service import run_decision_pipeline  # noqa: E402
from app.services.exception_service import run_exception_intelligence  # noqa: E402


def benchmark_deterministic_stages(sizes: list[int]) -> None:
    print("=" * 78)
    print("DETERMINISTIC STAGES (reconciliation + exception intelligence)")
    print("Synthetic data, local environment, no AI provider involved.")
    print("=" * 78)
    print(f"{'records':>10} {'reconcile (s)':>15} {'exc.intel (s)':>15} {'total rec/s':>14}")
    for n in sizes:
        payments, settlements, bank_txns = generate_benchmark_batch(n)

        t0 = time.perf_counter()
        results = reconcile_all(payments, settlements, bank_txns, [], FEE_RULES)
        t1 = time.perf_counter()
        assert len(results) == n

        _, bundles = run_exception_intelligence(payments, settlements, bank_txns, [], FEE_RULES)
        t2 = time.perf_counter()
        assert len(bundles) == n

        reconcile_time = t1 - t0
        exc_intel_time = t2 - t1
        total_time = t2 - t0
        rate = n / total_time if total_time > 0 else float("inf")
        print(f"{n:>10} {reconcile_time:>15.3f} {exc_intel_time:>15.3f} {rate:>14.1f}")


def benchmark_full_decision_pipeline(sizes: list[int]) -> None:
    print()
    print("=" * 78)
    print("FULL DECISION PIPELINE (AI investigation -> self-challenge ->")
    print("verification -> risk -> policy -> audit), MockAIProvider, local,")
    print("synthetic data -- NOT a production-scale or real-LLM-latency claim.")
    print("=" * 78)
    print(f"{'records':>10} {'total (s)':>12} {'records/sec':>14}")
    for n in sizes:
        payments, settlements, bank_txns = generate_benchmark_batch(n)
        _, bundles = run_exception_intelligence(payments, settlements, bank_txns, [], FEE_RULES)

        from app.engines.evidence.graph import build_graph
        from app.engines.reconciliation.candidate_generation import build_context

        context = build_context(payments, settlements, bank_txns, [], FEE_RULES)
        graph = build_graph(payments, settlements, bank_txns, [])
        reference_now = max(p.captured_at for p in payments)

        db_path = REPO_ROOT / "scripts" / f"_bench_pipeline_{n}.db"
        if db_path.exists():
            db_path.unlink()
        engine = make_engine(db_path)
        init_db(engine)
        session = make_session_factory(engine)()
        ledger = AuditLedger(session)
        store = ApprovalWorkflowStore()
        provider = MockAIProvider()

        t0 = time.perf_counter()
        for bundle in bundles:
            payment = next(p for p in payments if p.payment_id == bundle.payment_id)
            run_decision_pipeline(payment, bundle, context, graph, provider, ledger, reference_now, store)
            session.commit()
        t1 = time.perf_counter()

        elapsed = t1 - t0
        rate = n / elapsed if elapsed > 0 else float("inf")
        print(f"{n:>10} {elapsed:>12.3f} {rate:>14.1f}")

        session.close()
        engine.dispose()
        db_path.unlink()


if __name__ == "__main__":
    benchmark_deterministic_stages([300, 1000, 5000, 10000])
    benchmark_full_decision_pipeline([300, 1000, 2000])
