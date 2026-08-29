"""M9 Phase 24: baseline comparison. The original clean 300-record dataset,
run through the real M7 end-to-end pipeline, must continue to produce the
same decision distribution established in M7/M8 (219 auto-resolved / 67
human review / 2 rejected(blocked) / 12 unresolved) unless a legitimate
safety correction changed it -- in which case the change must be explained,
never silently absorbed.
"""
from app.ai.provider import MockAIProvider
from app.db.session import init_db, make_engine, make_session_factory
from app.services.reconciliation_pipeline import run_reconciliation_pipeline


def test_clean_300_record_baseline_distribution_is_preserved(tmp_path, dataset_seed_dir):
    engine = make_engine(tmp_path / "baseline.db")
    init_db(engine)
    session = make_session_factory(engine)()

    result = run_reconciliation_pipeline(session, dataset_seed_dir, MockAIProvider())

    print(f"\n\nM9 BASELINE COMPARISON (clean 300-record dataset)")
    print(f"  auto_resolved={result.auto_resolved} human_review={result.human_review} "
          f"blocked={result.blocked} rejected={result.rejected} unresolved={result.unresolved}")

    assert result.status == "completed"
    assert result.records_processed == 300
    # This is the M7/M8-established baseline. If a legitimate M9 safety fix
    # (see the dated decision in CLAUDE.md re: the fee_verified bank-credit
    # gap) changes any of these numbers, this assertion is the place that
    # documents and re-locks the new, correct baseline -- never silently.
    assert result.auto_resolved == 219
    assert result.human_review == 67
    assert result.rejected == 2
    assert result.blocked == 2
    assert result.unresolved == 12
    assert result.provenance_available is True

    session.close()
