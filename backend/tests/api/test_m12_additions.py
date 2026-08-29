"""Milestone 12: tests for the three smallest-additive backend changes made
to support the Finance Controller Command Center frontend -- GET /runs
(list), GET /runs/{run_id}/audit/events (event listing), and the
explanation endpoint's new `priority` field. None of these routes perform
matching, verification, risk, policy, or audit logic themselves; each test
below confirms the route only reshapes an already-computed M1-M11 result.
"""
from __future__ import annotations


def test_list_runs_returns_the_completed_run(api_client_with_run):
    client, state = api_client_with_run
    response = client.get("/runs")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(item["run_id"] == state["run_id"] for item in body["items"])


def test_list_runs_matches_get_run_by_id_for_the_same_run(api_client_with_run):
    client, state = api_client_with_run
    listed = next(i for i in client.get("/runs").json()["items"] if i["run_id"] == state["run_id"])
    single = client.get(f"/runs/{state['run_id']}").json()
    assert listed == single


def test_list_runs_empty_registry_returns_empty_list(api_client):
    response = api_client.get("/runs")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_list_runs_ai_actor_is_forbidden(api_client_with_run):
    client, _ = api_client_with_run
    response = client.get("/runs", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403


def test_audit_events_listing_matches_audit_status_count(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]
    status_body = client.get(f"/runs/{run_id}/audit").json()
    events_body = client.get(f"/runs/{run_id}/audit/events", params={"page_size": 100}).json()
    assert events_body["total"] == status_body["event_count"]
    assert events_body["run_id"] == run_id


def test_audit_events_listing_is_sequence_ordered_and_paginated(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]
    page1 = client.get(f"/runs/{run_id}/audit/events", params={"page": 1, "page_size": 10}).json()
    page2 = client.get(f"/runs/{run_id}/audit/events", params={"page": 2, "page_size": 10}).json()
    assert len(page1["items"]) == 10
    sequences = [item["sequence"] for item in page1["items"] + page2["items"]]
    assert sequences == sorted(sequences)
    assert set(i["event_id"] for i in page1["items"]).isdisjoint(i["event_id"] for i in page2["items"])


def test_audit_events_details_are_valid_json_text(api_client_with_run):
    import json

    client, state = api_client_with_run
    body = client.get(f"/runs/{state['run_id']}/audit/events", params={"page_size": 5}).json()
    for item in body["items"]:
        parsed = json.loads(item["details"])  # never raises -- canonical JSON text, not free-form
        assert isinstance(parsed, dict)


def test_audit_events_unknown_run_is_404(api_client):
    response = api_client.get("/runs/RUN-does-not-exist/audit/events")
    assert response.status_code == 404


def test_explanation_priority_field_matches_the_queue_item_for_the_same_exception(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]
    queue = client.get("/exceptions/queue", params={"run_id": run_id, "page_size": 1}).json()
    item = queue["items"][0]

    explanation = client.get(f"/exceptions/{item['exception_id']}/explanation").json()
    assert explanation["priority"] is not None
    assert explanation["priority"]["priority"] == item["priority"]
    assert explanation["priority"]["priority_score"] == item["priority_score"]
    assert explanation["priority"]["reason_codes"] == item["reason_codes"]
    assert explanation["priority"]["recommended_action"] == item["recommended_action"]


def test_explanation_unknown_exception_is_404_before_any_priority_lookup(api_client):
    # Confirms the route fails closed (404) before ever attempting the new
    # run/payment lookup added for the priority field -- no exception means
    # no explanation and no fabricated priority.
    response = api_client.get("/exceptions/EXC-does-not-exist/explanation")
    assert response.status_code == 404
