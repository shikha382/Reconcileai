"""Assembles the structured review packet a future UI can render directly,
without recomputing any business logic -- everything here is already-
computed M2/M3/M4/M5 output, reassembled into one JSON-serializable shape.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.engines.evidence.bundle import EvidenceBundle
from app.policy.risk import PriorityAssessment, SLAAssessment
from app.policy.schemas import PolicyDecision, ResolutionProposal


@dataclass
class ReviewPacket:
    exception: dict
    financial_summary: dict
    ai_summary: dict | None
    evidence: list[dict]
    negative_evidence: dict
    hypotheses: list[dict]
    policy: dict
    risk: dict
    proposal: dict

    def to_dict(self) -> dict:
        return {
            "exception": self.exception, "financial_summary": self.financial_summary,
            "ai_summary": self.ai_summary, "evidence": self.evidence, "negative_evidence": self.negative_evidence,
            "hypotheses": self.hypotheses, "policy": self.policy, "risk": self.risk, "proposal": self.proposal,
        }


def build_review_packet(
    bundle: EvidenceBundle, policy_decision: PolicyDecision, proposal: ResolutionProposal,
    priority: PriorityAssessment, sla: SLAAssessment, ai_summary: dict | None = None,
) -> ReviewPacket:
    return ReviewPacket(
        exception={
            "exception_id": bundle.exception_id, "payment_id": bundle.payment_id, "order_id": bundle.order_id,
            "category": bundle.category, "reconciliation_status": bundle.reconciliation_status,
        },
        financial_summary=bundle.financial_exposure.to_dict(),
        ai_summary=ai_summary,
        evidence=[c.to_dict() if hasattr(c, "to_dict") else c for c in [bundle.connected_records]],
        negative_evidence=bundle.negative_evidence_report.to_dict(),
        hypotheses=[h.to_dict() for h in bundle.root_cause.hypotheses],
        policy=policy_decision.to_dict(),
        risk={
            "risk_score": str(bundle.risk_score), "priority_score": str(priority.priority_score),
            "priority_level": priority.priority_level, "priority_reasons": priority.priority_reasons,
            "sla_status": sla.sla_status.value, "age_days": sla.age_days,
            "due_at": sla.due_at.isoformat(), "created_at": sla.created_at.isoformat(),
        },
        proposal=proposal.to_dict(),
    )
