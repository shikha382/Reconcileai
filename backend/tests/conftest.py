from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_SYNTHETIC = REPO_ROOT / "data" / "synthetic"
if str(DATA_SYNTHETIC) not in sys.path:
    sys.path.insert(0, str(DATA_SYNTHETIC))

from app.db.session import init_db, make_engine, make_session_factory  # noqa: E402
from generator import DEFAULT_SEED, generate_dataset, write_dataset  # noqa: E402


@pytest.fixture()
def db_session_factory(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    init_db(engine)
    return make_session_factory(engine)


@pytest.fixture()
def db_session(db_session_factory):
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def small_dataset():
    """A cheap, deterministic dataset for fast per-test use. Uses the same
    generator as the full 300-record dataset, just with a smaller archetype
    count override, so generator logic under test is identical either way."""
    # Calls the real generator at full scale once per test session and reuses
    # it -- 300 records generates in well under a second, so there's no need
    # for a separate "small" code path here (fixture name kept for
    # readability at call sites, not because the dataset is actually small).
    return generate_dataset(DEFAULT_SEED)


@pytest.fixture(scope="session")
def dataset_seed_dir(tmp_path_factory, small_dataset):
    out_dir = tmp_path_factory.mktemp("seeds")
    write_dataset(small_dataset, out_dir)
    return out_dir


# --- M2 fixtures below. M1 fixtures above are untouched. ---

@pytest.fixture(scope="session")
def ingested_full_dataset(tmp_path_factory, dataset_seed_dir):
    """Ingests the full 300-record M1 dataset once per test session and
    returns the loaded ORM objects plus ground truth -- session-scoped
    because ingestion + querying back is more expensive than pure in-memory
    fixtures, and every M2 test that needs the real dataset can share it
    (read-only; no test may mutate these objects)."""
    from shared.money import loads

    db_path = tmp_path_factory.mktemp("m2db") / "reconcileai.db"
    engine = make_engine(db_path)
    init_db(engine)
    session_factory = make_session_factory(engine)
    session = session_factory()

    from app.ingestion.pipeline import ingest_source_directory

    ingest_source_directory(session, dataset_seed_dir)
    session.commit()

    from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement

    data = {
        "payments": session.query(Payment).all(),
        "settlements": session.query(Settlement).all(),
        "bank_transactions": session.query(BankTransaction).all(),
        "refunds": session.query(Refund).all(),
        "fee_rules": session.query(FeeRule).all(),
        "ground_truth": loads((dataset_seed_dir / "ground_truth.json").read_text()),
    }
    yield data
    session.close()


@pytest.fixture(scope="session")
def full_reconciliation(ingested_full_dataset):
    """Runs the M2 engine once against the full dataset and evaluates it --
    shared read-only across tests that need the real end-to-end result."""
    from app.engines.reconciliation.engine import reconcile_all
    from app.engines.reconciliation.evaluation import evaluate

    d = ingested_full_dataset
    results = reconcile_all(d["payments"], d["settlements"], d["bank_transactions"], d["refunds"], d["fee_rules"])
    report = evaluate(d["payments"], results, d["ground_truth"])
    return {"results": results, "report": report, **d}


# --- M3 fixtures below. M1/M2 fixtures above are untouched. ---

@pytest.fixture(scope="session")
def full_exception_intelligence(ingested_full_dataset):
    """Runs the M3 exception-intelligence service once against the full
    300-record dataset and evaluates it -- shared read-only across tests."""
    from app.engines.exceptions.evaluation import evaluate_exceptions
    from app.services.exception_service import run_exception_intelligence

    d = ingested_full_dataset
    m2_results, bundles = run_exception_intelligence(
        d["payments"], d["settlements"], d["bank_transactions"], d["refunds"], d["fee_rules"]
    )
    report = evaluate_exceptions(bundles, d["ground_truth"])
    return {"m2_results": m2_results, "bundles": bundles, "report": report, **d}


# --- M4 fixtures below. M1/M2/M3 fixtures above are untouched. ---

@pytest.fixture(scope="session")
def full_ai_resolution(ingested_full_dataset):
    """Runs the M4 AI-assisted resolution (MockAIProvider -- no live API
    key needed) once against the full 300-record dataset -- shared
    read-only across tests."""
    from app.ai.provider import MockAIProvider
    from app.services.ai_exception_service import resolve_all

    d = ingested_full_dataset
    resolutions = resolve_all(
        d["payments"], d["settlements"], d["bank_transactions"], d["refunds"], d["fee_rules"], MockAIProvider()
    )
    return {"resolutions": resolutions, **d}


@pytest.fixture(scope="session")
def full_ai_evaluation(full_ai_resolution):
    from app.ai.evaluation import evaluate_ai_resolutions

    report = evaluate_ai_resolutions(full_ai_resolution["resolutions"], full_ai_resolution["ground_truth"])
    return {"report": report, **full_ai_resolution}


# --- M5 fixtures below. M1/M2/M3/M4 fixtures above are untouched. ---

@pytest.fixture(scope="session")
def full_m5_resolution(full_exception_intelligence):
    """Runs the M5 policy/resolution layer once against the full 300-record
    dataset's already-computed M3 EvidenceBundles -- shared read-only."""
    from app.policy.approval import ApprovalWorkflowStore
    from app.services.resolution_service import resolve_exception

    d = full_exception_intelligence
    payments_by_id = {p.payment_id: p for p in d["payments"]}
    reference_now = max(p.captured_at for p in d["payments"])
    store = ApprovalWorkflowStore()

    results = {}
    for bundle in d["bundles"]:
        payment = payments_by_id[bundle.payment_id]
        policy_input, policy_decision, proposal, review = resolve_exception(bundle, payment, reference_now, store)
        results[bundle.order_id] = {
            "bundle": bundle, "policy_input": policy_input, "policy_decision": policy_decision,
            "proposal": proposal, "review": review,
        }
    return {"results": results, "store": store, "reference_now": reference_now, **d}


# --- M6 fixtures below. M1/M2/M3/M4/M5 fixtures above are untouched. ---

@pytest.fixture(scope="session")
def full_m6_decisions(tmp_path_factory, full_exception_intelligence):
    """Runs the M6 unified decision pipeline (audit ledger + contradiction
    challenge + M5 policy) once against the full 300-record dataset, in its
    own isolated session-scoped SQLite DB -- shared read-only across tests."""
    from app.ai.provider import MockAIProvider
    from app.audit.ledger import AuditLedger
    from app.db.session import init_db, make_engine, make_session_factory
    from app.engines.evidence.graph import build_graph
    from app.engines.reconciliation.candidate_generation import build_context
    from app.policy.approval import ApprovalWorkflowStore
    from app.services.decision_service import run_decision_pipeline

    d = full_exception_intelligence
    db_path = tmp_path_factory.mktemp("m6db") / "reconcileai.db"
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()

    context = build_context(d["payments"], d["settlements"], d["bank_transactions"], d["refunds"], d["fee_rules"])
    graph = build_graph(d["payments"], d["settlements"], d["bank_transactions"], d["refunds"])
    payments_by_id = {p.payment_id: p for p in d["payments"]}
    reference_now = max(p.captured_at for p in d["payments"])

    ledger = AuditLedger(session)
    store = ApprovalWorkflowStore()
    provider = MockAIProvider()

    results = {}
    for bundle in d["bundles"]:
        payment = payments_by_id[bundle.payment_id]
        result = run_decision_pipeline(payment, bundle, context, graph, provider, ledger, reference_now, store)
        session.commit()
        results[bundle.order_id] = result

    yield {"results": results, "session": session, "reference_now": reference_now, **d}
    session.close()


# --- M7 fixtures below. M1-M6 fixtures above are untouched. ---

@pytest.fixture(scope="session")
def full_pipeline_run(tmp_path_factory, dataset_seed_dir):
    """Runs the ENTIRE M7 orchestrator (ingest -> reconcile -> exception
    intelligence -> per-exception decision -> audit) as ONE call, exactly
    the way a real caller would -- not by manually invoking M2/M3/M6
    separately and combining results afterward. Session-scoped and shared
    read-only across M7 tests; its own isolated SQLite DB."""
    from app.ai.provider import MockAIProvider
    from app.db.session import init_db, make_engine, make_session_factory
    from app.services.reconciliation_pipeline import run_reconciliation_pipeline
    from shared.money import loads

    db_path = tmp_path_factory.mktemp("m7db") / "reconcileai.db"
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()

    result = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider())
    ground_truth = loads((dataset_seed_dir / "ground_truth.json").read_text())

    yield {"result": result, "session": session, "ground_truth": ground_truth}
    session.close()
