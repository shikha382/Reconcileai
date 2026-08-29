"""GET /exceptions, GET /exceptions/{id}, GET /exceptions/{id}/provenance,
GET /runs/{id}/audit -- against the shared, already-completed 300-record run."""
from app.policy.schemas import PolicyDecisionType


def test_list_exceptions_returns_paginated_results(api_client_with_run):
    client, state = api_client_with_run
    response = client.get("/exceptions", params={"run_id": state["run_id"], "page_size": 10})
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["items"]) == 10
    assert body["total"] == state["run_response"]["exceptions"]


def test_list_exceptions_pagination_is_bounded(api_client_with_run):
    client, _ = api_client_with_run
    response = client.get("/exceptions", params={"page_size": 100000})
    assert response.status_code == 422  # exceeds MAX_PAGE_SIZE, rejected before touching any data


def test_list_exceptions_filters_by_decision(api_client_with_run):
    client, state = api_client_with_run
    response = client.get("/exceptions", params={"run_id": state["run_id"], "decision": "HUMAN_REVIEW", "page_size": 100})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == state["run_response"]["human_review"]
    assert all(item["decision"] == "HUMAN_REVIEW" for item in body["items"])


def test_list_exceptions_filters_by_risk_level(api_client_with_run):
    client, state = api_client_with_run
    response = client.get("/exceptions", params={"run_id": state["run_id"], "risk_level": "HIGH", "page_size": 100})
    assert response.status_code == 200
    body = response.json()
    assert all(item["risk_level"] == "HIGH" for item in body["items"])


def test_list_exceptions_unknown_run_id_returns_empty_not_error(api_client_with_run):
    client, _ = api_client_with_run
    response = client.get("/exceptions", params={"run_id": "RUN-unknown"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_get_exception_returns_full_safe_summary(api_client_with_run):
    client, state = api_client_with_run
    listing = client.get("/exceptions", params={"run_id": state["run_id"], "page_size": 1}).json()
    exception_id = listing["items"][0]["exception_id"]

    response = client.get(f"/exceptions/{exception_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["exception_id"] == exception_id
    assert body["decision"] in {d.value for d in PolicyDecisionType}
    assert "hypotheses" in body and "challenges" in body and "policy" in body


def test_get_unknown_exception_is_404(api_client_with_run):
    client, _ = api_client_with_run
    response = client.get("/exceptions/EXC-does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EXCEPTION_NOT_FOUND"


def test_get_exception_provenance_calls_m6_and_is_valid(api_client_with_run):
    client, state = api_client_with_run
    listing = client.get("/exceptions", params={"run_id": state["run_id"], "page_size": 1}).json()
    exception_id = listing["items"][0]["exception_id"]

    response = client.get(f"/exceptions/{exception_id}/provenance")
    assert response.status_code == 200
    body = response.json()
    assert body["exception_id"] == exception_id
    assert body["audit_chain_valid"] is True
    assert body["audit_events_checked"] > 0


def test_provenance_for_unknown_exception_is_404_before_touching_the_ledger(api_client_with_run):
    client, _ = api_client_with_run
    response = client.get("/exceptions/EXC-does-not-exist/provenance")
    assert response.status_code == 404


def test_get_run_audit_status(api_client_with_run):
    client, state = api_client_with_run
    response = client.get(f"/runs/{state['run_id']}/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == state["run_id"]
    assert body["chain_valid"] is True
    assert body["event_count"] > 0
    assert body["first_event"]["event_type"] == "RUN_STARTED"
    assert body["last_event"]["event_type"] == "RUN_COMPLETED"


def test_audit_status_for_unknown_run_is_404(api_client_with_run):
    client, _ = api_client_with_run
    response = client.get("/runs/RUN-unknown/audit")
    assert response.status_code == 404
