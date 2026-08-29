"""M10 Phase 15: provenance integrity. Every evidence item must trace back
to a real source; fabricated/altered/broken references must be detected,
never silently accepted."""
import copy

from app.explainability.builder import build_explanation
from app.explainability.provenance_check import validate_provenance


def test_real_explanation_passes_provenance_validation(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    validation = validate_provenance(explanation, result)
    assert validation.valid is True
    assert validation.errors == []


def test_provenance_validation_against_the_real_ledger(get_decision, decision_env):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    validation = validate_provenance(explanation, result, ledger=decision_env.ledger)
    assert validation.valid is True


def test_nonexistent_source_settlement_id_is_detected(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    explanation.source_records.settlement_ids.append("STL-DOES-NOT-EXIST")
    validation = validate_provenance(explanation, result)
    assert validation.valid is False
    assert any("STL-DOES-NOT-EXIST" in e for e in validation.errors)


def test_modified_exception_id_is_detected(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    explanation.exception_id = "EXC-forged-0000"
    validation = validate_provenance(explanation, result)
    assert validation.valid is False
    assert any("exception_id" in e for e in validation.errors)


def test_invalid_correlation_id_is_detected(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    explanation.audit_references.correlation_id = "CORR-forged"
    validation = validate_provenance(explanation, result)
    assert validation.valid is False


def test_broken_audit_reference_is_detected_against_the_real_ledger(get_decision, decision_env):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    explanation.audit_references.correlation_id = "CORR-never-appended-anywhere"
    validation = validate_provenance(explanation, result, ledger=decision_env.ledger)
    assert validation.valid is False
    assert any("no matching audit events" in e for e in validation.errors)


def test_fabricated_ai_hypothesis_id_is_detected(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    fabricated = copy.deepcopy(explanation.ai_hypotheses[0])
    fabricated.hypothesis_id = "HYP-fabricated-not-real"
    explanation.ai_hypotheses.append(fabricated)
    validation = validate_provenance(explanation, result)
    assert validation.valid is False
    assert any("HYP-fabricated-not-real" in e for e in validation.errors)


def test_fabricated_self_challenge_reference_is_detected(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    if explanation.self_challenge:
        fabricated = copy.deepcopy(explanation.self_challenge[0])
        fabricated.hypothesis_id = "HYP-not-real-either"
        explanation.self_challenge.append(fabricated)
        validation = validate_provenance(explanation, result)
        assert validation.valid is False
