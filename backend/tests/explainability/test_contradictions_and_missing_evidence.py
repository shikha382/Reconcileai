"""M10 Phase 12/13: contradictions and missing evidence must be represented
explicitly (never hidden inside prose), and missing evidence must never be
converted into a positive claim."""
from app.explainability.builder import build_explanation


def test_contradiction_shows_field_expected_observed_and_impact(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    fee_contradiction = next((c for c in explanation.contradictions if c.field == "FEE_EXPLAINS_DIFFERENCE"), None)
    assert fee_contradiction is not None
    assert fee_contradiction.status == "UNRESOLVED"
    assert fee_contradiction.impact == "AUTO_RESOLVE_NOT_PERMITTED"
    assert fee_contradiction.source_a == "ai_hypothesis"
    assert fee_contradiction.source_b == "deterministic_verifier"


def test_no_contradictions_for_a_clean_case(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.contradictions == []


def test_missing_transaction_case_reports_missing_evidence_not_a_positive_claim(get_decision):
    result, payment, settlement, context = get_decision("missing_transaction", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    assert explanation.missing_evidence
    item = explanation.missing_evidence[0]
    assert "cannot" in item.impact.lower() or "missing" in item.impact.lower() or "nothing exists" in item.impact.lower()
    # Never a positive claim like "is probably correct".
    for m in explanation.missing_evidence:
        assert "probably correct" not in m.impact.lower()
        assert "probably" not in m.impact.lower()


def test_missing_fee_rule_is_represented_as_missing_not_assumed_correct(get_decision, mutated_dataset, ground_truth, decision_env):
    from app.engines.reconciliation.candidate_generation import build_context
    from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype

    order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0, not_adversarial=True)
    payment = find_payment_by_order(mutated_dataset, order_id)
    mutated_dataset.fee_rules = [f for f in mutated_dataset.fee_rules if f.method != payment.method]
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)

    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    fee_rule_missing = next((m for m in explanation.missing_evidence if "fee rule" in m.required.lower()), None)
    assert fee_rule_missing is not None
    assert explanation.decision != "SAFE_TO_RESOLVE"
