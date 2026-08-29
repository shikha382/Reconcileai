"""M5 test builders."""
from __future__ import annotations

from decimal import Decimal

from app.policy.schemas import PolicyInput, RiskLevel


def make_policy_input(
    exception_id="EXC-1", exception_type="fee_mismatch", verifier_status="VERIFIED",
    residual_amount="0.00", financial_exposure="1000.00", ai_confidence=0.9,
    evidence_complete=True, conflicting_evidence=False, ambiguous=False,
    risk_score="0.00", risk_level=RiskLevel.LOW, auto_resolution_eligible_category=True,
) -> PolicyInput:
    return PolicyInput(
        exception_id=exception_id, exception_type=exception_type, verifier_status=verifier_status,
        residual_amount=Decimal(residual_amount), financial_exposure=Decimal(financial_exposure),
        ai_confidence=ai_confidence, evidence_complete=evidence_complete,
        conflicting_evidence=conflicting_evidence, ambiguous=ambiguous,
        risk_score=Decimal(risk_score), risk_level=risk_level,
        auto_resolution_eligible_category=auto_resolution_eligible_category,
    )
