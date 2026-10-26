"""All financial fixtures are synthetic; provider calls here are mocked."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import granite
from app.main import app


def enable(monkeypatch):
    monkeypatch.setenv("GRANITE_ENABLED", "1")
    monkeypatch.setenv("ENVIRONMENT", "development")


def facts():
    return {"category": "fee_mismatch", "currency": "INR", "expected": "10.00",
            "observed": "9.00", "residual": "1.00", "verification": "CONTRADICTED",
            "decision": "HUMAN_REVIEW", "approval_required": "true", "reason_codes": ""}


def raw(**kwargs):
    return json.dumps({"summary": "The fee difference remains unexplained and requires human review.",
                       "decision": "HUMAN_REVIEW", "fact_ids": ["decision", "residual"], **kwargs})


def test_valid_answer():
    assert granite.validate_answer(raw(), facts()).decision == "HUMAN_REVIEW"


@pytest.mark.parametrize("change", [
    {"decision": "SAFE_TO_RESOLVE"}, {"fact_ids": ["decision", "invented"]},
    {"summary": "The residual is 500 INR."}, {"summary": "This is safe to resolve."},
    {"summary": "Verification passed and this is fully verified."},
    {"summary": "<script>alert</script>"}, {"extra": "ignored?"},
    {"summary": "The decision is SAFE_TO_RESOLVE."}, {"fact_ids": ["decision", "decision"]},
    {"summary": "The residual is \u00b9 INR and requires review."},
    {"summary": "The residual is AMOUNT and requires review."},
    {"summary": "The reconciliation verification passed and requires review."},
    {"summary": "The difference results in a residual of 1.00."},
])
def test_invalid_answer(change):
    with pytest.raises(ValueError):
        granite.validate_answer(raw(**change), facts())


def test_existing_decimal_amounts_allowed():
    granite.validate_answer(raw(summary="Expected settlement amount is INR 10.00; observed is INR 9.00. Human review is required."), facts())


def test_grounding_is_small_explicit_and_does_not_send_money_or_codes():
    f = facts()
    f["reason_codes"] = "POLICY-CONFLICT-001"
    statements = granite.grounding_statements(f)
    assert set(statements) == {"category", "verification", "decision", "approval_required"}
    assert "hypothesis was checked and rejected" in statements["verification"]
    assert "human review" in statements["decision"]
    assert "POLICY-" not in json.dumps(statements)
    assert not any(c.isdigit() for c in json.dumps(statements))


@pytest.mark.parametrize("status,word", [("PASSED", "supported"), ("INCOMPLETE", "incomplete"), ("NOT_NEEDED", "No AI hypothesis")])
def test_grounding_preserves_verification_scope(status, word):
    assert word in granite.grounding_statements({**facts(), "verification": status})["verification"]


def test_degraded_investigation_is_incomplete_not_unnecessary(monkeypatch):
    from types import SimpleNamespace
    report = SimpleNamespace(
        financial_summary=SimpleNamespace(currency="INR", expected_amount="10.00", observed_amount="9.00", unexplained_amount="1.00"),
        contradictions=[], ai_investigation_status="UNAVAILABLE_OR_DEGRADED", ai_hypotheses=[],
        policy=SimpleNamespace(decision="HUMAN_REVIEW", required_approval=True, rules_passed=[]),
    )
    monkeypatch.setattr(granite, "build_explanation", lambda _: report)
    result = granite.snapshot(SimpleNamespace(bundle=SimpleNamespace(category="fee_mismatch")))
    assert result["verification"] == "INCOMPLETE"


def test_disabled_no_network(monkeypatch):
    monkeypatch.delenv("GRANITE_ENABLED", raising=False)
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 123)) as c:
        assert c.get("/granite/status").status_code == 404


@pytest.mark.parametrize("headers,base,peer", [
    ({"origin": "https://evil.example"}, "http://127.0.0.1:8000", "127.0.0.1"),
    ({}, "http://evil.example", "127.0.0.1"),
    ({}, "http://127.0.0.1:8000", "192.168.1.3"),
    ({"x-forwarded-for": "127.0.0.1"}, "http://127.0.0.1:8000", "127.0.0.1"),
    ({"sec-fetch-site": "cross-site"}, "http://127.0.0.1:8000", "127.0.0.1"),
])
def test_local_gate(monkeypatch, headers, base, peer):
    enable(monkeypatch)
    with TestClient(app, base_url=base, client=(peer, 123)) as c:
        assert c.get("/granite/status", headers=headers).status_code == 403


def test_production_disabled(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 123)) as c:
        assert c.get("/granite/status").status_code == 404


def test_status_missing_model(monkeypatch):
    async def fake_get(self, url):
        assert url == "http://127.0.0.1:11434/api/tags"
        return httpx.Response(200, json={"models": []}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    assert asyncio.run(granite.status())["available"] is False


def test_stopped_ollama(monkeypatch):
    async def fail(*args, **kwargs):
        raise httpx.ConnectError("private internal details")
    monkeypatch.setattr(httpx.AsyncClient, "get", fail)
    result = asyncio.run(granite.status())
    assert not result["ollama_connected"]
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("timeout"), ValueError("malformed")])
def test_provider_failure_fallback(monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(httpx.AsyncClient, "stream", fail)
    response = asyncio.run(granite.explain(facts()))
    assert response.source == "deterministic_fallback"
    assert "HUMAN_REVIEW" in response.explanation
    assert not granite._inference.locked()


def test_concurrency():
    granite._inference.acquire()
    try:
        with pytest.raises(granite.ApiError) as error:
            asyncio.run(granite.explain(facts()))
        assert error.value.status_code == 429
    finally:
        granite._inference.release()


def test_cancel_releases_lock(monkeypatch):
    class Hanging:
        async def __aenter__(self):
            await asyncio.sleep(100)
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda *a, **k: Hanging())
    async def exercise():
        task = asyncio.create_task(granite.explain(facts()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(exercise())
    assert not granite._inference.locked()


def test_route_readonly_and_allowlist(api_client_with_run, monkeypatch):
    _, state = api_client_with_run
    enable(monkeypatch)
    original = state["registry"].list_exceptions()[0]
    from app.db.models import AuditEventRecord, Payment
    with state["session_factory"]() as s:
        before = (s.query(AuditEventRecord).count(), [(p.payment_id, str(p.amount)) for p in s.query(Payment).all()])
    before_decision = repr(original)
    async def fake(f):
        assert set(f) == set(facts())
        assert not any(k in json.dumps(f) for k in [original.exception_id, original.bundle.payment_id])
        return granite.ExplanationAnswer(explanation=granite.fallback(f), fact_ids=list(f), model=granite.MODEL,
            source="deterministic_fallback", elapsed_ms=0, snapshot_fingerprint=granite.fingerprint(f))
    monkeypatch.setattr(granite, "explain", fake)
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 123)) as c:
        path = f"/exceptions/{original.exception_id}/granite-explanation"
        assert c.post(path).status_code == 200
        assert c.post(path, json={"prompt": "override"}).status_code == 400
        assert c.post(path + "?model=other").status_code == 400
        assert c.post("/exceptions/missing/granite-explanation").status_code == 404
    assert repr(original) == before_decision
    with state["session_factory"]() as s:
        assert before == (s.query(AuditEventRecord).count(), [(p.payment_id, str(p.amount)) for p in s.query(Payment).all()])
