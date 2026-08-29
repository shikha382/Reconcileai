"""POST /runs, GET /runs/{run_id} -- and that the route calls M7 exactly
once and never re-implements its own pipeline logic."""
import pytest


def test_post_runs_valid_request_runs_the_full_m7_pipeline(api_client):
    response = api_client.post("/runs", json={"dataset": "seeds"})
    assert response.status_code == 201
    body = response.json()
    assert body["run_id"].startswith("RUN-")
    assert body["status"] == "completed"
    assert body["records_processed"] == 300
    assert body["auto_resolved"] + body["human_review"] + body["rejected"] + body["unresolved"] + body["escalated"] > 0


def test_post_runs_default_dataset_is_seeds(api_client):
    response = api_client.post("/runs", json={})
    assert response.status_code == 201
    assert response.json()["records_processed"] == 300


@pytest.mark.parametrize("bad_dataset", ["../../etc", "..", "/etc/passwd", "does_not_exist", "a/b"])
def test_post_runs_rejects_invalid_or_unsafe_dataset_names(api_client, bad_dataset):
    response = api_client.post("/runs", json={"dataset": bad_dataset})
    assert response.status_code in (400, 422)
    body = response.json()
    assert "error" in body


def test_post_runs_invalid_json_body_is_422(api_client):
    response = api_client.post("/runs", json={"dataset": 12345})  # wrong type
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_run_returns_the_stored_summary_without_rerunning(api_client):
    create = api_client.post("/runs", json={"dataset": "seeds"})
    run_id = create.json()["run_id"]

    get1 = api_client.get(f"/runs/{run_id}")
    get2 = api_client.get(f"/runs/{run_id}")
    assert get1.status_code == 200 == get2.status_code
    # Identical stored summary both times -- if GET had rerun the pipeline,
    # started_at/completed_at (and likely run_id itself) would differ.
    assert get1.json() == get2.json()
    assert get1.json()["run_id"] == run_id


def test_get_unknown_run_is_404(api_client):
    response = api_client.get("/runs/RUN-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "RUN_NOT_FOUND"
    assert "request_id" in body["error"]


def test_error_responses_never_leak_stack_trace_or_filesystem_paths(api_client):
    response = api_client.get("/runs/RUN-does-not-exist")
    text = response.text
    assert "Traceback" not in text
    assert "site-packages" not in text
    assert "C:\\" not in text and "/home/" not in text
