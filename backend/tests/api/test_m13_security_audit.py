"""Milestone 13, Phase 7: API security audit additions for the three new
M12 endpoints (GET /runs, GET /runs/{run_id}/audit/events, and the
explanation route's new priority lookup). M8/M9 already exercised this
class of attack against every M1-M11 route (test_security.py,
test_api_adversarial.py); this file closes the specific gaps M12 opened --
malformed/injection-like run_id values, oversized pagination, and the
AI-actor-forbidden boundary -- for routes that didn't exist when those
suites were written. No new authorization mechanism, no new error model:
every assertion here exercises boundaries that already exist.
"""
from __future__ import annotations

import pytest

INJECTION_LIKE_RUN_IDS = [
    "../../etc/passwd",
    "'; DROP TABLE audit_events; --",
    "<script>alert(1)</script>",
    "a" * 5000,
    # A raw NUL byte is deliberately not included here -- httpx (and every
    # real browser/HTTP client) refuses to construct a request containing
    # one at all, so it can't reach the server as a URL in the first place;
    # this isn't a gap, it's untestable via HTTP by construction.
]


@pytest.mark.parametrize("bad_run_id", INJECTION_LIKE_RUN_IDS)
def test_audit_events_rejects_malformed_run_id_safely(api_client, bad_run_id):
    response = api_client.get(f"/runs/{bad_run_id}/audit/events")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert "code" in body["error"]
    # No stack trace, no internal path, no SQL error text ever reaches the response.
    text = response.text.lower()
    for leak in ("traceback", "sqlite3", "site-packages", "operationalerror"):
        assert leak not in text


@pytest.mark.parametrize("bad_run_id", INJECTION_LIKE_RUN_IDS)
def test_run_audit_status_rejects_malformed_run_id_safely(api_client, bad_run_id):
    response = api_client.get(f"/runs/{bad_run_id}/audit")
    assert response.status_code == 404
    assert "traceback" not in response.text.lower()


def test_audit_events_oversized_page_size_is_rejected(api_client_with_run):
    client, state = api_client_with_run
    response = client.get(f"/runs/{state['run_id']}/audit/events", params={"page_size": 100000})
    assert response.status_code == 422


def test_audit_events_negative_page_is_rejected(api_client_with_run):
    client, state = api_client_with_run
    response = client.get(f"/runs/{state['run_id']}/audit/events", params={"page": -1})
    assert response.status_code == 422


def test_audit_events_ai_actor_is_allowed_same_as_the_existing_audit_status_route(api_client_with_run):
    # Correct, intentional behavior (app.policy.authorization, M6): AI has
    # VIEW_AUDIT (it needs to read the ledger as part of its own
    # investigation tooling), exactly like the pre-existing
    # GET /runs/{id}/audit route. Confirmed here rather than assumed, so a
    # future capability-table change that accidentally revokes it is caught.
    client, state = api_client_with_run
    response = client.get(f"/runs/{state['run_id']}/audit/events", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 200


def test_list_runs_unknown_actor_type_is_a_clean_400(api_client):
    response = api_client.get("/runs", headers={"X-Actor-Type": "SUPERADMIN"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ACTOR_TYPE"


def test_explanation_route_ai_actor_is_forbidden_even_with_a_real_exception(api_client_with_run):
    client, state = api_client_with_run
    # Fetch a real exception id via the queue rather than assuming one.
    queue = client.get("/exceptions/queue", params={"run_id": state["run_id"], "page_size": 1}).json()
    exception_id = queue["items"][0]["exception_id"]
    response = client.get(f"/exceptions/{exception_id}/explanation", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403


def test_no_route_anywhere_accepts_put_patch_or_delete(api_client_with_run):
    """Structural check (Phase 19 continuation): the API surface has no
    mutation verb on any exception/run/audit resource."""
    client, state = api_client_with_run
    run_id = state["run_id"]
    for method, path in [
        ("put", f"/runs/{run_id}"),
        ("patch", f"/runs/{run_id}"),
        ("delete", f"/runs/{run_id}"),
        ("put", "/exceptions/queue"),
        ("delete", f"/runs/{run_id}/audit/events"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code in (404, 405), f"{method.upper()} {path} returned {response.status_code}"
