from __future__ import annotations

import pytest

from tests.adversarial.helpers import Dataset, DecisionEnvironment


@pytest.fixture(scope="session")
def base_dataset(ingested_full_dataset) -> Dataset:
    """The real 300-record M1 dataset, wrapped as a plain Dataset -- shared,
    session-scoped, and NEVER mutated directly (every test clones it first
    via `base_dataset.clone_all()`)."""
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
    """A fresh, fully-cloned copy of the base dataset -- safe for any test to
    mutate freely without affecting other tests or the shared base."""
    return base_dataset.clone_all()


@pytest.fixture(scope="module")
def decision_env(tmp_path_factory) -> DecisionEnvironment:
    """One shared, isolated audit ledger/session/provider/approval-store for
    an entire test module -- module-scoped purely for speed (DB setup cost),
    never for hiding cross-test state: every scenario still gets its own
    fresh mutated Dataset and its own exception_id/correlation_id."""
    from app.ai.provider import MockAIProvider
    from app.audit.ledger import AuditLedger
    from app.db.session import init_db, make_engine, make_session_factory
    from app.policy.approval import ApprovalWorkflowStore

    db_path = tmp_path_factory.mktemp("adv_decision_env") / "adversarial.db"
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()
    return DecisionEnvironment(
        ledger=AuditLedger(session), approval_store=ApprovalWorkflowStore(), provider=MockAIProvider(), session=session,
    )
