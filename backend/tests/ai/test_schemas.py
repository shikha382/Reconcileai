"""AI schema validation -- the AI must never return arbitrary free-form
text as its primary output; every schema here is strict."""
import pytest
from pydantic import ValidationError

from app.ai.schemas import (
    AIHypothesis,
    GetRecordInput,
    HypothesisType,
    RecommendedAction,
    TestHypothesisInput,
)


def test_valid_hypothesis_passes_validation():
    h = AIHypothesis(
        hypothesis_id="H-1", exception_id="EXC-1", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE,
        claim="fee explains it", record_ids=["PAY-00001"], evidence_ids=["PAY-00001"],
        confidence=0.9, recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
    )
    assert h.hypothesis_type == HypothesisType.FEE_EXPLAINS_DIFFERENCE


def test_invalid_hypothesis_type_is_rejected():
    """The AI cannot invent an arbitrary financial action type -- only the
    fixed HypothesisType enum values are accepted."""
    with pytest.raises(ValidationError):
        AIHypothesis(
            hypothesis_id="H-1", exception_id="EXC-1", hypothesis_type="POST_ZERO_DIFFERENCE",
            claim="x", confidence=0.9, recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
        )


def test_invalid_recommended_action_is_rejected():
    with pytest.raises(ValidationError):
        AIHypothesis(
            hypothesis_id="H-1", exception_id="EXC-1", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE,
            claim="x", confidence=0.9, recommended_action="APPROVE_REFUND",
        )


def test_confidence_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        AIHypothesis(
            hypothesis_id="H-1", exception_id="EXC-1", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE,
            claim="x", confidence=1.5, recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
        )


def test_get_record_input_rejects_unknown_record_type():
    with pytest.raises(ValidationError):
        GetRecordInput(record_id="X-1", record_type="user_account")  # not a financial record type


def test_test_hypothesis_input_requires_known_hypothesis_type():
    with pytest.raises(ValidationError):
        TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-1", hypothesis_type="SOMETHING_ELSE")


def test_hypothesis_defaults_are_empty_not_none():
    h = AIHypothesis(
        hypothesis_id="H-1", exception_id="EXC-1", hypothesis_type=HypothesisType.UNEXPLAINED_RESIDUAL,
        claim="x", confidence=0.1, recommended_action=RecommendedAction.HUMAN_REVIEW,
    )
    assert h.record_ids == []
    assert h.evidence_ids == []
