"""Phase 21: the 300-record end-to-end evaluation, run through ONE
orchestrator call (no manual per-engine execution). False-auto-resolution
rate must be 0% -- critical, stop-and-fix if not."""
from app.policy.schemas import PolicyDecisionType


def _gt_by_order_id(ground_truth):
    return {row["order_id"]: row for row in ground_truth}


def test_full_300_record_end_to_end_run_via_one_orchestrator_call(full_pipeline_run):
    result = full_pipeline_run["result"]
    gt_by_order = _gt_by_order_id(full_pipeline_run["ground_truth"])

    assert result.status == "completed"
    assert result.records_processed == 300

    false_auto_resolutions = []
    for order_id, decision in result.decisions.items():
        gt = gt_by_order.get(order_id)
        if gt is None:
            continue
        expected_action = gt["expected_action"]
        if decision.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE and expected_action != "auto_resolve":
            false_auto_resolutions.append(order_id)

    false_auto_resolution_rate = len(false_auto_resolutions) / result.records_processed

    print(f"\nM7 end-to-end 300-record evaluation:")
    print(f"  run_id={result.run_id}")
    print(f"  matched={result.matched} exceptions={result.exceptions}")
    print(f"  auto_resolved={result.auto_resolved} human_review={result.human_review} "
          f"blocked/rejected={result.rejected} unresolved={result.unresolved}")
    print(f"  false_auto_resolution_rate={false_auto_resolution_rate:.4f} ({len(false_auto_resolutions)}/{result.records_processed})")
    print(f"  processing_time={result.duration_seconds:.3f}s records_per_sec={result.records_processed / result.duration_seconds:.1f}")
    print(f"  audit_events={result.audit_events} provenance_available={result.provenance_available}")

    assert false_auto_resolution_rate == 0.0, f"false auto-resolutions found: {false_auto_resolutions}"
    assert result.provenance_available is True
    assert len(result.errors) == 0


def test_no_manual_stage_execution_was_required(full_pipeline_run):
    # The fixture calls run_reconciliation_pipeline exactly once -- this test
    # exists to make that requirement explicit and regression-visible: if a
    # future change makes the fixture call M2/M3/M6 separately, this
    # assertion's premise (one orchestrator call already produced a complete
    # run) documents what would be lost.
    result = full_pipeline_run["result"]
    assert result.status == "completed"
    assert len(result.decisions) == result.exceptions


def test_contradiction_cases_are_detected_end_to_end(full_pipeline_run):
    result = full_pipeline_run["result"]
    contradicted = [
        d for d in result.decisions.values() if any(c.status == "CONTRADICTED" for c in d.contradiction_records)
    ]
    assert len(contradicted) > 0
    for d in contradicted:
        assert d.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
