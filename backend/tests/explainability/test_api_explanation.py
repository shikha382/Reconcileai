"""M10 Phase 19/20: GET /exceptions/{id}/explanation. Reuses M8's existing
authorization boundary (Capability.VIEW_PROVENANCE) -- no new capability
was added, so AI actors gain nothing new merely because this endpoint
exists. Errors stay structured; no internal objects leak.
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
    engine = make_engine(tmp_path / "expl_api.db")
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


def _get_one_exception_id(client, run_id, decision=None):
    params = {"run_id": run_id, "page_size": 1}
    if decision:
        params["decision"] = decision
    listing = client.get("/exceptions", params=params).json()
    return listing["items"][0]["exception_id"]


def test_explanation_endpoint_returns_a_full_structured_response(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    exception_id = _get_one_exception_id(api_client, run["run_id"], "HUMAN_REVIEW")

    response = api_client.get(f"/exceptions/{exception_id}/explanation")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "exception_id", "decision", "financial_summary", "source_records", "matching_evidence",
        "calculation_evidence", "exception_evidence", "ai_investigation_status", "ai_hypotheses",
        "self_challenge", "policy", "risk", "resolution", "audit_references", "contradictions",
        "missing_evidence", "confidence_note", "human_readable",
    ):
        assert key in body, f"missing key {key!r}"
    assert body["exception_id"] == exception_id


def test_explanation_matches_the_actual_decision_for_the_same_exception(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    exception_id = _get_one_exception_id(api_client, run["run_id"], "HUMAN_REVIEW")

    detail = api_client.get(f"/exceptions/{exception_id}").json()
    explanation = api_client.get(f"/exceptions/{exception_id}/explanation").json()
    assert explanation["decision"] == detail["decision"]


def test_explanation_for_unknown_exception_is_404(api_client):
    response = api_client.get("/exceptions/EXC-does-not-exist/explanation")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "EXCEPTION_NOT_FOUND"


def test_ai_actor_cannot_access_explanation_no_new_capability_granted(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    exception_id = _get_one_exception_id(api_client, run["run_id"])

    response = api_client.get(f"/exceptions/{exception_id}/explanation", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_human_actor_can_access_explanation(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    exception_id = _get_one_exception_id(api_client, run["run_id"])
    response = api_client.get(f"/exceptions/{exception_id}/explanation")
    assert response.status_code == 200


def test_malformed_exception_id_is_404_not_a_crash(api_client):
    response = api_client.get("/exceptions/'; DROP TABLE audit_events; --/explanation")
    assert response.status_code == 404


def test_explanation_response_never_leaks_internal_details(api_client):
    run = api_client.post("/runs", json={"dataset": "seeds"}).json()
    exception_id = _get_one_exception_id(api_client, run["run_id"])
    response = api_client.get(f"/exceptions/{exception_id}/explanation")
    text = response.text
    assert "Traceback" not in text
    assert "site-packages" not in text
    assert "C:\\" not in text
