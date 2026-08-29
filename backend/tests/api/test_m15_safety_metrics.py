"""Milestone 15, Phase 2: GET /runs/{run_id}/safety-metrics -- the API
source for Overview's "impossible to miss" unsafe auto-resolution rate.
Reuses the real M7 orchestrator (via the existing api_client_with_run
fixture, which already runs POST /runs once against the real 300-record
dataset) rather than a second, parallel test harness.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from app.policy.schemas import PolicyDecisionType
from app.services.reconciliation_pipeline import PipelineRunResult
from app.services.safety_metrics import compute_safety_metrics


def test_safety_metrics_available_and_zero_unsafe_for_the_real_dataset(api_client_with_run):
    client, state = api_client_with_run
    response = client.get(f"/runs/{state['run_id']}/safety-metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["total"] == 300
    assert body["graded"] == 300
    assert body["false_auto_resolutions"] == 0
    assert body["false_auto_resolution_rate"] == 0.0
    assert body["match_rate"] > 0


def test_safety_metrics_unavailable_when_no_ground_truth_directory():
    result = PipelineRunResult(run_id="RUN-x", status="completed", started_at=datetime.now(), dataset_dir=None)
    metrics = compute_safety_metrics(result)
    assert metrics.available is False
    assert metrics.reason_unavailable is not None


def test_safety_metrics_unavailable_when_dataset_dir_has_no_ground_truth(tmp_path):
    empty_dir = tmp_path / "no_ground_truth_here"
    empty_dir.mkdir()
    result = PipelineRunResult(run_id="RUN-y", status="completed", started_at=datetime.now(), dataset_dir=empty_dir)
    metrics = compute_safety_metrics(result)
    assert metrics.available is False
    assert "ground_truth.json" in metrics.reason_unavailable


def test_safety_metrics_unknown_run_is_404(api_client):
    response = api_client.get("/runs/RUN-does-not-exist/safety-metrics")
    assert response.status_code == 404


def test_safety_metrics_ai_actor_is_forbidden(api_client_with_run):
    client, state = api_client_with_run
    response = client.get(f"/runs/{state['run_id']}/safety-metrics", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403


def test_safety_metrics_never_hides_a_nonzero_unsafe_rate(tmp_path):
    # A synthetic, deliberately-wrong PipelineRunResult proving the
    # computation itself (not just the real, already-safe dataset) would
    # correctly surface a nonzero rate if one existed -- this is the one
    # thing this metric must NEVER silently round away.
    import json

    dataset_dir = tmp_path / "fake_dataset"
    dataset_dir.mkdir()
    (dataset_dir / "ground_truth.json").write_text(json.dumps([
        {"order_id": "ORD-1", "expected_action": "human_review"},
        {"order_id": "ORD-2", "expected_action": "auto_resolve"},
    ]))

    fake_decision_1 = SimpleNamespace(policy_decision=SimpleNamespace(decision=PolicyDecisionType.SAFE_TO_RESOLVE))
    fake_decision_2 = SimpleNamespace(policy_decision=SimpleNamespace(decision=PolicyDecisionType.SAFE_TO_RESOLVE))

    result = PipelineRunResult(
        run_id="RUN-z", status="completed", started_at=datetime.now(), dataset_dir=dataset_dir,
        decisions={"ORD-1": fake_decision_1, "ORD-2": fake_decision_2}, records_processed=2, matched=2,
    )
    metrics = compute_safety_metrics(result)
    assert metrics.available is True
    assert metrics.false_auto_resolutions == 1  # ORD-1 was wrongly auto-resolved
    assert metrics.false_auto_resolution_rate == 0.5
