"""M9 Phase 18: core financial safety invariants, named and tested
explicitly (each one is already exercised indirectly by the category tests
above; this file states them as first-class, individually-named properties
so a regression in any one is immediately attributable).
"""
from decimal import Decimal

import pytest

from app.policy.engine import evaluate_policy
from app.policy.schemas import PolicyDecisionType, PolicyInput, RiskLevel
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype


def _input(**overrides) -> PolicyInput:
    defaults = dict(
        exception_id="EXC-inv", exception_type="fee_mismatch", verifier_status="VERIFIED",
        residual_amount=Decimal("0.00"), financial_exposure=Decimal("50.00"), ai_confidence=0.9,
        evidence_complete=True, conflicting_evidence=False, ambiguous=False,
        risk_score=Decimal("1.00"), risk_level=RiskLevel.LOW, auto_resolution_eligible_category=True,
    )
    defaults.update(overrides)
    return PolicyInput(**defaults)


# INVARIANT 1: No negative monetary amount is ever accepted as legitimate --
# a negative residual is blocked outright, never treated as "less than expected, fine".
def test_invariant_01_no_negative_residual_is_accepted():
    decision = evaluate_policy(_input(residual_amount=Decimal("-10.00")))
    assert decision.decision == PolicyDecisionType.REJECTED
    assert "POLICY-NEGATIVE-RESIDUAL-001" in decision.rules_passed


# INVARIANT 2: no floating-point arithmetic anywhere in authoritative
# financial calculations -- every PolicyInput monetary field is Decimal, and
# shared.money.quantize refuses a raw float outright.
def test_invariant_02_money_module_refuses_float_input():
    from shared.money import quantize

    with pytest.raises(TypeError):
        quantize(1.1)  # type: ignore[arg-type]


# INVARIANT 3: if deterministic verification fails (CONTRADICTED), the
# final decision can never be SAFE_TO_RESOLVE.
def test_invariant_03_contradicted_verifier_status_never_auto_resolves():
    decision = evaluate_policy(_input(verifier_status="CONTRADICTED"))
    assert decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
    assert decision.decision == PolicyDecisionType.REJECTED


# INVARIANT 4: if policy denies automation (category-blocked), final
# decision can never be SAFE_TO_RESOLVE.
def test_invariant_04_policy_blocked_category_never_auto_resolves():
    decision = evaluate_policy(_input(auto_resolution_eligible_category=False))
    assert decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# INVARIANT 5: if evidence is insufficient, final decision can never be SAFE_TO_RESOLVE.
def test_invariant_05_insufficient_evidence_never_auto_resolves():
    decision = evaluate_policy(_input(evidence_complete=False))
    assert decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# INVARIANT 6: if a contradiction remains unresolved (conflicting_evidence),
# final decision can never be SAFE_TO_RESOLVE.
def test_invariant_06_unresolved_contradiction_never_auto_resolves():
    decision = evaluate_policy(_input(conflicting_evidence=True))
    assert decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# INVARIANT 7: AI output alone can never create a financial resolution --
# ai_confidence is never read by evaluate_policy regardless of its value.
def test_invariant_07_ai_output_alone_cannot_create_a_resolution():
    low = evaluate_policy(_input(ai_confidence=0.0, conflicting_evidence=True))
    high = evaluate_policy(_input(ai_confidence=1.0, conflicting_evidence=True))
    assert low.decision == high.decision == PolicyDecisionType.HUMAN_REVIEW


# INVARIANT 8: audit-chain tampering can never remain VALID -- reconfirmed
# via M6's own verify_chain (not re-derived); see test_audit_tampering.py
# for the full adversarial-context version of this invariant.
def test_invariant_08_tampered_chain_never_reports_valid(mutated_dataset, ground_truth, decision_env):
    import json

    from app.audit.verify import verify_chain

    order_id = pick_by_archetype(ground_truth, "exact_match", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    decide_one(mutated_dataset, payment.payment_id, decision_env)

    events = decision_env.ledger.all_events()
    victim = events[0]
    payload = json.loads(victim.payload_json)
    payload["tampered"] = True
    victim.payload_json = json.dumps(payload, sort_keys=True)
    decision_env.session.commit()

    assert verify_chain(decision_env.session).valid is False


# INVARIANT 9: ambiguous matching can never silently become an exact match --
# reconfirmed via M2's own scoring: an ambiguous top-candidate score never
# gets treated as "accepted" without clearing BOTH the threshold and the
# margin over its runner-up.
def test_invariant_09_ambiguous_score_is_never_silently_accepted(mutated_dataset, ground_truth):
    order_id = pick_by_archetype(ground_truth, "ambiguous_match", 0, not_adversarial=False)
    payment = find_payment_by_order(mutated_dataset, order_id)
    from tests.adversarial.helpers import analyze

    bundle = analyze(mutated_dataset, payment.payment_id)
    assert bundle.reconciliation_status != "matched"


# INVARIANT 10: a replay must not create duplicate financial effects --
# reconfirmed via M1's ingestion idempotency and M7's run-level idempotency
# (see test_duplication_replay.py for the full scenarios); restated here as
# a named, standalone invariant check.
def test_invariant_10_replaying_ingestion_creates_no_duplicate_rows(tmp_path, dataset_seed_dir):
    from app.db.models import Payment
    from app.db.session import init_db, make_engine, make_session_factory
    from app.ingestion.pipeline import ingest_source_directory

    engine = make_engine(tmp_path / "invariant10.db")
    init_db(engine)
    session = make_session_factory(engine)()
    ingest_source_directory(session, dataset_seed_dir)
    ingest_source_directory(session, dataset_seed_dir)
    session.commit()
    assert session.query(Payment).count() == 300
    session.close()
