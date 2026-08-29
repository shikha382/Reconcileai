"""Phase 22 security checks, plus Phase 11's data-safety boundary (no
financial mutation endpoints) and the "no force-resolve escape hatch" rule."""
import json

from fastapi.testclient import TestClient

from app.main import app


def test_malformed_exception_id_is_404_not_500(api_client):
    response = api_client.get("/exceptions/'; DROP TABLE audit_events; --")
    assert response.status_code == 404


def test_malformed_run_id_is_404_not_500(api_client):
    response = api_client.get("/runs/<script>alert(1)</script>")
    assert response.status_code == 404


def test_invalid_json_body_does_not_crash_the_server(api_client):
    response = api_client.post("/runs", content=b"{not valid json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "error" in response.json()


def test_unexpected_extra_fields_in_request_body_are_ignored_not_dangerous(api_client):
    # Pydantic's default behavior ignores unknown fields rather than
    # erroring OR silently acting on them -- confirms an attacker cannot
    # smuggle e.g. a "force_decision" field into the request and have it
    # influence anything.
    response = api_client.post("/runs", json={"dataset": "seeds", "force_decision": "SAFE_TO_RESOLVE", "override_policy": True})
    assert response.status_code == 201
    body = response.json()
    assert "force_decision" not in body
    assert "override_policy" not in body


def test_no_financial_mutation_endpoints_exist():
    paths = {route.path for route in app.routes}
    for forbidden in ("/payments", "/settlements", "/orders", "/refunds", "/bank_transactions"):
        assert forbidden not in paths


def test_no_force_resolve_or_approval_bypass_endpoint_exists():
    paths = {route.path for route in app.routes}
    assert not any("force" in p.lower() for p in paths)
    assert not any("bypass" in p.lower() for p in paths)
    # No approval-mutation endpoint of any kind was built this milestone
    # (Phase 10: "if it is not necessary yet, do not invent it") -- only
    # read/trigger endpoints exist.
    assert not any(p.endswith("/approve") or p.endswith("/reject") for p in paths)


def test_response_never_contains_api_keys_or_db_credentials(api_client):
    response = api_client.post("/runs", json={"dataset": "seeds"})
    text = response.text
    for secret_marker in ("API_KEY", "api_key", "LLM_API_KEY", "sk-", "password", "secret"):
        assert secret_marker not in text


def test_unexpected_internal_error_is_generic_500_no_leak(api_client, monkeypatch):
    import app.api.routes.runs as runs_module

    def _boom(*args, **kwargs):
        raise RuntimeError("internal detail: /some/secret/filesystem/path leaked")

    monkeypatch.setattr(runs_module, "run_reconciliation_pipeline", _boom)

    # A real deployed server always converts an unhandled exception to a 500
    # response (see app.api.errors' generic Exception handler) -- TestClient's
    # default re-raises server exceptions for debugging convenience, so this
    # test explicitly asks it to behave like a real client instead.
    no_raise_client = TestClient(app, raise_server_exceptions=False)
    response = no_raise_client.post("/runs", json={"dataset": "seeds"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in json.dumps(body)
    assert "filesystem" not in json.dumps(body)
    assert "Traceback" not in response.text
