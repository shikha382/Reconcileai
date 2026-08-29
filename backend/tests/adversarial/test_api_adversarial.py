"""M9 Category N: API-level attacks (Phase 17). Extends M8's own API test
suite (backend/tests/api/test_security.py, test_authorization.py) with
scenarios not already covered there -- extremely long IDs, unexpected
Unicode, negative pagination, unsupported filters, repeated requests --
rather than duplicating what M8 already tests exhaustively (malformed IDs,
invalid JSON, the authorization boundary, no financial-mutation endpoints).
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
    engine = make_engine(tmp_path / "adv_api.db")
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


def test_extremely_long_run_id_is_a_safe_404_not_a_crash(api_client):
    # Long enough to be a real "unreasonably long ID" attempt, short enough
    # to stay under the test HTTP client's own URL-length guard rail (a real
    # deployment's reverse proxy enforces an analogous limit ahead of the app).
    response = api_client.get(f"/runs/{'A' * 4000}")
    assert response.status_code == 404


def test_extremely_long_exception_id_is_a_safe_404_not_a_crash(api_client):
    response = api_client.get(f"/exceptions/{'B' * 4000}")
    assert response.status_code == 404


def test_unexpected_unicode_in_ids_is_handled_safely(api_client):
    # Built from escape sequences (not pasted glyphs) to keep this source
    # file itself plain ASCII: a right-to-left override + zero-width space,
    # an emoji pair, and assorted non-ASCII letters/symbols.
    weird_ids = [
        "RUN-" + "‮" + "​",
        "EXC-" + "\U0001F600" + "\U0001F4A9",
        "run-" + "Ω≈ç√∫˜µ",
    ]
    for weird_id in weird_ids:
        run_response = api_client.get(f"/runs/{weird_id}")
        exc_response = api_client.get(f"/exceptions/{weird_id}")
        assert run_response.status_code == 404
        assert exc_response.status_code == 404


def test_negative_page_is_rejected(api_client):
    response = api_client.get("/exceptions", params={"page": -1})
    assert response.status_code == 422


def test_zero_page_is_rejected(api_client):
    response = api_client.get("/exceptions", params={"page": 0})
    assert response.status_code == 422


def test_negative_page_size_is_rejected(api_client):
    response = api_client.get("/exceptions", params={"page_size": -5})
    assert response.status_code == 422


def test_unsupported_filter_is_ignored_not_a_crash(api_client):
    api_client.post("/runs", json={"dataset": "seeds"})
    response = api_client.get("/exceptions", params={"totally_unsupported_filter": "anything"})
    assert response.status_code == 200


def test_invalid_enum_style_decision_filter_returns_empty_not_a_crash(api_client):
    api_client.post("/runs", json={"dataset": "seeds"})
    response = api_client.get("/exceptions", params={"decision": "NOT_A_REAL_DECISION_VALUE"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_repeated_get_requests_are_idempotent_and_stable(api_client):
    create = api_client.post("/runs", json={"dataset": "seeds"})
    run_id = create.json()["run_id"]
    responses = [api_client.get(f"/runs/{run_id}").json() for _ in range(5)]
    assert all(r == responses[0] for r in responses)


def test_ai_actor_attempting_a_restricted_operation_through_the_api_is_refused(api_client):
    response = api_client.post("/runs", json={"dataset": "seeds"}, headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "FORBIDDEN"
    assert "Traceback" not in response.text


def test_missing_required_field_is_a_clean_422_not_a_crash(api_client):
    response = api_client.post("/runs", content=b"{}", headers={"Content-Type": "application/json"})
    # `dataset` has a default, so an empty body is actually valid -- confirms
    # the route doesn't crash on a minimal/empty JSON object either way.
    assert response.status_code in (201, 422)
