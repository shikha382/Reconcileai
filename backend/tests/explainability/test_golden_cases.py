"""M10 Phase 17: golden explanation cases. Tests structured SEMANTIC FACTS
(decision, residual, verification result, policy.required_approval, ...),
never a snapshot of arbitrary wording -- natural-language phrasing may
change freely; the underlying financial facts must not.
"""
from decimal import Decimal

from app.explainability.builder import build_explanation
from app.explainability.completeness import check_explanation_completeness
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype


# GOLDEN-01: exact match.
def test_golden_01_exact_match(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.decision == "SAFE_TO_RESOLVE"
    assert e.matching_evidence.match_status in ("EXACT_MATCH", "NORMALIZED_MATCH")
    assert Decimal(e.financial_summary.unexplained_amount) == Decimal("0.00")


# GOLDEN-02: normalized match -- settlement stays directly linked (so M2's
# single-linked-settlement path, not candidate scoring, is what runs); only
# the reference text gains whitespace/case/punctuation noise that breaks a
# raw substring match but survives normalize_reference().
def test_golden_02_normalized_match(mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context

    order_id = pick_by_archetype(ground_truth, "exact_match", 5)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    token = payment.payment_id.replace("-", "")
    settlement.utr_reference = f"utr-{token[:3]}-{token[3:]}".lower()  # breaks the raw substring match, survives normalization
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.decision == "SAFE_TO_RESOLVE"
    assert e.matching_evidence.match_status == "NORMALIZED_MATCH"


# GOLDEN-03: split settlement.
def test_golden_03_split_settlement(get_decision):
    result, payment, settlement, context = get_decision("split_settlement", 0)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert len(e.source_records.settlement_ids) >= 2
    assert e.decision == "SAFE_TO_RESOLVE"


# GOLDEN-04: aggregated settlement.
def test_golden_04_aggregated_settlement(get_decision):
    result, payment, settlement, context = get_decision("aggregated_settlement", 0)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.decision == "SAFE_TO_RESOLVE"
    assert e.exception_evidence["root_cause"] == "aggregated_settlement"


# GOLDEN-05: refund.
def test_golden_05_refund(get_decision, ground_truth):
    order_id = pick_by_archetype(ground_truth, "refund_mismatch", 0)
    row = next(r for r in ground_truth if r["order_id"] == order_id)
    result, payment, settlement, context = get_decision("refund_mismatch", 0)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.source_records.refund_ids
    if row["expected_action"] == "auto_resolve":
        assert e.decision == "SAFE_TO_RESOLVE"


# GOLDEN-06: fee mismatch (the real adversarial case).
def test_golden_06_fee_mismatch(mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context

    order_id = next(r["order_id"] for r in ground_truth if r["archetype"] == "fee_mismatch" and r.get("is_adversarial"))
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.decision != "SAFE_TO_RESOLVE"
    fee_hyp = next((h for h in e.ai_hypotheses if h.hypothesis_type == "FEE_EXPLAINS_DIFFERENCE"), None)
    assert fee_hyp is not None and fee_hyp.verification_result == "FAILED"


# GOLDEN-07: ambiguous match.
def test_golden_07_ambiguous_match(get_decision):
    result, payment, settlement, context = get_decision("ambiguous_match", 0, not_adversarial=False)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.matching_evidence.match_status == "AMBIGUOUS"
    assert e.decision == "HUMAN_REVIEW"


# GOLDEN-08: missing evidence.
def test_golden_08_missing_evidence(get_decision):
    result, payment, settlement, context = get_decision("missing_transaction", 0)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.missing_evidence
    assert e.decision == "UNRESOLVED"


# GOLDEN-09: contradictory evidence (same real adversarial fee_mismatch case).
def test_golden_09_contradictory_evidence(mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context

    order_id = next(r["order_id"] for r in ground_truth if r["archetype"] == "fee_mismatch" and r.get("is_adversarial"))
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.contradictions
    assert all(c.status == "UNRESOLVED" for c in e.contradictions)


# GOLDEN-10: AI hypothesis rejected (same case).
def test_golden_10_ai_hypothesis_rejected(mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context

    order_id = next(r["order_id"] for r in ground_truth if r["archetype"] == "fee_mismatch" and r.get("is_adversarial"))
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert any(h.final_disposition == "REJECTED" for h in e.ai_hypotheses)


# GOLDEN-11: AI unavailable.
def test_golden_11_ai_unavailable(mutated_dataset, ground_truth, tmp_path):
    from app.ai.provider import ProviderError
    from app.audit.ledger import AuditLedger
    from app.db.session import init_db, make_engine, make_session_factory
    from app.engines.reconciliation.candidate_generation import build_context
    from app.policy.approval import ApprovalWorkflowStore
    from tests.adversarial.helpers import DecisionEnvironment

    class _AlwaysFailingProvider:
        def decide_next_action(self, state):
            raise ProviderError("simulated outage")

    order_id = pick_by_archetype(ground_truth, "unexplained_difference", 1)
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next((s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id), None)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)

    engine = make_engine(tmp_path / "golden11.db")
    init_db(engine)
    session = make_session_factory(engine)()
    env = DecisionEnvironment(ledger=AuditLedger(session), approval_store=ApprovalWorkflowStore(), provider=_AlwaysFailingProvider(), session=session)
    result = decide_one(mutated_dataset, payment.payment_id, env)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    session.close()
    engine.dispose()

    assert e.ai_investigation_status == "UNAVAILABLE_OR_DEGRADED"
    assert e.decision != "SAFE_TO_RESOLVE"


# GOLDEN-12: policy-denied automation (ambiguous, MANDATORY_APPROVAL tier).
def test_golden_12_policy_denied_automation(get_decision):
    result, payment, settlement, context = get_decision("ambiguous_match", 0, not_adversarial=False)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.policy.decision != "SAFE_TO_RESOLVE"
    assert "POLICY-AMBIG-001" in e.policy.rules_passed


# GOLDEN-13: human review (real duplicate archetype).
def test_golden_13_human_review(get_decision):
    result, payment, settlement, context = get_decision("duplicate", 0, not_adversarial=False)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.decision == "HUMAN_REVIEW"
    assert e.policy.required_approval is True


# GOLDEN-14: rejected/blocked (real adversarial fee_mismatch, BLOCK tier).
def test_golden_14_rejected_blocked(mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context

    order_id = next(r["order_id"] for r in ground_truth if r["archetype"] == "fee_mismatch" and r.get("is_adversarial"))
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.decision == "REJECTED"
    assert e.policy.blocked_reasons


# GOLDEN-15: fully auto-resolved clean case (a different archetype from GOLDEN-01, for diversity).
def test_golden_15_fully_auto_resolved_clean_case(get_decision):
    result, payment, settlement, context = get_decision("timing_mismatch", 0)
    e = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert e.decision == "SAFE_TO_RESOLVE"
    completeness = check_explanation_completeness(e)
    assert completeness.explanation_complete
