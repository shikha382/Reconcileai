"""Tool schema validation and tool authorization -- the AI interacts with
financial data ONLY through the fixed, allow-listed tool set."""
import pytest

from app.ai.tools import ToolAuthorizationError, invoke_tool

from .factories import make_bank_txn, make_investigation_context, make_payment, make_settlement


def test_unknown_tool_name_is_rejected():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment)
    with pytest.raises(ToolAuthorizationError):
        invoke_tool("execute_sql", {"query": "SELECT * FROM payments"}, ctx)


def test_arbitrary_python_is_not_a_tool():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment)
    with pytest.raises(ToolAuthorizationError):
        invoke_tool("eval", {"code": "1+1"}, ctx)


def test_invalid_tool_input_is_rejected_before_reaching_data():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment)
    with pytest.raises(ToolAuthorizationError):
        # get_record requires record_type to be one of the fixed literals
        invoke_tool("get_record", {"record_id": "PAY-00001", "record_type": "user"}, ctx)


def test_get_exception_context_returns_bounded_fields_only():
    payment = make_payment(amount="1000.00", method="card")
    ctx = make_investigation_context(payment)
    result = invoke_tool("get_exception_context", {"exception_id": "EXC-1"}, ctx)
    assert result["payment_id"] == "PAY-00001"
    assert result["payment_amount"] == "1000.00"
    assert "root_cause" not in result  # M3's answer is deliberately not handed to the AI


def test_get_record_returns_not_found_for_missing_record():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment)
    result = invoke_tool("get_record", {"record_id": "STL-99999", "record_type": "settlement"}, ctx)
    assert result["found"] is False


def test_get_record_only_returns_allow_listed_fields():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00")
    ctx = make_investigation_context(payment, [settlement])
    result = invoke_tool("get_record", {"record_id": "STL-00001", "record_type": "settlement"}, ctx)
    assert result["found"] is True
    assert set(result["fields"].keys()) <= {
        "settlement_id", "payment_id", "amount", "fee", "tax", "net_amount", "currency", "settled_at", "utr_reference", "status",
    }


def test_calculate_balance_wraps_decomposition():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="700.00", net_amount="700.00")
    bank_txn = make_bank_txn(amount="700.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])
    result = invoke_tool("calculate_balance", {"payment_id": "PAY-00001", "settlement_id": "STL-00001"}, ctx)
    assert result["residual"] == "300.00"
    assert result["fully_explained"] is False


def test_compare_candidates_flags_ambiguous_when_none_accepted():
    payment = make_payment(amount="1000.00")
    settlement_1 = make_settlement(settlement_id="STL-A", payment_id=None, amount="900.00")
    settlement_2 = make_settlement(settlement_id="STL-B", payment_id=None, amount="1100.00")
    ctx = make_investigation_context(payment, [settlement_1, settlement_2])
    result = invoke_tool("compare_candidates", {"payment_id": "PAY-00001", "settlement_ids": ["STL-A", "STL-B"]}, ctx)
    assert result["ambiguous"] is True
    assert result["any_accepted"] is False


def test_test_hypothesis_is_not_in_the_generic_tool_registry():
    """test_hypothesis is invoked directly by the controller's verification
    step (app.ai.verifier), not as a free-form tool call -- it IS the
    deterministic boundary, not an evidence-gathering step."""
    from app.ai.tools import TOOL_REGISTRY

    assert "test_hypothesis" not in TOOL_REGISTRY
