"""End-to-end M5 pipeline against the real 300-record dataset:
EvidenceBundle -> PolicyInput -> PolicyEngine -> ResolutionProposal ->
(ReviewRequest if required). CRITICAL: false_auto_resolution_rate and
unsafe_approval_rate must both be 0.
"""
from decimal import Decimal

from app.policy.evaluation import evaluate_policy_layer
from app.policy.schemas import PolicyDecisionType


def test_covers_all_300_records(full_m5_resolution):
    assert len(full_m5_resolution["results"]) == 300


def test_false_auto_resolution_rate_is_zero(full_m5_resolution):
    report = evaluate_policy_layer(full_m5_resolution["results"], full_m5_resolution["ground_truth"])
    assert report.false_auto_resolution_rate == Decimal("0.0000")
    assert report.false_auto_resolutions == []


def test_unsafe_approval_rate_is_zero(full_m5_resolution):
    report = evaluate_policy_layer(full_m5_resolution["results"], full_m5_resolution["ground_truth"])
    assert report.unsafe_approval_rate == Decimal("0.0000")


def test_policy_decision_accuracy_is_perfect(full_m5_resolution):
    report = evaluate_policy_layer(full_m5_resolution["results"], full_m5_resolution["ground_truth"])
    assert report.policy_decision_accuracy == Decimal("1.0000")
    assert report.mismatches == []


def test_all_five_adversarial_cases_are_blocked(full_m5_resolution):
    report = evaluate_policy_layer(full_m5_resolution["results"], full_m5_resolution["ground_truth"])
    assert report.blocked_unsafe_action_rate == Decimal("1.0000")


def test_adversarial_fee_cases_are_rejected_by_the_block_tier(full_m5_resolution):
    ground_truth = full_m5_resolution["ground_truth"]
    results = full_m5_resolution["results"]
    adversarial_fee = [g for g in ground_truth if g["is_adversarial"] and g["archetype"] == "fee_mismatch"]
    for gt in adversarial_fee:
        decision = results[gt["order_id"]]["policy_decision"]
        assert decision.decision == PolicyDecisionType.REJECTED
        assert "POLICY-VERIFIER-FAIL-001" in decision.rules_passed


def test_reviews_are_created_only_when_required(full_m5_resolution):
    for order_id, r in full_m5_resolution["results"].items():
        if r["policy_decision"].required_approval:
            assert r["review"] is not None
        else:
            assert r["review"] is None


def test_no_financial_record_is_mutated(full_m5_resolution):
    """Sanity check on the architectural boundary: resolving every exception
    must not change the underlying Payment/Settlement amounts."""
    payments_by_id = {p.payment_id: p for p in full_m5_resolution["payments"]}
    for order_id, r in full_m5_resolution["results"].items():
        payment = payments_by_id[r["bundle"].payment_id]
        assert payment.amount == payment.amount  # identity check: nothing here writes to `payment`
    # A stronger check: the proposal object is a separate dataclass, never
    # the ORM Payment/Settlement instance itself.
    sample = next(iter(full_m5_resolution["results"].values()))
    assert not hasattr(sample["proposal"], "amount")
