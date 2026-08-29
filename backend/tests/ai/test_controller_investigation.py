"""The full bounded AI investigation loop, end to end -- the architectural
spine of M4: EXCEPTION -> EVIDENCE -> HYPOTHESIS -> TOOLS -> VERIFICATION ->
POLICY -> SAFE_TO_RESOLVE / HUMAN_REVIEW / REJECTED / UNRESOLVED.
"""
from decimal import Decimal

from app.ai.config import settings
from app.ai.controller import investigate
from app.ai.provider import MockAIProvider
from app.ai.schemas import RecommendedAction

from .factories import CARD_FEE_RULE, ZERO_FEE_RULE, make_bank_txn, make_investigation_context, make_payment, make_refund, make_settlement


def test_multi_hop_verified_refund_and_fee_investigation():
    """The M3/M4 brief's own worked example: Order 10,000, refund 2,000,
    fee+GST 180, settlement 7,820. Multi-hop: payment -> refund -> fee rule
    -> settlement, verified via the deterministic checker, not asserted by
    the AI."""
    payment = make_payment(amount="10000.00", method="upi")  # zero-fee rule; refund alone explains it
    settlement = make_settlement(amount="10000.00", net_amount="10000.00")
    bank_credit = make_bank_txn(amount="8000.00", direction="credit")  # already net of the refund
    refund = make_refund(amount="2000.00")
    ctx = make_investigation_context(payment, [settlement], [bank_credit], [refund])

    result = investigate("EXC-1", ctx, MockAIProvider())

    assert result.final_decision == RecommendedAction.SAFE_TO_RESOLVE
    assert any(o.hypothesis.hypothesis_type.value == "REFUND_EXPLAINS_DIFFERENCE" for o in result.outcomes)
    verified = [o for o in result.outcomes if o.decision == RecommendedAction.SAFE_TO_RESOLVE]
    assert len(verified) == 1


def test_rejected_fee_hypothesis_escalates_to_human_review():
    """TRACE B (see docs/ai-controller.md and the final report): the exact
    fee rule does not explain the residual -- must escalate, never
    auto-resolve."""
    payment = make_payment(amount="7842.54", method="card")
    correct_fee, correct_tax = Decimal("143.17"), Decimal("25.77")
    correct_net = payment.amount - correct_fee - correct_tax
    bogus_net = correct_net - Decimal("9.83")
    settlement = make_settlement(amount="7842.54", fee=str(correct_fee), tax=str(correct_tax), net_amount=str(bogus_net))
    bank_txn = make_bank_txn(amount=str(bogus_net))
    ctx = make_investigation_context(payment, [settlement], [bank_txn], fee_rules=[CARD_FEE_RULE])

    result = investigate("EXC-1", ctx, MockAIProvider())

    assert result.final_decision == RecommendedAction.HUMAN_REVIEW
    fee_outcomes = [o for o in result.outcomes if o.hypothesis.hypothesis_type.value == "FEE_EXPLAINS_DIFFERENCE"]
    assert fee_outcomes and fee_outcomes[0].decision == RecommendedAction.REJECTED


def test_investigation_never_exceeds_max_tool_calls():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment, [])
    result = investigate("EXC-1", ctx, MockAIProvider())
    assert result.trace.tool_call_count <= settings.max_tool_calls


def test_investigation_produces_a_structured_trace_with_final_decision():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment, [])
    result = investigate("EXC-1", ctx, MockAIProvider())

    assert result.trace.investigation_id
    assert result.trace.exception_id == "EXC-1"
    assert result.trace.final_decision is not None
    assert result.trace.duration_seconds is not None
    assert len(result.trace.steps) > 0


def test_missing_record_investigation_reaches_unresolved():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment, [])  # genuinely nothing exists
    result = investigate("EXC-1", ctx, MockAIProvider())
    assert result.final_decision == RecommendedAction.UNRESOLVED
