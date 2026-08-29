from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.ai.provider import MockAIProvider
from app.api.dependencies import get_approval_store, get_provider, get_run_registry, get_session
from app.api.run_registry import RunRegistry
from app.db.session import init_db, make_engine, make_session_factory
from app.main import app
from app.policy.approval import ApprovalWorkflowStore


def _build_state(db_path):
    engine = make_engine(db_path)
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

    return {
        "engine": engine, "session_factory": session_factory, "registry": registry, "store": store,
        "override_session": override_session,
    }


def _apply_overrides(state: dict) -> None:
    app.dependency_overrides[get_session] = state["override_session"]
    app.dependency_overrides[get_run_registry] = lambda: state["registry"]
    app.dependency_overrides[get_approval_store] = lambda: state["store"]
    app.dependency_overrides[get_provider] = lambda: MockAIProvider()


@pytest.fixture()
def api_client(tmp_path):
    """A fresh, empty, isolated DB per test -- for tests that need a clean
    slate (invalid requests, 404s, path-traversal, auth boundary)."""
    state = _build_state(tmp_path / "api_test.db")
    _apply_overrides(state)
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def _api_run_state(tmp_path_factory):
    """Runs the real 300-record dataset through POST /runs exactly ONCE
    (expensive: ~3-4s), reused read-only across every test that needs an
    already-completed run."""
    db_path = tmp_path_factory.mktemp("apidb") / "reconcileai.db"
    state = _build_state(db_path)
    _apply_overrides(state)
    client = TestClient(app)

    response = client.post("/runs", json={"dataset": "seeds"})
    assert response.status_code == 201, response.text
    state["run_id"] = response.json()["run_id"]
    state["run_response"] = response.json()
    return state


@pytest.fixture()
def api_client_with_run(_api_run_state):
    """Re-applies the session run's overrides before every test that uses
    it (an intervening `api_client` test may have pointed app.dependency_overrides
    elsewhere) -- guarantees fixture ordering never matters."""
    _apply_overrides(_api_run_state)
    client = TestClient(app)
    yield client, _api_run_state
    app.dependency_overrides.clear()
