"""Phase 20 tamper demonstration -- an ISOLATED demo database, never the
real development one. Shows: chain VALID -> tamper one event -> chain
INVALID, with the specific event and reason.

Run: python scripts/tamper_demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ai.provider import MockAIProvider  # noqa: E402
from app.audit.ledger import AuditLedger  # noqa: E402
from app.audit.verify import verify_chain  # noqa: E402
from app.db.models import AuditEventRecord, BankTransaction, FeeRule, Payment, Refund, Settlement  # noqa: E402
from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from app.engines.evidence.graph import build_graph  # noqa: E402
from app.engines.reconciliation.candidate_generation import build_context  # noqa: E402
from app.ingestion.pipeline import ingest_source_directory  # noqa: E402
from app.policy.approval import ApprovalWorkflowStore  # noqa: E402
from app.services.decision_service import run_decision_pipeline  # noqa: E402
from app.services.exception_service import run_exception_intelligence  # noqa: E402
from sqlalchemy import select  # noqa: E402

DEMO_DB_PATH = REPO_ROOT / "scripts" / "_tamper_demo.db"  # isolated -- never the real dev DB


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

    # Process a handful of exceptions -- enough for a real, non-trivial chain.
    for bundle in bundles[:30]:
        payment = payments_by_id[bundle.payment_id]
        run_decision_pipeline(payment, bundle, context, graph, provider, ledger, reference_now, store)
        session.commit()

    print("=" * 40)
    print("RECONCILEAI TAMPER DEMONSTRATION (isolated demo DB)")
    print("=" * 40)

    before = verify_chain(session)
    print(f"\nBEFORE TAMPER: chain valid = {before.valid}, events checked = {before.events_checked}")

    victim = session.execute(select(AuditEventRecord).order_by(AuditEventRecord.sequence).limit(1).offset(10)).scalar_one()
    print(f"\nTampering with event {victim.event_id} ({victim.event_type})...")
    payload = json.loads(victim.payload_json)
    tampered_key = next(iter(payload), None)
    payload["__tampered__"] = "an attacker changed this event after the fact"
    victim.payload_json = json.dumps(payload, sort_keys=True)
    session.commit()

    after = verify_chain(session)
    print(f"\nAFTER TAMPER:  chain valid = {after.valid}")
    print(f"  first invalid event: {after.first_invalid_event_id}")
    print(f"  reason: {after.reason}")
    print(f"  details: {after.details}")

    assert before.valid is True
    assert after.valid is False
    assert after.first_invalid_event_id == victim.event_id
    assert after.reason == "HASH_MISMATCH"
    print("\nDemo assertions passed: tamper detection works as designed.")

    session.close()
    engine.dispose()  # release the SQLite file handle (required on Windows before unlink)
    try:
        DEMO_DB_PATH.unlink()  # clean up -- this was an isolated demo DB only
    except PermissionError:
        print(f"\n(note: could not delete {DEMO_DB_PATH} immediately -- clean it up manually if needed)")


if __name__ == "__main__":
    main()
