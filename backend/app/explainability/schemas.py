"""Milestone 10's canonical, structured explanation contract (Phase 2).

This is a READ/TRACE layer, not a second source of truth: every field here
is populated directly from an already-computed M2-M6 object
(`EvidenceBundle`, `RootCauseResult`, `NegativeEvidenceReport`,
`AIInvestigationResult`/`HypothesisOutcome`, `ContradictionRecord`,
`PolicyDecision`, `ResolutionProposal`, `ReviewRequest`) -- nothing here
recomputes a match, a fee, a risk score, or a policy decision. See
`app.explainability.builder.build_explanation` for the actual assembly
logic, which is where every field's provenance is documented at the point
of use.

Every dataclass carries a `to_dict()` (str-only Decimal/enum
serialization, matching the project-wide convention already used by
`ConstraintResult`, `PolicyDecision`, `ContradictionRecord`, etc.) so this
contract is both the internal shape and the JSON shape the API returns.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --- Evidence (Phase 3) -------------------------------------------------------

@dataclass
class EvidenceItem:
    """The atomic, structured evidence unit -- adapts M3's existing
    `ConstraintResult` (constraint/passed/expected/observed/delta/reason_code)
    rather than inventing a competing shape; every `EvidenceItem` here is
    built FROM a real `ConstraintResult`, `HypothesisResult`, or
    `ContradictionRecord`, never invented independently."""

    evidence_id: str
    evidence_type: str  # "constraint" | "hypothesis_verification" | "contradiction" | "audit_event"
    source_type: str  # "payment" | "settlement" | "bank_transaction" | "refund" | "fee_rule" | "audit_ledger"
    source_id: str
    field: str | None
    observed_value: str | None
    expected_value: str | None
    relationship: str | None
    status: str  # "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT_EVIDENCE" | "NOT_APPLICABLE"
    explanation: str
    severity: str  # "info" | "warning" | "critical"
    provenance_reference: str | None

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id, "evidence_type": self.evidence_type,
            "source_type": self.source_type, "source_id": self.source_id, "field": self.field,
            "observed_value": self.observed_value, "expected_value": self.expected_value,
            "relationship": self.relationship, "status": self.status, "explanation": self.explanation,
            "severity": self.severity, "provenance_reference": self.provenance_reference,
        }


# --- Financial summary / source records (Phase 2 items 3-4) ------------------

@dataclass
class FinancialSummary:
    currency: str
    gross_amount: str
    expected_amount: str
    observed_amount: str
    explained_amount: str
    unexplained_amount: str

    def to_dict(self) -> dict:
        return dict(
            currency=self.currency, gross_amount=self.gross_amount, expected_amount=self.expected_amount,
            observed_amount=self.observed_amount, explained_amount=self.explained_amount,
            unexplained_amount=self.unexplained_amount,
        )


@dataclass
class SourceRecordRefs:
    payment_id: str
    order_id: str
    settlement_ids: list[str] = field(default_factory=list)
    bank_transaction_ids: list[str] = field(default_factory=list)
    refund_ids: list[str] = field(default_factory=list)
    fee_rule_method: str | None = None

    def to_dict(self) -> dict:
        return dict(
            payment_id=self.payment_id, order_id=self.order_id, settlement_ids=self.settlement_ids,
            bank_transaction_ids=self.bank_transaction_ids, refund_ids=self.refund_ids,
            fee_rule_method=self.fee_rule_method,
        )


# --- Matching explanation (Phase 6) -------------------------------------------

@dataclass
class CandidateMatchEvidence:
    settlement_id: str
    verdict: str  # "ACCEPTED" | "REJECTED"
    score: str
    match_class: str  # "EXACT_MATCH" | "NORMALIZED_MATCH" | "FUZZY_CANDIDATE" | "REJECTED"
    positive_evidence: list[EvidenceItem] = field(default_factory=list)
    negative_evidence: list[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(
            settlement_id=self.settlement_id, verdict=self.verdict, score=self.score, match_class=self.match_class,
            positive_evidence=[e.to_dict() for e in self.positive_evidence],
            negative_evidence=[e.to_dict() for e in self.negative_evidence],
        )


@dataclass
class MatchingExplanation:
    match_status: str  # "EXACT_MATCH" | "NORMALIZED_MATCH" | "FUZZY_SCORED" | "AMBIGUOUS" | "REJECTED" | "UNMATCHED"
    accepted_settlement_id: str | None
    candidates: list[CandidateMatchEvidence] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(
            match_status=self.match_status, accepted_settlement_id=self.accepted_settlement_id,
            candidates=[c.to_dict() for c in self.candidates],
        )


# --- Calculation trace (Phase 5) ----------------------------------------------

@dataclass
class CalculationTrace:
    label: str  # e.g. "fee_verification", "discrepancy_decomposition"
    rule_id: str | None
    inputs: dict[str, str] = field(default_factory=dict)
    expected_value: str | None = None
    observed_value: str | None = None
    residual: str | None = None
    verification_result: str = "NOT_APPLICABLE"  # "PASSED" | "FAILED" | "NOT_APPLICABLE"

    def to_dict(self) -> dict:
        return dict(
            label=self.label, rule_id=self.rule_id, inputs=self.inputs, expected_value=self.expected_value,
            observed_value=self.observed_value, residual=self.residual, verification_result=self.verification_result,
        )


# --- AI hypothesis trace (Phase 7) --------------------------------------------

@dataclass
class AIHypothesisTrace:
    hypothesis_id: str
    hypothesis_type: str
    claim: str
    ai_confidence: float  # advisory ONLY -- see CONFIDENCE_DISCLAIMER; never authoritative
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    verification_result: str = "NOT_TESTED"  # "PASSED" | "FAILED" | "NOT_TESTED"
    verification_reason: str = ""
    final_disposition: str = "NOT_ACCEPTED"  # "ACCEPTED" | "REJECTED" | "NOT_ACCEPTED"

    def to_dict(self) -> dict:
        return dict(
            hypothesis_id=self.hypothesis_id, hypothesis_type=self.hypothesis_type, claim=self.claim,
            ai_confidence=self.ai_confidence, supporting_evidence=self.supporting_evidence,
            contradicting_evidence=self.contradicting_evidence, verification_result=self.verification_result,
            verification_reason=self.verification_reason, final_disposition=self.final_disposition,
        )


# --- Self-challenge trace (Phase 8) -------------------------------------------

@dataclass
class SelfChallengeTrace:
    hypothesis_id: str
    challenge_question: str
    counter_evidence: list[str]
    verification_result: str  # "SUPPORTED" | "CONTRADICTED" | "INSUFFICIENT_EVIDENCE"
    final_result: str  # human-readable, generated from the structured fields above, not a separate fact

    def to_dict(self) -> dict:
        return dict(
            hypothesis_id=self.hypothesis_id, challenge_question=self.challenge_question,
            counter_evidence=self.counter_evidence, verification_result=self.verification_result,
            final_result=self.final_result,
        )


# --- Policy / risk / resolution traces (Phases 9-11) --------------------------

@dataclass
class PolicyTrace:
    policy_id: str
    policy_version: str
    decision: str
    rules_evaluated: list[str]
    rules_passed: list[str]
    rules_failed: list[str]
    reasons: list[str]
    blocked_reasons: list[str]
    required_approval: bool
    risk_level: str

    def to_dict(self) -> dict:
        return dict(
            policy_id=self.policy_id, policy_version=self.policy_version, decision=self.decision,
            rules_evaluated=self.rules_evaluated, rules_passed=self.rules_passed, rules_failed=self.rules_failed,
            reasons=self.reasons, blocked_reasons=self.blocked_reasons, required_approval=self.required_approval,
            risk_level=self.risk_level,
        )


@dataclass
class RiskTrace:
    risk_level: str
    risk_score: str
    reasons: list[str]

    def to_dict(self) -> dict:
        return dict(risk_level=self.risk_level, risk_score=self.risk_score, reasons=self.reasons)


@dataclass
class ResolutionTrace:
    resolution_type: str
    requires_approval: bool
    review_state: str | None
    dual_control_required: bool | None
    financial_impact: str

    def to_dict(self) -> dict:
        return dict(
            resolution_type=self.resolution_type, requires_approval=self.requires_approval,
            review_state=self.review_state, dual_control_required=self.dual_control_required,
            financial_impact=self.financial_impact,
        )


# --- Contradictions / missing evidence (Phases 12-13) -------------------------

@dataclass
class ContradictionItem:
    field: str
    expected: str | None
    observed: str | None
    source_a: str
    source_b: str
    status: str  # "UNRESOLVED" (a CONTRADICTED hypothesis is always unresolved by construction -- see builder)
    impact: str

    def to_dict(self) -> dict:
        return dict(
            field=self.field, expected=self.expected, observed=self.observed, source_a=self.source_a,
            source_b=self.source_b, status=self.status, impact=self.impact,
        )


@dataclass
class MissingEvidenceItem:
    required: str
    available: list[str]
    impact: str
    resulting_decision_influence: str

    def to_dict(self) -> dict:
        return dict(
            required=self.required, available=self.available, impact=self.impact,
            resulting_decision_influence=self.resulting_decision_influence,
        )


# --- Audit / provenance references (Phase 2 item 13) --------------------------

@dataclass
class AuditReferences:
    exception_id: str
    correlation_id: str
    run_id: str | None
    audit_events_available: bool

    def to_dict(self) -> dict:
        return dict(
            exception_id=self.exception_id, correlation_id=self.correlation_id, run_id=self.run_id,
            audit_events_available=self.audit_events_available,
        )


# --- Priority (M11, optional) -------------------------------------------------
# A minimal, self-contained summary -- NOT an import from app.prioritization
# (that package imports FROM this module to build the full
# `PrioritizedException`; this module must never import back, or the two
# packages would form a circular dependency). `app.prioritization.scorer
# .attach_priority` is what actually populates this field, after both a
# `PrioritizedException` and this `ExplanationReport` already exist -- M10's
# own explanation-building logic never computes a priority itself.

@dataclass
class PriorityInfo:
    priority: str  # "P0" | "P1" | "P2" | "P3"
    priority_score: str
    reason_codes: list[str] = field(default_factory=list)
    recommended_action: str = ""

    def to_dict(self) -> dict:
        return dict(
            priority=self.priority, priority_score=self.priority_score,
            reason_codes=self.reason_codes, recommended_action=self.recommended_action,
        )


# --- The canonical report -----------------------------------------------------

CONFIDENCE_DISCLAIMER = (
    "AI confidence is a self-reported, advisory signal only. It is never read by the deterministic "
    "verifier or the policy engine, and it never overrides a verification or policy result."
)


@dataclass
class ExplanationReport:
    exception_id: str
    order_id: str
    payment_id: str
    decision: str
    decision_status: str
    financial_summary: FinancialSummary
    source_records: SourceRecordRefs
    matching_evidence: MatchingExplanation
    calculation_evidence: list[CalculationTrace]
    exception_evidence: dict
    ai_investigation_status: str  # "NOT_NEEDED" | "INVESTIGATED" | "UNAVAILABLE_OR_DEGRADED"
    ai_hypotheses: list[AIHypothesisTrace]
    self_challenge: list[SelfChallengeTrace]
    policy: PolicyTrace
    risk: RiskTrace
    resolution: ResolutionTrace
    audit_references: AuditReferences
    contradictions: list[ContradictionItem]
    missing_evidence: list[MissingEvidenceItem]
    confidence_note: str
    human_readable: str
    priority: PriorityInfo | None = None  # M11 -- absent until app.prioritization.scorer.attach_priority sets it

    def to_dict(self) -> dict:
        return {
            "exception_id": self.exception_id, "order_id": self.order_id, "payment_id": self.payment_id,
            "decision": self.decision, "decision_status": self.decision_status,
            "financial_summary": self.financial_summary.to_dict(),
            "source_records": self.source_records.to_dict(),
            "matching_evidence": self.matching_evidence.to_dict(),
            "calculation_evidence": [c.to_dict() for c in self.calculation_evidence],
            "priority": self.priority.to_dict() if self.priority is not None else None,
            "exception_evidence": self.exception_evidence,
            "ai_investigation_status": self.ai_investigation_status,
            "ai_hypotheses": [h.to_dict() for h in self.ai_hypotheses],
            "self_challenge": [s.to_dict() for s in self.self_challenge],
            "policy": self.policy.to_dict(), "risk": self.risk.to_dict(), "resolution": self.resolution.to_dict(),
            "audit_references": self.audit_references.to_dict(),
            "contradictions": [c.to_dict() for c in self.contradictions],
            "missing_evidence": [m.to_dict() for m in self.missing_evidence],
            "confidence_note": self.confidence_note, "human_readable": self.human_readable,
        }
