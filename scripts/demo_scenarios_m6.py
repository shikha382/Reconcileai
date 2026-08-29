"""Phase 24 demo scenarios for Milestone 6, run against an ISOLATED demo
database (never the real dev DB). Five cases:

  1. Clean exact match -- auto-resolves, no AI needed, full audit trail.
  2. Fee mismatch with a genuine residual -- AI proposes, verifier finds a
     contradiction, self-challenge rule blocks auto-resolution.
  3. Ambiguous match -- always routed to human review, dual control aside.
  4. High-value exposure -- dual control required regardless of confidence.
  5. Audit tampering -- chain VALID before, INVALID after, with the exact
     event/reason identified (this is scenario 5 of the M6 brief; case
     detail also demonstrated end-to-end in scripts/tamper_demo.py).

Run: python scripts/demo_scenarios_m6.py
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
from app.audit.provenance import build_decision_summary, get_decision_provenance  # noqa: E402
from app.audit.verify import verify_chain  # noqa: E402
from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.engines.evidence.graph import build_graph  # noqa: E402
from app.engines.reconciliation.candidate_generation import build_context  # noqa: E402
from app.ingestion.pipeline import ingest_source_directory  # noqa: E402
from app.policy.approval import ApprovalWorkflowStore  # noqa: E402
from app.policy.schemas import PolicyDecisionType, RiskLevel  # noqa: E402
from app.services.decision_service import run_decision_pipeline  # noqa: E402
from app.services.exception_service import run_exception_intelligence  # noqa: E402
from shared.money import loads as loads_decimal_json  # noqa: E402

DEMO_DB_PATH = REPO_ROOT / "scripts" / "_demo_scenarios_m6.db"


def _print_header(n: int, title: str) -> None:
    print(f"\n{'=' * 70}\nDEMO CASE {n}: {title}\n{'=' * 70}")


def main() -> None:
    if DEMO_DB_PATH.exists():
        DEMO_DB_PATH.unlink()

    engine = make_engine(DEMO_DB_PATH)
    init_db(engine)
    session = make_session_factory(engine)()
    seeds = REPO_ROOT / "data" / "synthetic" / "seeds"
    ingest_source_directory(session, seeds)
    session.commit()

    ground_truth = loads_decimal_json((seeds / "ground_truth.json").read_text())
    gt_by_order = {row["order_id"]: row for row in ground_truth}

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

    results = {}
    for bundle in bundles:
        payment = payments_by_id[bundle.payment_id]
        result = run_decision_pipeline(payment, bundle, context, graph, provider, ledger, reference_now, store)
        session.commit()
        results[bundle.order_id] = result

    # --- Case 1: clean exact match, auto-resolved, no AI needed ------------
    _print_header(1, "Clean exact match -- auto-resolved, no AI investigation")
    case1 = next(
        (r for order_id, r in results.items() if gt_by_order[order_id]["archetype"] == "exact_match"
         and r.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE), None,
    )
    if case1:
        summary = build_decision_summary(get_decision_provenance(session, case1.exception_id))
        print(f"  exception_id: {case1.exception_id}")
        print(f"  AI investigation needed: {case1.ai_investigation is not None}")
        print(f"  policy_decision: {summary['policy_decision']} (policy {summary['policy_id']} v{summary['policy_version']})")
        print(f"  audit_chain_valid: {summary['audit_chain_valid']}")

    # --- Case 2: fee mismatch with a real residual -> contradiction blocks resolution
    _print_header(2, "Fee mismatch -- AI hypothesis contradicted by a real residual, auto-resolution blocked")
    # Real cases in the dataset where a fee hypothesis is contradicted by a
    # genuine residual are archetype `unexplained_difference` (a corrupted
    # net_amount survives every single-settlement hypothesis attempt,
    # including a fee explanation, with a nonzero residual) rather than
    # `fee_mismatch` -- picking by hypothesis_type is the honest selector.
    case2 = next(
        (r for r in results.values()
         if any(c.status == "CONTRADICTED" and c.hypothesis_type == "FEE_EXPLAINS_DIFFERENCE" for c in r.contradiction_records)),
        None,
    )
    if case2 is None:  # fall back to any contradicted case at all
        case2 = next((r for r in results.values() if any(c.status == "CONTRADICTED" for c in r.contradiction_records)), None)
    if case2:
        contradiction = next(
            (c for c in case2.contradiction_records if c.status == "CONTRADICTED" and c.hypothesis_type == "FEE_EXPLAINS_DIFFERENCE"),
            next(c for c in case2.contradiction_records if c.status == "CONTRADICTED"),
        )
        summary = build_decision_summary(get_decision_provenance(session, case2.exception_id))
        print(f"  exception_id: {case2.exception_id}")
        print(f"  hypothesis_type: {contradiction.hypothesis_type}")
        print(f"  expected: {contradiction.expected_value}  observed: {contradiction.observed_value}  residual: {contradiction.residual}")
        print(f"  self-challenge rule fired: {'POLICY-CONFLICT-001' in case2.policy_decision.rules_passed}")
        print(f"  final policy_decision: {summary['policy_decision']} (never SAFE_TO_RESOLVE despite the AI's own proposal)")
    else:
        print("  (no contradicted hypothesis found in this run -- see test_evaluation_m6.py for the guaranteed case)")

    # --- Case 3: ambiguous match -> always human review ---------------------
    _print_header(3, "Ambiguous match -- always routed to human review")
    case3 = next((r for order_id, r in results.items() if gt_by_order[order_id]["archetype"] == "ambiguous_match"), None)
    if case3:
        print(f"  exception_id: {case3.exception_id}")
        print(f"  policy_decision: {case3.policy_decision.decision.value}")
        print(f"  reasons: {case3.policy_decision.reasons}")

    # --- Case 4: high financial exposure -> dual control -------------------
    _print_header(4, "High-value exposure -- dual control required regardless of confidence")
    case4 = next(
        (r for r in results.values() if r.review is not None and r.review.dual_control_required), None,
    )
    if case4:
        print(f"  exception_id: {case4.exception_id}")
        print(f"  financial_impact: {case4.proposal.financial_impact}")
        print(f"  risk_level: {case4.policy_decision.risk_level.value}")
        print(f"  dual_control_required: {case4.review.dual_control_required}")
    else:
        print("  (no dual-control case in this run's risk distribution)")

    # --- Case 5: audit tampering, valid -> invalid --------------------------
    _print_header(5, "Audit tampering -- chain VALID before, INVALID after")
    before = verify_chain(session)
    print(f"  BEFORE: valid={before.valid}, events_checked={before.events_checked}")

    import json
    from sqlalchemy import select
    from app.db.models import AuditEventRecord

    # Pick the POLICY_EVALUATED event for a case that did NOT auto-resolve,
    # so the tamper below is a real, meaningful change (an attacker
    # "upgrading" a HUMAN_REVIEW/REJECTED decision to SAFE_TO_RESOLVE), not
    # a no-op overwrite of a value that already matched.
    blocked_result = next(r for r in results.values() if r.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE)
    victim = session.execute(
        select(AuditEventRecord).where(
            AuditEventRecord.entity_id == blocked_result.exception_id, AuditEventRecord.event_type == "POLICY_EVALUATED",
        )
    ).scalar_one()
    payload = json.loads(victim.payload_json)
    original_decision = payload["decision"]
    payload["decision"] = "SAFE_TO_RESOLVE"  # an attacker "upgrading" a blocked decision after the fact
    victim.payload_json = json.dumps(payload, sort_keys=True)
    session.commit()
    print(f"  tampering event {victim.event_id}: decision {original_decision!r} -> 'SAFE_TO_RESOLVE'")

    after = verify_chain(session)
    print(f"  AFTER:  valid={after.valid}")
    print(f"    tampered event: {victim.event_id}")
    print(f"    reason: {after.reason}")
    assert before.valid is True and after.valid is False and after.first_invalid_event_id == victim.event_id

    print(f"\n{'=' * 70}\nAll 5 demo cases completed.\n{'=' * 70}")

    session.close()
    engine.dispose()
    try:
        DEMO_DB_PATH.unlink()
    except PermissionError:
        print(f"(note: could not delete {DEMO_DB_PATH} immediately -- clean it up manually if needed)")


if __name__ == "__main__":
    main()
