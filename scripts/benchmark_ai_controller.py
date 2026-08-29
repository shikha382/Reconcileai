"""M4 cost/latency benchmark: compares M2/M3 deterministic-only processing
time against M4's AI-assisted resolution (MockAIProvider -- no network
latency, so this measures the CONTROLLER's own overhead, not a real
model's inference time) on the real 300-record M1 dataset.

Run: python scripts/benchmark_ai_controller.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "data" / "synthetic"))

from app.ai.provider import MockAIProvider  # noqa: E402
from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.ingestion.pipeline import ingest_source_directory  # noqa: E402
from app.services.ai_exception_service import resolve_all  # noqa: E402
from app.services.exception_service import run_exception_intelligence  # noqa: E402


def main() -> None:
    seeds = REPO_ROOT / "data" / "synthetic" / "seeds"
    engine = make_engine(REPO_ROOT / "scripts" / "_bench_ai.db")
    init_db(engine)
    session = make_session_factory(engine)()
    ingest_source_directory(session, seeds)
    session.commit()

    payments = session.query(Payment).all()
    settlements = session.query(Settlement).all()
    bank_txns = session.query(BankTransaction).all()
    refunds = session.query(Refund).all()
    fee_rules = session.query(FeeRule).all()

    t0 = time.perf_counter()
    m2_results, bundles = run_exception_intelligence(payments, settlements, bank_txns, refunds, fee_rules)
    t1 = time.perf_counter()
    deterministic_only_seconds = t1 - t0

    t2 = time.perf_counter()
    resolutions = resolve_all(payments, settlements, bank_txns, refunds, fee_rules, MockAIProvider())
    t3 = time.perf_counter()
    ai_assisted_seconds = t3 - t2

    ai_assisted = [r for r in resolutions if r.used_ai]
    total_tool_calls = sum(r.ai_result.trace.tool_call_count for r in ai_assisted)
    total_investigation_time = sum(r.ai_result.trace.duration_seconds or 0 for r in ai_assisted)

    print(f"Records: {len(payments)}")
    print(f"M2/M3 deterministic-only time:  {deterministic_only_seconds:.4f}s")
    print(f"M4 AI-assisted total time:       {ai_assisted_seconds:.4f}s ({ai_assisted_seconds / deterministic_only_seconds:.1f}x)")
    print(f"AI-assisted record count:        {len(ai_assisted)} / {len(payments)} ({100 * len(ai_assisted) / len(payments):.1f}%)")
    print(f"Total tool calls (AI-assisted):  {total_tool_calls}")
    print(f"Mean tool calls per AI case:      {total_tool_calls / len(ai_assisted):.2f}")
    print(f"Mean investigation latency:       {total_investigation_time / len(ai_assisted) * 1000:.3f}ms (MockAIProvider -- no network)")
    print("Note: MockAIProvider has zero network latency and zero token cost; a live")
    print("provider's per-call latency/cost would dominate these numbers instead.")


if __name__ == "__main__":
    main()
