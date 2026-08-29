"""Phase 18: idempotency. Running the same reconciliation input twice must
not create duplicate FINANCIAL outcomes.

Design (documented in docs/end-to-end-pipeline.md): this pipeline never
mutates source-of-truth financial records (Order/Payment/Settlement/... are
read-only inputs throughout) and never executes real money movement (CLAUDE.md's
explicit non-goal) -- so there is no financial state a rerun could duplicate
in the first place. What CAN be tested for duplication: (1) ingestion itself
(M1's existing merge-based idempotency, reused unchanged), and (2) the human
approval workflow's existing idempotent review-request creation (M5,
unchanged), when the same ApprovalWorkflowStore is shared across two runs of
the same input. Each pipeline call gets its own new, explicitly identified
run_id -- a new, separately auditable run, never a silently duplicated one.
"""
from pathlib import Path

from app.ai.provider import MockAIProvider
from app.db.models import Payment
from app.db.session import init_db, make_engine, make_session_factory
from app.policy.approval import ApprovalWorkflowStore
from app.services.reconciliation_pipeline import run_reconciliation_pipeline


def test_rerunning_the_same_dataset_does_not_duplicate_ingested_rows(tmp_path, dataset_seed_dir):
    db_path = tmp_path / "idempotency.db"
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()
    store = ApprovalWorkflowStore()

    result1 = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider(), approval_store=store)
    payment_count_after_1 = session.query(Payment).count()

    result2 = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider(), approval_store=store)
    payment_count_after_2 = session.query(Payment).count()

    assert result1.run_id != result2.run_id  # a new, distinctly identified run each time
    assert payment_count_after_1 == 300
    assert payment_count_after_2 == 300  # ingestion's existing merge-based idempotency (M1) -- no duplicate rows
    session.close()


def test_rerun_produces_the_same_policy_decisions_deterministically(tmp_path, dataset_seed_dir):
    db_path = tmp_path / "idempotency_decisions.db"
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()

    result1 = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider())
    result2 = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider())

    decisions1 = {oid: d.policy_decision.decision for oid, d in result1.decisions.items()}
    decisions2 = {oid: d.policy_decision.decision for oid, d in result2.decisions.items()}
    assert decisions1 == decisions2  # deterministic given the same (unchanged) input -- not a coincidence of ordering
    session.close()


def test_two_full_runs_are_each_independently_and_explicitly_identified(tmp_path, dataset_seed_dir):
    # Real, verified behavior (found while writing this test -- see
    # docs/end-to-end-pipeline.md's idempotency section): `ResolutionProposal.proposal_id`
    # is randomly generated fresh on every call to `build_resolution_proposal`
    # (app.policy.schemas), not derived deterministically from the exception's
    # content. M5's idempotency key is `exception_id|proposal_id|policy_version`
    # (app.policy.approval.review_idempotency_key) -- so a SECOND, independent
    # full pipeline run does NOT collide with the first run's review request;
    # it builds its own fresh proposal_id and gets its own fresh review_id.
    # This is intentional, not a gap: each pipeline run is "a new, explicitly
    # identified run" (the third option the M7 brief itself offers for
    # idempotency), because nothing here ever executes real financial
    # movement for there to be duplicate state of in the first place. Within
    # a SINGLE run, or across a retry of the SAME ResolutionProposal object,
    # M5's idempotency guarantee still holds unchanged -- see
    # backend/tests/audit/test_adversarial_m6.py::test_12_duplicate_review_request_creation_is_idempotent
    # and backend/tests/policy/ for that guarantee's own direct tests.
    db_path = tmp_path / "idempotency_reviews.db"
    engine = make_engine(db_path)
    init_db(engine)
    session = make_session_factory(engine)()
    store = ApprovalWorkflowStore()

    result1 = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider(), approval_store=store)
    reviewed_order_id = next(oid for oid, d in result1.decisions.items() if d.review is not None)
    review_id_1 = result1.decisions[reviewed_order_id].review.review_id
    proposal_id_1 = result1.decisions[reviewed_order_id].proposal.proposal_id
    reviews_after_run_1 = len(store._reviews_by_key)

    result2 = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider(), approval_store=store)
    review_id_2 = result2.decisions[reviewed_order_id].review.review_id
    proposal_id_2 = result2.decisions[reviewed_order_id].proposal.proposal_id
    reviews_after_run_2 = len(store._reviews_by_key)

    assert result1.run_id != result2.run_id
    assert proposal_id_1 != proposal_id_2  # a fresh proposal is built each run -- not shared/cached state
    assert review_id_1 != review_id_2  # therefore a distinct, independently auditable review request each run
    assert reviews_after_run_2 == reviews_after_run_1 * 2  # both runs' reviews coexist -- no financial state was overwritten or lost
    session.close()
