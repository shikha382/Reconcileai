"""Milestone 10: assembles the canonical `ExplanationReport` from
already-computed M2-M6 objects. This module is a pure READ/TRACE layer --
it calls no matching, verification, risk, policy, or audit logic of its
own. Every number and status here was already computed by M2-M6 before
`build_explanation` is ever called; this function only reshapes it.

The one exception, and it is deliberate: `_fee_calculation_trace` may
re-invoke `app.engines.reconciliation.verification.verify_fee_consistency`
-- the SAME authoritative, already-tested function M2/M3 use to make the
actual decision -- purely to recover its full structured output (expected
fee/tax/net, rule_id) for DISPLAY. This is calling the one authoritative
calculator a second time to read its answer more fully, not a second
implementation of fee math; the settlement/payment/context passed in are
the exact same real objects the original decision was made from.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.ai.policy import HypothesisOutcome
from app.challenge.contradiction import ContradictionRecord
from app.engines.evidence.candidates import CandidateEvidence, NegativeEvidenceReport
from app.engines.evidence.constraints import ConstraintResult
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.root_cause.result import RootCauseResult
from app.explainability.schemas import (
    CONFIDENCE_DISCLAIMER,
    AIHypothesisTrace,
    AuditReferences,
    CalculationTrace,
    CandidateMatchEvidence,
    ContradictionItem,
    EvidenceItem,
    ExplanationReport,
    FinancialSummary,
    MatchingExplanation,
    MissingEvidenceItem,
    PolicyTrace,
    ResolutionTrace,
    RiskTrace,
    SelfChallengeTrace,
    SourceRecordRefs,
)
from app.services.decision_service import DecisionResult

_MISSING_EVIDENCE_REASON_CODES = {
    "NO_CONFIRMED_AMOUNT": "confirmed bank credit",
    "NO_FEE_RULE_APPLICABLE": "applicable fee rule",
    "NO_VALID_CANDIDATE": "a valid candidate settlement",
    # NO_REFUND_ON_RECORD is deliberately excluded: it means "no refund was
    # ever claimed for this payment" -- a complete, non-concerning state
    # exactly like "no fee was deducted", not missing evidence (there is no
    # refund explanation being attempted for this to leave unverified).
}

_CHALLENGE_QUESTIONS = {
    "REFUND_EXPLAINS_DIFFERENCE": "Does a recorded refund, backed by a matching bank debit, explain the difference?",
    "FEE_EXPLAINS_DIFFERENCE": "Does the configured fee rule mathematically explain the difference?",
    "TAX_EXPLAINS_DIFFERENCE": "Does the configured tax component mathematically explain the difference?",
    "PARTIAL_SETTLEMENT": "Does the settlement cover only part of the payment, with the remainder still outstanding?",
    "SPLIT_SETTLEMENT": "Do multiple settlements sum exactly to the payment amount?",
    "AGGREGATED_SETTLEMENT": "Do multiple payments sum exactly to this settlement amount?",
    "DUPLICATE": "Is there a genuine duplicate settlement record for this payment?",
    "TIMING_DELAY": "Is the discrepancy explained by settlement timing alone, with the amount still matching exactly?",
    "REFERENCE_ERROR": "Is the reference the only mismatch, with amount and timing otherwise in agreement?",
    "MISSING_RECORD": "Does no settlement or candidate exist yet for this payment?",
    "UNEXPLAINED_RESIDUAL": "Is there a residual that no tested hypothesis can explain?",
    "AMBIGUOUS": "Do multiple candidates remain plausible with no safe way to choose between them?",
}


def _classify_match_status(bundle) -> str:
    status = bundle.reconciliation_status
    if status == "ambiguous":
        return "AMBIGUOUS"
    if status == "unresolved":
        return "UNMATCHED"
    if status != "matched":
        return "REJECTED"

    root_cause = bundle.root_cause.root_cause
    if root_cause == "exact_match":
        accepted_id = bundle.negative_evidence_report.accepted_settlement_id
        candidate = next((c for c in bundle.negative_evidence_report.candidates if c.settlement_id == accepted_id), None)
        if candidate is not None:
            ref_constraint = next((c for c in candidate.constraints if c.constraint == "reference_match"), None)
            if ref_constraint is not None and ref_constraint.reason_code == "NORMALIZED_MATCH":
                return "NORMALIZED_MATCH"
        return "EXACT_MATCH"
    if root_cause == "candidate_scoring":
        return "FUZZY_SCORED_MATCH"
    return "VERIFIED_MATCH"  # fee_verified / split / aggregated / timing-or-reference-tolerance / reversed / currency_mismatch


def _evidence_item_from_constraint(c: ConstraintResult, *, source_id: str, index: int) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"CONSTRAINT-{source_id}-{c.constraint}-{index}", evidence_type="constraint",
        source_type="settlement", source_id=source_id, field=c.constraint,
        observed_value=c.observed, expected_value=c.expected,
        relationship="payment<->settlement", status="SUPPORTED" if c.passed else "CONTRADICTED",
        explanation=(f"{c.constraint} passed" if c.passed else f"{c.constraint} failed: {c.reason_code}"),
        severity="info" if c.passed else "warning", provenance_reference=c.reason_code,
    )


def _candidate_match_evidence(candidate: CandidateEvidence) -> CandidateMatchEvidence:
    positive = [_evidence_item_from_constraint(c, source_id=candidate.settlement_id, index=i) for i, c in enumerate(candidate.positive_evidence)]
    negative = [_evidence_item_from_constraint(c, source_id=candidate.settlement_id, index=i) for i, c in enumerate(candidate.negative_evidence)]
    match_class = "REJECTED" if candidate.verdict == "REJECTED" else "ACCEPTED"
    return CandidateMatchEvidence(
        settlement_id=candidate.settlement_id, verdict=candidate.verdict, score=str(candidate.score),
        match_class=match_class, positive_evidence=positive, negative_evidence=negative,
    )


def _matching_explanation(bundle) -> MatchingExplanation:
    report: NegativeEvidenceReport = bundle.negative_evidence_report
    # `bundle.reconciliation_status` (M2, the AUTHORITATIVE decision-driving
    # status) and `report.accepted_settlement_id` (M3's own, separately-
    # computed NegativeEvidenceReport, built for "Why NOT Matched" detail)
    # can legitimately disagree: M3's evaluate_candidate() accepts a
    # candidate on hard-constraint-passing alone, without M2's own
    # score-threshold-plus-ambiguity-margin rule. Found while building this
    # explanation layer (an ambiguous_match case where M3 reports exactly
    # one ACCEPTED candidate while M2 correctly calls the payment AMBIGUOUS).
    # M2's status is authoritative for the real decision, so the explanation
    # must never surface an "accepted" settlement the real decision didn't
    # actually accept -- this is a fix to THIS read layer only, never to
    # M2/M3's own business logic.
    accepted_settlement_id = report.accepted_settlement_id if bundle.reconciliation_status == "matched" else None
    return MatchingExplanation(
        match_status=_classify_match_status(bundle), accepted_settlement_id=accepted_settlement_id,
        candidates=[_candidate_match_evidence(c) for c in report.candidates],
    )


def _fee_calculation_trace(context: Optional[ReconciliationContext], payment, settlement) -> Optional[CalculationTrace]:
    """Re-invokes the SAME authoritative `verify_fee_consistency` (not a
    reimplementation) purely to recover the rule_id/expected-fee detail for
    display, when the caller has the raw context/payment/settlement
    available. Omitted entirely (never fabricated) when they are not."""
    if context is None or payment is None or settlement is None:
        return None
    from app.engines.reconciliation.verification import verify_fee_consistency

    fee_check = verify_fee_consistency(payment, settlement, context)
    if fee_check is None:
        return None
    return CalculationTrace(
        label="fee_verification", rule_id=fee_check.rule_id,
        inputs={"gross_amount": str(settlement.amount), "expected_fee": str(fee_check.expected_fee), "expected_tax": str(fee_check.expected_tax)},
        expected_value=str(fee_check.expected_net), observed_value=str(fee_check.actual_net),
        residual=str(fee_check.delta), verification_result="PASSED" if fee_check.consistent else "FAILED",
    )


def _decomposition_trace(root_cause: RootCauseResult) -> Optional[CalculationTrace]:
    d = root_cause.decomposition
    if d is None:
        return None
    return CalculationTrace(
        label="discrepancy_decomposition", rule_id=None,
        inputs={k: str(v) for k, v in d.components.items()} | {"expected": str(d.expected), "observed": str(d.observed)},
        expected_value=str(d.expected), observed_value=str(d.observed), residual=str(d.residual),
        verification_result="PASSED" if d.fully_explained else "FAILED",
    )


def _ai_hypothesis_trace(outcome: HypothesisOutcome, contradiction: Optional[ContradictionRecord]) -> AIHypothesisTrace:
    hyp = outcome.hypothesis
    supporting = list(contradiction.supporting_evidence) if contradiction else []
    contradicting = list(contradiction.contradicting_evidence) if contradiction else []
    if contradiction is not None and contradiction.status == "SUPPORTED":
        disposition = "ACCEPTED" if outcome.decision.value == "SAFE_TO_RESOLVE" else "NOT_ACCEPTED"
        verification_result = "PASSED"
    elif contradiction is not None and contradiction.status == "CONTRADICTED":
        disposition, verification_result = "REJECTED", "FAILED"
    else:
        disposition, verification_result = "NOT_ACCEPTED", "NOT_TESTED"
    return AIHypothesisTrace(
        hypothesis_id=hyp.hypothesis_id, hypothesis_type=hyp.hypothesis_type.value, claim=hyp.claim,
        ai_confidence=hyp.confidence, supporting_evidence=supporting, contradicting_evidence=contradicting,
        verification_result=verification_result, verification_reason=outcome.reason, final_disposition=disposition,
    )


def _self_challenge_trace(contradiction: ContradictionRecord) -> SelfChallengeTrace:
    question = _CHALLENGE_QUESTIONS.get(contradiction.hypothesis_type, "Does the evidence support this hypothesis?")
    if contradiction.status == "CONTRADICTED":
        final = f"Challenge failed: {contradiction.reason}"
    elif contradiction.status == "SUPPORTED":
        final = f"Challenge passed: {contradiction.reason}"
    else:
        final = f"Insufficient evidence to evaluate: {contradiction.reason}"
    return SelfChallengeTrace(
        hypothesis_id=contradiction.hypothesis_id, challenge_question=question,
        counter_evidence=list(contradiction.contradicting_evidence), verification_result=contradiction.status,
        final_result=final,
    )


def _missing_evidence_items(
    bundle, context: Optional[ReconciliationContext] = None, payment=None,
) -> list[MissingEvidenceItem]:
    items: list[MissingEvidenceItem] = []
    report: NegativeEvidenceReport = bundle.negative_evidence_report
    seen_codes: set[str] = set()

    if report.verdict == "NO_VALID_CANDIDATE" and not report.candidates:
        items.append(MissingEvidenceItem(
            required="a settlement or candidate record", available=["payment"],
            impact="the discrepancy cannot be explained because nothing exists yet to compare against",
            resulting_decision_influence="escalated as unresolved rather than assumed correct",
        ))
        return items

    # NO_FEE_RULE_APPLICABLE is reported by fee_rule_constraint() for TWO
    # distinct, deliberately-collapsed (by M3's own design) reasons: (a) no
    # FeeRule is configured for this payment's method at all -- genuinely
    # missing evidence, or (b) a rule IS configured but net_amount==amount,
    # i.e. no fee was ever deducted -- nothing is missing, there was simply
    # nothing to check. Reporting (b) as "missing evidence" would be a false
    # claim of uncertainty where none exists (found while building the
    # Phase-25 demo: a clean auto-resolved case showed a spurious "missing
    # fee rule" line). When `context`/`payment` are available, this explanation
    # layer distinguishes the two; without them, case (a) is still correctly
    # surfaced -- see the fallback `no_context` branch below.
    fee_rule_genuinely_missing = None
    if context is not None and payment is not None:
        fee_rule_genuinely_missing = context.fee_rule_by_method.get(payment.method) is None

    for candidate in report.candidates:
        # Some "missing evidence" reason codes (e.g. NO_FEE_RULE_APPLICABLE)
        # are attached to a constraint that's marked `passed=True` (M2's own
        # "nothing to check, so it vacuously passes" convention) -- scanning
        # only `negative_evidence` would silently miss these, exactly the
        # "missing evidence treated as a positive claim" failure mode Phase
        # 13 warns against. Scan every constraint, not just the failing ones.
        for c in candidate.constraints:
            if c.reason_code not in _MISSING_EVIDENCE_REASON_CODES or c.reason_code in seen_codes:
                continue
            if c.reason_code == "NO_FEE_RULE_APPLICABLE" and fee_rule_genuinely_missing is False:
                continue  # a rule exists and there was simply no fee to check -- not missing evidence
            seen_codes.add(c.reason_code)
            items.append(MissingEvidenceItem(
                required=_MISSING_EVIDENCE_REASON_CODES[c.reason_code],
                available=["payment", "settlement"],
                impact=f"{c.constraint} cannot be verified because the required evidence is missing",
                resulting_decision_influence="never treated as a positive claim; contributes to a non-safe outcome",
            ))
    return items


def _contradiction_items(contradiction_records: list[ContradictionRecord], policy_decision) -> list[ContradictionItem]:
    items = []
    for record in contradiction_records:
        if record.status != "CONTRADICTED":
            continue
        impact = "AUTO_RESOLVE_NOT_PERMITTED" if policy_decision.decision.value != "SAFE_TO_RESOLVE" else "NONE"
        items.append(ContradictionItem(
            field=record.hypothesis_type, expected=record.expected_value, observed=record.observed_value,
            source_a="ai_hypothesis", source_b="deterministic_verifier", status="UNRESOLVED", impact=impact,
        ))
    return items


def _risk_reasons(bundle, policy_decision, contradiction_records: list[ContradictionRecord]) -> list[str]:
    reasons = []
    if bundle.financial_exposure.unexplained_amount != Decimal("0.00"):
        reasons.append("unexplained financial residual")
    if any(c.status == "CONTRADICTED" for c in contradiction_records):
        reasons.append("contradictory evidence")
    if not policy_decision.required_approval and policy_decision.decision.value != "SAFE_TO_RESOLVE":
        reasons.append("automation not authorized")
    elif policy_decision.required_approval:
        reasons.append("automation not authorized without human approval")
    if policy_decision.risk_level.value in ("HIGH", "CRITICAL"):
        reasons.append(f"risk level classified {policy_decision.risk_level.value}")
    return reasons or ["none -- within normal parameters"]


def _render_human_readable(report: ExplanationReport) -> str:
    lines = [
        f"FINAL DECISION: {report.decision}", "",
        f"Payment {report.payment_id} (order {report.order_id}): gross amount {report.financial_summary.gross_amount} {report.financial_summary.currency}.",
        f"Expected {report.financial_summary.expected_amount}, observed {report.financial_summary.observed_amount}, "
        f"unexplained {report.financial_summary.unexplained_amount}.",
        f"Matching: {report.matching_evidence.match_status}"
        + (f" (settlement {report.matching_evidence.accepted_settlement_id})" if report.matching_evidence.accepted_settlement_id else ""),
    ]
    if report.ai_investigation_status == "NOT_NEEDED":
        lines.append("AI investigation: not needed (already deterministically explained).")
    elif report.ai_investigation_status == "UNAVAILABLE_OR_DEGRADED":
        lines.append("AI investigation: unavailable/degraded -- no hypothesis could be obtained.")
    else:
        for h in report.ai_hypotheses:
            lines.append(f"AI hypothesis ({h.hypothesis_type}): \"{h.claim}\" -- verification {h.verification_result}, {h.final_disposition}.")
    if report.contradictions:
        for c in report.contradictions:
            lines.append(f"CONTRADICTION on {c.field}: expected {c.expected}, observed {c.observed} -- {c.impact}.")
    if report.missing_evidence:
        for m in report.missing_evidence:
            lines.append(f"MISSING EVIDENCE: {m.required} -- {m.impact}.")
    lines.append(f"Policy: {report.policy.decision} ({report.policy.policy_id} v{report.policy.policy_version}).")
    if report.policy.reasons:
        lines.append("Reasons: " + "; ".join(report.policy.reasons))
    lines.append(f"Risk: {report.risk.risk_level} -- " + "; ".join(report.risk.reasons))
    lines.append(f"Audit: correlation {report.audit_references.correlation_id}, exception {report.audit_references.exception_id}.")
    return "\n".join(lines)


def build_explanation(
    decision: DecisionResult, *, context: Optional[ReconciliationContext] = None, payment=None, settlement=None,
) -> ExplanationReport:
    """Assembles the canonical explanation for one already-decided
    exception. `context`/`payment`/`settlement` are OPTIONAL -- when
    supplied (the caller already has them in scope, e.g. right after
    `run_decision_pipeline`), the fee-calculation trace includes the literal
    FeeRule ID; when absent, every other section is still fully populated
    from `decision` alone, since `EvidenceBundle`/`RootCauseResult`/
    `NegativeEvidenceReport` already carry every number needed."""
    bundle = decision.bundle
    exposure = bundle.financial_exposure
    root_cause = bundle.root_cause
    policy_decision = decision.policy_decision
    connected = bundle.connected_records

    financial_summary = FinancialSummary(
        currency=exposure.currency, gross_amount=str(exposure.gross_amount), expected_amount=str(exposure.expected_amount),
        observed_amount=str(exposure.observed_amount), explained_amount=str(exposure.explained_amount),
        unexplained_amount=str(exposure.unexplained_amount),
    )
    source_records = SourceRecordRefs(
        payment_id=connected.get("payment_id") or bundle.payment_id, order_id=connected.get("order_id") or bundle.order_id,
        settlement_ids=list(connected.get("settlements", [])), bank_transaction_ids=list(connected.get("bank_transactions", [])),
        refund_ids=list(connected.get("refunds", [])), fee_rule_method=connected.get("fee_rule_method"),
    )

    calculation_evidence = []
    fee_trace = _fee_calculation_trace(context, payment, settlement)
    if fee_trace is not None:
        calculation_evidence.append(fee_trace)
    decomposition_trace = _decomposition_trace(root_cause)
    if decomposition_trace is not None:
        calculation_evidence.append(decomposition_trace)

    if decision.ai_investigation is None:
        ai_status = "NOT_NEEDED"
        ai_hypotheses: list[AIHypothesisTrace] = []
    elif decision.ai_investigation.trace.errors:
        ai_status = "UNAVAILABLE_OR_DEGRADED"
        ai_hypotheses = []
    else:
        ai_status = "INVESTIGATED"
        contradiction_by_hyp_id = {c.hypothesis_id: c for c in decision.contradiction_records}
        ai_hypotheses = [
            _ai_hypothesis_trace(outcome, contradiction_by_hyp_id.get(outcome.hypothesis.hypothesis_id))
            for outcome in decision.ai_investigation.outcomes
        ]

    self_challenge = [_self_challenge_trace(c) for c in decision.contradiction_records]

    policy_trace = PolicyTrace(
        policy_id=policy_decision.policy_id, policy_version=policy_decision.policy_version,
        decision=policy_decision.decision.value, rules_evaluated=policy_decision.rules_evaluated,
        rules_passed=policy_decision.rules_passed, rules_failed=policy_decision.rules_failed,
        reasons=policy_decision.reasons, blocked_reasons=policy_decision.blocked_reasons,
        required_approval=policy_decision.required_approval, risk_level=policy_decision.risk_level.value,
    )
    risk_trace = RiskTrace(
        risk_level=policy_decision.risk_level.value, risk_score=str(bundle.risk_score),
        reasons=_risk_reasons(bundle, policy_decision, decision.contradiction_records),
    )
    review = decision.review
    resolution_trace = ResolutionTrace(
        resolution_type=decision.proposal.resolution_type.value, requires_approval=policy_decision.required_approval,
        review_state=review.state.value if review is not None else None,
        dual_control_required=review.dual_control_required if review is not None else None,
        financial_impact=str(decision.proposal.financial_impact),
    )
    audit_references = AuditReferences(
        exception_id=decision.exception_id, correlation_id=decision.correlation_id, run_id=decision.run_id,
        audit_events_available=True,
    )
    contradictions = _contradiction_items(decision.contradiction_records, policy_decision)
    missing_evidence = _missing_evidence_items(bundle, context, payment)

    exception_evidence = {
        "category": bundle.category, "reconciliation_status": bundle.reconciliation_status,
        "root_cause": root_cause.root_cause, "root_cause_status": root_cause.status,
        "financial_delta": str(root_cause.financial_delta), "explained_amount": str(root_cause.explained_amount),
        "unexplained_amount": str(root_cause.unexplained_amount),
    }

    review = decision.review
    decision_status = review.state.value if review is not None else policy_decision.decision.value

    report = ExplanationReport(
        exception_id=decision.exception_id, order_id=source_records.order_id, payment_id=source_records.payment_id,
        decision=policy_decision.decision.value, decision_status=decision_status, financial_summary=financial_summary,
        source_records=source_records, matching_evidence=_matching_explanation(bundle),
        calculation_evidence=calculation_evidence, exception_evidence=exception_evidence,
        ai_investigation_status=ai_status, ai_hypotheses=ai_hypotheses, self_challenge=self_challenge,
        policy=policy_trace, risk=risk_trace, resolution=resolution_trace, audit_references=audit_references,
        contradictions=contradictions, missing_evidence=missing_evidence, confidence_note=CONFIDENCE_DISCLAIMER,
        human_readable="",
    )
    report.human_readable = _render_human_readable(report)
    return report
