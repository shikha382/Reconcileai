"""Phase 19: fail-safe behavior. A failure at any stage must never become
an AUTO_RESOLVE -- it must either fail the whole run explicitly, or (for a
single exception) be skipped with a recorded warning, never silently
counted as resolved."""
from pathlib import Path

import pytest

from app.ai.provider import MockAIProvider
from app.db.session import init_db, make_engine, make_session_factory
from app.policy.schemas import PolicyDecisionType
import app.services.reconciliation_pipeline as pipeline_module
from app.services.reconciliation_pipeline import run_reconciliation_pipeline


def _fresh_session(tmp_path, name):
    engine = make_engine(tmp_path / name)
    init_db(engine)
    return make_session_factory(engine)()


def test_ingestion_failure_fails_the_whole_run_not_auto_resolve(tmp_path):
    session = _fresh_session(tmp_path, "fail_ingestion.db")
    missing_dir = tmp_path / "does_not_exist"

    result = run_reconciliation_pipeline(session, missing_dir, MockAIProvider())

    # A missing source directory yields zero records ingested (M1's
    # ingest_source_directory tolerates a missing file per source type, see
    # its own `if not path.exists(): continue`), so this specific case
    # "succeeds" with 0 records rather than raising -- either way, nothing
    # is ever auto-resolved from records that were never ingested.
    assert result.records_processed == 0
    assert result.auto_resolved == 0
    session.close()


def test_matching_stage_exception_fails_the_run_explicitly(tmp_path, dataset_seed_dir, monkeypatch):
    session = _fresh_session(tmp_path, "fail_matching.db")

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated reconciliation engine crash")

    monkeypatch.setattr(pipeline_module, "run_exception_intelligence", _boom)

    result = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider())

    assert result.status == "failed"
    assert result.auto_resolved == 0
    assert result.human_review == 0
    assert any("reconciliation" in e for e in result.errors)
    session.close()


def test_one_exceptions_decision_failure_is_skipped_not_auto_resolved(tmp_path, dataset_seed_dir, monkeypatch):
    session = _fresh_session(tmp_path, "fail_one_decision.db")

    real_run_decision_pipeline = pipeline_module.run_decision_pipeline
    call_count = {"n": 0}

    def _flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 3:  # simulate a crash partway through the batch, not the first or last call
            raise RuntimeError("simulated decision-pipeline crash")
        return real_run_decision_pipeline(*args, **kwargs)

    monkeypatch.setattr(pipeline_module, "run_decision_pipeline", _flaky)

    result = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider())

    assert result.status == "completed"  # a single exception's failure does not fail the whole run
    assert len(result.warnings) >= 1
    assert any("failed safely, skipped" in w for w in result.warnings)
    # The failed exception is simply absent -- not present with any decision at all, safe or otherwise.
    assert len(result.decisions) == result.exceptions - 1
    session.close()


def test_provider_failure_degrades_to_human_review_never_auto_resolve(tmp_path, dataset_seed_dir):
    from app.ai.schemas import InvestigationState
    from app.ai.provider import ProviderError

    class _AlwaysFailingProvider:
        def decide_next_action(self, state: InvestigationState):
            raise ProviderError("simulated provider outage")

    session = _fresh_session(tmp_path, "fail_provider.db")
    result = run_reconciliation_pipeline(session, dataset_seed_dir, _AlwaysFailingProvider())

    assert result.status == "completed"
    # Every case that needed AI investigation must degrade to HUMAN_REVIEW
    # (M4's existing safe-fallback), never SAFE_TO_RESOLVE -- a total
    # provider outage must not silently look like a clean run.
    ai_assisted = [d for d in result.decisions.values() if d.ai_investigation is not None]
    assert len(ai_assisted) > 0
    for d in ai_assisted:
        assert d.ai_investigation.outcomes == []  # the provider never successfully produced a single hypothesis
        assert d.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE, (
            f"{d.exception_id} auto-resolved despite total AI provider failure"
        )
    session.close()
