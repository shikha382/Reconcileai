"""Milestone 14, Phase 28: benchmarks the adapter/mapping/ingestion path at
scale, entirely offline (no network call is ever made -- this measures
FIXTURE-mode throughput only, clearly distinct from live-provider network
latency, which is not measured anywhere in this project since no live
provider is exercised in this environment).

Run: python scripts/benchmark_provider_adapter.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.adapters.razorpay_mapping import map_razorpay_payment  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.ingestion.pipeline import ingest_records  # noqa: E402


def _generate_payments(n: int) -> list[dict]:
    return [
        {
            "id": f"pay_BENCH{i:07d}", "entity": "payment", "amount": 100000 + i, "currency": "INR",
            "status": "captured", "order_id": f"order_BENCH{i:07d}", "method": "upi",
            "captured": True, "created_at": 1785574800 + i, "notes": {},
        }
        for i in range(n)
    ]


def run_benchmark(n: int) -> None:
    raw_payments = _generate_payments(n)

    started = time.monotonic()
    canonical = [map_razorpay_payment(r).canonical for r in raw_payments]
    mapping_time = time.monotonic() - started
    assert all(c is not None for c in canonical)

    db_path = REPO_ROOT / "scripts" / f"_bench_adapter_{n}.db"
    if db_path.exists():
        db_path.unlink()
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()

    started = time.monotonic()
    validation_report = ingest_records(session, "payment", canonical, raise_on_invalid=True)
    session.commit()
    ingestion_time = time.monotonic() - started

    session.close()
    engine.dispose()
    db_path.unlink()

    print(f"n={n:>6}  mapping={mapping_time:.4f}s ({n / mapping_time:.0f} rec/s)  "
          f"ingestion(validate+normalize+persist)={ingestion_time:.4f}s ({n / ingestion_time:.0f} rec/s)  "
          f"valid={len(validation_report.valid_records)}/{n}")


def main() -> None:
    print("=" * 70)
    print("RECONCILEAI -- PROVIDER ADAPTER PERFORMANCE (Milestone 14)")
    print("Fixture-mode only -- no network call is ever made in this benchmark.")
    print("=" * 70)
    for n in (300, 1000):
        run_benchmark(n)


if __name__ == "__main__":
    main()
