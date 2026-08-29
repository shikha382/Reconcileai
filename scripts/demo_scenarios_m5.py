"""Milestone 5 demo scenarios -- ten representative cases feeding the future
dashboard/demo (not built yet). Uses the real 300-record M1 dataset where a
matching archetype exists, and small hand-built cases for the workflow-only
scenarios (human approval/rejection) and the AI-hallucination scenario.

Run: python scripts/demo_scenarios_m5.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ai.controller import investigate  # noqa: E402
from app.ai.provider import MockAIProvider  # noqa: E402
from app.ai.tools import InvestigationContext  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.engines.evidence.candidates import why_not_matched  # noqa: E402
from app.engines.evidence.graph import build_graph  # noqa: E402
from app.engines.reconciliation.candidate_generation import build_context  # noqa: E402
from app.ingestion.pipeline import ingest_source_directory  # noqa: E402
from app.policy.approval import ApprovalWorkflowStore, submit_review_decision  # noqa: E402
from app.policy.engine import evaluate_policy  # noqa: E402
from app.policy.schemas import Actor, ActorType, ReasonCode, ReviewDecisionType  # noqa: E402
from app.services.exception_service import run_exception_intelligence  # noqa: E402
from app.services.resolution_service import resolve_exception  # noqa: E402
from shared.money import loads  # noqa: E402

SEEDS = REPO_ROOT / "data" / "synthetic" / "seeds"


def _load_real_dataset():
    engine = make_engine(REPO_ROOT / "scripts" / "_demo_m5.db")
    init_db(engine)
    session = make_session_factory(engine)()
    ingest_source_directory(session, SEEDS)
    session.commit()
    from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement

    return (
        session.query(Payment).all(), session.query(Settlement).all(),
        session.query(BankTransaction).all(), session.query(Refund).all(), session.query(FeeRule).all(),
    )


def main() -> None:
    payments, settlements, bank_txns, refunds, fee_rules = _load_real_dataset()
    m2_results, bundles = run_exception_intelligence(payments, settlements, bank_txns, refunds, fee_rules)
    ground_truth = loads((SEEDS / "ground_truth.json").read_text())
    gt_by_order = {g["order_id"]: g for g in ground_truth}
    bundles_by_order = {b.order_id: b for b in bundles}
    payments_by_id = {p.payment_id: p for p in payments}
    reference_now = max(p.captured_at for p in payments)
    store = ApprovalWorkflowStore()

    def show(label: str, order_id: str) -> None:
        bundle = bundles_by_order[order_id]
        payment = payments_by_id[bundle.payment_id]
        _, decision, proposal, review = resolve_exception(bundle, payment, reference_now, store)
        print(f"\n=== {label} ({order_id}, {gt_by_order[order_id]['archetype']}) ===")
        print(f"  policy decision: {decision.decision.value}  (rules passed: {decision.rules_passed})")
        print(f"  proposal: {proposal.resolution_type.value}, requires_approval={proposal.requires_approval}")
        if review:
            print(f"  review created: {review.review_id}, dual_control={review.dual_control_required}")

    # 1. Clean verified fee case
    fee_ok = next(o for o, g in gt_by_order.items() if g["archetype"] == "fee_mismatch" and not g["is_adversarial"])
    show("1. Clean verified fee case", fee_ok)

    # 2. Verified refund case
    refund_ok = next(o for o, g in gt_by_order.items() if g["archetype"] == "refund_mismatch")
    show("2. Verified refund case", refund_ok)

    # 3. Ambiguous match
    ambiguous = next(o for o, g in gt_by_order.items() if g["archetype"] == "ambiguous_match" and not g["is_adversarial"])
    show("3. Ambiguous match", ambiguous)

    # 4. High-value case (largest payment amount in the dataset)
    high_value = max(payments, key=lambda p: p.amount)
    high_value_order = next(o for o, b in bundles_by_order.items() if b.payment_id == high_value.payment_id)
    show("4. High-value case", high_value_order)

    # 5. Unexplained residual
    unexplained = next(o for o, g in gt_by_order.items() if g["archetype"] == "unexplained_difference")
    show("5. Unexplained residual", unexplained)

    # 6. AI hallucination
    print("\n=== 6. AI hallucination (hand-built) ===")
    hallucinating_provider = MockAIProvider(hallucinate_record_id="STL-99999")
    fee_bad = next(o for o, g in gt_by_order.items() if g["archetype"] == "fee_mismatch" and g["is_adversarial"])
    bundle = bundles_by_order[fee_bad]
    payment = payments_by_id[bundle.payment_id]
    context = build_context(payments, settlements, bank_txns, refunds, fee_rules)
    graph = build_graph(payments, settlements, bank_txns, refunds)
    report = why_not_matched(payment, context)
    ctx = InvestigationContext(exception_id=bundle.exception_id, payment=payment, reconciliation_context=context, graph=graph, negative_evidence_report=report)
    ai_result = investigate(bundle.exception_id, ctx, hallucinating_provider)
    print(f"  AI final decision: {ai_result.final_decision.value} -- {ai_result.reason}")

    # 7. Policy conflict (verified but over exposure threshold)
    from decimal import Decimal

    over_threshold = next((p for p in payments if p.amount > Decimal("100000.00")), None)
    if over_threshold:
        order_id = next(o for o, b in bundles_by_order.items() if b.payment_id == over_threshold.payment_id)
        show("7. Policy conflict (verified but over exposure threshold)", order_id)
    else:
        print("\n=== 7. Policy conflict === (no payment in this dataset exceeds the exposure threshold; see docs/policy-engine.md's worked example instead)")

    # 8 & 9. Human approval / rejection workflow
    print("\n=== 8. Human approval ===")
    # Reuse the ambiguous case's review (already created via `show` above).
    _, decision, proposal, review = resolve_exception(bundles_by_order[ambiguous], payments_by_id[bundles_by_order[ambiguous].payment_id], reference_now, store)
    reviewer = Actor(ActorType.HUMAN, "reviewer-demo-1")
    approved = submit_review_decision(review, reviewer, ReviewDecisionType.APPROVE, ReasonCode.VERIFIED_EVIDENCE, comment="Manually confirmed correct candidate.")
    print(f"  review {review.review_id} -> {review.state.value} by {approved.reviewer_id}")

    print("\n=== 9. Human rejection ===")
    _, decision2, proposal2, review2 = resolve_exception(bundles_by_order[unexplained], payments_by_id[bundles_by_order[unexplained].payment_id], reference_now, store, created_by="ai-controller-1")
    reviewer2 = Actor(ActorType.HUMAN, "reviewer-demo-2")
    rejected = submit_review_decision(review2, reviewer2, ReviewDecisionType.REJECT, ReasonCode.EVIDENCE_INSUFFICIENT, comment="Needs finance team follow-up.")
    print(f"  review {review2.review_id} -> {review2.state.value} by {rejected.reviewer_id}")

    # 10. SLA breach
    print("\n=== 10. SLA breach ===")
    from app.policy.risk import assess_sla
    from datetime import timedelta

    far_future = reference_now + timedelta(days=30)
    sla = assess_sla(payments_by_id[bundles_by_order[unexplained].payment_id], far_future)
    print(f"  30 days after the dataset's latest record: sla_status={sla.sla_status.value}, age_days={sla.age_days}")


if __name__ == "__main__":
    main()
