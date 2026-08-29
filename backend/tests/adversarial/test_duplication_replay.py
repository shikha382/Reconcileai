"""M9 Category H: duplication / replay (Phase 11). No duplicate financial
effect, no duplicated authoritative resolution, audit behavior stays
understandable, and run-level idempotency stays consistent with M7/M8
(reused directly here, not re-derived).
"""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import analyze, clone, decide_one, find_payment_by_order, pick_by_archetype


# 1. Duplicate payment record (two distinct payment_ids for what looks like
# the same real-world transaction) must not cause either to be silently
# double-resolved against the same settlement.
def test_01_duplicate_payment_record_does_not_double_resolve(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    duplicate_payment = clone(payment, payment_id=f"{payment.payment_id}-DUP", gateway_ref=f"{payment.gateway_ref}-DUP")
    mutated_dataset.payments.append(duplicate_payment)

    original_result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    duplicate_result = decide_one(mutated_dataset, duplicate_payment.payment_id, decision_env)
    # The duplicate payment has no settlement of its own -- it must not be
    # silently matched to the ORIGINAL's settlement (which is already
    # legitimately claimed), and must not auto-resolve.
    assert duplicate_result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 2. Duplicate settlement (both genuinely linked to the same payment) --
# extends test_08 from Category A with a full decision-level assertion.
def test_02_duplicate_settlement_never_auto_resolves(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 1)
    payment = find_payment_by_order(mutated_dataset, order_id)
    original = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    duplicate = clone(original, settlement_id=f"{original.settlement_id}-DUP")
    mutated_dataset.settlements.append(duplicate)

    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 3. Duplicate/replayed bank transaction line -- a credit transaction
# processed twice must not silently double the confirmed credit and thereby
# manufacture a false exact match out of what was really an under-settlement.
def test_03_replayed_bank_credit_line_does_not_manufacture_a_false_match(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "under_settlement", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    original_credit = next(
        b for b in mutated_dataset.bank_transactions
        if b.matched_settlement_id == settlement.settlement_id and b.direction == "credit"
    )
    # Before replay: under_settlement is already a genuine shortfall (never
    # auto-resolved). Replaying (duplicating) the SAME credit line must not
    # coincidentally "fix" that shortfall by doubling it into an exact match.
    result_before = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result_before.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE

    replay = clone(original_credit, bank_txn_id=f"{original_credit.bank_txn_id}-REPLAY")
    mutated_dataset.bank_transactions.append(replay)
    result_after = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result_after.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 4. Duplicate refund -- covered thoroughly in test_refund_manipulation.py
# (item 5, including the real bug found and fixed there); not duplicated here.


# 5. Replayed source file (re-ingesting the same directory) -- M1's
# existing merge-based idempotency, reused and re-confirmed here as an M9
# regression check, not re-derived.
def test_05_replaying_the_same_source_directory_does_not_duplicate_rows(tmp_path, dataset_seed_dir):
    from app.db.models import Payment
    from app.db.session import init_db, make_engine, make_session_factory
    from app.ingestion.pipeline import ingest_source_directory

    engine = make_engine(tmp_path / "replay.db")
    init_db(engine)
    session = make_session_factory(engine)()
    ingest_source_directory(session, dataset_seed_dir)
    session.commit()
    count_1 = session.query(Payment).count()

    ingest_source_directory(session, dataset_seed_dir)  # replay the exact same source
    session.commit()
    count_2 = session.query(Payment).count()

    assert count_1 == count_2 == 300
    session.close()


# 6. Repeated API run -- already covered end-to-end in
# backend/tests/pipeline/test_pipeline_idempotency.py and
# backend/tests/api/test_runs.py; reused, not duplicated here.


# 7. Repeated exception processing -- running the decision pipeline twice
# for the SAME exception must be deterministic and must never flip a
# correctly-blocked case into an auto-resolve on a later attempt.
def test_07_repeated_exception_processing_is_deterministic_and_never_flips_to_unsafe(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0, not_adversarial=False)
    payment = find_payment_by_order(mutated_dataset, order_id)

    first = decide_one(mutated_dataset, payment.payment_id, decision_env)
    second = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert first.policy_decision.decision == second.policy_decision.decision
    assert first.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
