"""End-to-end M3 evaluation against the real 300-record dataset. Ground
truth is never modified to improve these numbers -- see CLAUDE.md's M3
entry for the one confirmed, intentional status divergence
(reversed_transaction correctly reaches VERIFIED root-cause status despite
ground truth's expected_action saying human_review; those answer different
questions, see app.engines.exceptions.evaluation's docstring).
"""
from decimal import Decimal


def test_covers_all_300_records(full_exception_intelligence):
    report = full_exception_intelligence["report"]
    assert report.total_records == 300


def test_exception_classification_accuracy_is_perfect(full_exception_intelligence):
    report = full_exception_intelligence["report"]
    assert report.exception_classification_accuracy == Decimal("1.0000")


def test_root_cause_status_accuracy_is_perfect(full_exception_intelligence):
    report = full_exception_intelligence["report"]
    assert report.root_cause_status_accuracy == Decimal("1.0000")


def test_false_explanation_rate_is_zero(full_exception_intelligence):
    """MOST IMPORTANT metric per the M3 brief."""
    report = full_exception_intelligence["report"]
    assert report.false_explanation_rate == Decimal("0.00")
    assert report.false_explanations == []


def test_false_root_cause_rate_is_zero(full_exception_intelligence):
    report = full_exception_intelligence["report"]
    assert report.false_root_cause_rate == Decimal("0.00")


def test_all_five_adversarial_cases_never_reach_verified(full_exception_intelligence):
    from app.engines.root_cause.result import VERIFIED

    ground_truth = full_exception_intelligence["ground_truth"]
    bundles_by_order = {b.order_id: b for b in full_exception_intelligence["bundles"]}
    adversarial = [g for g in ground_truth if g["is_adversarial"]]
    assert len(adversarial) == 5

    for gt in adversarial:
        bundle = bundles_by_order[gt["order_id"]]
        assert bundle.root_cause.status != VERIFIED, (
            f"{gt['order_id']} ({gt['archetype']}) is adversarial and must never reach VERIFIED"
        )


def test_average_candidates_and_evidence_are_positive(full_exception_intelligence):
    report = full_exception_intelligence["report"]
    assert report.average_candidates_evaluated > 0
    assert report.average_evidence_records_generated > 0


def test_report_never_hides_a_record(full_exception_intelligence):
    bundles = full_exception_intelligence["bundles"]
    assert len(bundles) == 300
