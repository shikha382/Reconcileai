"""Phase 24/25: the ONE command that runs the complete ReconcileAI pipeline
end-to-end -- no manual stage-by-stage script execution required.

Usage:
    python scripts/run_reconciliation.py [--dataset data/synthetic/seeds] [--db path/to/db]

Defaults to the real 300-record M1 dataset and a fresh isolated database
under scripts/ (never the shared dev DB, so repeated demo runs don't
accumulate state across each other unless --db is passed explicitly).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "data" / "synthetic"))

from app.ai.config import settings as ai_settings  # noqa: E402
from app.ai.provider import build_provider  # noqa: E402
from app.audit.ledger import AuditLedger  # noqa: E402
from app.audit.provenance import build_decision_summary, get_decision_provenance  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.policy.approval import ApprovalWorkflowStore  # noqa: E402
from app.services.reconciliation_pipeline import run_reconciliation_pipeline  # noqa: E402


def _pick_showcase_order_id(result) -> str | None:
    """Picks one exception to show in full detail (Phase 25): prefer a
    contradicted-hypothesis case (the most demonstrative -- AI proposed,
    evidence disagreed, auto-resolution was blocked); otherwise the first
    HUMAN_REVIEW case; otherwise whatever the first processed exception is."""
    for order_id, decision in result.decisions.items():
        if any(c.status == "CONTRADICTED" for c in decision.contradiction_records):
            return order_id
    for order_id, decision in result.decisions.items():
        if decision.policy_decision.decision.value == "HUMAN_REVIEW":
            return order_id
    return next(iter(result.decisions), None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full ReconcileAI reconciliation pipeline end-to-end.")
    parser.add_argument("--dataset", default=str(REPO_ROOT / "data" / "synthetic" / "seeds"))
    parser.add_argument("--db", default=str(REPO_ROOT / "scripts" / "_run_reconciliation.db"))
    args = parser.parse_args()

    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()

    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()

    provider = build_provider(ai_settings.provider, ai_settings.model, ai_settings.api_key)
    ledger = AuditLedger(session)
    approval_store = ApprovalWorkflowStore()

    result = run_reconciliation_pipeline(session, Path(args.dataset), provider, ledger, approval_store)

    print("=" * 50)
    print("RECONCILEAI -- RECONCILIATION RUN")
    print("=" * 50)
    print()
    print(f"Run ID: {result.run_id}")
    print(f"Status: {result.status}")
    print()
    print(f"Records processed: {result.records_processed}")
    print()
    print(f"Matched:            {result.matched}")
    print(f"Evidence bundles:   {result.exceptions}  (one per payment -- includes clean matches, see docs/end-to-end-pipeline.md)")
    print()
    print(f"AUTO RESOLVED: {result.auto_resolved}")
    print(f"HUMAN REVIEW:  {result.human_review}")
    print(f"BLOCKED:       {result.blocked}")
    print(f"REJECTED:      {result.rejected}")
    print(f"UNRESOLVED:    {result.unresolved}")
    print()

    false_auto_resolutions = 0  # a true 0/300 check needs ground truth (see backend/tests/pipeline/test_evaluation_m7.py); this script reports the raw distribution only
    print(f"Processing time: {result.duration_seconds:.3f}s")
    print(f"Records/sec:     {result.records_processed / result.duration_seconds:.1f}" if result.duration_seconds else "")
    print()
    print(f"Audit events:    {result.audit_events}")
    print(f"Audit integrity: {'VALID' if result.provenance_available else 'INVALID'}")
    if result.warnings:
        print(f"Warnings:        {len(result.warnings)}")
        for w in result.warnings[:5]:
            print(f"  - {w}")
    print()
    print("=" * 50)

    showcase_order_id = _pick_showcase_order_id(result)
    if showcase_order_id is not None:
        decision = result.decisions[showcase_order_id]
        provenance = get_decision_provenance(session, decision.exception_id)
        summary = build_decision_summary(provenance)

        print()
        print(f"EXCEPTION: {decision.exception_id}  (order {showcase_order_id})")
        print()
        print(f"Exposure: Rs. {decision.proposal.financial_impact}")
        print()
        if decision.ai_investigation is not None:
            print("AI hypothesis:")
            for h in provenance.ai_hypotheses:
                print(f"  {h.get('hypothesis_type')}: {h.get('claim')}")
            print()
            print("Challenge:")
            # A CONTRADICTED hypothesis has two audit events referencing it
            # (HYPOTHESIS_CHALLENGED, then CONTRADICTION_FOUND -- both real,
            # distinct ledger events, see docs/contradiction-evidence.md) so
            # dedupe by hypothesis_id here purely for display.
            seen = set()
            for c in provenance.contradictions:
                hid = c.get("hypothesis_id")
                if not c.get("status") or hid in seen:
                    continue
                seen.add(hid)
                print(f"  {c.get('hypothesis_type')}: {c.get('status')} -- {c.get('reason')}")
            print()
            contradicted = [c for c in provenance.contradictions if c.get("status") == "CONTRADICTED"]
            print(f"Contradiction: {'YES -- ' + str(contradicted[0].get('reason')) if contradicted else 'none'}")
        else:
            print("AI hypothesis: not needed (root cause already conclusive without AI investigation)")
            print("Challenge: n/a")
            print("Contradiction: n/a")
        print()
        print(f"Verifier conclusion: {summary['verification_conclusion']}")
        print()
        print(f"Policy: {summary['policy_decision']} ({summary['policy_id']} v{summary['policy_version']})")
        print()
        print(f"Decision:\n{decision.policy_decision.decision.value}")
        print()
        print(f"Provenance:\n{'AVAILABLE' if summary['audit_chain_valid'] else 'CHAIN INVALID'}")
        print()
        print("=" * 50)

    session.close()
    engine.dispose()
    try:
        db_path.unlink()
    except PermissionError:
        print(f"(note: could not delete {db_path} immediately)")

    return 0 if result.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
