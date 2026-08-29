"""M8 API DTOs. Deliberately separate from every SQLAlchemy model and from
M2-M6's own internal dataclasses (`EvidenceBundle`, `PolicyDecision`,
`ResolutionProposal`, `ContradictionRecord`, ...) -- these are the public,
versioned, safe-to-display contract; the internal shapes stay free to change
without becoming an API break, and nothing internal (raw model prompts,
hidden chain-of-thought, filesystem paths, secrets) leaks through by
accident because every field here is explicitly listed, never a raw
`.__dict__` dump.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Data sources (M14) -------------------------------------------------------
# Read-only, honest reporting of every configured data source's mode
# (SYNTHETIC DATA / MOCK PROVIDER / LIVE READ-ONLY / UNAVAILABLE) -- never
# reports LIVE unless real credentials are actually configured (M14 Phase 23).

class SourceStatusResponse(BaseModel):
    name: str
    mode: str
    configured: bool
    available: bool
    record_count: Optional[int] = None
    detail: str


class SourcesStatusResponse(BaseModel):
    sources: list[SourceStatusResponse]


# --- Safety metrics (M15) ------------------------------------------------------
# Ground-truth-based safety metrics for a completed run -- ONLY available
# when the run's dataset has a ground_truth.json (the reference 300-record
# demo dataset does; a hypothetical future live-provider dataset would not).
# `available=False` is a real, honest answer, never backed by a fabricated
# number.

class SafetyMetricsResponse(BaseModel):
    available: bool
    total: int = 0
    graded: int = 0
    false_auto_resolutions: int = 0
    false_auto_resolution_rate: float = 0.0
    match_rate: float = 0.0
    reason_unavailable: Optional[str] = None


# --- Health -----------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "reconcileai"


# --- Errors -------------------------------------------------------------------

class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# --- Runs ---------------------------------------------------------------------

class RunCreateRequest(BaseModel):
    """`dataset` names a subdirectory of the project's existing synthetic
    dataset location (app.config.settings.dataset_base_dir), never an
    absolute path or a new data model -- this is the same source format M1's
    ingestion pipeline already accepts. Defaults to the real 300-record
    dataset used throughout M1-M7."""

    dataset: str = Field(default="seeds", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_\-]+$")


class StageTimingResponse(BaseModel):
    stage: str
    seconds: float


class RunListResponse(BaseModel):
    """M12 addition: the smallest additive change needed for a Runs page --
    `RunRegistry.list_runs()` (M8) already existed but had no route exposing
    it. Reuses the exact same `_to_run_response` shaping as GET /runs/{id}."""

    items: list["RunResponse"]
    total: int


class RunResponse(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    records_processed: int
    matched: int
    exceptions: int
    auto_resolved: int
    human_review: int
    blocked: int
    rejected: int
    unresolved: int
    escalated: int
    audit_event_count: int
    audit_chain_valid: bool
    stage_timings: list[StageTimingResponse] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --- Exceptions -----------------------------------------------------------------

class ExceptionListItem(BaseModel):
    """The safe-to-display summary shown in a list -- enough for an overview/
    triage screen without pulling the full investigation detail per row."""

    exception_id: str
    run_id: str
    order_id: str
    payment_id: str
    category: Optional[str] = None
    reconciliation_status: str
    financial_exposure: str
    risk_level: str
    decision: str
    review_required: bool
    ai_investigated: bool
    contradiction_found: bool


class ExceptionListResponse(BaseModel):
    items: list[ExceptionListItem]
    page: int
    page_size: int
    total: int


class HypothesisSummary(BaseModel):
    hypothesis_id: str
    hypothesis_type: str
    claim: str
    confidence: float  # advisory only, never authoritative -- see docs/ai-design.md / CLAUDE.md


class ChallengeSummary(BaseModel):
    hypothesis_id: str
    hypothesis_type: str
    status: str  # SUPPORTED | CONTRADICTED | INSUFFICIENT_EVIDENCE
    reason: str
    expected_value: Optional[str] = None
    observed_value: Optional[str] = None
    residual: Optional[str] = None


class PolicyResultSummary(BaseModel):
    decision: str
    policy_id: str
    policy_version: str
    risk_level: str
    required_approval: bool
    reasons: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)


class ReviewSummary(BaseModel):
    review_id: str
    state: str
    dual_control_required: bool
    created_by: str


class ExceptionDetailResponse(BaseModel):
    exception_id: str
    run_id: str
    correlation_id: str
    order_id: str
    payment_id: str
    category: Optional[str] = None
    reconciliation_status: str
    financial_exposure: str
    risk_level: str
    risk_score: str
    ai_investigated: bool
    hypotheses: list[HypothesisSummary] = Field(default_factory=list)
    challenges: list[ChallengeSummary] = Field(default_factory=list)
    verification_conclusion: str  # SUPPORTED-derived summary: VERIFIED | CONTRADICTED | NOT_NEEDED
    policy: PolicyResultSummary
    decision: str
    review: Optional[ReviewSummary] = None
    provenance_available: bool


# --- Provenance -----------------------------------------------------------------

class TimelineEntryResponse(BaseModel):
    timestamp: datetime
    event_type: str
    actor_type: str
    actor_id: Optional[str] = None


class ProvenanceResponse(BaseModel):
    exception_id: str
    correlation_id: Optional[str] = None
    timeline: list[TimelineEntryResponse] = Field(default_factory=list)
    ai_believed: list[str] = Field(default_factory=list)
    supporting_evidence: list[list[str]] = Field(default_factory=list)
    contradicting_evidence: list[list[str]] = Field(default_factory=list)
    verification_conclusion: str
    policy_decision: Optional[str] = None
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None
    financial_exposure: Optional[str] = None
    approval_required: bool = False
    review_id: Optional[str] = None
    audit_chain_valid: bool
    audit_events_checked: int


# --- Audit status ---------------------------------------------------------------

class AuditEventSummary(BaseModel):
    event_id: str
    event_type: str
    timestamp: datetime


class AuditStatusResponse(BaseModel):
    run_id: str
    event_count: int
    chain_valid: bool
    invalid_reason: Optional[str] = None
    first_event: Optional[AuditEventSummary] = None
    last_event: Optional[AuditEventSummary] = None


# --- Audit event listing (M12) ------------------------------------------------
# The smallest additive change for a real audit-log viewer (Phase 16): M6's
# AuditLedger already supports listing every event for a correlation id;
# GET /runs/{run_id}/audit only ever reduced that to a count + first/last
# event. This DTO/route exposes the full, already-computed event list --
# no second audit mechanism, no independent tamper-check logic.

class AuditEventDetailResponse(BaseModel):
    event_id: str
    sequence: int
    event_type: str
    timestamp: datetime
    actor_type: str
    actor_id: Optional[str] = None
    entity_type: str
    entity_id: str
    correlation_id: str
    details: str  # the event's own stored payload, as canonical JSON text (Decimal-safe, never re-derived)


class AuditEventListResponse(BaseModel):
    run_id: str
    items: list[AuditEventDetailResponse]
    page: int
    page_size: int
    total: int


# --- Explanation (M10) -------------------------------------------------------
# Mirrors app.explainability.schemas.ExplanationReport field-for-field --
# this DTO layer exists so the API never returns that internal dataclass
# (or any SQLAlchemy object) directly, exactly like every other M8 response.

class EvidenceItemResponse(BaseModel):
    evidence_id: str
    evidence_type: str
    source_type: str
    source_id: str
    field: Optional[str] = None
    observed_value: Optional[str] = None
    expected_value: Optional[str] = None
    relationship: Optional[str] = None
    status: str
    explanation: str
    severity: str
    provenance_reference: Optional[str] = None


class FinancialSummaryResponse(BaseModel):
    currency: str
    gross_amount: str
    expected_amount: str
    observed_amount: str
    explained_amount: str
    unexplained_amount: str


class SourceRecordRefsResponse(BaseModel):
    payment_id: str
    order_id: str
    settlement_ids: list[str] = Field(default_factory=list)
    bank_transaction_ids: list[str] = Field(default_factory=list)
    refund_ids: list[str] = Field(default_factory=list)
    fee_rule_method: Optional[str] = None


class CandidateMatchEvidenceResponse(BaseModel):
    settlement_id: str
    verdict: str
    score: str
    match_class: str
    positive_evidence: list[EvidenceItemResponse] = Field(default_factory=list)
    negative_evidence: list[EvidenceItemResponse] = Field(default_factory=list)


class MatchingExplanationResponse(BaseModel):
    match_status: str
    accepted_settlement_id: Optional[str] = None
    candidates: list[CandidateMatchEvidenceResponse] = Field(default_factory=list)


class CalculationTraceResponse(BaseModel):
    label: str
    rule_id: Optional[str] = None
    inputs: dict[str, str] = Field(default_factory=dict)
    expected_value: Optional[str] = None
    observed_value: Optional[str] = None
    residual: Optional[str] = None
    verification_result: str


class AIHypothesisTraceResponse(BaseModel):
    hypothesis_id: str
    hypothesis_type: str
    claim: str
    ai_confidence: float
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    verification_result: str
    verification_reason: str
    final_disposition: str


class SelfChallengeTraceResponse(BaseModel):
    hypothesis_id: str
    challenge_question: str
    counter_evidence: list[str] = Field(default_factory=list)
    verification_result: str
    final_result: str


class ExplanationPolicyResponse(BaseModel):
    policy_id: str
    policy_version: str
    decision: str
    rules_evaluated: list[str] = Field(default_factory=list)
    rules_passed: list[str] = Field(default_factory=list)
    rules_failed: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    required_approval: bool
    risk_level: str


class ExplanationRiskResponse(BaseModel):
    risk_level: str
    risk_score: str
    reasons: list[str] = Field(default_factory=list)


class ExplanationResolutionResponse(BaseModel):
    resolution_type: str
    requires_approval: bool
    review_state: Optional[str] = None
    dual_control_required: Optional[bool] = None
    financial_impact: str


class ExplanationAuditReferencesResponse(BaseModel):
    exception_id: str
    correlation_id: str
    run_id: Optional[str] = None
    audit_events_available: bool


class ContradictionItemResponse(BaseModel):
    field: str
    expected: Optional[str] = None
    observed: Optional[str] = None
    source_a: str
    source_b: str
    status: str
    impact: str


class MissingEvidenceItemResponse(BaseModel):
    required: str
    available: list[str] = Field(default_factory=list)
    impact: str
    resulting_decision_influence: str


class PriorityInfoResponse(BaseModel):
    """M12 addition: mirrors app.explainability.schemas.PriorityInfo
    field-for-field -- the M11 dataclass and ExplanationReport.to_dict()
    already carried this; the API DTO simply hadn't been extended to
    surface it yet (see the M12 dated decision). Populated only when the
    explanation route can locate both the owning run's reference_now and
    the payment -- never fabricated when unavailable."""

    priority: str
    priority_score: str
    reason_codes: list[str] = Field(default_factory=list)
    recommended_action: str


class ExplanationResponse(BaseModel):
    exception_id: str
    order_id: str
    payment_id: str
    decision: str
    decision_status: str
    financial_summary: FinancialSummaryResponse
    source_records: SourceRecordRefsResponse
    matching_evidence: MatchingExplanationResponse
    calculation_evidence: list[CalculationTraceResponse] = Field(default_factory=list)
    exception_evidence: dict
    ai_investigation_status: str
    ai_hypotheses: list[AIHypothesisTraceResponse] = Field(default_factory=list)
    self_challenge: list[SelfChallengeTraceResponse] = Field(default_factory=list)
    policy: ExplanationPolicyResponse
    risk: ExplanationRiskResponse
    resolution: ExplanationResolutionResponse
    audit_references: ExplanationAuditReferencesResponse
    contradictions: list[ContradictionItemResponse] = Field(default_factory=list)
    missing_evidence: list[MissingEvidenceItemResponse] = Field(default_factory=list)
    confidence_note: str
    human_readable: str
    priority: Optional[PriorityInfoResponse] = None


# --- Prioritization / work queue (M11) --------------------------------------
# Mirrors app.prioritization.schemas.PrioritizedException/QueueSummary
# field-for-field -- same DTO-separation discipline as every other M8/M10 response.

class PrioritizedExceptionResponse(BaseModel):
    exception_id: str
    order_id: str
    payment_id: str
    priority: str
    priority_score: str
    risk_level: str
    risk_score: str
    financial_exposure: str
    currency: str
    age_days: int
    sla_status: str
    exception_category: Optional[str] = None
    decision_status: str
    contradiction_count: int
    missing_evidence_count: int
    recommended_action: str
    reason_codes: list[str] = Field(default_factory=list)
    explanation_reference: Optional[str] = None
    provenance_reference: Optional[str] = None


class QueueSummaryResponse(BaseModel):
    total: int
    counts_by_priority: dict[str, int]
    total_financial_exposure: str
    sla_breached_count: int
    sla_at_risk_count: int
    highest_exposure_exception_id: Optional[str] = None
    most_common_category: Optional[str] = None


class QueueResponse(BaseModel):
    items: list[PrioritizedExceptionResponse]
    summary: QueueSummaryResponse
    page: int
    page_size: int
    total: int
