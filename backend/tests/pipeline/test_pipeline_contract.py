"""Phase 3/4/23: the pipeline's structured contract -- run_id, per-exception
correlation_id threading back to the run, stage timings, and the JSON-shaped
result contract."""
from app.audit.ledger import AuditLedger
from app.policy.schemas import PolicyDecisionType


def test_run_produces_a_run_id_and_completes(full_pipeline_run):
    result = full_pipeline_run["result"]
    assert result.run_id.startswith("RUN-")
    assert result.status == "completed"
    assert result.completed_at is not None
    assert result.duration_seconds is not None and result.duration_seconds >= 0


def test_result_counts_are_computed_not_hardcoded(full_pipeline_run):
    result = full_pipeline_run["result"]
    assert result.records_processed == 300
    total_by_decision = result.auto_resolved + result.human_review + result.rejected + result.unresolved + result.escalated
    assert total_by_decision == len(result.decisions)
    assert result.decisions  # not empty -- a real run happened


def test_every_exception_correlation_id_traces_back_to_the_run(full_pipeline_run):
    session = full_pipeline_run["session"]
    result = full_pipeline_run["result"]
    ledger = AuditLedger(session)

    run_events = ledger.events_for_correlation(result.run_id)
    event_types = {e.event_type for e in run_events}
    assert "RUN_STARTED" in event_types
    assert "RUN_COMPLETED" in event_types

    from shared.money import loads

    sample = list(result.decisions.values())[:20]
    for decision in sample:
        events = ledger.events_for_correlation(decision.correlation_id)
        exception_created = next(e for e in events if e.event_type == "EXCEPTION_CREATED")
        payload = loads(exception_created.payload_json)
        assert payload["run_id"] == result.run_id


def test_stage_timings_cover_every_major_stage(full_pipeline_run):
    result = full_pipeline_run["result"]
    stages = {t.stage for t in result.stage_timings}
    assert "ingestion" in stages
    assert "reconciliation_and_exception_intelligence" in stages
    assert "decision_pipeline" in stages
    assert all(t.seconds >= 0 for t in result.stage_timings)


def test_to_dict_matches_the_documented_contract_shape(full_pipeline_run):
    result = full_pipeline_run["result"]
    d = result.to_dict()
    required_keys = {
        "run_id", "status", "started_at", "completed_at", "duration_seconds",
        "records_processed", "matched", "exceptions", "auto_resolved", "human_review",
        "blocked", "rejected", "unresolved", "escalated", "audit_events", "provenance_available",
        "stage_timings", "errors", "warnings",
    }
    assert required_keys.issubset(d.keys())


def test_audit_events_and_provenance_available_are_real(full_pipeline_run):
    result = full_pipeline_run["result"]
    assert result.audit_events > 0
    assert result.provenance_available is True


def test_blocked_is_an_alias_of_rejected_not_a_competing_status(full_pipeline_run):
    # This codebase's actual PolicyDecisionType taxonomy has no BLOCKED
    # value -- the BLOCK tier produces REJECTED. `blocked` mirrors `rejected`
    # rather than inventing a new status (M7 brief: "use the repository's
    # actual canonical taxonomy, do not invent competing status values").
    result = full_pipeline_run["result"]
    assert result.blocked == result.rejected
    rejected_count = sum(1 for d in result.decisions.values() if d.policy_decision.decision == PolicyDecisionType.REJECTED)
    assert result.rejected == rejected_count
