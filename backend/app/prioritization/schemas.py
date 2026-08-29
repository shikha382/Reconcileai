"""Milestone 11's canonical prioritization contract. An OPERATIONAL layer,
not a second decision engine -- every field here is read from an
already-computed M3/M5/M6/M10 object (`PriorityAssessment`/`SLAAssessment`
from `app.policy.risk`, `DecisionResult` from M6, `ExplanationReport` from
M10). This module invents no financial facts and recomputes no risk, no
policy, and no verification -- see `app.prioritization.scorer` for the
read-only assembly logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --- Priority hierarchy (Phase 4) --------------------------------------------
# Maps directly onto `app.policy.risk.PriorityAssessment.priority_level`
# (CRITICAL/HIGH/MEDIUM/LOW, M5, reused verbatim -- not reinvented here).
PRIORITY_LEVEL_TO_CODE = {"CRITICAL": "P0", "HIGH": "P1", "MEDIUM": "P2", "LOW": "P3"}
PRIORITY_CODE_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}  # lower rank sorts first


# --- Reason codes (Phase 5) --------------------------------------------------
# Only codes actually backed by a real, already-computed signal. Each is
# documented at the point it's assigned in app.prioritization.scorer.
class ReasonCode:
    HIGH_EXPOSURE = "HIGH_EXPOSURE"
    CRITICAL_RISK = "CRITICAL_RISK"
    SLA_BREACHED = "SLA_BREACHED"
    SLA_AT_RISK = "SLA_AT_RISK"
    OLD_EXCEPTION = "OLD_EXCEPTION"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    AUTO_RESOLUTION_BLOCKED = "AUTO_RESOLUTION_BLOCKED"
    HIGH_VALUE_REFUND = "HIGH_VALUE_REFUND"
    UNRESOLVED_FINANCIAL_DIFFERENCE = "UNRESOLVED_FINANCIAL_DIFFERENCE"
    CLEAN_LOW_PRIORITY = "CLEAN_LOW_PRIORITY"  # the honest "nothing wrong" reason for a P3 auto-resolved case


# --- Recommended next action (Phase 6) ---------------------------------------
# Advisory only. Never executed, never approves, never mutates anything --
# see app.prioritization.scorer.recommend_action's own docstring.
class RecommendedAction:
    REVIEW_EVIDENCE = "REVIEW_EVIDENCE"
    VERIFY_SETTLEMENT = "VERIFY_SETTLEMENT"
    CHECK_FEE_RULE = "CHECK_FEE_RULE"
    INVESTIGATE_REFUND = "INVESTIGATE_REFUND"
    REQUEST_MISSING_EVIDENCE = "REQUEST_MISSING_EVIDENCE"
    ESCALATE_FINANCE_CONTROLLER = "ESCALATE_FINANCE_CONTROLLER"
    NONE_REQUIRED = "NONE_REQUIRED"  # a clean, already auto-resolved case needs no human action


@dataclass
class PrioritizedException:
    exception_id: str
    order_id: str
    payment_id: str
    priority: str  # "P0" | "P1" | "P2" | "P3"
    priority_score: str  # Decimal-as-string -- ranking input only, never an authoritative financial value
    risk_level: str
    risk_score: str
    financial_exposure: str
    currency: str
    age_days: int
    sla_status: str
    exception_category: str | None
    decision_status: str
    contradiction_count: int
    missing_evidence_count: int
    recommended_action: str
    reason_codes: list[str] = field(default_factory=list)
    explanation_reference: str | None = None  # exception_id -- the key GET /exceptions/{id}/explanation takes
    provenance_reference: str | None = None  # correlation_id -- the key GET /exceptions/{id}/provenance takes

    def to_dict(self) -> dict:
        return {
            "exception_id": self.exception_id, "order_id": self.order_id, "payment_id": self.payment_id,
            "priority": self.priority, "priority_score": self.priority_score, "risk_level": self.risk_level,
            "risk_score": self.risk_score, "financial_exposure": self.financial_exposure, "currency": self.currency,
            "age_days": self.age_days, "sla_status": self.sla_status, "exception_category": self.exception_category,
            "decision_status": self.decision_status, "contradiction_count": self.contradiction_count,
            "missing_evidence_count": self.missing_evidence_count, "recommended_action": self.recommended_action,
            "reason_codes": self.reason_codes, "explanation_reference": self.explanation_reference,
            "provenance_reference": self.provenance_reference,
        }


@dataclass
class QueueSummary:
    total: int
    counts_by_priority: dict[str, int]
    total_financial_exposure: str
    sla_breached_count: int
    sla_at_risk_count: int
    highest_exposure_exception_id: str | None
    most_common_category: str | None

    def to_dict(self) -> dict:
        return {
            "total": self.total, "counts_by_priority": self.counts_by_priority,
            "total_financial_exposure": self.total_financial_exposure, "sla_breached_count": self.sla_breached_count,
            "sla_at_risk_count": self.sla_at_risk_count,
            "highest_exposure_exception_id": self.highest_exposure_exception_id,
            "most_common_category": self.most_common_category,
        }
