"""Phase 24: the complete fixture (Razorpay-like payment + settlement +
bank transaction + internal order + refund, `data/synthetic/provider_fixtures/`)
run through the REAL, unmodified pipeline -- adapter -> mapping ->
validation -> normalization -> ingestion -> reconciliation -> exception
intelligence -> AI investigation -> self-challenge -> verification -> risk
-> policy -> decision -> audit. No special fixture-only decision path
exists anywhere; this test calls the exact same functions every other
pipeline test in this project calls.
"""
from __future__ import annotations

from app.adapters.config import ProviderSettings
from app.adapters.pipeline import ingest_from_provider
from app.adapters.razorpay_adapter import RazorpayAdapter
from app.ai.provider import MockAIProvider
from app.audit.ledger import AuditLedger
from app.audit.verify import verify_chain
from app.db.models import BankTransaction, FeeRule, Order, Payment, Refund, Settlement
from app.policy.approval import ApprovalWorkflowStore
from app.policy.schemas import PolicyDecisionType
from app.services.decision_service import run_decision_pipeline
from app.services.exception_service import run_exception_intelligence


def test_complete_provider_fixture_runs_through_the_real_pipeline_end_to_end(db_session):
    session = db_session
    settings = ProviderSettings()
    settings.provider_mode = "fixture"
    adapter = RazorpayAdapter(settings)

    ingestion_report = ingest_from_provider(session, adapter)
    session.commit()

    assert ingestion_report.all_valid
    assert ingestion_report.counts["order"] == 3
    assert ingestion_report.counts["payment"] == 3
    assert ingestion_report.counts["settlement"] == 3
    assert ingestion_report.counts["bank_transaction"] == 3
    assert ingestion_report.counts["refund"] == 1
    for rejections in ingestion_report.mapping_rejections.values():
        assert rejections == []  # every real fixture record mapped cleanly

    payments = session.query(Payment).all()
    settlements = session.query(Settlement).all()
    bank_txns = session.query(BankTransaction).all()
    refunds = session.query(Refund).all()
    fee_rules = session.query(FeeRule).all()
    orders = session.query(Order).all()
    assert len(orders) == 3

    _reconciliation_results, evidence_bundles = run_exception_intelligence(payments, settlements, bank_txns, refunds, fee_rules)

    from app.engines.reconciliation.candidate_generation import build_context
    from app.engines.evidence.graph import build_graph

    context = build_context(payments, settlements, bank_txns, refunds, fee_rules)
    graph = build_graph(payments, settlements, bank_txns, refunds)

    ledger = AuditLedger(session)
    store = ApprovalWorkflowStore()
    provider = MockAIProvider()
    reference_now = max(p.captured_at for p in payments)

    decisions = []
    for bundle in evidence_bundles:
        payment = next(p for p in payments if p.payment_id == bundle.payment_id)
        result = run_decision_pipeline(payment, bundle, context, graph, provider, ledger, reference_now, store)
        session.commit()
        decisions.append(result)

    assert len(decisions) == 3

    # No decision here is ever REJECTED/blocked-with-unsafe-outcome silently
    # -- every one reaches a real, named PolicyDecisionType, and NONE is a
    # false auto-resolution (there is no ground truth for this small
    # hand-built fixture, but the invariant that matters is checkable
    # directly: the payment WITH a refund the settlement doesn't reflect
    # must never be SAFE_TO_RESOLVE).
    by_payment_id = {d.bundle.payment_id for d in decisions}
    assert by_payment_id == {p.payment_id for p in payments}

    refunded_payment_id = refunds[0].payment_id
    refunded_decision = next(d for d in decisions if d.bundle.payment_id == refunded_payment_id)
    assert refunded_decision.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE

    # The two clean (no-refund) payments settle safely.
    clean_decisions = [d for d in decisions if d.bundle.payment_id != refunded_payment_id]
    assert all(d.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE for d in clean_decisions)

    # The audit chain covering this run is fully valid.
    chain_result = verify_chain(session)
    assert chain_result.valid is True
    assert chain_result.events_checked > 0


def test_the_fixture_pipeline_uses_no_special_decision_path():
    # A structural guard: app.adapters has no module named anything like
    # "decision"/"policy"/"verify" -- decision-making stays entirely inside
    # the existing M4-M6 modules, never duplicated here.
    import app.adapters as adapters_pkg
    import pkgutil

    module_names = {m.name for m in pkgutil.iter_modules(adapters_pkg.__path__)}
    forbidden = {"policy", "verifier", "verification", "decision", "risk", "priority"}
    assert module_names.isdisjoint(forbidden)
