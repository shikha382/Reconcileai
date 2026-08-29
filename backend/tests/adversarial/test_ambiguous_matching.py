"""M9 Category G: ambiguous matching (Phase 10). Two plausible candidates
must never be resolved by an arbitrary pick -- AMBIGUOUS -> HUMAN_REVIEW is
the only safe outcome unless a deterministic rule (score threshold AND
margin) genuinely, unambiguously settles it. Target: ZERO unsafe ambiguous
auto-resolutions, system-wide.
"""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import analyze, clone, decide_one, find_payment_by_order, pick_by_archetype


# 1. Real ambiguous_match archetype -- regression re-confirmation.
def test_01_real_ambiguous_match_reaches_human_review(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "ambiguous_match", 0, not_adversarial=False)
    payment = find_payment_by_order(mutated_dataset, order_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
    assert result.policy_decision.decision == PolicyDecisionType.HUMAN_REVIEW


# 2. Constructed ambiguity: two unlinked settlements, same amount, both
# weakly referencing the payment -- neither may be silently preferred.
def test_02_constructed_two_equally_plausible_candidates_are_never_auto_resolved(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "exact_match", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    real_settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    real_settlement.payment_id = None  # both candidates now unlinked, competing purely on score

    rival = clone(
        real_settlement, settlement_id=f"{real_settlement.settlement_id}-RIVAL",
        utr_reference=real_settlement.utr_reference,  # identical reference signal
    )
    mutated_dataset.settlements.append(rival)
    # Give the rival its own confirmed bank credit at the SAME amount, so
    # both candidates score identically on amount too.
    from tests.adversarial.helpers import clone as _clone
    original_credit = next(
        b for b in mutated_dataset.bank_transactions
        if b.matched_settlement_id == real_settlement.settlement_id and b.direction == "credit"
    )
    rival_credit = _clone(original_credit, bank_txn_id=f"{original_credit.bank_txn_id}-RIVAL", matched_settlement_id=rival.settlement_id)
    mutated_dataset.bank_transactions.append(rival_credit)

    bundle = analyze(mutated_dataset, payment.payment_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    assert bundle.reconciliation_status == "ambiguous"
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# 3. System-wide sweep: every genuinely ambiguous exception in the real
# dataset (M2's own AMBIGUOUS status) must reach a non-auto-resolve
# decision -- zero unsafe ambiguous auto-resolutions, measured directly.
def test_03_zero_ambiguous_auto_resolutions_dataset_wide(mutated_dataset, decision_env):
    from tests.adversarial.helpers import analyze as _analyze
    from app.services.exception_service import run_exception_intelligence

    _, bundles = run_exception_intelligence(
        mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions,
        mutated_dataset.refunds, mutated_dataset.fee_rules,
    )
    ambiguous_bundles = [b for b in bundles if b.reconciliation_status == "ambiguous"]
    assert len(ambiguous_bundles) > 0, "expected at least one real ambiguous case in the dataset"

    unsafe = []
    for bundle in ambiguous_bundles:
        result = decide_one(mutated_dataset, bundle.payment_id, decision_env)
        if result.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE:
            unsafe.append(bundle.payment_id)
    assert unsafe == [], f"ambiguous cases incorrectly auto-resolved: {unsafe}"
