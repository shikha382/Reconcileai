"""M5 performance benchmark: policy evaluation, risk scoring, and priority/
SLA assessment at 300/1,000/5,000/10,000 exceptions. Reuses M2's benchmark
data generator (not M1's locked 300-record dataset) to reach larger scales.

Run: python scripts/benchmark_policy_engine.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark_reconciliation import generate_benchmark_batch  # noqa: E402

from app.db.models import FeeRule  # noqa: E402
from app.engines.evidence.graph import build_graph  # noqa: E402
from app.engines.exceptions.classifier import classify_exception  # noqa: E402
from app.engines.reconciliation.candidate_generation import build_context  # noqa: E402
from app.engines.reconciliation.engine import reconcile_all  # noqa: E402
from app.engines.risk.scoring import build_financial_exposure, compute_risk_score  # noqa: E402
from app.engines.root_cause.result import determine_root_cause  # noqa: E402
from app.policy.engine import evaluate_policy  # noqa: E402
from app.policy.risk import assess_priority, assess_sla, risk_level_for_score  # noqa: E402
from app.policy.schemas import PolicyInput  # noqa: E402
from app.services.exception_service import _resolve_settlement  # noqa: E402

_FEE_RULES = [
    FeeRule(fee_rule_id="FEE-UPI-001", method="upi", mdr_percent=Decimal("0.000"), fixed_fee=Decimal("0.00"), tax_percent=Decimal("0.000"), effective_from=datetime(2026, 1, 1)),
    FeeRule(fee_rule_id="FEE-CARD-001", method="card", mdr_percent=Decimal("0.018"), fixed_fee=Decimal("2.00"), tax_percent=Decimal("0.180"), effective_from=datetime(2026, 1, 1)),
]

_NEVER_AUTO_CATEGORIES = {"duplicate", "reversed_transaction", "ambiguous_match", "partial_settlement", "unexplained_difference"}


def run_benchmark(sizes: list[int]) -> None:
    print(f"{'exceptions':>10} {'m2/m3(s)':>10} {'policy(s)':>10} {'risk(s)':>10} {'total(s)':>10} {'exc/sec':>10}")
    for n in sizes:
        payments, settlements, bank_txns = generate_benchmark_batch(n)

        t_setup0 = time.perf_counter()
        m2_results = reconcile_all(payments, settlements, bank_txns, [], _FEE_RULES)
        context = build_context(payments, settlements, bank_txns, [], _FEE_RULES)
        build_graph(payments, settlements, bank_txns, [])
        reference_now = max(p.captured_at for p in payments)
        t_setup1 = time.perf_counter()
        m2m3_seconds = t_setup1 - t_setup0

        t0 = time.perf_counter()
        policy_decisions = []
        root_causes = []
        for payment, m2_result in zip(payments, m2_results):
            settlement, siblings = _resolve_settlement(payment, m2_result, context)
            category = classify_exception(payment, settlement, m2_result, context)
            root_cause = determine_root_cause(payment, m2_result, context, settlement, siblings)
            root_causes.append((payment, root_cause))
            exposure = build_financial_exposure(payment, root_cause)
            risk_score = compute_risk_score(payment, root_cause, reference_now)

            policy_input = PolicyInput(
                exception_id=f"EXC-{m2_result.reconciliation_id}", exception_type=category.value if category else None,
                verifier_status=root_cause.status, residual_amount=root_cause.unexplained_amount,
                financial_exposure=exposure.gross_amount, ai_confidence=None, evidence_complete=True,
                conflicting_evidence=(root_cause.status == "CONTRADICTED"), ambiguous=(root_cause.status == "AMBIGUOUS"),
                risk_score=risk_score, risk_level=risk_level_for_score(risk_score),
                auto_resolution_eligible_category=(category is None or category.value not in _NEVER_AUTO_CATEGORIES),
            )
            policy_decisions.append(evaluate_policy(policy_input))
        t1 = time.perf_counter()
        policy_seconds = t1 - t0

        t2 = time.perf_counter()
        for payment, root_cause in root_causes:
            assess_priority(payment, root_cause, reference_now)
            assess_sla(payment, reference_now)
        t3 = time.perf_counter()
        risk_seconds = t3 - t2

        total_seconds = m2m3_seconds + policy_seconds + risk_seconds
        rate = n / total_seconds if total_seconds > 0 else float("inf")
        print(f"{n:>10} {m2m3_seconds:>10.4f} {policy_seconds:>10.4f} {risk_seconds:>10.4f} {total_seconds:>10.4f} {rate:>10.1f}")


if __name__ == "__main__":
    run_benchmark([300, 1000, 5000, 10000])
