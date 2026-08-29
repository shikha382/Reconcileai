"""End-to-end evaluation against the real 300-record dataset. Ground truth
is never modified to make these numbers look better -- if a future change
regresses any of these, that's a real regression to investigate, not a
threshold to loosen.
"""
from decimal import Decimal


def test_evaluation_report_covers_all_300_records(full_reconciliation):
    report = full_reconciliation["report"]
    assert report.total_records == 300


def test_no_incorrect_auto_resolutions(full_reconciliation):
    report = full_reconciliation["report"]
    assert report.incorrect_auto_resolution_rate == Decimal("0.00")
    assert report.incorrect_match_count == 0


def test_precision_and_recall_on_auto_resolvable_cases(full_reconciliation):
    report = full_reconciliation["report"]
    assert report.precision == Decimal("1.0000")
    assert report.recall == Decimal("1.0000")
    assert report.f1 == Decimal("1.0000")


def test_action_level_agreement_with_ground_truth(full_reconciliation):
    """The engine's status (mapped to auto_resolve/human_review/unresolved)
    must agree with ground truth's expected_action for every record. Any
    disagreement here is investigated and documented (see CLAUDE.md's M2
    entry), never silently patched by changing ground truth."""
    report = full_reconciliation["report"]
    assert report.disagreements == []
    assert report.action_accuracy == Decimal("1.0000")


def test_every_archetype_is_represented_in_the_report(full_reconciliation):
    report = full_reconciliation["report"]
    archetypes_seen = {r.archetype for r in report.per_record}
    assert len(archetypes_seen) == 15  # 14 exception categories + exact_match


def test_financial_totals_are_consistent(full_reconciliation):
    report = full_reconciliation["report"]
    assert report.correctly_reconciled_amount + report.incorrectly_reconciled_amount \
        + report.unresolved_amount + report.ambiguous_amount <= report.total_transaction_amount
    assert report.incorrectly_reconciled_amount == Decimal("0.00")


def test_report_never_hides_a_record(full_reconciliation):
    report = full_reconciliation["report"]
    assert len(report.per_record) == report.total_records == 300
