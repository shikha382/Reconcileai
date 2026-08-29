"""Human approval workflow. Approval changes WORKFLOW STATE only -- nothing
here mutates a financial record (M5's explicit boundary).

Persistence note: kept as a small in-memory store for this milestone
(`ApprovalWorkflowStore`), mirroring how M4's investigation state was pure
Python with no DB dependency. A `ReviewRequest`/`ApprovalDecision` DB model
is deferred (see PROJECT_PLAN.md's M5 note) -- this proves the state
machine, dual-control, and idempotency logic correctly; swapping in
persistence later does not change any of the logic below.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from app.policy.authorization import AuthorizationError, is_authorized
from app.policy.schemas import (
    Actor,
    ActorType,
    ApprovalDecision,
    Capability,
    PolicyDecision,
    ReasonCode,
    ResolutionProposal,
    ReviewDecisionType,
    ReviewRequest,
    ReviewState,
    RiskLevel,
)
DEFAULT_REVIEW_EXPIRY_HOURS = 72
# Dual control ("maker != checker") is required for any review whose risk
# level is at least this severe -- a policy option per the brief's dual
# control section, expressed as one clear, documented threshold rather than
# scattered conditionals.
DUAL_CONTROL_RISK_LEVELS = (RiskLevel.HIGH, RiskLevel.CRITICAL)


def review_idempotency_key(exception_id: str, proposal_id: str, policy_version: str) -> str:
    raw = f"{exception_id}|{proposal_id}|{policy_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


class ApprovalWorkflowStore:
    """In-memory registry keyed by idempotency key -- creating a review
    request twice for the same (exception, proposal, policy_version) never
    produces two PENDING_REVIEW records."""

    def __init__(self) -> None:
        self._reviews_by_key: dict[str, ReviewRequest] = {}

    def create_review_request(
        self, exception_id: str, proposal: ResolutionProposal, policy_decision: PolicyDecision,
        created_by: str, *, ai_hypothesis_summary: dict | None = None, verifier_result_summary: dict | None = None,
        rejected_alternatives: list[dict] | None = None, reference_now: datetime | None = None,
        expiry_hours: int = DEFAULT_REVIEW_EXPIRY_HOURS,
    ) -> ReviewRequest:
        key = review_idempotency_key(exception_id, proposal.proposal_id, policy_decision.policy_version)
        if key in self._reviews_by_key:
            return self._reviews_by_key[key]  # idempotent: return the existing request, don't create a duplicate

        now = reference_now or datetime.now(timezone.utc).replace(tzinfo=None)
        review = ReviewRequest(
            exception_id=exception_id, financial_impact=proposal.financial_impact,
            evidence_ids=proposal.evidence_ids, proposed_resolution=proposal, policy_decision=policy_decision,
            risk_level=policy_decision.risk_level, created_by=created_by,
            ai_hypothesis_summary=ai_hypothesis_summary, verifier_result_summary=verifier_result_summary,
            rejected_alternatives=rejected_alternatives or [], created_at=now,
            expiry_at=now + timedelta(hours=expiry_hours),
            dual_control_required=policy_decision.risk_level in DUAL_CONTROL_RISK_LEVELS,
        )
        self._reviews_by_key[key] = review
        return review

    def get(self, review_id: str) -> ReviewRequest | None:
        for review in self._reviews_by_key.values():
            if review.review_id == review_id:
                return review
        return None

    def expire_overdue(self, reference_now: datetime) -> list[ReviewRequest]:
        expired = []
        for review in self._reviews_by_key.values():
            if review.state == ReviewState.PENDING_REVIEW and review.expiry_at and reference_now > review.expiry_at:
                review.state = ReviewState.EXPIRED
                expired.append(review)
        return expired


def submit_review_decision(
    review: ReviewRequest, actor: Actor, decision: ReviewDecisionType, reason_code: ReasonCode,
    comment: str = "", *, reference_now: datetime | None = None,
) -> ApprovalDecision:
    """Applies a human review decision. Enforces authorization, dual
    control, idempotency (a repeat decision on an already-terminal review is
    a no-op, not a duplicate state transition), and valid state transitions."""
    now = reference_now or datetime.now(timezone.utc).replace(tzinfo=None)

    required_capability = {
        ReviewDecisionType.APPROVE: Capability.APPROVE,
        ReviewDecisionType.REJECT: Capability.REJECT,
        ReviewDecisionType.REQUEST_MORE_EVIDENCE: Capability.REJECT,  # same capability tier as reject: a reviewer action, not an approval
    }[decision]
    if not is_authorized(actor, required_capability):
        raise AuthorizationError(f"actor {actor.actor_type.value}:{actor.actor_id} is not authorized to {decision.value}")

    # Idempotency: a review already in a terminal state is not re-transitioned.
    if review.state != ReviewState.PENDING_REVIEW:
        return ApprovalDecision(decision=decision, reason_code=reason_code, reviewer_id=actor.actor_id, comment=f"no-op: review already {review.state.value}", decided_at=now)

    # Dual control: maker cannot check their own high-risk proposal.
    if decision == ReviewDecisionType.APPROVE and review.dual_control_required and actor.actor_id == review.created_by:
        raise AuthorizationError(
            f"dual control required: actor {actor.actor_id} created this proposal and cannot also approve it"
        )

    approval = ApprovalDecision(decision=decision, reason_code=reason_code, reviewer_id=actor.actor_id, comment=comment, decided_at=now)
    review.decisions.append(approval)

    if decision == ReviewDecisionType.APPROVE:
        review.state = ReviewState.APPROVED
    elif decision == ReviewDecisionType.REJECT:
        review.state = ReviewState.REJECTED
    # REQUEST_MORE_EVIDENCE leaves the review PENDING_REVIEW -- it's a
    # request, not a terminal decision.

    return approval


def cancel_review(review: ReviewRequest, actor: Actor) -> None:
    if review.state == ReviewState.PENDING_REVIEW:
        review.state = ReviewState.CANCELLED
