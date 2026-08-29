from __future__ import annotations

import pytest

from tests.adversarial.helpers import Dataset, DecisionEnvironment, decide_one, find_payment_by_order, pick_by_archetype


@pytest.fixture(scope="session")
def base_dataset(ingested_full_dataset) -> Dataset:
    d = ingested_full_dataset
    return Dataset(
        payments=d["payments"], settlements=d["settlements"], bank_transactions=d["bank_transactions"],
        refunds=d["refunds"], fee_rules=d["fee_rules"],
    )


@pytest.fixture(scope="session")
def ground_truth(ingested_full_dataset) -> list[dict]:
    return ingested_full_dataset["ground_truth"]


@pytest.fixture()
def mutated_dataset(base_dataset) -> Dataset:
    return base_dataset.clone_all()


@pytest.fixture(scope="module")
def decision_env(tmp_path_factory) -> DecisionEnvironment:
    from app.ai.provider import MockAIProvider
    from app.audit.ledger import AuditLedger
    from app.db.session import init_db, make_engine, make_session_factory
    from app.policy.approval import ApprovalWorkflowStore

    db_path = tmp_path_factory.mktemp("expl_decision_env") / "explainability.db"
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()
    return DecisionEnvironment(
        ledger=AuditLedger(session), approval_store=ApprovalWorkflowStore(), provider=MockAIProvider(), session=session,
    )


@pytest.fixture()
def get_decision(mutated_dataset, ground_truth, decision_env):
    """Returns a helper: get_decision(archetype, index, not_adversarial=True)
    -> (DecisionResult, payment, settlement, context) for a real dataset
    record, via the exact same M4-M6 decision pipeline every other
    milestone's tests use -- no shortcuts, no fabricated results."""
    from app.engines.reconciliation.candidate_generation import build_context

    def _get(archetype: str, index: int = 0, *, not_adversarial: bool = True):
        order_id = pick_by_archetype(ground_truth, archetype, index, not_adversarial=not_adversarial)
        payment = find_payment_by_order(mutated_dataset, order_id)
        result = decide_one(mutated_dataset, payment.payment_id, decision_env)
        context = build_context(
            mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions,
            mutated_dataset.refunds, mutated_dataset.fee_rules,
        )
        settlement = next((s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id), None)
        return result, payment, settlement, context

    return _get
