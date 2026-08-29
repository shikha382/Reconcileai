"""The deterministic verifier -- completely independent of the LLM. This is
THE authority: an AIHypothesis is never accepted because the model sounded
confident, only because this module recomputed the claim with Decimal
arithmetic against real records and it held.

Every branch here delegates to a function that already existed in M2/M3
(app.engines.reconciliation.verification, app.engines.root_cause.hypotheses)
-- this module does not invent a second implementation of any financial
check; it dispatches an AIHypothesis's claimed type to the one true checker
for that claim, and translates the result into the tool-shaped output the
controller/trace expects.
"""
from __future__ import annotations

from decimal import Decimal

from app.ai.schemas import AIHypothesis, HypothesisType, TestHypothesisInput, TestHypothesisOutput
from app.ai.tools import InvestigationContext
from app.engines.reconciliation.verification import bank_credited_amount, verify_settlement_self_consistency
from app.engines.root_cause.hypotheses import (
    test_aggregation_hypothesis,
    test_duplicate_hypothesis,
    test_fee_hypothesis,
    test_refund_hypothesis,
    test_timing_hypothesis,
)


def validate_grounding(hypothesis: AIHypothesis, known_record_ids: set[str]) -> list[str]:
    """Every record_id/evidence_id the hypothesis cites must be an ID the
    session actually retrieved via a logged tool call. Returns the list of
    violations (empty = fully grounded). This is what catches a
    hallucinated/nonexistent record before it ever reaches the verifier."""
    violations = []
    for record_id in hypothesis.record_ids:
        if record_id not in known_record_ids:
            violations.append(f"record_id {record_id!r} was never retrieved via a tool call this session")
    for evidence_id in hypothesis.evidence_ids:
        if evidence_id not in known_record_ids:
            violations.append(f"evidence_id {evidence_id!r} was never retrieved via a tool call this session")
    return violations


def _single_settlement_selection_conflict(payment, settlement, ctx: InvestigationContext) -> str | None:
    """Guards every single-settlement, positive-explanation hypothesis
    (refund/fee/tax/timing/reference_error) against three ways a naive
    amount-and-date check can be fooled -- caught empirically while
    building this milestone against the real M1 dataset (see CLAUDE.md's
    M4 architectural decision for the specific incidents):

    1. The settlement's own status is 'reversed' -- a full credit amount
       can still match the payment exactly even though the money was
       later reversed by an equal debit; M2's matching.py checks this
       explicitly and so must this verifier.
    2. Another settlement is ALSO genuinely linked to this same payment
       (a duplicate-settlement situation) -- checking just the one
       settlement the hypothesis names, in isolation, can look perfectly
       clean while ignoring that a sibling claim on the same payment
       exists and hasn't been ruled out.
    3. The settlement is unlinked (no direct payment_id FK) and there is
       more than one comparably-plausible unlinked candidate for this
       payment -- the non-negotiable ambiguity rule (M2/relationships.py)
       applies here exactly as it does in deterministic matching: a
       single-candidate check must not silently pick a winner among
       multiple plausible, unlinked settlements.

    Returns a human-readable conflict reason, or None if there's no
    conflict and the single-settlement hypothesis may proceed.
    """
    if settlement.status == "reversed":
        return "settlement status is 'reversed' -- a single-settlement hypothesis cannot safely explain a reversed credit"

    linked = ctx.reconciliation_context.settlements_by_payment_id.get(payment.payment_id, [])
    if settlement.payment_id is not None:
        siblings = [s for s in linked if s.settlement_id != settlement.settlement_id]
        if siblings:
            return f"payment {payment.payment_id} has {len(siblings)} other linked settlement(s) ({', '.join(s.settlement_id for s in siblings)}) -- possible duplicate, not safe to verify a single-settlement hypothesis in isolation"
        return None

    unlinked_candidates = [s for s in ctx.reconciliation_context.candidates_for(payment) if s.payment_id is None]
    if len(unlinked_candidates) > 1:
        other_ids = [s.settlement_id for s in unlinked_candidates if s.settlement_id != settlement.settlement_id]
        if other_ids:
            return f"{len(other_ids)} other unlinked candidate settlement(s) exist for this payment ({', '.join(other_ids)}) -- ambiguous, not safe to verify a single-settlement hypothesis without ruling them out"
    return None
    return violations


def _verify_refund(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    payment = ctx.payment_by_id(input.payment_id)
    settlement = ctx.settlement_by_id(input.settlement_id) if input.settlement_id else None
    if payment is None or settlement is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="referenced payment or settlement does not exist")
    conflict = _single_settlement_selection_conflict(payment, settlement, ctx)
    if conflict:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason=conflict)
    hyp = test_refund_hypothesis(payment, settlement, ctx.reconciliation_context)
    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=(hyp.status == "VERIFIED"),
        expected_value=str(hyp.expected_value) if hyp.expected_value is not None else None,
        observed_value=str(hyp.observed_value) if hyp.observed_value is not None else None,
        residual=str(hyp.residual) if hyp.residual is not None else None,
        reason="refund fully explains the observed amount" if hyp.status == "VERIFIED" else "refund does not fully explain the observed amount",
        evidence_ids=hyp.evidence_ids,
    )


def _verify_fee_or_tax(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    payment = ctx.payment_by_id(input.payment_id)
    settlement = ctx.settlement_by_id(input.settlement_id) if input.settlement_id else None
    if payment is None or settlement is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="referenced payment or settlement does not exist")
    conflict = _single_settlement_selection_conflict(payment, settlement, ctx)
    if conflict:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason=conflict)
    hyp = test_fee_hypothesis(payment, settlement, ctx.reconciliation_context)
    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=(hyp.status == "VERIFIED"),
        expected_value=str(hyp.expected_value) if hyp.expected_value is not None else None,
        observed_value=str(hyp.observed_value) if hyp.observed_value is not None else None,
        residual=str(hyp.residual) if hyp.residual is not None else None,
        reason="fee rule exactly explains the observed amount" if hyp.status == "VERIFIED" else "the configured fee rule does not explain the observed amount",
        evidence_ids=hyp.evidence_ids,
    )


def _verify_timing(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    """TIMING_DELAY claims the ONLY discrepancy is a settlement lag -- that
    requires BOTH the date being within tolerance AND the amount matching
    exactly (date proximity alone proves nothing about whether the amount
    also reconciles). Checking date alone here was a real bug caught while
    building this milestone: it let the real M1 adversarial fee_mismatch
    case (a genuine fee discrepancy that also happens to settle within the
    timing window) verify as TIMING_DELAY and reach SAFE_TO_RESOLVE -- see
    CLAUDE.md's M4 architectural decision for the full incident."""
    payment = ctx.payment_by_id(input.payment_id)
    settlement = ctx.settlement_by_id(input.settlement_id) if input.settlement_id else None
    if payment is None or settlement is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="referenced payment or settlement does not exist")
    conflict = _single_settlement_selection_conflict(payment, settlement, ctx)
    if conflict:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason=conflict)

    hyp = test_timing_hypothesis(payment, settlement)
    observed = bank_credited_amount(settlement, ctx.reconciliation_context)
    amount_ok = observed is not None and observed == payment.amount

    passed = hyp.status == "VERIFIED" and amount_ok
    if not amount_ok:
        reason = "amount does not match exactly -- timing delay alone does not explain this discrepancy"
    elif hyp.status != "VERIFIED":
        reason = "settlement date exceeds the configured tolerance window"
    else:
        reason = "settlement date is within the configured window and the amount matches exactly"

    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=passed,
        expected_value=str(payment.amount), observed_value=str(observed) if observed is not None else None,
        reason=reason,
    )


def _verify_duplicate(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    """A DUPLICATE claim inherently means MORE THAN ONE settlement exists
    for this payment -- a single named settlement ID is not evidence of a
    duplicate at all (it's just the one candidate). Requiring at least 2
    IDs here was added after empirically finding the verifier would
    otherwise trivially 'verify' DUPLICATE for almost any case with at
    least one candidate settlement, since a length check on a 1-item list
    is always true. Harmless for safety (DUPLICATE is policy-blocked from
    auto-resolution either way -- see app.ai.policy), but was a real
    correctness gap in what 'verified' actually meant. See CLAUDE.md's M4
    architectural decision."""
    payment = ctx.payment_by_id(input.payment_id)
    if payment is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="referenced payment does not exist")
    if len(input.candidate_settlement_ids) < 2:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="fewer than 2 candidate settlements named -- not evidence of a duplicate")
    siblings = [ctx.settlement_by_id(sid) for sid in input.candidate_settlement_ids]
    if any(s is None for s in siblings):
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="one or more referenced settlement IDs do not exist")
    hyp = test_duplicate_hypothesis(payment, siblings)
    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=(hyp.status == "VERIFIED"),
        reason="multiple settlement records genuinely claim this payment" if hyp.status == "VERIFIED" else "no sibling settlement found",
        evidence_ids=hyp.evidence_ids,
    )


def _verify_aggregation(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    settlement = ctx.settlement_by_id(input.settlement_id) if input.settlement_id else None
    if settlement is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="referenced settlement does not exist")
    candidate_payments = [ctx.payment_by_id(pid) for pid in input.candidate_payment_ids]
    if any(p is None for p in candidate_payments):
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="one or more referenced payment IDs do not exist")
    hyp = test_aggregation_hypothesis(candidate_payments, settlement, ctx.reconciliation_context)
    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=(hyp.status == "VERIFIED"),
        expected_value=str(hyp.expected_value) if hyp.expected_value is not None else None,
        observed_value=str(hyp.observed_value) if hyp.observed_value is not None else None,
        residual=str(hyp.residual) if hyp.residual is not None else None,
        reason="candidate payments sum exactly to the settlement" if hyp.status == "VERIFIED" else "candidate payments do not sum to the settlement amount",
        evidence_ids=hyp.evidence_ids,
    )


def _verify_split(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    payment = ctx.payment_by_id(input.payment_id)
    if payment is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="referenced payment does not exist")
    settlements = [ctx.settlement_by_id(sid) for sid in input.candidate_settlement_ids]
    if not settlements or any(s is None for s in settlements):
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="one or more referenced settlement IDs do not exist")
    amounts = [bank_credited_amount(s, ctx.reconciliation_context) for s in settlements]
    if any(a is None for a in amounts):
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="one or more candidate settlements have no confirmed bank credit")
    total = sum(amounts, Decimal("0.00"))
    passed = total == payment.amount
    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=passed,
        expected_value=str(payment.amount), observed_value=str(total), residual=str((payment.amount - total).copy_abs()),
        reason="settlements sum exactly to the payment amount" if passed else "settlements do not sum exactly to the payment amount",
    )


def _verify_reference_error(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    """Claims that the ONLY problem is a bad reference -- amount and timing
    otherwise agree. Verified by checking the amount balances exactly and
    the settlement is within the timing window, using the same primitives
    as the fee/timing checks (no reference-specific arithmetic needed)."""
    payment = ctx.payment_by_id(input.payment_id)
    settlement = ctx.settlement_by_id(input.settlement_id) if input.settlement_id else None
    if payment is None or settlement is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="referenced payment or settlement does not exist")
    conflict = _single_settlement_selection_conflict(payment, settlement, ctx)
    if conflict:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason=conflict)
    observed = bank_credited_amount(settlement, ctx.reconciliation_context)
    timing = test_timing_hypothesis(payment, settlement)
    amount_ok = observed is not None and observed == payment.amount
    passed = amount_ok and timing.status == "VERIFIED"
    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=passed,
        expected_value=str(payment.amount), observed_value=str(observed) if observed is not None else None,
        reason="amount and timing agree; reference alone is unreliable evidence here" if passed else "amount and/or timing do not agree either, reference is not the only issue",
    )


def _verify_missing_record(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    payment = ctx.payment_by_id(input.payment_id)
    if payment is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason="referenced payment does not exist")
    linked = ctx.reconciliation_context.settlements_by_payment_id.get(payment.payment_id, [])
    blocked = [s for s in ctx.reconciliation_context.candidates_for(payment) if s.payment_id is None]
    passed = not linked and not blocked
    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=passed,
        reason="no settlement or candidate exists for this payment" if passed else "a settlement or candidate does exist -- this is not a missing record",
    )


def _verify_unexplained_or_ambiguous(input: TestHypothesisInput) -> TestHypothesisOutput:
    """UNEXPLAINED_RESIDUAL and AMBIGUOUS are not positive explanatory
    claims -- they're an honest admission. 'passed' here means the
    admission is accurate, not that anything is safe to auto-resolve
    (app.ai.policy never allows these to become SAFE_TO_RESOLVE)."""
    return TestHypothesisOutput(
        hypothesis_type=input.hypothesis_type, passed=True,
        reason="no verified explanation found; correctly escalating rather than guessing",
    )


_DISPATCH = {
    HypothesisType.REFUND_EXPLAINS_DIFFERENCE: _verify_refund,
    HypothesisType.FEE_EXPLAINS_DIFFERENCE: _verify_fee_or_tax,
    HypothesisType.TAX_EXPLAINS_DIFFERENCE: _verify_fee_or_tax,
    HypothesisType.TIMING_DELAY: _verify_timing,
    HypothesisType.DUPLICATE: _verify_duplicate,
    HypothesisType.AGGREGATED_SETTLEMENT: _verify_aggregation,
    HypothesisType.SPLIT_SETTLEMENT: _verify_split,
    HypothesisType.REFERENCE_ERROR: _verify_reference_error,
    HypothesisType.MISSING_RECORD: _verify_missing_record,
    HypothesisType.PARTIAL_SETTLEMENT: _verify_split,  # a degenerate 1-settlement "sum" -- same check, sum < payment means not-passed, which is correct: PARTIAL_SETTLEMENT is not a fully-explaining hypothesis
}


def verify_hypothesis(input: TestHypothesisInput, ctx: InvestigationContext) -> TestHypothesisOutput:
    if input.hypothesis_type in (HypothesisType.UNEXPLAINED_RESIDUAL, HypothesisType.AMBIGUOUS):
        return _verify_unexplained_or_ambiguous(input)
    handler = _DISPATCH.get(input.hypothesis_type)
    if handler is None:
        return TestHypothesisOutput(hypothesis_type=input.hypothesis_type, passed=False, reason=f"no verifier registered for {input.hypothesis_type}")
    return handler(input, ctx)
