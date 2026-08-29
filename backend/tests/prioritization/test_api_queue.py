"""M11 Phases 14-15: GET /exceptions/queue. Read-only, reuses existing
authorization (Capability.VIEW_EXCEPTION, no new capability), no financial
mutation, no resolution, no approval endpoint of any kind.
"""
import pytest
from fastapi.testclient import TestClient

from app.ai.provider import MockAIProvider
from app.api.dependencies import get_approval_store, get_provider, get_run_registry, get_session
from app.api.run_registry import RunRegistry
from app.db.session import init_db, make_engine, make_session_factory
from app.main import app
from app.policy.approval import ApprovalWorkflowStore


@pytest.fixture()
def api_client(tmp_path):
    engine = make_engine(tmp_path / "queue_api.db")
    init_db(engine)
    session_factory = make_session_factory(engine)
    registry = RunRegistry()
    store = ApprovalWorkflowStore()

    def override_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_run_registry] = lambda: registry
    app.dependency_overrides[get_approval_store] = lambda: store
    app.dependency_overrides[get_provider] = lambda: MockAIProvider()
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_queue_endpoint_returns_a_full_structured_response(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"], "page_size": 10})
    assert response.status_code == 200
    body = response.json()
    assert "items" in body and "summary" in body
    assert body["total"] == run["exceptions"]
    assert len(body["items"]) == 10
    for key in ("priority", "priority_score", "reason_codes", "recommended_action", "sla_status", "risk_level"):
        assert key in body["items"][0]


def test_queue_is_ordered_p0_first(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"], "page_size": 100})
    priorities = [item["priority"] for item in response.json()["items"]]
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ranks = [priority_rank[p] for p in priorities]
    assert ranks == sorted(ranks)  # non-decreasing -- P0s all appear before P1s, etc.


def test_queue_filter_by_priority(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"], "priority": "P0", "page_size": 50})
    assert response.status_code == 200
    body = response.json()
    assert all(item["priority"] == "P0" for item in body["items"])


def test_queue_summary_matches_the_full_filtered_set(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    # page_size is bounded at 100 (Phase 8) -- the summary must still reflect
    # the FULL filtered set (300), independent of how many items this one
    # page returns.
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"], "page_size": 100})
    body = response.json()
    assert body["summary"]["total"] == body["total"] == run["exceptions"]
    assert sum(body["summary"]["counts_by_priority"].values()) == body["total"]
    assert len(body["items"]) == 100


def test_unknown_run_id_is_404(api_client):
    response = api_client.get("/exceptions/queue", params={"run_id": "RUN-does-not-exist"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_negative_page_is_rejected(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"], "page": -1})
    assert response.status_code == 422


def test_oversized_page_size_is_rejected(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"], "page_size": 999999})
    assert response.status_code == 422


def test_invalid_min_exposure_is_a_clean_400_not_a_crash(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"], "min_exposure": "not-a-number"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_FILTER"


def test_malformed_run_id_is_404_not_a_crash(api_client):
    response = api_client.get("/exceptions/queue", params={"run_id": "'; DROP TABLE audit_events; --"})
    assert response.status_code == 404


def test_ai_actor_can_still_view_the_queue_same_as_exception_list(api_client):
    # No new capability was added for the queue -- it reuses
    # Capability.VIEW_EXCEPTION, which AI already had from M4. Confirms this
    # endpoint did not accidentally tighten OR loosen the existing boundary.
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"]}, headers={"X-Actor-Type": "AI"})
    assert response.status_code == 200


def test_unauthorized_bogus_actor_type_is_rejected(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"]}, headers={"X-Actor-Type": "NOT_REAL"})
    assert response.status_code == 400


def test_no_mutation_endpoint_exists_for_the_queue():
    paths_and_methods = {(route.path, m) for route in app.routes for m in getattr(route, "methods", set())}
    assert ("/exceptions/queue", "POST") not in paths_and_methods
    assert ("/exceptions/queue", "PUT") not in paths_and_methods
    assert ("/exceptions/queue", "DELETE") not in paths_and_methods


def test_queue_response_never_leaks_internal_details(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    response = api_client.get("/exceptions/queue", params={"run_id": run["run_id"]})
    text = response.text
    assert "Traceback" not in text
    assert "site-packages" not in text
