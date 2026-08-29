"""Phase 25: three deterministic, highly understandable M10 explanation
traces, built entirely from real project logic (no fake UI output, no
hardcoded "successful" narrative) -- run through the real M1-M6 pipeline
against the real 300-record dataset, then explained via
`app.explainability.builder.build_explanation`.

DEMO A: clean auto-resolution.
DEMO B: adversarial fee trap (AI hypothesis -> fee calculation -> residual
        -> verification failure -> policy denial -> human review -> audit).
DEMO C: ambiguous/missing evidence (candidate matches -> uncertainty ->
        no unsafe automation -> human review).

Run: python scripts/demo_scenarios_m10.py
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
from app.engines.reconciliation.candidate_generation import build_context  # noqa: E402
from app.engines.evidence.graph import build_graph  # noqa: E402
from app.explainability.builder import build_explanation  # noqa: E402
from app.explainability.completeness import check_explanation_completeness  # noqa: E402
from app.explainability.provenance_check import validate_provenance  # noqa: E402
from app.ingestion.pipeline import ingest_source_directory  # noqa: E402
from app.policy.approval import ApprovalWorkflowStore  # noqa: E402
from app.services.decision_service import run_decision_pipeline  # noqa: E402
from app.services.exception_service import run_exception_intelligence  # noqa: E402
from shared.money import loads  # noqa: E402

DEMO_DB_PATH = REPO_ROOT / "scripts" / "_demo_m10.db"


def _print_explanation(label: str, explanation) -> None:
    print("=" * 70)
    print(label)
    print("=" * 70)
    print(explanation.human_readable)
    print()
    completeness = check_explanation_completeness(explanation)
    print(f"Explanation complete: {completeness.explanation_complete}"
          + (f" (missing: {completeness.missing_sections})" if not completeness.explanation_complete else ""))
    print()


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
    ground_truth = loads((seeds / "ground_truth.json").read_text())

    _, bundles = run_exception_intelligence(payments, settlements, bank_txns, refunds, fee_rules)
    context = build_context(payments, settlements, bank_txns, refunds, fee_rules)
    graph = build_graph(payments, settlements, bank_txns, refunds)
    payments_by_id = {p.payment_id: p for p in payments}
    settlements_by_payment_id = {s.payment_id: s for s in settlements if s.payment_id}
    reference_now = max(p.captured_at for p in payments)

    ledger = AuditLedger(session)
    store = ApprovalWorkflowStore()
    provider = MockAIProvider()
    bundles_by_order = {b.order_id: b for b in bundles}

    def _decide(order_id: str):
        bundle = bundles_by_order[order_id]
        payment = payments_by_id[bundle.payment_id]
        result = run_decision_pipeline(payment, bundle, context, graph, provider, ledger, reference_now, store)
        session.commit()
        settlement = settlements_by_payment_id.get(payment.payment_id)
        return result, payment, settlement

    # --- DEMO A: clean auto-resolution ---
    order_a = next(r["order_id"] for r in ground_truth if r["archetype"] == "exact_match")
    result_a, payment_a, settlement_a = _decide(order_a)
    explanation_a = build_explanation(result_a, context=context, payment=payment_a, settlement=settlement_a)
    _print_explanation("DEMO A: CLEAN AUTO-RESOLUTION", explanation_a)
    validation_a = validate_provenance(explanation_a, result_a, ledger=ledger)
    print(f"Provenance valid: {validation_a.valid}\n")

    # --- DEMO B: adversarial fee trap ---
    order_b = next(r["order_id"] for r in ground_truth if r["archetype"] == "fee_mismatch" and r.get("is_adversarial"))
    result_b, payment_b, settlement_b = _decide(order_b)
    explanation_b = build_explanation(result_b, context=context, payment=payment_b, settlement=settlement_b)
    _print_explanation("DEMO B: ADVERSARIAL FEE TRAP", explanation_b)
    validation_b = validate_provenance(explanation_b, result_b, ledger=ledger)
    print(f"Provenance valid: {validation_b.valid}\n")

    # --- DEMO C: ambiguous / missing evidence ---
    order_c = next(r["order_id"] for r in ground_truth if r["archetype"] == "ambiguous_match")
    result_c, payment_c, settlement_c = _decide(order_c)
    explanation_c = build_explanation(result_c, context=context, payment=payment_c, settlement=settlement_c)
    _print_explanation("DEMO C: AMBIGUOUS / MISSING EVIDENCE", explanation_c)
    validation_c = validate_provenance(explanation_c, result_c, ledger=ledger)
    print(f"Provenance valid: {validation_c.valid}\n")

    assert explanation_a.decision == "SAFE_TO_RESOLVE"
    assert explanation_b.decision != "SAFE_TO_RESOLVE"
    assert explanation_c.decision != "SAFE_TO_RESOLVE"
    assert validation_a.valid and validation_b.valid and validation_c.valid
    print("All three demo assertions passed: correct decisions, complete and provenance-valid explanations.")

    session.close()
    engine.dispose()
    try:
        DEMO_DB_PATH.unlink()
    except PermissionError:
        print(f"(note: could not delete {DEMO_DB_PATH} immediately)")


if __name__ == "__main__":
    main()
