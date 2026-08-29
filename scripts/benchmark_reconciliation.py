"""Performance benchmark for the M2 reconciliation engine at scale.

This is a SEPARATE, lightweight synthetic generator from
data/synthetic/generator.py -- it does not touch or reuse M1's dataset
generator (which is locked to producing exactly 300 ground-truthed records
with a fixed archetype distribution) and makes no correctness claims; it
exists purely to stress the matching/candidate-generation/scoring code paths
at 1,000 / 5,000 / 10,000 records and measure throughput, per the M2 brief's
explicit performance-benchmarking requirement.

Run: python scripts/benchmark_reconciliation.py
"""
from __future__ import annotations

import random
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.db.models import BankTransaction, FeeRule, Payment, Settlement  # noqa: E402
from app.engines.reconciliation.engine import reconcile_all  # noqa: E402

BASE_DATE = datetime(2026, 1, 1)
FEE_RULES = [
    FeeRule(fee_rule_id="FEE-UPI-001", method="upi", mdr_percent=Decimal("0.000"), fixed_fee=Decimal("0.00"), tax_percent=Decimal("0.000"), effective_from=BASE_DATE),
    FeeRule(fee_rule_id="FEE-CARD-001", method="card", mdr_percent=Decimal("0.018"), fixed_fee=Decimal("2.00"), tax_percent=Decimal("0.180"), effective_from=BASE_DATE),
]


def generate_benchmark_batch(n: int, seed: int = 42):
    """70% clean exact matches (linked+confirmed), 20% fee-consistent card
    payments (linked, requires fee verification), 10% unlinked (forces
    candidate generation + multi-field scoring) -- a deliberately mixed load
    so the benchmark exercises every stage, not just the cheap path."""
    rng = random.Random(seed)
    payments: list[Payment] = []
    settlements: list[Settlement] = []
    bank_txns: list[BankTransaction] = []

    for i in range(n):
        amount = (Decimal(rng.randint(10000, 5000000)) / Decimal(100)).quantize(Decimal("0.01"))
        day = rng.randint(0, 365)
        captured_at = BASE_DATE + timedelta(days=day, minutes=rng.randint(0, 1000))
        payment_id = f"PAY-{i:06d}"
        order_id = f"ORD-{i:06d}"
        bucket = rng.random()

        if bucket < 0.70:
            payment = Payment(payment_id=payment_id, order_id=order_id, amount=amount, currency="INR", method="upi", captured_at=captured_at, status="captured", gateway_ref=f"GW{i}", metadata_json="{}")
            settlement_id = f"STL-{i:06d}"
            settlement = Settlement(settlement_id=settlement_id, payment_id=payment_id, settlement_batch_id="B", amount=amount, fee=Decimal("0.00"), tax=Decimal("0.00"), net_amount=amount, currency="INR", settled_at=captured_at + timedelta(days=1), utr_reference=f"UTR{i}PAY{i:06d}", status="settled", metadata_json="{}")
            bank_txn = BankTransaction(bank_txn_id=f"BANKTXN-{i:06d}", amount=amount, currency="INR", value_date=captured_at + timedelta(days=2), narration="x", direction="credit", matched_settlement_id=settlement_id, metadata_json="{}")
            payments.append(payment); settlements.append(settlement); bank_txns.append(bank_txn)

        elif bucket < 0.90:
            payment = Payment(payment_id=payment_id, order_id=order_id, amount=amount, currency="INR", method="card", captured_at=captured_at, status="captured", gateway_ref=f"GW{i}", metadata_json="{}")
            fee = (amount * Decimal("0.018") + Decimal("2.00")).quantize(Decimal("0.01"))
            tax = (fee * Decimal("0.18")).quantize(Decimal("0.01"))
            net = (amount - fee - tax).quantize(Decimal("0.01"))
            settlement_id = f"STL-{i:06d}"
            settlement = Settlement(settlement_id=settlement_id, payment_id=payment_id, settlement_batch_id="B", amount=amount, fee=fee, tax=tax, net_amount=net, currency="INR", settled_at=captured_at + timedelta(days=1), utr_reference=f"UTR{i}PAY{i:06d}", status="settled", metadata_json="{}")
            bank_txn = BankTransaction(bank_txn_id=f"BANKTXN-{i:06d}", amount=net, currency="INR", value_date=captured_at + timedelta(days=2), narration="x", direction="credit", matched_settlement_id=settlement_id, metadata_json="{}")
            payments.append(payment); settlements.append(settlement); bank_txns.append(bank_txn)

        else:
            payment = Payment(payment_id=payment_id, order_id=order_id, amount=amount, currency="INR", method="upi", captured_at=captured_at, status="captured", gateway_ref=f"GW{i}", metadata_json="{}")
            settlement_id = f"STL-{i:06d}"
            settlement = Settlement(settlement_id=settlement_id, payment_id=None, settlement_batch_id="B", amount=amount, fee=Decimal("0.00"), tax=Decimal("0.00"), net_amount=amount, currency="INR", settled_at=captured_at + timedelta(days=1), utr_reference=f"UTRSTANDALONE{i}", status="settled", metadata_json="{}")
            bank_txn = BankTransaction(bank_txn_id=f"BANKTXN-{i:06d}", amount=amount, currency="INR", value_date=captured_at + timedelta(days=2), narration="x", direction="credit", matched_settlement_id=settlement_id, metadata_json="{}")
            payments.append(payment); settlements.append(settlement); bank_txns.append(bank_txn)

    return payments, settlements, bank_txns


def run_benchmark(sizes: list[int]) -> None:
    print(f"{'records':>10} {'runtime (s)':>12} {'records/sec':>14}")
    for n in sizes:
        payments, settlements, bank_txns = generate_benchmark_batch(n)
        t0 = time.perf_counter()
        results = reconcile_all(payments, settlements, bank_txns, [], FEE_RULES)
        t1 = time.perf_counter()
        elapsed = t1 - t0
        rate = n / elapsed if elapsed > 0 else float("inf")
        assert len(results) == n
        print(f"{n:>10} {elapsed:>12.3f} {rate:>14.1f}")


if __name__ == "__main__":
    run_benchmark([300, 1000, 5000, 10000])
