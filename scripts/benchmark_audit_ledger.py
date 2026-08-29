"""Phase 22 performance benchmark: append / query / chain-verification /
provenance-reconstruction time at 1,000 / 10,000 / 100,000 audit events.

Deliberately the simplest architecture that satisfies the brief -- a single
SQLite table with a SHA-256 hash chain, no blockchain, no Merkle tree, no
distributed infrastructure. This benchmark exercises AuditLedger/verify_chain
directly (not the full decision pipeline) since the brief asks for ledger
performance at these scales, not 100,000 simulated exceptions.

Run: python scripts/benchmark_audit_ledger.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.audit.ledger import AuditLedger  # noqa: E402
from app.audit.provenance import get_decision_provenance  # noqa: E402
from app.audit.verify import verify_chain  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402

BENCH_DB_PATH = REPO_ROOT / "scripts" / "_bench_audit_ledger.db"

# Commits every N appends rather than one commit per event -- a real
# decision pipeline commits once per exception (a handful of events), not
# once per event; batching here just keeps 100,000-event generation itself
# from being commit-bound, it does not change what's being measured.
COMMIT_BATCH = 200


def _generate_events(session, ledger: AuditLedger, count: int) -> float:
    t0 = time.perf_counter()
    for i in range(count):
        correlation_id = f"CORR-{i // 5:08d}"  # ~5 events per simulated exception, like a real run
        ledger.append(
            "EXCEPTION_CREATED" if i % 5 == 0 else "POLICY_EVALUATED",
            "exception", f"EXC-{i // 5:08d}", "SYSTEM", "benchmark",
            {"i": i, "note": "synthetic benchmark event"}, correlation_id, "bench-actor",
        )
        if (i + 1) % COMMIT_BATCH == 0:
            session.commit()
    session.commit()
    return time.perf_counter() - t0


def _bench_scale(n: int) -> None:
    db_path = BENCH_DB_PATH.with_name(f"_bench_audit_ledger_{n}.db")
    if db_path.exists():
        db_path.unlink()
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()
    ledger = AuditLedger(session)

    append_seconds = _generate_events(session, ledger, n)

    t0 = time.perf_counter()
    all_events = ledger.all_events()
    all_events_seconds = time.perf_counter() - t0

    sample_correlation = all_events[len(all_events) // 2].correlation_id
    t0 = time.perf_counter()
    for _ in range(50):
        ledger.events_for_correlation(sample_correlation)
    correlation_query_seconds = (time.perf_counter() - t0) / 50

    t0 = time.perf_counter()
    verify_result = verify_chain(session)
    verify_seconds = time.perf_counter() - t0

    sample_entity = all_events[len(all_events) // 2].entity_id
    t0 = time.perf_counter()
    for _ in range(50):
        get_decision_provenance(session, sample_entity)
    provenance_seconds = (time.perf_counter() - t0) / 50

    print(f"\n--- {n:,} events ---")
    print(f"  append (total):            {append_seconds:.4f}s  ({n / append_seconds:,.0f} events/sec)")
    print(f"  all_events() query:        {all_events_seconds:.4f}s")
    print(f"  events_for_correlation():  {correlation_query_seconds * 1000:.4f}ms (mean of 50 calls)")
    print(f"  verify_chain() full pass:  {verify_seconds:.4f}s ({verify_result.events_checked:,} events, valid={verify_result.valid})")
    print(f"  get_decision_provenance(): {provenance_seconds * 1000:.4f}ms (mean of 50 calls)")

    session.close()
    engine.dispose()
    try:
        db_path.unlink()
    except PermissionError:
        print(f"  (note: could not delete {db_path} immediately)")


def main() -> None:
    print("RECONCILEAI AUDIT LEDGER PERFORMANCE BENCHMARK")
    print("=" * 47)
    for n in (1_000, 10_000, 100_000):
        _bench_scale(n)


if __name__ == "__main__":
    main()
