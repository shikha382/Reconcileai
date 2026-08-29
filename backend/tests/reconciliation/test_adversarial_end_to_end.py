"""Scenario 18 (adversarial fee mismatch) -- run through the REAL engine
against the REAL M1 dataset, not a hand-built fixture. This is the one test
that must never be allowed to regress: the engine must reject every one of
M1's 5 designed adversarial cases, end to end.
"""
from shared.taxonomy import ReconciliationStatus


def test_all_five_adversarial_cases_are_rejected(full_reconciliation):
    ground_truth = full_reconciliation["ground_truth"]
    results_by_order_id = {r.order_id: r for r in full_reconciliation["results"]}

    adversarial = [g for g in ground_truth if g["is_adversarial"]]
    assert len(adversarial) == 5

    for gt in adversarial:
        result = results_by_order_id[gt["order_id"]]
        assert result.status != ReconciliationStatus.MATCHED, (
            f"{gt['order_id']} ({gt['archetype']}) was adversarial and MUST NOT be auto-matched, "
            f"but the engine returned {result.status}"
        )


def test_adversarial_fee_mismatch_specifically_fails_fee_verification(full_reconciliation):
    ground_truth = full_reconciliation["ground_truth"]
    results_by_order_id = {r.order_id: r for r in full_reconciliation["results"]}

    adversarial_fee_cases = [
        g for g in ground_truth if g["is_adversarial"] and g["archetype"] == "fee_mismatch"
    ]
    assert len(adversarial_fee_cases) == 2

    for gt in adversarial_fee_cases:
        result = results_by_order_id[gt["order_id"]]
        assert result.status == ReconciliationStatus.MISMATCH
        assert any("does not explain" in line for line in result.why_not_matched)
        assert result.financial_impact > 0


def test_zero_incorrect_auto_resolutions_across_the_full_dataset(full_reconciliation):
    report = full_reconciliation["report"]
    assert report.incorrect_match_count == 0
    assert report.incorrectly_reconciled_amount == 0
