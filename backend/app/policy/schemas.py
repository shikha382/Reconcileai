"""Milestone 5 schemas: the control layer between AI investigation and any
notion of "resolved". Every enum here is closed (no free-form strings) so a
decision can always be explained by which named value fired, never by prose
alone. Field names follow docs/data-model.md's original Decision/Approval/
AuditEvent sketch where applicable, extended with the richer decision/state
vocabulary this milestone's brief requires.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4


# --- Policy decision -------------------------------------------------------

class PolicyDecisionType(str, Enum):
    SAFE_TO_RESOLVE = "SAFE_TO_RESOLVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    UNRESOLVED = "UNRESOLVED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SLAStatus(str, Enum):
    WITHIN_SLA = "WITHIN_SLA"
    AT_RISK = "AT_RISK"
    BREACHED = "BREACHED"


class ResolutionType(str, Enum):
    """Closed set. Deliberately excludes anything like EXECUTE_ARBITRARY_UPDATE."""
    MARK_RECONCILED = "MARK_RECONCILED"
    LINK_RECORDS = "LINK_RECORDS"
    CLASSIFY_EXCEPTION = "CLASSIFY_EXCEPTION"
    REQUEST_HUMAN_REVIEW = "REQUEST_HUMAN_REVIEW"
    ESCALATE = "ESCALATE"
    NO_ACTION = "NO_ACTION"


@dataclass
class PolicyInput:
    """Everything the PolicyEngine is allowed to look at. Built once per
    exception from M2/M3/M4's own already-computed outputs -- never
    re-derived here, and never populated from anything the AI itself
    asserted about safety (its `confidence`/`recommended_action` are carried
    for audit only, see `ai_confidence`)."""
    exception_id: str
    exception_type: str | None  # ExceptionCategory value, or None for a clean match
    verifier_status: str  # RootCauseResult.status: VERIFIED/PARTIALLY_EXPLAINED/UNEXPLAINED/CONTRADICTED/AMBIGUOUS
    residual_amount: Decimal
    financial_exposure: Decimal
    ai_confidence: float | None  # advisory only -- never read by any rule
    evidence_complete: bool
    conflicting_evidence: bool
    ambiguous: bool
    risk_score: Decimal
    risk_level: RiskLevel
    auto_resolution_eligible_category: bool  # False for categories policy always blocks (duplicate, reversed_transaction, ...)
    currency: str = "INR"


@dataclass
class PolicyDecision:
    decision: PolicyDecisionType
    policy_id: str
    policy_version: str
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    required_approval: bool = False
    risk_level: RiskLevel = RiskLevel.LOW
    resolution_type: ResolutionType = ResolutionType.NO_ACTION
    rules_evaluated: list[str] = field(default_factory=list)
    rules_passed: list[str] = field(default_factory=list)
    rules_failed: list[str] = field(default_factory=list)
    input_hash: str = ""
    evaluated_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value, "policy_id": self.policy_id, "policy_version": self.policy_version,
            "reasons": self.reasons, "blocked_reasons": self.blocked_reasons,
            "required_approval": self.required_approval, "risk_level": self.risk_level.value,
            "resolution_type": self.resolution_type.value, "rules_evaluated": self.rules_evaluated,
            "rules_passed": self.rules_passed, "rules_failed": self.rules_failed,
            "input_hash": self.input_hash,
            "evaluated_at": self.evaluated_at.isoformat() if self.evaluated_at else None,
        }


# --- Resolution proposal ---------------------------------------------------

@dataclass
class ResolutionProposal:
    exception_id: str
    resolution_type: ResolutionType
    reason: str
    evidence_ids: list[str]
    verified: bool
    financial_impact: Decimal
    requires_approval: bool
    proposal_id: str = field(default_factory=lambda: f"PROP-{uuid4().hex[:10]}")

    def to_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id, "exception_id": self.exception_id,
            "resolution_type": self.resolution_type.value, "reason": self.reason,
            "evidence_ids": self.evidence_ids, "verified": self.verified,
            "financial_impact": str(self.financial_impact), "requires_approval": self.requires_approval,
        }


# --- Human approval workflow -----------------------------------------------

class ReviewState(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ReviewDecisionType(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_MORE_EVIDENCE = "REQUEST_MORE_EVIDENCE"


class ReasonCode(str, Enum):
    VERIFIED_EVIDENCE = "VERIFIED_EVIDENCE"
    FINANCIAL_RISK = "FINANCIAL_RISK"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    POLICY_BLOCK = "POLICY_BLOCK"
    INCORRECT_PROPOSAL = "INCORRECT_PROPOSAL"
    DUPLICATE = "DUPLICATE"
    OTHER = "OTHER"


@dataclass
class ApprovalDecision:
    decision: ReviewDecisionType
    reason_code: ReasonCode
    reviewer_id: str
    comment: str = ""
    decided_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value, "reason_code": self.reason_code.value,
            "reviewer_id": self.reviewer_id, "comment": self.comment,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
        }


@dataclass
class ReviewRequest:
    exception_id: str
    financial_impact: Decimal
    evidence_ids: list[str]
    proposed_resolution: ResolutionProposal
    policy_decision: PolicyDecision
    risk_level: RiskLevel
    created_by: str  # maker (actor id, e.g. "system" or an AI/human identity placeholder)
    ai_hypothesis_summary: dict | None = None
    verifier_result_summary: dict | None = None
    rejected_alternatives: list[dict] = field(default_factory=list)
    review_id: str = field(default_factory=lambda: f"REV-{uuid4().hex[:10]}")
    state: ReviewState = ReviewState.PENDING_REVIEW
    created_at: datetime | None = None
    expiry_at: datetime | None = None
    dual_control_required: bool = False
    decisions: list[ApprovalDecision] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id, "exception_id": self.exception_id, "state": self.state.value,
            "financial_impact": str(self.financial_impact), "evidence_ids": self.evidence_ids,
            "ai_hypothesis_summary": self.ai_hypothesis_summary, "verifier_result_summary": self.verifier_result_summary,
            "rejected_alternatives": self.rejected_alternatives, "proposed_resolution": self.proposed_resolution.to_dict(),
            "policy_decision": self.policy_decision.to_dict(), "risk_level": self.risk_level.value,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expiry_at": self.expiry_at.isoformat() if self.expiry_at else None,
            "dual_control_required": self.dual_control_required,
            "decisions": [d.to_dict() for d in self.decisions],
        }


# --- Actor model / authorization --------------------------------------------

class ActorType(str, Enum):
    SYSTEM = "SYSTEM"
    AI = "AI"
    HUMAN = "HUMAN"
    POLICY_ENGINE = "POLICY_ENGINE"
    VERIFIER = "VERIFIER"


class Capability(str, Enum):
    VIEW_EXCEPTION = "VIEW_EXCEPTION"
    INVESTIGATE = "INVESTIGATE"
    PROPOSE_RESOLUTION = "PROPOSE_RESOLUTION"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"
    CHANGE_POLICY = "CHANGE_POLICY"
    # M6 audit capabilities. Deliberately no UPDATE_AUDIT/DELETE_AUDIT value
    # exists at all -- not merely "unauthorized for everyone", structurally
    # absent, since app.audit.ledger.AuditLedger has no update/delete method
    # for any capability check to even gate.
    VIEW_AUDIT = "VIEW_AUDIT"
    VERIFY_AUDIT = "VERIFY_AUDIT"
    APPEND_AUDIT = "APPEND_AUDIT"
    # M8 API-boundary capabilities -- gate what an HTTP caller may do, mirroring
    # the exact pattern M6 used for its 3 audit capabilities above. There is
    # deliberately no FORCE_RESOLVE/BYPASS_POLICY value: the API has nothing
    # for such a capability to gate (see app.api.routes.runs/exceptions --
    # no route accepts or writes a caller-supplied decision/resolution).
    VIEW_RUN = "VIEW_RUN"
    VIEW_PROVENANCE = "VIEW_PROVENANCE"
    START_RECONCILIATION = "START_RECONCILIATION"


@dataclass
class Actor:
    actor_type: ActorType
    actor_id: str


# --- Exception lifecycle state machine --------------------------------------

class ExceptionState(str, Enum):
    EXCEPTION_OPEN = "EXCEPTION_OPEN"
    INVESTIGATING = "INVESTIGATING"
    PROPOSAL_READY = "PROPOSAL_READY"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    AUTO_RESOLVE = "AUTO_RESOLVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    BLOCKED = "BLOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"


# --- Audit events (structure only -- not persisted/hash-chained in M5) -----

class AuditEventType(str, Enum):
    EXCEPTION_CREATED = "EXCEPTION_CREATED"
    AI_INVESTIGATION_COMPLETED = "AI_INVESTIGATION_COMPLETED"
    HYPOTHESIS_VERIFIED = "HYPOTHESIS_VERIFIED"
    HYPOTHESIS_REJECTED = "HYPOTHESIS_REJECTED"
    POLICY_EVALUATED = "POLICY_EVALUATED"
    RESOLUTION_PROPOSED = "RESOLUTION_PROPOSED"
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    REVIEW_REJECTED = "REVIEW_REJECTED"
    RESOLUTION_BLOCKED = "RESOLUTION_BLOCKED"


@dataclass
class AuditEvent:
    event_type: AuditEventType
    entity_id: str
    actor_type: ActorType
    source: str
    payload: dict
    correlation_id: str
    actor_id: str | None = None
    event_id: str = field(default_factory=lambda: f"EVT-{uuid4().hex[:12]}")
    timestamp: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id, "event_type": self.event_type.value, "entity_id": self.entity_id,
            "actor_type": self.actor_type.value, "actor_id": self.actor_id, "source": self.source,
            "payload": self.payload, "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
