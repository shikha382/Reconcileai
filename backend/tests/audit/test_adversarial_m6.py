"""Phase 18: the 12 numbered adversarial tests from the M6 brief."""
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.ai.policy import HypothesisOutcome
from app.ai.schemas import AIHypothesis, HypothesisType, RecommendedAction, TestHypothesisOutput
from app.audit.ledger import AuditAppendError, AuditLedger
from app.audit.verify import verify_chain
from app.challenge.contradiction import build_contradiction_record, has_unresolved_contradiction
from app.db.models import AuditEventRecord
from app.policy.approval import ApprovalWorkflowStore
from app.policy.authorization import AuthorizationError, require_authorization
from app.policy.engine import evaluate_policy
from app.policy.schemas import Actor, ActorType, Capability, PolicyDecisionType, PolicyInput, RiskLevel


def _base_policy_input(**overrides):
    defaults = dict(
        exception_id="EXC-adv", exception_type="fee_mismatch", verifier_status="VERIFIED",
        residual_amount=__import__("decimal").Decimal("0.00"), financial_exposure=__import__("decimal").Decimal("500.00"),
        ai_confidence=0.99, evidence_complete=True, conflicting_evidence=False, ambiguous=False,
        risk_score=__import__("decimal").Decimal("1.00"), risk_level=RiskLevel.LOW,
        auto_resolution_eligible_category=True,
    )
    defaults.update(overrides)
    return PolicyInput(**defaults)


# 1. Verifier contradicts AI -- a hypothesis with high self-reported
# confidence but a failed deterministic verification must never be trusted.
def test_01_verifier_contradiction_overrides_high_ai_confidence():
    hypothesis = AIHypothesis(
        hypothesis_id="HYP-1", exception_id="EXC-1", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE,
        claim="fee explains it", record_ids=["SETL-1"], evidence_ids=["EV-1"],
        confidence=0.99, recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
    )
    verifier_result = TestHypothesisOutput(
        hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=False,
        expected_value="100.00", observed_value="90.17", residual="9.83",
        reason="fee amount does not match", evidence_ids=["EV-1"],
    )
    outcome = HypothesisOutcome(hypothesis=hypothesis, verifier_result=verifier_result, grounded=True,
                                 decision=RecommendedAction.REJECTED, reason="deterministic verification failed")
    record = build_contradiction_record(outcome)
    assert record.status == "CONTRADICTED"  # the AI's 0.99 self-confidence is never consulted here


# 2. Risk engine overrides an AI/verified low-risk claim.
def test_02_risk_tier_overrides_verified_and_eligible_input():
    policy_input = _base_policy_input(risk_level=RiskLevel.HIGH, financial_exposure=__import__("decimal").Decimal("500.00"))
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-HIGH-RISK-001" in decision.rules_passed


# 3. Ambiguous auto-resolution attempt must be blocked regardless of everything else looking safe.
def test_03_ambiguous_candidate_never_auto_resolves():
    policy_input = _base_policy_input(ambiguous=True)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-AMBIG-001" in decision.rules_passed


# 4. A contradiction (conflicting_evidence) blocks auto-resolution even
# when every other signal looks eligible.
def test_04_conflicting_evidence_blocks_auto_resolution():
    policy_input = _base_policy_input(conflicting_evidence=True)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-CONFLICT-001" in decision.rules_passed


def _chain(session, n=4):
    ledger = AuditLedger(session)
    records = []
    for i in range(n):
        records.append(ledger.append("EXCEPTION_CREATED", "exception", f"EXC-{i}", "SYSTEM", "test", {"i": i}, f"CORR-{i}"))
    session.commit()
    return records


# 5. Payload modification invalidates the chain.
def test_05_payload_modification_invalidates_chain(db_session):
    import json
    records = _chain(db_session)
    victim = records[1]
    payload = json.loads(victim.payload_json)
    payload["i"] = "tampered"
    victim.payload_json = json.dumps(payload, sort_keys=True)
    db_session.commit()
    assert verify_chain(db_session).valid is False


# 6. Event deletion invalidates the chain.
def test_06_event_deletion_invalidates_chain(db_session):
    records = _chain(db_session)
    db_session.delete(records[1])
    db_session.commit()
    assert verify_chain(db_session).valid is False


# 7. Event insertion (rogue row, forged hash, never went through
# AuditLedger.append) invalidates the chain even though it takes the next
# free sequence number -- its hash was never legitimately computed.
def test_07_event_insertion_invalidates_chain(db_session):
    records = _chain(db_session)
    rogue = AuditEventRecord(
        event_id="EVT-rogueinsert1", sequence=records[-1].sequence + 1, event_type="FORGED",
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None), entity_type="exception", entity_id="EXC-rogue",
        actor_type="SYSTEM", actor_id=None, source="attacker", correlation_id="CORR-rogue",
        payload_json="{}", schema_version="1.0.0", previous_event_hash=records[-1].event_hash, event_hash="1" * 64,
    )
    db_session.add(rogue)
    db_session.commit()
    assert verify_chain(db_session).valid is False


# 8. Reordering invalidates the chain.
def test_08_event_reordering_invalidates_chain(db_session):
    records = _chain(db_session)
    a, b = records[1], records[2]
    a_seq, b_seq = a.sequence, b.sequence
    # Swap via an unused placeholder to avoid transiently violating the
    # sequence column's unique constraint (test-harness mechanic only).
    a.sequence = -1
    db_session.flush()
    b.sequence = a_seq
    db_session.flush()
    a.sequence = b_seq
    db_session.commit()
    assert verify_chain(db_session).valid is False


# 9. Forged previous_hash invalidates the chain.
def test_09_forged_previous_hash_invalidates_chain(db_session):
    records = _chain(db_session)
    records[2].previous_event_hash = "a" * 64
    db_session.commit()
    result = verify_chain(db_session)
    assert result.valid is False
    assert result.reason == "PREVIOUS_HASH_MISMATCH"


# 10. Unauthorized audit modification is rejected -- AI cannot append,
# and no actor at all can update/delete (the capability doesn't exist).
def test_10_unauthorized_audit_actor_rejected():
    ai = Actor(ActorType.AI, "ai-1")
    with pytest.raises(AuthorizationError):
        require_authorization(ai, Capability.APPEND_AUDIT)
    assert not hasattr(AuditLedger, "update")
    assert not hasattr(AuditLedger, "delete")


# 11. Audit persistence failure is fail-safe -- a rejected append never
# silently produces a row, and a failed commit rolls back the whole
# transaction (decision state change + audit event succeed or fail together).
def test_11_audit_append_failure_does_not_silently_create_a_row(db_session):
    ledger = AuditLedger(db_session)
    before = ledger.count()
    with pytest.raises(AuditAppendError):
        ledger.append("EXCEPTION_CREATED", "exception", "EXC-bad", "SYSTEM", "test", {"event_hash": "attacker-forged"}, "CORR-bad")
    db_session.rollback()
    assert ledger.count() == before


def test_11b_failed_commit_rolls_back_the_audit_event_too(db_session):
    ledger = AuditLedger(db_session)
    before = ledger.count()
    ledger.append("EXCEPTION_CREATED", "exception", "EXC-ok", "SYSTEM", "test", {"k": "v"}, "CORR-ok")
    # Force a commit failure by adding a row that violates the event_id PK
    # uniqueness constraint in the SAME transaction as the pending append.
    dupe = AuditEventRecord(
        event_id="EVT-duplicate-pk01", sequence=999, event_type="X", timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        entity_type="exception", entity_id="EXC-dup", actor_type="SYSTEM", actor_id=None, source="test",
        correlation_id="CORR-dup", payload_json="{}", schema_version="1.0.0", previous_event_hash="0" * 64, event_hash="0" * 64,
    )
    dupe2 = AuditEventRecord(
        event_id="EVT-duplicate-pk01", sequence=1000, event_type="X", timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        entity_type="exception", entity_id="EXC-dup2", actor_type="SYSTEM", actor_id=None, source="test",
        correlation_id="CORR-dup2", payload_json="{}", schema_version="1.0.0", previous_event_hash="0" * 64, event_hash="1" * 64,
    )
    db_session.add(dupe)
    db_session.add(dupe2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert ledger.count() == before  # the earlier, legitimate append never silently survived either


# 12. Duplicate event/request submission is idempotent -- creating a review
# request twice for the same (exception, proposal, policy_version) never
# produces two pending reviews (M5's guarantee, unchanged by M6).
def test_12_duplicate_review_request_creation_is_idempotent(full_m6_decisions):
    results = full_m6_decisions["results"]
    reviewed = next(r for r in results.values() if r.review is not None)

    store = ApprovalWorkflowStore()
    first = store.create_review_request(
        reviewed.exception_id, reviewed.proposal, reviewed.policy_decision, "system",
        reference_now=full_m6_decisions["reference_now"],
    )
    second = store.create_review_request(
        reviewed.exception_id, reviewed.proposal, reviewed.policy_decision, "system",
        reference_now=full_m6_decisions["reference_now"],
    )
    assert first.review_id == second.review_id
    assert len(store._reviews_by_key) == 1
