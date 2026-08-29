"""Milestone 5 orchestrator: wires M3's EvidenceBundle (+ M4's optional AI
investigation) into PolicyInput -> PolicyEngine -> ResolutionProposal ->
(if required) a ReviewRequest. No financial mutation happens anywhere in
this module -- it only produces a proposal, a policy decision, and (for
review cases) a workflow record.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.ai.policy import NEVER_AUTO_RESOLVE_CATEGORIES as AI_NEVER_AUTO_RESOLVE_CATEGORIES
from app.engines.evidence.bundle import EvidenceBundle
from app.policy.approval import ApprovalWorkflowStore
from app.policy.engine import evaluate_policy
from app.policy.risk import assess_priority, assess_sla, risk_level_for_score
from app.policy.schemas import PolicyDecisionType, PolicyInput, ResolutionProposal, ResolutionType, ReviewRequest

# Categories the classifier (app.engines.exceptions.classifier) can assign
# that are policy-blocked from auto-resolution regardless of verification
# certainty -- the same categorical rule M4's AI-hypothesis policy already
# enforces (app.ai.policy.NEVER_AUTO_RESOLVE_CATEGORIES), extended with the
# category-level equivalents of M4's NEVER_AUTO_RESOLVE_TYPES so a
# non-AI-assisted exception is held to the identical bar.
#
# `missing_transaction` is deliberately EXCLUDED from this set: it is not a
# "needs human review" category, it's a "genuinely nothing exists yet"
# category, which app.policy.engine.evaluate_policy's own UNRESOLVED
# fallback handles distinctly (ground_truth.expected_action agrees:
# `unresolved`, not `human_review`, for this specific archetype). Routing it
# through this set instead would have collapsed a real, meaningful
# five-way outcome distinction down to the old three-way one.
NEVER_AUTO_RESOLVE_CATEGORIES = AI_NEVER_AUTO_RESOLVE_CATEGORIES | {
    "ambiguous_match", "partial_settlement", "unexplained_difference",
}


def build_policy_input(bundle: EvidenceBundle, ai_confidence: float | None = None) -> PolicyInput:
    root_cause = bundle.root_cause
    risk_score = bundle.risk_score
    return PolicyInput(
        exception_id=bundle.exception_id,
        exception_type=bundle.category,
        verifier_status=root_cause.status,
        residual_amount=root_cause.unexplained_amount,
        financial_exposure=bundle.financial_exposure.gross_amount,
        ai_confidence=ai_confidence,
        evidence_complete=True,  # M3 always assembles a full bundle for every exception in this pipeline
        conflicting_evidence=(root_cause.status == "CONTRADICTED"),
        ambiguous=(root_cause.status == "AMBIGUOUS"),
        risk_score=risk_score,
        risk_level=risk_level_for_score(risk_score),
        auto_resolution_eligible_category=(bundle.category not in NEVER_AUTO_RESOLVE_CATEGORIES),
        currency=bundle.financial_exposure.currency,
    )


def build_resolution_proposal(bundle: EvidenceBundle, policy_decision) -> ResolutionProposal:
    resolution_type = policy_decision.resolution_type
    verified = policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE
    reason = "; ".join(policy_decision.reasons) or "; ".join(policy_decision.blocked_reasons) or "no rule fired"
    return ResolutionProposal(
        exception_id=bundle.exception_id, resolution_type=resolution_type, reason=reason,
        evidence_ids=[bundle.exception_id], verified=verified,
        financial_impact=bundle.root_cause.unexplained_amount, requires_approval=policy_decision.required_approval,
    )


def resolve_exception(
    bundle: EvidenceBundle, payment, reference_now: datetime, store: ApprovalWorkflowStore | None = None,
    ai_confidence: float | None = None, created_by: str = "system",
) -> tuple[PolicyInput, object, ResolutionProposal, ReviewRequest | None]:
    """Full M5 pipeline for one exception: schema-valid inputs are
    guaranteed by construction (PolicyInput/ResolutionProposal are
    dataclasses); evidence validation is M3's own bundle; deterministic
    verification is already baked into `bundle.root_cause`; policy + risk
    are evaluated here; approval-requirement routing produces a
    ReviewRequest only when required."""
    policy_input = build_policy_input(bundle, ai_confidence)
    policy_decision = evaluate_policy(policy_input)
    proposal = build_resolution_proposal(bundle, policy_decision)

    rejected_alternatives = [
        {"settlement_id": c.settlement_id, "verdict": c.verdict, "score": str(c.score),
         "negative_evidence": [e.to_dict() for e in c.negative_evidence]}
        for c in bundle.negative_evidence_report.candidates if c.verdict == "REJECTED"
    ]

    review = None
    if policy_decision.required_approval and store is not None:
        review = store.create_review_request(
            bundle.exception_id, proposal, policy_decision, created_by,
            rejected_alternatives=rejected_alternatives, reference_now=reference_now,
        )

    return policy_input, policy_decision, proposal, review
