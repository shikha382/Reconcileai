"""Strict Pydantic schemas for everything that crosses the AI boundary:
the AI's own structured output (AIHypothesis), every tool's input/output,
and the audit trace. The AI NEVER returns free-form text as a primary
output -- every call to a provider returns one of the models below,
validated, or it's a hard failure (see app.ai.provider).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import ClassVar, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class HypothesisType(str, Enum):
    """The ONLY hypothesis types the AI may propose. Not an open-ended
    string -- an invalid value is a Pydantic validation error, not a
    financial action the system has to interpret."""
    REFUND_EXPLAINS_DIFFERENCE = "REFUND_EXPLAINS_DIFFERENCE"
    FEE_EXPLAINS_DIFFERENCE = "FEE_EXPLAINS_DIFFERENCE"
    TAX_EXPLAINS_DIFFERENCE = "TAX_EXPLAINS_DIFFERENCE"
    PARTIAL_SETTLEMENT = "PARTIAL_SETTLEMENT"
    SPLIT_SETTLEMENT = "SPLIT_SETTLEMENT"
    AGGREGATED_SETTLEMENT = "AGGREGATED_SETTLEMENT"
    DUPLICATE = "DUPLICATE"
    TIMING_DELAY = "TIMING_DELAY"
    REFERENCE_ERROR = "REFERENCE_ERROR"
    MISSING_RECORD = "MISSING_RECORD"
    UNEXPLAINED_RESIDUAL = "UNEXPLAINED_RESIDUAL"
    AMBIGUOUS = "AMBIGUOUS"


class RecommendedAction(str, Enum):
    SAFE_TO_RESOLVE = "SAFE_TO_RESOLVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class AIHypothesis(BaseModel):
    """The AI's structured proposal. `confidence` and `recommended_action`
    are the model's OWN self-report -- advisory only, exactly like
    `model_self_reported_signals` elsewhere in this project (docs/ai-design.md).
    Neither field is trusted as the system's actual decision; see
    app.ai.policy for the authoritative gate."""
    model_config = ConfigDict(str_strip_whitespace=True)

    hypothesis_id: str
    exception_id: str
    hypothesis_type: HypothesisType
    claim: str
    record_ids: list[str] = Field(default_factory=list)
    calculation_request: Optional[dict] = None
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: RecommendedAction  # advisory self-report only


# --- Tool input/output schemas -----------------------------------------
# Every tool takes a strict, bounded input and returns a strict, bounded
# output. No tool accepts a free-form query string, SQL fragment, or code.

class GetExceptionContextInput(BaseModel):
    exception_id: str


class GetExceptionContextOutput(BaseModel):
    exception_id: str
    payment_id: str
    order_id: str
    payment_amount: str  # Decimal-as-string, never float
    payment_currency: str
    payment_method: str
    # Deliberately does NOT include M3's already-computed root_cause/category
    # -- the AI investigates from raw context, it doesn't get handed the
    # answer M3 already worked out (that would make "investigation" fake;
    # see docs/ai-controller.md).


RecordType = Literal["order", "payment", "settlement", "bank_transaction", "refund", "fee_rule"]


class GetRecordInput(BaseModel):
    record_id: str
    record_type: RecordType


class GetRecordOutput(BaseModel):
    record_type: RecordType
    record_id: str
    found: bool
    fields: dict = Field(default_factory=dict)  # bounded, allow-listed fields only -- see tools.py


RelationshipType = Literal["payment", "settlement", "refund", "bank_transaction", "order"]


class GetRelatedRecordsInput(BaseModel):
    record_id: str
    relationship_types: list[RelationshipType]


class GetRelatedRecordsOutput(BaseModel):
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    settlement_ids: list[str] = Field(default_factory=list)
    bank_transaction_ids: list[str] = Field(default_factory=list)
    refund_ids: list[str] = Field(default_factory=list)
    fee_rule_method: Optional[str] = None


class GetCandidateMatchesInput(BaseModel):
    payment_id: str


class CandidateSummary(BaseModel):
    settlement_id: str
    amount: str
    currency: str
    settled_at: str
    has_confirmed_credit: bool


class GetCandidateMatchesOutput(BaseModel):
    payment_id: str
    candidates: list[CandidateSummary] = Field(default_factory=list)


class GetNegativeEvidenceInput(BaseModel):
    payment_id: str


class ConstraintEvidence(BaseModel):
    constraint: str
    passed: bool
    expected: Optional[str] = None
    observed: Optional[str] = None
    delta: Optional[str] = None
    reason_code: Optional[str] = None


class CandidateEvidenceOutput(BaseModel):
    settlement_id: str
    verdict: str
    positive_evidence: list[ConstraintEvidence]
    negative_evidence: list[ConstraintEvidence]


class GetNegativeEvidenceOutput(BaseModel):
    payment_id: str
    report_verdict: str
    candidates: list[CandidateEvidenceOutput] = Field(default_factory=list)


class GetFeeRuleInput(BaseModel):
    method: str


class GetFeeRuleOutput(BaseModel):
    found: bool
    fee_rule_id: Optional[str] = None
    method: Optional[str] = None
    mdr_percent: Optional[str] = None
    fixed_fee: Optional[str] = None
    tax_percent: Optional[str] = None


class GetRefundsInput(BaseModel):
    payment_id: str


class RefundSummary(BaseModel):
    refund_id: str
    amount: str
    currency: str
    status: str
    has_matching_debit: bool


class GetRefundsOutput(BaseModel):
    payment_id: str
    refunds: list[RefundSummary] = Field(default_factory=list)


class GetSettlementInput(BaseModel):
    settlement_id: str


class GetSettlementOutput(BaseModel):
    found: bool
    settlement_id: str
    amount: Optional[str] = None
    fee: Optional[str] = None
    tax: Optional[str] = None
    net_amount: Optional[str] = None
    currency: Optional[str] = None
    settled_at: Optional[str] = None
    status: Optional[str] = None
    confirmed_credit_amount: Optional[str] = None


class CalculateBalanceInput(BaseModel):
    payment_id: str
    settlement_id: Optional[str] = None
    include_refunds: bool = True
    include_fees: bool = True


class CalculateBalanceOutput(BaseModel):
    expected: str
    observed: str
    difference: str
    components: dict = Field(default_factory=dict)
    residual: str
    fully_explained: bool


class TestHypothesisInput(BaseModel):
    __test__: ClassVar[bool] = False  # not a pytest test class -- named after the `test_hypothesis` tool concept

    exception_id: str
    payment_id: str
    hypothesis_type: HypothesisType
    settlement_id: Optional[str] = None
    candidate_payment_ids: list[str] = Field(default_factory=list)  # for AGGREGATED_SETTLEMENT
    candidate_settlement_ids: list[str] = Field(default_factory=list)  # for SPLIT_SETTLEMENT / DUPLICATE


class TestHypothesisOutput(BaseModel):
    __test__: ClassVar[bool] = False  # not a pytest test class

    hypothesis_type: HypothesisType
    passed: bool
    expected_value: Optional[str] = None
    observed_value: Optional[str] = None
    residual: Optional[str] = None
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class CompareCandidatesInput(BaseModel):
    payment_id: str
    settlement_ids: list[str]


class CompareCandidatesOutput(BaseModel):
    payment_id: str
    candidates: list[CandidateEvidenceOutput] = Field(default_factory=list)
    any_accepted: bool
    ambiguous: bool  # true if 0 or 2+ candidates are individually acceptable


# --- Investigation trace (auditable, machine-readable for a future UI) ---

class TraceStepType(str, Enum):
    OBSERVATION = "observation"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    HYPOTHESIS = "hypothesis"
    VERIFICATION = "verification"
    POLICY = "policy"
    REJECTION = "rejection"  # ungrounded hypothesis, invalid tool call, etc.
    ERROR = "error"


class TraceStep(BaseModel):
    type: TraceStepType
    message: str
    payload: dict = Field(default_factory=dict)
    timestamp: datetime


class ObservedToolCall(BaseModel):
    """One completed tool call this investigation session has made --
    part of the state handed to the provider so it can decide what to do
    next, and the source of truth for grounding validation (an AI
    hypothesis may only cite IDs that appear somewhere in here)."""
    tool_name: str
    tool_input: dict
    tool_output: dict


class InvestigationState(BaseModel):
    """Everything the provider sees when deciding its next action. Contains
    NO raw database access and NO M3 root-cause conclusion -- only what has
    been explicitly retrieved through logged tool calls so far."""
    exception_id: str
    payment_id: str
    step_count: int = 0
    tool_call_count: int = 0
    observations: list[ObservedToolCall] = Field(default_factory=list)
    hypotheses_tested: list[dict] = Field(default_factory=list)  # {hypothesis, verifier_result, decision}

    def known_record_ids(self) -> set[str]:
        ids: set[str] = {self.payment_id, self.exception_id}
        for obs in self.observations:
            for value in obs.tool_output.values():
                _collect_ids(value, ids)
        return ids


def _collect_ids(value, out: set[str]) -> None:
    if isinstance(value, str):
        out.add(value)
    elif isinstance(value, list):
        for item in value:
            _collect_ids(item, out)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_ids(item, out)


class ToolCallAction(BaseModel):
    action_type: Literal["tool_call"] = "tool_call"
    tool_name: str
    tool_input: dict


class HypothesisAction(BaseModel):
    action_type: Literal["hypothesis"] = "hypothesis"
    hypothesis: AIHypothesis


class ConcludeAction(BaseModel):
    action_type: Literal["conclude"] = "conclude"
    reason: str


class AIInvestigationTrace(BaseModel):
    investigation_id: str
    exception_id: str
    provider: str
    model: str
    prompt_version: str
    steps: list[TraceStep] = Field(default_factory=list)
    tool_call_count: int = 0
    hypotheses_tested: list[str] = Field(default_factory=list)
    final_decision: Optional[RecommendedAction] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    token_usage: Optional[dict] = None
    errors: list[str] = Field(default_factory=list)
