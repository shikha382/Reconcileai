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

    db_path = tmp_path_factory.mktemp("prio_decision_env") / "prioritization.db"
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()
    return DecisionEnvironment(
        ledger=AuditLedger(session), approval_store=ApprovalWorkflowStore(), provider=MockAIProvider(), session=session,
    )


@pytest.fixture()
def get_prioritized(mutated_dataset, ground_truth, decision_env):
    """Returns a helper: get_prioritized(archetype, index, not_adversarial=True)
    -> (PrioritizedException, DecisionResult, ExplanationReport, payment,
    reference_now) built through the real M2-M6+M10 pipeline, never
    shortcut or fabricated.
    """
    from app.explainability.builder import build_explanation
    from app.prioritization.scorer import build_prioritized_exception

    def _get(archetype: str, index: int = 0, *, not_adversarial: bool = True, reference_now=None):
        order_id = pick_by_archetype(ground_truth, archetype, index, not_adversarial=not_adversarial)
        payment = find_payment_by_order(mutated_dataset, order_id)
        result = decide_one(mutated_dataset, payment.payment_id, decision_env)
        ref_now = reference_now or max(p.captured_at for p in mutated_dataset.payments)
        explanation = build_explanation(result)
        prioritized = build_prioritized_exception(result, payment, ref_now, explanation)
        return prioritized, result, explanation, payment, ref_now

    return _get
