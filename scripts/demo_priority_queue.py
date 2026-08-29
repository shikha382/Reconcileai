"""Phase 18: the deterministic finance work-queue demo. Runs the real
300-record dataset through the real M1-M6 pipeline, builds one
PrioritizedException per exception (reusing M5's assess_priority/assess_sla
and M10's explanation for contradiction/missing-evidence counts -- never a
second decision engine), and prints the queue exactly as a finance
controller would see it.

Run: python scripts/demo_priority_queue.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "data" / "synthetic"))

from app.ai.provider import MockAIProvider  # noqa: E402
from app.audit.ledger import AuditLedger  # noqa: E402
from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.engines.evidence.graph import build_graph  # noqa: E402
from app.engines.reconciliation.candidate_generation import build_context  # noqa: E402
from app.explainability.builder import build_explanation  # noqa: E402
from app.ingestion.pipeline import ingest_source_directory  # noqa: E402
from app.policy.approval import ApprovalWorkflowStore  # noqa: E402
from app.prioritization.queue import get_priority_queue, summarize_queue  # noqa: E402
from app.prioritization.scorer import attach_priority, build_prioritized_exception  # noqa: E402
from app.services.decision_service import run_decision_pipeline  # noqa: E402
from app.services.exception_service import run_exception_intelligence  # noqa: E402

DEMO_DB_PATH = REPO_ROOT / "scripts" / "_demo_m11.db"


def main() -> None:
    if DEMO_DB_PATH.exists():
        DEMO_DB_PATH.unlink()
    engine = make_engine(DEMO_DB_PATH)
    init_db(engine)
    session = make_session_factory(engine)()
    seeds = REPO_ROOT / "data" / "synthetic" / "seeds"
    ingest_source_directory(session, seeds)
    session.commit()

    payments = session.query(Payment).all()
    settlements = session.query(Settlement).all()
    bank_txns = session.query(BankTransaction).all()
    refunds = session.query(Refund).all()
    fee_rules = session.query(FeeRule).all()

    _, bundles = run_exception_intelligence(payments, settlements, bank_txns, refunds, fee_rules)
    context = build_context(payments, settlements, bank_txns, refunds, fee_rules)
    graph = build_graph(payments, settlements, bank_txns, refunds)
    payments_by_id = {p.payment_id: p for p in payments}
    reference_now = max(p.captured_at for p in payments)

    ledger = AuditLedger(session)
    store = ApprovalWorkflowStore()
    provider = MockAIProvider()

    prioritized = []
    decisions_by_exception_id = {}
    for bundle in bundles:
        payment = payments_by_id[bundle.payment_id]
        result = run_decision_pipeline(payment, bundle, context, graph, provider, ledger, reference_now, store)
        session.commit()
        explanation = build_explanation(result, context=context, payment=payment,
                                         settlement=next((s for s in settlements if s.payment_id == payment.payment_id), None))
        item = build_prioritized_exception(result, payment, reference_now, explanation)
        attach_priority(explanation, item)
        prioritized.append(item)
        decisions_by_exception_id[item.exception_id] = (result, explanation)

    ordered = get_priority_queue(prioritized)
    summary = summarize_queue(ordered)

    print("=" * 52)
    print("RECONCILEAI FINANCE WORK QUEUE")
    print("=" * 52)
    print()
    print(f"{summary.total} exceptions")
    print()
    print(f"P0 CRITICAL — {summary.counts_by_priority.get('P0', 0)}")
    print(f"P1 HIGH     — {summary.counts_by_priority.get('P1', 0)}")
    print(f"P2 MEDIUM   — {summary.counts_by_priority.get('P2', 0)}")
    print(f"P3 LOW      — {summary.counts_by_priority.get('P3', 0)}")
    print()
    print(f"Total financial exposure: Rs. {summary.total_financial_exposure}")
    print(f"SLA breached:  {summary.sla_breached_count}")
    print(f"SLA at risk:   {summary.sla_at_risk_count}")
    print(f"Highest exposure: {summary.highest_exposure_exception_id}")
    print(f"Most common category: {summary.most_common_category}")
    print()
    print("-" * 52)
    print("TOP PRIORITIES")
    print("-" * 52)

    for i, item in enumerate(ordered[:5], start=1):
        print()
        print(f"#{i}")
        print(f"Exception: {item.exception_id}")
        print(f"Priority: {item.priority}")
        print(f"Exposure: Rs. {item.financial_exposure}")
        print(f"Risk: {item.risk_level}")
        print(f"SLA: {item.sla_status}")
        print()
        print("Reasons:")
        for code in item.reason_codes:
            print(f"- {code}")
        print()
        print("Action:")
        print(item.recommended_action)
        print()
        print("-" * 52)

    # Prove the story end-to-end for the #1 item: priority -> explanation -> audit.
    top = ordered[0]
    top_result, top_explanation = decisions_by_exception_id[top.exception_id]
    print()
    print("FULL TRACE FOR #1:")
    print(top_explanation.human_readable)

    # Priority never changed the underlying decision -- the #1 queue item's
    # own decision_status still matches the real, authoritative policy decision.
    assert top_result.policy_decision.decision.value == top.decision_status

    session.close()
    engine.dispose()
    try:
        DEMO_DB_PATH.unlink()
    except PermissionError:
        print(f"(note: could not delete {DEMO_DB_PATH} immediately)")


if __name__ == "__main__":
    main()
