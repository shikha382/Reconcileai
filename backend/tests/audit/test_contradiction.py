"""Structured challenge/contradiction records -- built straight from an
already-computed HypothesisOutcome, never from free-form model text."""
from app.ai.policy import HypothesisOutcome
from app.ai.schemas import AIHypothesis, HypothesisType, RecommendedAction, TestHypothesisOutput
from app.challenge.contradiction import (
    CONTRADICTED,
    INSUFFICIENT_EVIDENCE,
    SUPPORTED,
    build_contradiction_record,
    has_unresolved_contradiction,
)


def _hypothesis(htype=HypothesisType.FEE_EXPLAINS_DIFFERENCE):
    return AIHypothesis(
        hypothesis_id="HYP-1", exception_id="EXC-1", hypothesis_type=htype,
        claim="a fee deduction explains the difference", record_ids=["SETL-1"], evidence_ids=["EV-1"],
        confidence=0.9, recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
    )


def _verifier(passed, residual="0.00"):
    return TestHypothesisOutput(
        hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, passed=passed,
        expected_value="100.00", observed_value="90.17", residual=residual,
        reason="test reason", evidence_ids=["EV-1"],
    )


def test_supported_hypothesis_yields_supported_status():
    outcome = HypothesisOutcome(
        hypothesis=_hypothesis(), verifier_result=_verifier(passed=True), grounded=True,
        decision=RecommendedAction.SAFE_TO_RESOLVE, reason="verified",
    )
    record = build_contradiction_record(outcome)
    assert record.status == SUPPORTED
    assert record.supporting_evidence == ["EV-1"]
    assert record.contradicting_evidence == []


def test_failed_verification_yields_contradicted_status():
    outcome = HypothesisOutcome(
        hypothesis=_hypothesis(), verifier_result=_verifier(passed=False, residual="9.83"), grounded=True,
        decision=RecommendedAction.REJECTED, reason="deterministic verification failed",
    )
    record = build_contradiction_record(outcome)
    assert record.status == CONTRADICTED
    assert record.contradicting_evidence == ["EV-1"]
    assert record.residual == "9.83"


def test_grounding_violation_yields_insufficient_evidence_regardless_of_verifier_result():
    # Even a "passed" verifier result must not count as SUPPORTED if the
    # hypothesis cited IDs never actually retrieved -- can't support a claim
    # grounded in nothing.
    outcome = HypothesisOutcome(
        hypothesis=_hypothesis(), verifier_result=_verifier(passed=True), grounded=False,
        decision=RecommendedAction.REJECTED, reason="ungrounded",
    )
    record = build_contradiction_record(outcome, grounding_violations=["SETL-999-never-retrieved"])
    assert record.status == INSUFFICIENT_EVIDENCE
    assert record.missing_evidence == ["SETL-999-never-retrieved"]
    assert record.supporting_evidence == []
    assert record.contradicting_evidence == []


def test_has_unresolved_contradiction_true_when_any_record_contradicted():
    supported = build_contradiction_record(HypothesisOutcome(
        hypothesis=_hypothesis(), verifier_result=_verifier(True), grounded=True,
        decision=RecommendedAction.SAFE_TO_RESOLVE, reason="ok",
    ))
    contradicted = build_contradiction_record(HypothesisOutcome(
        hypothesis=_hypothesis(), verifier_result=_verifier(False), grounded=True,
        decision=RecommendedAction.REJECTED, reason="bad",
    ))
    assert has_unresolved_contradiction([supported, contradicted]) is True
    assert has_unresolved_contradiction([supported]) is False
    assert has_unresolved_contradiction([]) is False


def test_contradiction_record_to_dict_is_json_serializable_shape():
    outcome = HypothesisOutcome(
        hypothesis=_hypothesis(), verifier_result=_verifier(True), grounded=True,
        decision=RecommendedAction.SAFE_TO_RESOLVE, reason="ok",
    )
    record = build_contradiction_record(outcome)
    d = record.to_dict()
    assert set(d.keys()) == {
        "hypothesis_id", "hypothesis_type", "supporting_evidence", "contradicting_evidence",
        "missing_evidence", "status", "expected_value", "observed_value", "residual", "reason",
    }
