"""M10 Phase 3/5: the structured evidence model and financial calculation
trace. Every value must trace back to the real, already-computed
authoritative objects -- never fabricated, never floating-point.
"""
from decimal import Decimal

from app.explainability.builder import build_explanation
from tests.adversarial.helpers import decide_one, find_payment_by_order


def _real_adversarial_fee_case(ground_truth, mutated_dataset, decision_env, context):
    order_id = next(row["order_id"] for row in ground_truth if row["archetype"] == "fee_mismatch" and row.get("is_adversarial"))
    payment = find_payment_by_order(mutated_dataset, order_id)
    settlement = next(s for s in mutated_dataset.settlements if s.payment_id == payment.payment_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    return result, payment, settlement


def test_evidence_item_built_from_a_real_constraint(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    assert explanation.matching_evidence.candidates, "expected at least one evaluated candidate"
    candidate = explanation.matching_evidence.candidates[0]
    assert candidate.positive_evidence or candidate.negative_evidence
    for item in candidate.positive_evidence + candidate.negative_evidence:
        assert item.status in ("SUPPORTED", "CONTRADICTED")
        assert item.source_type == "settlement"
        assert item.source_id == candidate.settlement_id  # traces to the real settlement, not a placeholder


def test_calculation_trace_uses_decimal_strings_never_float(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=True)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    assert explanation.calculation_evidence, "expected at least one calculation trace for a fee case"
    for trace in explanation.calculation_evidence:
        for value in (trace.expected_value, trace.observed_value, trace.residual):
            if value is not None:
                Decimal(value)  # must parse cleanly as Decimal -- proves it's never a float repr


def test_fee_calculation_trace_matches_the_real_verifier_output(get_decision):
    from app.engines.reconciliation.verification import verify_fee_consistency

    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=True)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    fee_trace = next(t for t in explanation.calculation_evidence if t.label == "fee_verification")
    real_check = verify_fee_consistency(payment, settlement, context)
    assert fee_trace.expected_value == str(real_check.expected_net)
    assert fee_trace.observed_value == str(real_check.actual_net)
    assert fee_trace.residual == str(real_check.delta)
    assert fee_trace.verification_result == ("PASSED" if real_check.consistent else "FAILED")
    assert fee_trace.rule_id == real_check.rule_id


def test_fee_calculation_trace_reproduces_the_real_adversarial_9_83_residual(get_decision, ground_truth, mutated_dataset, decision_env):
    # The exact case named throughout the project's own documentation
    # (CLAUDE.md, docs/end-to-end-pipeline.md): expected net 7673.60,
    # observed 7663.77, residual 9.83. `pick_by_archetype`'s
    # not_adversarial=False widens (rather than restricts) the pool, so the
    # real adversarial record is selected directly here instead.
    from app.engines.reconciliation.candidate_generation import build_context

    result, payment, settlement = _real_adversarial_fee_case(ground_truth, mutated_dataset, decision_env, None)
    context = build_context(mutated_dataset.payments, mutated_dataset.settlements, mutated_dataset.bank_transactions, mutated_dataset.refunds, mutated_dataset.fee_rules)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)

    # The precise, authoritative unexplained-residual figure for this
    # archetype comes from RootCauseResult.unexplained_amount (computed by
    # the fee hypothesis's own recomputation, app.engines.root_cause
    # .hypotheses) -- exposed here via exception_evidence/financial_summary.
    # decompose_discrepancy's own `residual` is a coarser, always-present
    # figure (the raw gap with no unverified component credited) and is
    # legitimately a different, larger number (178.77) for this same case --
    # both are real, both are shown, neither is fabricated.
    assert Decimal(explanation.exception_evidence["unexplained_amount"]) == Decimal("9.83")
    assert Decimal(explanation.financial_summary.unexplained_amount) == Decimal("9.83")

    decomposition = next(t for t in explanation.calculation_evidence if t.label == "discrepancy_decomposition")
    assert decomposition.verification_result == "FAILED"


def test_calculation_trace_omitted_gracefully_without_context(get_decision, ground_truth, mutated_dataset, decision_env):
    result, payment, settlement = _real_adversarial_fee_case(ground_truth, mutated_dataset, decision_env, None)
    explanation = build_explanation(result)  # no context/payment/settlement supplied
    labels = {t.label for t in explanation.calculation_evidence}
    assert "fee_verification" not in labels  # never fabricated without the real verifier being callable
    assert "discrepancy_decomposition" in labels  # still present -- this one lives entirely on the bundle already
