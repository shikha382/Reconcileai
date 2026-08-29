"""The controlled tool layer. The AI interacts with financial data ONLY
through these functions -- never raw SQL, never arbitrary Python, never a
direct database session. Every tool takes a strict Pydantic input, returns
a strict Pydantic output, and reads from an already-loaded, read-only
InvestigationContext (built once per exception from M2/M3's own objects,
never queried fresh by the AI's own request).

Every tool wraps an M2/M3 function that already exists -- nothing here
re-derives financial logic; see the specific `app.engines.*` import next to
each tool for what it delegates to.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement
from app.engines.evidence.candidates import NegativeEvidenceReport, evaluate_candidate, why_not_matched
from app.engines.evidence.graph import EvidenceGraph, connected_records
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.verification import bank_credited_amount
from app.engines.root_cause.decomposition import decompose_discrepancy

from app.ai.schemas import (
    CalculateBalanceInput,
    CalculateBalanceOutput,
    CandidateEvidenceOutput,
    CandidateSummary,
    CompareCandidatesInput,
    CompareCandidatesOutput,
    ConstraintEvidence,
    GetCandidateMatchesInput,
    GetCandidateMatchesOutput,
    GetExceptionContextInput,
    GetExceptionContextOutput,
    GetFeeRuleInput,
    GetFeeRuleOutput,
    GetNegativeEvidenceInput,
    GetNegativeEvidenceOutput,
    GetRecordInput,
    GetRecordOutput,
    GetRefundsInput,
    GetRefundsOutput,
    GetRelatedRecordsInput,
    GetRelatedRecordsOutput,
    GetSettlementInput,
    GetSettlementOutput,
    RefundSummary,
)


class ToolAuthorizationError(Exception):
    """Raised when a requested tool name is not on the allow-list, or an
    input fails schema validation -- these never reach the underlying
    financial data at all."""


@dataclass
class InvestigationContext:
    """Everything one AI investigation session needs, pre-loaded and
    read-only. Built once per exception in app.services.ai_exception_service
    -- the AI never gets a live database handle."""
    exception_id: str
    payment: Payment
    reconciliation_context: ReconciliationContext
    graph: EvidenceGraph
    negative_evidence_report: NegativeEvidenceReport

    def settlement_by_id(self, settlement_id: str) -> Settlement | None:
        return self.graph.settlement_by_id.get(settlement_id)

    def payment_by_id(self, payment_id: str) -> Payment | None:
        return self.graph.payment_by_id.get(payment_id)

    def refund_by_id(self, refund_id: str) -> Refund | None:
        return self.graph.refund_by_id.get(refund_id)

    def bank_txn_by_id(self, bank_txn_id: str) -> BankTransaction | None:
        return self.graph.bank_txn_by_id.get(bank_txn_id)

    def fee_rule_by_id(self, fee_rule_id: str) -> FeeRule | None:
        for rule in self.reconciliation_context.fee_rules:
            if rule.fee_rule_id == fee_rule_id:
                return rule
        return None


def get_exception_context(input: GetExceptionContextInput, ctx: InvestigationContext) -> GetExceptionContextOutput:
    p = ctx.payment
    return GetExceptionContextOutput(
        exception_id=input.exception_id, payment_id=p.payment_id, order_id=p.order_id,
        payment_amount=str(p.amount), payment_currency=p.currency, payment_method=p.method,
    )


_ALLOWED_RECORD_FIELDS = {
    "order": ("order_id", "customer_ref", "amount", "currency", "created_at", "status"),
    "payment": ("payment_id", "order_id", "amount", "currency", "method", "captured_at", "status", "gateway_ref"),
    "settlement": ("settlement_id", "payment_id", "amount", "fee", "tax", "net_amount", "currency", "settled_at", "utr_reference", "status"),
    "bank_transaction": ("bank_txn_id", "amount", "currency", "value_date", "direction", "matched_settlement_id"),
    "refund": ("refund_id", "payment_id", "amount", "currency", "initiated_at", "status", "reference"),
    "fee_rule": ("fee_rule_id", "method", "mdr_percent", "fixed_fee", "tax_percent"),
}


def get_record(input: GetRecordInput, ctx: InvestigationContext) -> GetRecordOutput:
    """Bounded field lookup -- returns ONLY the allow-listed fields for the
    given record_type, never the full ORM object, and never `narration`/
    `utr_reference` raw text is treated as anything but a plain string value
    (never interpreted). Narration IS included for bank_transaction/
    settlement since it's a legitimate evidence field, but it is returned
    as inert data -- see docs/ai-controller.md's prompt-injection section."""
    record = None
    if input.record_type == "payment":
        record = ctx.payment_by_id(input.record_id)
    elif input.record_type == "settlement":
        record = ctx.settlement_by_id(input.record_id)
    elif input.record_type == "bank_transaction":
        record = ctx.bank_txn_by_id(input.record_id)
    elif input.record_type == "refund":
        record = ctx.refund_by_id(input.record_id)
    elif input.record_type == "fee_rule":
        record = ctx.fee_rule_by_id(input.record_id)
    elif input.record_type == "order":
        record = ctx.payment if ctx.payment.order_id == input.record_id else None

    if record is None:
        return GetRecordOutput(record_type=input.record_type, record_id=input.record_id, found=False)

    allowed = _ALLOWED_RECORD_FIELDS[input.record_type]
    fields = {name: str(getattr(record, name)) for name in allowed if hasattr(record, name)}
    return GetRecordOutput(record_type=input.record_type, record_id=input.record_id, found=True, fields=fields)


def get_related_records(input: GetRelatedRecordsInput, ctx: InvestigationContext) -> GetRelatedRecordsOutput:
    result = connected_records("payment", input.record_id, ctx.graph) if ctx.graph.payment_by_id.get(input.record_id) else \
        connected_records("order", input.record_id, ctx.graph)
    return GetRelatedRecordsOutput(
        order_id=result.get("order_id"), payment_id=result.get("payment_id"),
        settlement_ids=result.get("settlements", []), bank_transaction_ids=result.get("bank_transactions", []),
        refund_ids=result.get("refunds", []), fee_rule_method=result.get("fee_rule_method"),
    )


def get_candidate_matches(input: GetCandidateMatchesInput, ctx: InvestigationContext) -> GetCandidateMatchesOutput:
    payment = ctx.payment_by_id(input.payment_id)
    if payment is None:
        return GetCandidateMatchesOutput(payment_id=input.payment_id, candidates=[])

    linked = ctx.reconciliation_context.settlements_by_payment_id.get(payment.payment_id, [])
    blocked = [s for s in ctx.reconciliation_context.candidates_for(payment) if s.payment_id is None]
    candidates = []
    for s in linked + blocked:
        credit = bank_credited_amount(s, ctx.reconciliation_context)
        candidates.append(CandidateSummary(
            settlement_id=s.settlement_id, amount=str(s.amount), currency=s.currency,
            settled_at=s.settled_at.isoformat(), has_confirmed_credit=credit is not None,
        ))
    return GetCandidateMatchesOutput(payment_id=input.payment_id, candidates=candidates)


def _to_constraint_evidence(items) -> list[ConstraintEvidence]:
    return [ConstraintEvidence(constraint=c.constraint, passed=c.passed, expected=c.expected, observed=c.observed, delta=c.delta, reason_code=c.reason_code) for c in items]


def get_negative_evidence(input: GetNegativeEvidenceInput, ctx: InvestigationContext) -> GetNegativeEvidenceOutput:
    report = ctx.negative_evidence_report
    return GetNegativeEvidenceOutput(
        payment_id=input.payment_id, report_verdict=report.verdict,
        candidates=[
            CandidateEvidenceOutput(
                settlement_id=c.settlement_id, verdict=c.verdict,
                positive_evidence=_to_constraint_evidence(c.positive_evidence),
                negative_evidence=_to_constraint_evidence(c.negative_evidence),
            )
            for c in report.candidates
        ],
    )


def get_fee_rule(input: GetFeeRuleInput, ctx: InvestigationContext) -> GetFeeRuleOutput:
    rule = ctx.reconciliation_context.fee_rule_by_method.get(input.method)
    if rule is None:
        return GetFeeRuleOutput(found=False)
    return GetFeeRuleOutput(
        found=True, fee_rule_id=rule.fee_rule_id, method=rule.method,
        mdr_percent=str(rule.mdr_percent), fixed_fee=str(rule.fixed_fee), tax_percent=str(rule.tax_percent),
    )


def get_refunds(input: GetRefundsInput, ctx: InvestigationContext) -> GetRefundsOutput:
    refunds = ctx.reconciliation_context.refunds_by_payment_id.get(input.payment_id, [])
    all_debits = [b for b in ctx.reconciliation_context.bank_transactions if b.direction == "debit"]
    summaries = []
    for r in refunds:
        matching_debit = any(b.amount == r.amount and b.currency == r.currency for b in all_debits)
        summaries.append(RefundSummary(refund_id=r.refund_id, amount=str(r.amount), currency=r.currency, status=r.status, has_matching_debit=matching_debit))
    return GetRefundsOutput(payment_id=input.payment_id, refunds=summaries)


def get_settlement(input: GetSettlementInput, ctx: InvestigationContext) -> GetSettlementOutput:
    s = ctx.settlement_by_id(input.settlement_id)
    if s is None:
        return GetSettlementOutput(found=False, settlement_id=input.settlement_id)
    credit = bank_credited_amount(s, ctx.reconciliation_context)
    return GetSettlementOutput(
        found=True, settlement_id=s.settlement_id, amount=str(s.amount), fee=str(s.fee), tax=str(s.tax),
        net_amount=str(s.net_amount), currency=s.currency, settled_at=s.settled_at.isoformat(), status=s.status,
        confirmed_credit_amount=str(credit) if credit is not None else None,
    )


def calculate_balance(input: CalculateBalanceInput, ctx: InvestigationContext) -> CalculateBalanceOutput:
    payment = ctx.payment_by_id(input.payment_id)
    settlement = ctx.settlement_by_id(input.settlement_id) if input.settlement_id else None
    decomposition = decompose_discrepancy(payment, settlement, ctx.reconciliation_context)
    return CalculateBalanceOutput(
        expected=str(decomposition.expected), observed=str(decomposition.observed),
        difference=str(decomposition.difference), components={k: str(v) for k, v in decomposition.components.items()},
        residual=str(decomposition.residual), fully_explained=decomposition.fully_explained,
    )


def compare_candidates(input: CompareCandidatesInput, ctx: InvestigationContext) -> CompareCandidatesOutput:
    payment = ctx.payment_by_id(input.payment_id)
    evaluations = []
    accepted_count = 0
    for sid in input.settlement_ids:
        settlement = ctx.settlement_by_id(sid)
        if settlement is None:
            continue
        siblings = [s2 for s2 in input.settlement_ids if s2 != sid]
        evidence = evaluate_candidate(payment, settlement, ctx.reconciliation_context, siblings)
        if evidence.verdict == "ACCEPTED":
            accepted_count += 1
        evaluations.append(CandidateEvidenceOutput(
            settlement_id=sid, verdict=evidence.verdict,
            positive_evidence=_to_constraint_evidence(evidence.positive_evidence),
            negative_evidence=_to_constraint_evidence(evidence.negative_evidence),
        ))
    return CompareCandidatesOutput(
        payment_id=input.payment_id, candidates=evaluations,
        any_accepted=accepted_count >= 1, ambiguous=(accepted_count == 0 or accepted_count >= 2),
    )


# The tool allow-list. Nothing outside this dict is callable, by name --
# this is the "tool authorization" boundary: a request for any other name
# is rejected before it ever touches financial data (see controller.py).
TOOL_REGISTRY: dict[str, tuple[type, type, object]] = {
    "get_exception_context": (GetExceptionContextInput, GetExceptionContextOutput, get_exception_context),
    "get_record": (GetRecordInput, GetRecordOutput, get_record),
    "get_related_records": (GetRelatedRecordsInput, GetRelatedRecordsOutput, get_related_records),
    "get_candidate_matches": (GetCandidateMatchesInput, GetCandidateMatchesOutput, get_candidate_matches),
    "get_negative_evidence": (GetNegativeEvidenceInput, GetNegativeEvidenceOutput, get_negative_evidence),
    "get_fee_rule": (GetFeeRuleInput, GetFeeRuleOutput, get_fee_rule),
    "get_refunds": (GetRefundsInput, GetRefundsOutput, get_refunds),
    "get_settlement": (GetSettlementInput, GetSettlementOutput, get_settlement),
    "calculate_balance": (CalculateBalanceInput, CalculateBalanceOutput, calculate_balance),
    "compare_candidates": (CompareCandidatesInput, CompareCandidatesOutput, compare_candidates),
    # "test_hypothesis" is intentionally NOT here -- it lives in verifier.py
    # and is invoked directly by the controller's verification step, not as
    # a free tool call, since it IS the deterministic boundary itself, not
    # an evidence-gathering step. See app.ai.verifier.
}


def invoke_tool(tool_name: str, raw_input: dict, ctx: InvestigationContext) -> dict:
    """The single entry point the controller uses to call a tool. Validates
    the tool name against the allow-list, validates the input against its
    strict schema, invokes the (already-existing, deterministic) function,
    and validates the output too -- the model never gets to skip validation
    in either direction."""
    if tool_name not in TOOL_REGISTRY:
        raise ToolAuthorizationError(f"tool {tool_name!r} is not on the allow-list")

    input_schema, output_schema, fn = TOOL_REGISTRY[tool_name]
    try:
        validated_input = input_schema.model_validate(raw_input)
    except Exception as exc:  # pydantic.ValidationError
        raise ToolAuthorizationError(f"invalid input for tool {tool_name!r}: {exc}") from exc

    output = fn(validated_input, ctx)
    assert isinstance(output, output_schema)  # defensive: fn must return the declared schema
    return output.model_dump()
