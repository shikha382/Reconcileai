"""Decision provenance reconstruction. Given only an exception_id (and the
audit ledger), reproduce the full story -- a future UI renders this
directly, it never recomputes any business logic itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.audit.ledger import AuditLedger
from app.audit.verify import verify_chain
from shared.money import loads


@dataclass
class TimelineEntry:
    timestamp: str
    event_type: str
    actor_type: str
    actor_id: str | None
    payload: dict


@dataclass
class DecisionProvenance:
    exception_id: str
    correlation_id: str | None
    timeline: list[TimelineEntry] = field(default_factory=list)
    ai_hypotheses: list[dict] = field(default_factory=list)
    contradictions: list[dict] = field(default_factory=list)
    policy_evaluation: dict | None = None
    resolution_proposal: dict | None = None
    review: dict | None = None
    audit_chain_valid: bool = True
    audit_events_checked: int = 0

    def to_dict(self) -> dict:
        return {
            "exception_id": self.exception_id, "correlation_id": self.correlation_id,
            "timeline": [
                {"timestamp": e.timestamp, "event_type": e.event_type, "actor_type": e.actor_type,
                 "actor_id": e.actor_id, "payload": e.payload}
                for e in self.timeline
            ],
            "ai_hypotheses": self.ai_hypotheses, "contradictions": self.contradictions,
            "policy_evaluation": self.policy_evaluation, "resolution_proposal": self.resolution_proposal,
            "review": self.review, "audit_chain_valid": self.audit_chain_valid,
            "audit_events_checked": self.audit_events_checked,
        }


def get_decision_provenance(session: Session, exception_id: str) -> DecisionProvenance:
    ledger = AuditLedger(session)
    events = ledger.events_for_entity(exception_id)

    correlation_id = events[0].correlation_id if events else None
    timeline: list[TimelineEntry] = []
    ai_hypotheses: list[dict] = []
    contradictions: list[dict] = []
    policy_evaluation: dict | None = None
    resolution_proposal: dict | None = None
    review: dict | None = None

    for event in events:
        payload = loads(event.payload_json)
        timeline.append(TimelineEntry(
            timestamp=event.timestamp.isoformat(), event_type=event.event_type,
            actor_type=event.actor_type, actor_id=event.actor_id, payload=payload,
        ))
        if event.event_type == "HYPOTHESIS_CREATED":
            ai_hypotheses.append(payload)
        elif event.event_type in ("HYPOTHESIS_CHALLENGED", "CONTRADICTION_FOUND"):
            contradictions.append(payload)
        elif event.event_type == "POLICY_EVALUATED":
            policy_evaluation = payload
        elif event.event_type == "RESOLUTION_PROPOSED":
            resolution_proposal = payload
        elif event.event_type == "REVIEW_REQUESTED":
            review = payload

    chain_result = verify_chain(session)

    return DecisionProvenance(
        exception_id=exception_id, correlation_id=correlation_id, timeline=timeline,
        ai_hypotheses=ai_hypotheses, contradictions=contradictions, policy_evaluation=policy_evaluation,
        resolution_proposal=resolution_proposal, review=review,
        audit_chain_valid=chain_result.valid, audit_events_checked=chain_result.events_checked,
    )


def build_decision_summary(provenance: DecisionProvenance) -> dict:
    """Phase 14: one structured response answering every question the
    brief lists (why did it happen, what did AI believe, what contradicted
    it, what did policy decide, was approval required, is the chain valid)."""
    contradicted = [c for c in provenance.contradictions if c.get("status") == "CONTRADICTED"]
    return {
        "exception_id": provenance.exception_id,
        "ai_believed": [h.get("claim") for h in provenance.ai_hypotheses],
        "supporting_evidence": [c.get("supporting_evidence") for c in provenance.contradictions if c.get("status") == "SUPPORTED"],
        "contradicting_evidence": [c.get("contradicting_evidence") for c in contradicted],
        "verification_conclusion": "CONTRADICTED" if contradicted else ("VERIFIED" if provenance.ai_hypotheses else "NOT_NEEDED"),
        "policy_decision": provenance.policy_evaluation.get("decision") if provenance.policy_evaluation else None,
        "policy_id": provenance.policy_evaluation.get("policy_id") if provenance.policy_evaluation else None,
        "policy_version": provenance.policy_evaluation.get("policy_version") if provenance.policy_evaluation else None,
        "financial_exposure": provenance.resolution_proposal.get("financial_impact") if provenance.resolution_proposal else None,
        "approval_required": provenance.review is not None,
        "review_id": provenance.review.get("review_id") if provenance.review else None,
        "audit_chain_valid": provenance.audit_chain_valid,
        "audit_events_checked": provenance.audit_events_checked,
    }
