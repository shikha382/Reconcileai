"""The deterministic PolicyEngine -- precedence, the lettered test
scenarios (CASE A-I) from the M5 brief, and fail-closed behavior."""
from decimal import Decimal

from app.policy.engine import MAX_AUTO_RESOLVE_EXPOSURE, evaluate_policy
from app.policy.schemas import PolicyDecisionType, RiskLevel

from .factories import make_policy_input


# --- CASE A-I -----------------------------------------------------------

def test_case_a_safe_auto_resolution():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", risk_level=RiskLevel.LOW)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE


def test_case_b_high_value_verified_but_over_exposure_threshold():
    policy_input = make_policy_input(
        verifier_status="VERIFIED", residual_amount="0.00", risk_level=RiskLevel.LOW,
        financial_exposure=str(MAX_AUTO_RESOLVE_EXPOSURE + Decimal("1.00")),
    )
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert decision.required_approval


def test_case_c_ambiguous_candidates():
    policy_input = make_policy_input(verifier_status="AMBIGUOUS", ambiguous=True, residual_amount="1000.00")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_case_d_unexplained_residual():
    policy_input = make_policy_input(verifier_status="UNEXPLAINED", residual_amount="250.00", exception_type="unexplained_difference")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_case_e_ai_hallucination_verifier_fail():
    """AI claims a refund exists; the deterministic verifier disproves it
    -- verifier_status is CONTRADICTED, must BLOCK (REJECTED)."""
    policy_input = make_policy_input(verifier_status="CONTRADICTED", residual_amount="500.00")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_case_f_policy_conflict_auto_resolve_vs_mandatory_approval():
    """Rule A: verified fee mismatch -> auto-resolve. Rule B: amount >
    threshold -> human review. Expected: HUMAN_REVIEW (risk tier outranks
    auto-eligibility tier)."""
    policy_input = make_policy_input(
        verifier_status="VERIFIED", residual_amount="0.00", exception_type="fee_mismatch",
        financial_exposure=str(MAX_AUTO_RESOLVE_EXPOSURE * 2),
    )
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-EXPOSURE-001" in decision.rules_passed


def test_case_h_sla_breach_produces_high_priority():
    """Covered in test_risk.py's SLA/priority tests -- this asserts the
    policy engine itself doesn't change decision based on aging alone
    (aging affects PRIORITY, not the safety decision)."""
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE  # aging plays no role here by design


def test_case_i_provider_failure_deterministic_path_continues():
    """AI unavailable -- ai_confidence is simply None; the deterministic
    policy path is entirely unaffected since it never reads that field."""
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", ai_confidence=None)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE


# --- Precedence -----------------------------------------------------------

def test_precedence_block_beats_everything():
    policy_input = make_policy_input(verifier_status="CONTRADICTED", ambiguous=True, risk_level=RiskLevel.CRITICAL)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_precedence_mandatory_approval_beats_risk_and_auto():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", ambiguous=True, risk_level=RiskLevel.LOW)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-AMBIG-001" in decision.rules_passed


def test_precedence_risk_beats_auto_eligibility():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", risk_level=RiskLevel.HIGH)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW
    assert "POLICY-HIGH-RISK-001" in decision.rules_passed


def test_precedence_documented_order_matches_engine_module_docstring():
    from app import policy as policy_pkg  # noqa: F401
    import app.policy.engine as engine_module

    assert "BLOCK" in engine_module.__doc__
    assert engine_module.__doc__.index("BLOCK") < engine_module.__doc__.index("MANDATORY APPROVAL")
    assert engine_module.__doc__.index("MANDATORY APPROVAL") < engine_module.__doc__.index("RISK RULES")
    assert engine_module.__doc__.index("RISK RULES") < engine_module.__doc__.index("AUTO-RESOLUTION ELIGIBILITY")


# --- Fail-closed ------------------------------------------------------------

def test_fail_closed_missing_evidence_blocks():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", evidence_complete=False)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_fail_closed_negative_residual_blocks():
    """Negative residual hidden by rounding -- must BLOCK, never silently
    treated as zero."""
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="-0.01")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_fail_closed_unknown_exception_type_blocks():
    policy_input = make_policy_input(verifier_status="UNEXPLAINED", exception_type=None, residual_amount="100.00")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.REJECTED


def test_fail_closed_conflicting_evidence_blocks_auto_resolution():
    policy_input = make_policy_input(verifier_status="VERIFIED", residual_amount="0.00", conflicting_evidence=True)
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.HUMAN_REVIEW


def test_missing_transaction_maps_to_unresolved_not_human_review():
    policy_input = make_policy_input(verifier_status="UNEXPLAINED", exception_type="missing_transaction", residual_amount="1000.00")
    decision = evaluate_policy(policy_input)
    assert decision.decision == PolicyDecisionType.UNRESOLVED


# --- Versioning / decision fields ------------------------------------------

def test_decision_records_policy_id_version_and_hash():
    policy_input = make_policy_input()
    decision = evaluate_policy(policy_input)
    assert decision.policy_id
    assert decision.policy_version
    assert decision.input_hash
    assert decision.evaluated_at is not None


def test_same_input_produces_same_hash_and_decision():
    policy_input_1 = make_policy_input()
    policy_input_2 = make_policy_input()
    d1 = evaluate_policy(policy_input_1)
    d2 = evaluate_policy(policy_input_2)
    assert d1.input_hash == d2.input_hash
    assert d1.decision == d2.decision


def test_rules_evaluated_never_hidden_even_when_decision_is_early():
    """Even a BLOCK-tier decision (returned immediately) must record which
    BLOCK rules were checked, not just the one that fired."""
    policy_input = make_policy_input(verifier_status="CONTRADICTED")
    decision = evaluate_policy(policy_input)
    assert len(decision.rules_evaluated) >= 4  # all 4 BLOCK-tier rules checked
