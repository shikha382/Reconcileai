"""Phase 22: end-to-end golden cases. Each asserts the FINAL decision that
comes out of the full pipeline, not an intermediate function's own output --
these are what a judge running the real dataset through ONE pipeline call
would actually see."""
from app.policy.schemas import PolicyDecisionType, RiskLevel


def _gt_by_order_id(ground_truth):
    return {row["order_id"]: row for row in ground_truth}


def test_golden_001_clean_exact_match_auto_resolves(full_pipeline_run):
    result = full_pipeline_run["result"]
    gt_by_order = _gt_by_order_id(full_pipeline_run["ground_truth"])

    case = next(
        (d for order_id, d in result.decisions.items() if gt_by_order[order_id]["archetype"] == "exact_match"), None,
    )
    assert case is not None, "GOLDEN-001: no exact_match case found"
    assert case.ai_investigation is None, "GOLDEN-001: a clean exact match should never need AI investigation"
    assert case.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE


def test_golden_002_adversarial_fee_mismatch_is_never_auto_resolved(full_pipeline_run):
    result = full_pipeline_run["result"]
    gt_by_order = _gt_by_order_id(full_pipeline_run["ground_truth"])

    adversarial_fee_cases = [
        d for order_id, d in result.decisions.items()
        if gt_by_order[order_id].get("is_adversarial") and gt_by_order[order_id]["archetype"] == "fee_mismatch"
    ]
    assert len(adversarial_fee_cases) > 0, "GOLDEN-002: no adversarial fee_mismatch case found"
    for case in adversarial_fee_cases:
        assert case.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE, (
            f"GOLDEN-002: adversarial fee_mismatch case {case.exception_id} was auto-resolved"
        )


def test_golden_003_ambiguous_match_always_reaches_human_review(full_pipeline_run):
    result = full_pipeline_run["result"]
    gt_by_order = _gt_by_order_id(full_pipeline_run["ground_truth"])

    case = next(
        (d for order_id, d in result.decisions.items() if gt_by_order[order_id]["archetype"] == "ambiguous_match"), None,
    )
    assert case is not None, "GOLDEN-003: no ambiguous_match case found"
    assert case.policy_decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-AMBIG-001" in case.policy_decision.rules_passed


def test_golden_004_high_risk_case_requires_approval(full_pipeline_run):
    result = full_pipeline_run["result"]

    case = next(
        (d for d in result.decisions.values() if d.policy_decision.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)), None,
    )
    assert case is not None, "GOLDEN-004: no HIGH/CRITICAL risk case found"
    assert case.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
    assert case.policy_decision.required_approval is True


def test_golden_005_contradicted_ai_hypothesis_cannot_force_resolution(full_pipeline_run):
    result = full_pipeline_run["result"]

    case = next(
        (d for d in result.decisions.values() if any(c.status == "CONTRADICTED" for c in d.contradiction_records)), None,
    )
    assert case is not None, "GOLDEN-005: no contradicted-hypothesis case found"
    assert case.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE, (
        "GOLDEN-005: AI hypothesis was contradicted by the verifier but the exception still auto-resolved"
    )
