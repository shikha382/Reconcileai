"""API authorization boundary (Phase 9). No fake IAM -- one Actor identity
per request (default: HUMAN "api-client"), each route gated by exactly one
Capability from app.policy.schemas, checked via the existing
app.policy.authorization.require_authorization (unchanged from M5/M6).
"""


def test_default_caller_can_start_a_run(api_client):
    response = api_client.post("/runs", json={"dataset": "seeds"})
    assert response.status_code == 201


def test_ai_actor_cannot_start_a_reconciliation_run(api_client):
    # AI's capability set (app.policy.authorization.ACTOR_CAPABILITIES, M4/M6,
    # unchanged by M8) has no START_RECONCILIATION -- exactly the M8 brief's
    # "AI cannot bypass policy through API" requirement, enforced structurally.
    response = api_client.post("/runs", json={"dataset": "seeds"}, headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_ai_actor_cannot_view_run_summaries(api_client):
    create = api_client.post("/runs", json={"dataset": "seeds"})
    run_id = create.json()["run_id"]

    response = api_client.get(f"/runs/{run_id}", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403


def test_ai_actor_can_still_view_exceptions_its_own_pre_existing_capability(api_client):
    # AI already has VIEW_EXCEPTION from M4 (it needs to see the exceptions
    # it investigates) -- M8 did not remove or restrict that; only the new
    # run/provenance-trigger capabilities are withheld from it.
    api_client.post("/runs", json={"dataset": "seeds"})
    response = api_client.get("/exceptions", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 200


def test_ai_actor_cannot_view_provenance(api_client):
    create = api_client.post("/runs", json={"dataset": "seeds"})
    exception_id = api_client.get(
        "/exceptions", params={"run_id": create.json()["run_id"], "page_size": 1}
    ).json()["items"][0]["exception_id"]

    response = api_client.get(f"/exceptions/{exception_id}/provenance", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403


def test_unknown_actor_type_header_is_rejected(api_client):
    response = api_client.post("/runs", json={"dataset": "seeds"}, headers={"X-Actor-Type": "NOT_A_REAL_TYPE"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ACTOR_TYPE"
