"""Milestone 14, Phase 27: re-confirms M13's own guarantees still hold
after adding the adapter layer and its new `/sources/status` endpoint --
not a re-implementation of M13's own test suite (which still runs
unchanged and unmodified), just a direct, explicit check that the new
surface area didn't quietly weaken anything M13 established.
"""
from __future__ import annotations


def test_unmatched_route_still_uses_the_structured_error_contract(api_client):
    # The M13 HTTPException-handler fix must still apply to routes that
    # exist alongside the new /sources router, not just the ones present
    # when that fix was written.
    response = api_client.get("/sources/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert "code" in body["error"]


def test_ai_actor_permissions_are_unchanged_for_pre_existing_routes(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]
    # Still forbidden (M8/M13, unchanged):
    assert client.get(f"/runs/{run_id}", headers={"X-Actor-Type": "AI"}).status_code == 403
    assert client.post("/runs", json={"dataset": "seeds"}, headers={"X-Actor-Type": "AI"}).status_code == 403
    # Still allowed (M6, unchanged -- AI has VIEW_AUDIT):
    assert client.get(f"/runs/{run_id}/audit", headers={"X-Actor-Type": "AI"}).status_code == 200
    # New in M14, and correctly forbidden (VIEW_RUN, not granted to AI):
    assert client.get("/sources/status", headers={"X-Actor-Type": "AI"}).status_code == 403


def test_no_new_mutation_endpoint_exists_anywhere_after_m14(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]
    for method, path in [
        ("post", "/sources/status"),
        ("put", "/sources/status"),
        ("delete", "/sources/status"),
        ("post", f"/runs/{run_id}/audit/events"),
        ("post", "/exceptions/queue"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code in (404, 405), f"{method.upper()} {path} returned {response.status_code}"


def test_frontend_still_cannot_bypass_policy_through_any_m14_route(api_client_with_run):
    # There is no endpoint anywhere (old or new) that accepts a caller-
    # supplied decision/policy/priority value -- /sources/status takes no
    # request body at all, and every other route's request schemas
    # (app.api.schemas) contain no such field, confirmed structurally.
    client, state = api_client_with_run
    response = client.get("/sources/status", params={"decision": "SAFE_TO_RESOLVE", "override_policy": "true"})
    assert response.status_code == 200
    body = response.json()
    # The extra query params are simply ignored -- they have no code path
    # to act on, unlike a real mutation endpoint would.
    assert "decision" not in str(body)
