"""AI failure modes must degrade safely to HUMAN_REVIEW -- never to
auto-resolve. Simulated via a provider stub that raises ProviderError,
since the mock never makes network calls to actually fail."""
from app.ai.controller import investigate
from app.ai.provider import ProviderError
from app.ai.schemas import ConcludeAction, InvestigationState, RecommendedAction, ToolCallAction

from .factories import make_bank_txn, make_investigation_context, make_payment, make_settlement


class _AlwaysFailsProvider:
    """Simulates a provider that is unavailable / times out on the very
    first call."""
    def decide_next_action(self, state: InvestigationState):
        raise ProviderError("simulated: provider unavailable")


class _FailsAfterOneCallProvider:
    """Simulates a mid-investigation failure (e.g. a timeout partway
    through), after one tool call already succeeded."""
    def __init__(self):
        self.calls = 0

    def decide_next_action(self, state: InvestigationState):
        self.calls += 1
        if self.calls == 1:
            return ToolCallAction(tool_name="get_exception_context", tool_input={"exception_id": state.exception_id})
        raise ProviderError("simulated: request timed out")


def test_provider_unavailable_on_first_call_degrades_to_human_review():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="900.00", net_amount="900.00")  # a real discrepancy exists
    bank_txn = make_bank_txn(amount="900.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = investigate("EXC-1", ctx, _AlwaysFailsProvider())

    assert result.final_decision == RecommendedAction.HUMAN_REVIEW
    assert result.trace.errors  # the failure is recorded, not hidden
    assert "simulated" in result.trace.errors[0]


def test_provider_timeout_mid_investigation_degrades_to_human_review():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="900.00", net_amount="900.00")
    bank_txn = make_bank_txn(amount="900.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = investigate("EXC-1", ctx, _FailsAfterOneCallProvider())

    assert result.final_decision == RecommendedAction.HUMAN_REVIEW
    assert result.trace.tool_call_count == 1  # the one successful call is still recorded


def test_provider_failure_never_produces_safe_to_resolve_even_on_a_clean_record():
    """Even when the underlying record would have verified cleanly, a
    provider failure must still degrade to HUMAN_REVIEW -- the system
    never assumes success on error."""
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")  # perfectly clean
    bank_txn = make_bank_txn(amount="1000.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = investigate("EXC-1", ctx, _AlwaysFailsProvider())
    assert result.final_decision != RecommendedAction.SAFE_TO_RESOLVE


class _ConcludesImmediatelyProvider:
    def decide_next_action(self, state: InvestigationState):
        return ConcludeAction(reason="simulated: model gave up immediately")


def test_provider_concluding_with_no_hypothesis_is_human_review():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="900.00", net_amount="900.00")
    bank_txn = make_bank_txn(amount="900.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = investigate("EXC-1", ctx, _ConcludesImmediatelyProvider())
    assert result.final_decision == RecommendedAction.HUMAN_REVIEW
