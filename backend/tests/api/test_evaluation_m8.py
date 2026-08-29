"""Phase 20: the critical end-to-end API test. The 300-record dataset run
through HTTP -> POST /runs -> M7 pipeline -> M1-M6 -> final result -> HTTP
response. The API must not manually reproduce the pipeline -- verified by
call-count instrumentation, not just by reading the code."""
from shared.money import loads


def test_300_record_dataset_runs_end_to_end_through_http(api_client_with_run):
    _, state = api_client_with_run
    response = state["run_response"]

    assert response["status"] == "completed"
    assert response["records_processed"] == 300
    assert response["audit_chain_valid"] is True
    assert response["audit_event_count"] > 0


def test_false_auto_resolution_rate_is_zero_via_http(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]

    listing = client.get("/exceptions", params={"run_id": run_id, "decision": "SAFE_TO_RESOLVE", "page_size": 100}).json()
    dataset_seed_dir_ground_truth = loads(
        (__import__("pathlib").Path(__file__).resolve().parents[3] / "data" / "synthetic" / "seeds" / "ground_truth.json").read_text()
    )
    gt_by_order = {row["order_id"]: row for row in dataset_seed_dir_ground_truth}

    false_auto_resolutions = []
    page, page_size = 1, 100
    seen = 0
    while True:
        page_response = client.get("/exceptions", params={"run_id": run_id, "page": page, "page_size": page_size}).json()
        if not page_response["items"]:
            break
        for item in page_response["items"]:
            seen += 1
            gt = gt_by_order.get(item["order_id"])
            if gt is None:
                continue
            if item["decision"] == "SAFE_TO_RESOLVE" and gt["expected_action"] != "auto_resolve":
                false_auto_resolutions.append(item["exception_id"])
        page += 1

    assert seen == 300
    assert false_auto_resolutions == [], f"false auto-resolutions surfaced via API: {false_auto_resolutions}"


def test_decision_distribution_matches_the_run_summary(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]
    run_summary = state["run_response"]

    for decision_type, expected_count in [
        ("SAFE_TO_RESOLVE", run_summary["auto_resolved"]), ("HUMAN_REVIEW", run_summary["human_review"]),
        ("REJECTED", run_summary["rejected"]), ("UNRESOLVED", run_summary["unresolved"]),
    ]:
        listing = client.get("/exceptions", params={"run_id": run_id, "decision": decision_type, "page_size": 1}).json()
        assert listing["total"] == expected_count, f"{decision_type}: expected {expected_count}, API reports {listing['total']}"


def test_pipeline_invoked_exactly_once_per_post_runs_call(api_client, monkeypatch):
    import app.api.routes.runs as runs_module

    call_count = {"n": 0}
    real_pipeline = runs_module.run_reconciliation_pipeline

    def _counting_pipeline(*args, **kwargs):
        call_count["n"] += 1
        return real_pipeline(*args, **kwargs)

    monkeypatch.setattr(runs_module, "run_reconciliation_pipeline", _counting_pipeline)

    response = api_client.post("/runs", json={"dataset": "seeds"})
    assert response.status_code == 201
    assert call_count["n"] == 1


def test_api_response_matches_the_actual_pipeline_result_object(api_client, monkeypatch):
    import app.api.routes.runs as runs_module

    captured = {}
    real_pipeline = runs_module.run_reconciliation_pipeline

    def _capturing_pipeline(*args, **kwargs):
        result = real_pipeline(*args, **kwargs)
        captured["result"] = result
        return result

    monkeypatch.setattr(runs_module, "run_reconciliation_pipeline", _capturing_pipeline)

    response = api_client.post("/runs", json={"dataset": "seeds"})
    body = response.json()
    result = captured["result"]

    assert body["run_id"] == result.run_id
    assert body["records_processed"] == result.records_processed
    assert body["auto_resolved"] == result.auto_resolved
    assert body["human_review"] == result.human_review
    assert body["audit_event_count"] == result.audit_events
