"""get_decision_provenance / build_decision_summary: reconstructing the full
decision story from only an exception_id and the audit ledger -- a future UI
renders this directly, it never recomputes any business logic itself."""
from app.audit.provenance import build_decision_summary, get_decision_provenance


def test_provenance_reconstructs_timeline_for_a_clean_auto_resolved_case(full_m6_decisions):
    results = full_m6_decisions["results"]
    session = full_m6_decisions["session"]

    clean = next(r for r in results.values() if r.ai_investigation is None)
    provenance = get_decision_provenance(session, clean.exception_id)

    assert provenance.exception_id == clean.exception_id
    assert provenance.correlation_id == clean.correlation_id
    event_types = [t.event_type for t in provenance.timeline]
    assert "EXCEPTION_CREATED" in event_types
    assert "POLICY_EVALUATED" in event_types
    assert "RESOLUTION_PROPOSED" in event_types
    # No AI was needed for this case, so no investigation events should appear.
    assert "AI_INVESTIGATION_STARTED" not in event_types
    assert provenance.audit_chain_valid is True


def test_provenance_reconstructs_ai_hypotheses_and_contradictions_for_an_ai_assisted_case(full_m6_decisions):
    results = full_m6_decisions["results"]
    session = full_m6_decisions["session"]

    ai_case = next(r for r in results.values() if r.ai_investigation is not None)
    provenance = get_decision_provenance(session, ai_case.exception_id)

    event_types = [t.event_type for t in provenance.timeline]
    assert "AI_INVESTIGATION_STARTED" in event_types
    assert "AI_INVESTIGATION_COMPLETED" in event_types
    assert len(provenance.ai_hypotheses) == len(ai_case.contradiction_records)


def test_provenance_for_unknown_exception_id_returns_empty_but_valid_shape(full_m6_decisions):
    session = full_m6_decisions["session"]
    provenance = get_decision_provenance(session, "EXC-does-not-exist")
    assert provenance.timeline == []
    assert provenance.correlation_id is None
    assert provenance.policy_evaluation is None


def test_build_decision_summary_answers_every_required_question(full_m6_decisions):
    results = full_m6_decisions["results"]
    session = full_m6_decisions["session"]

    sample = next(iter(results.values()))
    provenance = get_decision_provenance(session, sample.exception_id)
    summary = build_decision_summary(provenance)

    required_keys = {
        "exception_id", "ai_believed", "supporting_evidence", "contradicting_evidence",
        "verification_conclusion", "policy_decision", "policy_id", "policy_version",
        "financial_exposure", "approval_required", "review_id", "audit_chain_valid", "audit_events_checked",
    }
    assert required_keys.issubset(summary.keys())
    assert summary["policy_decision"] == sample.policy_decision.decision.value
    assert summary["audit_chain_valid"] is True


def test_build_decision_summary_reports_contradicted_when_a_contradiction_exists(full_m6_decisions):
    results = full_m6_decisions["results"]
    session = full_m6_decisions["session"]

    contradicted_case = next(
        (r for r in results.values() if any(c.status == "CONTRADICTED" for c in r.contradiction_records)), None,
    )
    assert contradicted_case is not None, "expected at least one contradicted case in the real dataset"

    provenance = get_decision_provenance(session, contradicted_case.exception_id)
    summary = build_decision_summary(provenance)
    assert summary["verification_conclusion"] == "CONTRADICTED"
    assert summary["approval_required"] in (True, False)  # always answered, never omitted
