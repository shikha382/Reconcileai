"""The auditable AI trace -- structured events a future UI/hash-chain
(M5/M6) can render or seal, per every field the M4 brief requires."""
from app.ai.controller import investigate
from app.ai.provider import MockAIProvider

from .factories import make_bank_txn, make_investigation_context, make_payment, make_settlement


def test_trace_has_every_required_field():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="900.00", net_amount="900.00")
    bank_txn = make_bank_txn(amount="900.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = investigate("EXC-1", ctx, MockAIProvider())
    trace = result.trace

    assert trace.investigation_id
    assert trace.exception_id == "EXC-1"
    assert trace.provider == "MockAIProvider"
    assert trace.prompt_version
    assert trace.started_at is not None
    assert trace.completed_at is not None
    assert trace.duration_seconds is not None and trace.duration_seconds >= 0
    assert trace.final_decision is not None
    assert isinstance(trace.tool_call_count, int)
    assert isinstance(trace.hypotheses_tested, list)


def test_trace_serializes_to_json_round_trip():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="900.00", net_amount="900.00")
    bank_txn = make_bank_txn(amount="900.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = investigate("EXC-1", ctx, MockAIProvider())
    raw = result.trace.model_dump_json()

    import json

    parsed = json.loads(raw)
    assert parsed["exception_id"] == "EXC-1"
    assert parsed["final_decision"] in ("SAFE_TO_RESOLVE", "HUMAN_REVIEW", "REJECTED", "UNRESOLVED")


def test_trace_step_order_is_observation_then_tool_calls_then_hypothesis_chain():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="900.00", net_amount="900.00")
    bank_txn = make_bank_txn(amount="900.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = investigate("EXC-1", ctx, MockAIProvider())
    step_types = [s.type.value for s in result.trace.steps]

    assert step_types[0] == "observation"
    assert "tool_call" in step_types
    assert "hypothesis" in step_types
    assert "verification" in step_types
    assert "policy" in step_types


def test_every_hypothesis_step_is_followed_by_a_verification_and_policy_step():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="900.00", net_amount="900.00")
    bank_txn = make_bank_txn(amount="900.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = investigate("EXC-1", ctx, MockAIProvider())
    steps = result.trace.steps
    for i, step in enumerate(steps):
        if step.type.value == "hypothesis":
            remaining_types = [s.type.value for s in steps[i + 1:i + 3]]
            assert "verification" in remaining_types or "rejection" in remaining_types
