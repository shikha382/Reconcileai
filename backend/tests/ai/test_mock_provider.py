"""Mock AI provider -- fully deterministic, no network access, no API key
required. This is what the whole test suite and 300-record evaluation run
against."""
from app.ai.provider import MockAIProvider
from app.ai.schemas import HypothesisAction, InvestigationState, ToolCallAction


def test_mock_provider_starts_with_evidence_gathering_tool_calls():
    provider = MockAIProvider()
    state = InvestigationState(exception_id="EXC-1", payment_id="PAY-00001")
    action = provider.decide_next_action(state)
    assert isinstance(action, ToolCallAction)
    assert action.tool_name == "get_exception_context"


def test_mock_provider_proposes_a_hypothesis_after_gathering_evidence():
    provider = MockAIProvider()
    state = InvestigationState(exception_id="EXC-1", payment_id="PAY-00001", tool_call_count=5)
    action = provider.decide_next_action(state)
    assert isinstance(action, HypothesisAction)


def test_mock_provider_is_deterministic_across_runs():
    provider = MockAIProvider()
    state = InvestigationState(exception_id="EXC-1", payment_id="PAY-00001")
    actions_1 = [provider.decide_next_action(InvestigationState(exception_id="EXC-1", payment_id="PAY-00001", tool_call_count=i)) for i in range(5)]
    actions_2 = [provider.decide_next_action(InvestigationState(exception_id="EXC-1", payment_id="PAY-00001", tool_call_count=i)) for i in range(5)]
    assert [type(a) for a in actions_1] == [type(a) for a in actions_2]


def test_mock_provider_tries_hypotheses_in_priority_order_not_already_tried():
    provider = MockAIProvider()
    state = InvestigationState(
        exception_id="EXC-1", payment_id="PAY-00001", tool_call_count=5,
        hypotheses_tested=[{"hypothesis": {"hypothesis_type": "REFUND_EXPLAINS_DIFFERENCE"}}],
    )
    action = provider.decide_next_action(state)
    assert isinstance(action, HypothesisAction)
    assert action.hypothesis.hypothesis_type.value != "REFUND_EXPLAINS_DIFFERENCE"


def test_mock_provider_concludes_when_all_hypothesis_types_exhausted():
    from app.ai.provider import _HYPOTHESIS_PRIORITY
    from app.ai.schemas import ConcludeAction

    provider = MockAIProvider()
    all_tried = [{"hypothesis": {"hypothesis_type": h.value}} for h in _HYPOTHESIS_PRIORITY]
    state = InvestigationState(exception_id="EXC-1", payment_id="PAY-00001", tool_call_count=5, hypotheses_tested=all_tried)
    action = provider.decide_next_action(state)
    assert isinstance(action, ConcludeAction)


def test_mock_provider_hallucination_hook_injects_a_fake_record_id():
    """Test-only hook used by the adversarial/hallucination test suite to
    simulate a misbehaving model deterministically."""
    provider = MockAIProvider(hallucinate_record_id="STL-99999")
    state = InvestigationState(exception_id="EXC-1", payment_id="PAY-00001", tool_call_count=5)
    action = provider.decide_next_action(state)
    assert isinstance(action, HypothesisAction)
    assert "STL-99999" in action.hypothesis.record_ids
