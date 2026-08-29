"""End-to-end M4 evaluation against the real 300-record dataset, with
MockAIProvider (no live API key needed). CRITICAL: false_auto_resolution_rate
must be exactly 0 -- if this ever fails, STOP and investigate (per the M4
brief), never loosen the assertion.
"""
from decimal import Decimal


def test_covers_all_300_records(full_ai_evaluation):
    assert full_ai_evaluation["report"].total_records == 300


def test_false_auto_resolution_rate_is_zero(full_ai_evaluation):
    report = full_ai_evaluation["report"]
    assert report.false_auto_resolution_rate == Decimal("0.0000")
    assert report.false_auto_resolutions == []


def test_ai_only_investigates_the_non_verified_residual(full_ai_evaluation, full_exception_intelligence):
    """AI routing must match M3's own non-VERIFIED count exactly -- not
    every record, and not zero."""
    from app.engines.root_cause.result import VERIFIED

    bundles_by_order = {b.order_id: b for b in full_exception_intelligence["bundles"]}
    expected_ai_count = sum(1 for b in bundles_by_order.values() if b.root_cause.status != VERIFIED)

    report = full_ai_evaluation["report"]
    assert report.ai_assisted_count == expected_ai_count
    assert 0 < report.ai_assisted_count < report.total_records


def test_ai_investigation_success_rate_is_high(full_ai_evaluation):
    report = full_ai_evaluation["report"]
    assert report.ai_investigation_success_rate == Decimal("1.0000")  # MockAIProvider never errors


def test_deterministic_verifier_rejects_a_meaningful_fraction(full_ai_evaluation):
    """The residual cases are, by construction, ones M3 couldn't fully
    verify -- so the AI's early hypothesis guesses should mostly be
    rejected before (if ever) landing on the right one."""
    report = full_ai_evaluation["report"]
    assert report.deterministic_verifier_rejection_rate > Decimal("0.00")


def test_hallucinated_record_rate_is_zero_for_the_honest_mock(full_ai_evaluation):
    """MockAIProvider never hallucinates by default (only when explicitly
    configured to, for the adversarial test suite) -- so across the real
    dataset, its hypotheses are always grounded."""
    report = full_ai_evaluation["report"]
    assert report.hallucinated_record_rate == Decimal("0.0000")


def test_mean_latency_is_reported_and_fast(full_ai_evaluation):
    report = full_ai_evaluation["report"]
    assert report.mean_investigation_latency_seconds >= 0
    assert report.mean_investigation_latency_seconds < Decimal("1.0")  # mock provider, no network


def test_report_never_hides_a_record(full_ai_resolution):
    assert len(full_ai_resolution["resolutions"]) == 300
