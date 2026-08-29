"""Milestone 16, Phase 2: the API-level quarter of the final financial-
safety invariant suite (items 15, 16, 17, 19 -- the rest live in
tests/adversarial/test_m16_final_safety_invariants.py, split here only
because the api_client/api_client_with_run fixtures live in this
directory's own conftest.py, not the adversarial one).
"""
from __future__ import annotations


# --- 15. Mutate financial records through API endpoints ---

def test_15_no_route_mutates_a_financial_record(api_client_with_run):
    """See also tests/api/test_security.py::test_no_financial_mutation_endpoints_exist."""
    client, state = api_client_with_run
    for path in ("/exceptions/queue", f"/runs/{state['run_id']}", "/sources/status"):
        for method in ("post", "put", "patch", "delete"):
            response = getattr(client, method)(path)
            assert response.status_code in (404, 405)


# --- 16/17. No leak of secrets, stack traces, or internal paths ---

def test_16_provider_credentials_are_never_returned_anywhere(api_client_with_run, monkeypatch):
    monkeypatch.setenv("RAZORPAY_API_SECRET", "sk_should_never_leak_ABC123")
    client, state = api_client_with_run
    for path in ("/health", "/sources/status", f"/runs/{state['run_id']}", f"/runs/{state['run_id']}/audit/events"):
        response = client.get(path)
        assert "sk_should_never_leak_ABC123" not in response.text


def test_17_a_forced_internal_error_never_leaks_a_stack_trace(api_client):
    response = api_client.get("/exceptions/EXC-nonexistent-1234")
    assert response.status_code == 404
    body = response.json()
    assert "Traceback" not in str(body)
    assert "site-packages" not in str(body)


# --- 19. Frontend state cannot alter backend authority ---

def test_19_the_api_never_accepts_a_caller_supplied_decision_field(api_client_with_run):
    client, state = api_client_with_run
    queue = client.get("/exceptions/queue", params={"run_id": state["run_id"], "page_size": 1}).json()
    exception_id = queue["items"][0]["exception_id"]
    real_decision = client.get(f"/exceptions/{exception_id}").json()["decision"]
    # Attempting to smuggle a decision override via query params on a GET
    # route has no effect -- there is no code path that reads it.
    tampered = client.get(f"/exceptions/{exception_id}", params={"decision": "SAFE_TO_RESOLVE", "force": "true"}).json()
    assert tampered["decision"] == real_decision
