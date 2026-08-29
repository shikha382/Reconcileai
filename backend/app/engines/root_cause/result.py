"""RootCauseResult: the final, structured output of M3's deterministic
investigation for one payment. A root cause is only ever marked VERIFIED
when arithmetic evidence proves it -- never inferred from a single field,
never guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.db.models import Payment, Settlement
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.types import ReconciliationResult
from app.engines.root_cause.decomposition import DecompositionResult, decompose_discrepancy
from app.engines.root_cause.hypotheses import HypothesisResult, run_all_hypotheses
from app.engines.reconciliation.verification import verify_refund_consistency
from shared.taxonomy import ReconciliationStatus

# Statuses, per the M3 brief:
VERIFIED = "VERIFIED"
PARTIALLY_EXPLAINED = "PARTIALLY_EXPLAINED"
UNEXPLAINED = "UNEXPLAINED"
CONTRADICTED = "CONTRADICTED"
AMBIGUOUS = "AMBIGUOUS"

_MATCHED_METHOD_TO_ROOT_CAUSE = {
    "exact_reference": "exact_match",
    "normalized_reference": "exact_match",
    "financial_consistency": "timing_or_reference_tolerance",
    "fee_verified": "fee_mismatch",
    "split_settlement_sum": "split_settlement",
    "aggregated_settlement_sum": "aggregated_settlement",
    "candidate_scoring": "candidate_scoring",
}


@dataclass
class RootCauseResult:
    exception_id: str
    root_cause: str | None
    status: str
    financial_delta: Decimal
    explained_amount: Decimal
    unexplained_amount: Decimal
    evidence_ids: list[str] = field(default_factory=list)
    constraints_passed: list[str] = field(default_factory=list)
    constraints_failed: list[str] = field(default_factory=list)
    hypotheses: list[HypothesisResult] = field(default_factory=list)
    decomposition: DecompositionResult | None = None

    def to_dict(self) -> dict:
        return {
            "exception_id": self.exception_id, "root_cause": self.root_cause, "status": self.status,
            "financial_delta": str(self.financial_delta), "explained_amount": str(self.explained_amount),
            "unexplained_amount": str(self.unexplained_amount), "evidence_ids": self.evidence_ids,
            "constraints_passed": self.constraints_passed, "constraints_failed": self.constraints_failed,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "decomposition": self.decomposition.to_dict() if self.decomposition else None,
        }


def determine_root_cause(
    payment: Payment, m2_result: ReconciliationResult, context: ReconciliationContext,
    settlement: Settlement | None, sibling_settlements: list[Settlement] | None = None,
) -> RootCauseResult:
    exception_id = f"EXC-{m2_result.reconciliation_id}"

    if m2_result.status == ReconciliationStatus.MATCHED:
        # M2 already deterministically verified this -- root cause is known
        # directly from its method, financial delta is 0 by construction.
        root_cause = _MATCHED_METHOD_TO_ROOT_CAUSE.get(m2_result.method, m2_result.method)
        return RootCauseResult(
            exception_id=exception_id, root_cause=root_cause, status=VERIFIED,
            financial_delta=Decimal("0.00"), explained_amount=Decimal("0.00"), unexplained_amount=Decimal("0.00"),
            constraints_passed=[l for l in m2_result.why_matched],
        )

    if m2_result.status == ReconciliationStatus.AMBIGUOUS:
        return RootCauseResult(
            exception_id=exception_id,
            root_cause="duplicate_candidates" if m2_result.relationship.value == "none" and settlement is None else "ambiguous_match",
            status=AMBIGUOUS, financial_delta=m2_result.financial_impact,
            explained_amount=Decimal("0.00"), unexplained_amount=m2_result.financial_impact,
            constraints_failed=[l for l in m2_result.why_not_matched],
        )

    if m2_result.status == ReconciliationStatus.UNRESOLVED:
        root_cause = "missing_transaction" if settlement is None else "insufficient_evidence"
        return RootCauseResult(
            exception_id=exception_id, root_cause=root_cause, status=UNEXPLAINED,
            financial_delta=payment.amount, explained_amount=Decimal("0.00"), unexplained_amount=payment.amount,
            constraints_failed=[l for l in m2_result.why_not_matched],
        )

    if m2_result.status == ReconciliationStatus.PARTIAL:
        # A genuine partial settlement: what DID arrive reconciles cleanly
        # 1:1; the remainder is honestly reported as still outstanding, not
        # papered over as "explained".
        decomposition = decompose_discrepancy(payment, settlement, context)
        return RootCauseResult(
            exception_id=exception_id, root_cause="partial_settlement", status=PARTIALLY_EXPLAINED,
            financial_delta=m2_result.financial_impact,
            explained_amount=(payment.amount - m2_result.financial_impact),
            unexplained_amount=m2_result.financial_impact,
            decomposition=decomposition,
            constraints_failed=[l for l in m2_result.why_not_matched],
        )

    # MISMATCH: run the full hypothesis battery and decomposition to find
    # out WHY, rather than reporting only "amount mismatch".
    hypotheses = run_all_hypotheses(payment, settlement, context, sibling_settlements)
    decomposition = decompose_discrepancy(payment, settlement, context) if settlement is not None else None

    if settlement is not None and settlement.status == "reversed":
        return RootCauseResult(
            exception_id=exception_id, root_cause="reversed_transaction", status=VERIFIED,
            financial_delta=m2_result.financial_impact, explained_amount=m2_result.financial_impact,
            unexplained_amount=Decimal("0.00"), hypotheses=hypotheses, decomposition=decomposition,
        )

    if settlement is not None and payment.currency != settlement.currency:
        return RootCauseResult(
            exception_id=exception_id, root_cause="currency_mismatch", status=VERIFIED,
            financial_delta=m2_result.financial_impact, explained_amount=Decimal("0.00"),
            unexplained_amount=m2_result.financial_impact, hypotheses=hypotheses,
        )

    # A failing fee hypothesis is only a genuine "fee_mismatch" story if the
    # applicable rule prescribes a non-trivial deduction in the first place
    # (e.g. card MDR) -- under a zero-rate rule (UPI here), the fee
    # hypothesis "fails" for the same underlying reason
    # relationship_consistency does, which would otherwise mislabel
    # unexplained_difference cases as a fee dispute. Mirrors the same guard
    # in app.engines.exceptions.classifier -- see CLAUDE.md's M3 decision.
    applicable_rule = context.fee_rule_by_method.get(payment.method)
    rule_is_nontrivial = applicable_rule is not None and (applicable_rule.mdr_percent > 0 or applicable_rule.fixed_fee > 0)

    fee_hyp = next((h for h in hypotheses if h.hypothesis_type == "fee_mismatch"), None)
    if fee_hyp is not None and fee_hyp.status == "REJECTED" and fee_hyp.residual is not None and fee_hyp.residual > 0 and rule_is_nontrivial:
        # A fee WAS deducted, but the exact rule does not explain the gap --
        # the M1 adversarial trap. A plausible explanation existed and was
        # disproven by arithmetic: CONTRADICTED, not UNEXPLAINED.
        return RootCauseResult(
            exception_id=exception_id, root_cause="fee_mismatch_unverified", status=CONTRADICTED,
            financial_delta=m2_result.financial_impact, explained_amount=Decimal("0.00"),
            unexplained_amount=fee_hyp.residual, hypotheses=hypotheses, decomposition=decomposition,
            evidence_ids=fee_hyp.evidence_ids,
        )

    # A refund is only a genuine CONTRADICTION when the refund claim ITSELF
    # isn't backed by any matching bank debit at all (verify_refund_consistency,
    # the refund's own evidence check) -- not merely because the combined
    # refund+fee hypothesis doesn't reach a zero residual, which is the
    # expected shape of a partial explanation (M3 brief CASE 3), not a
    # contradiction.
    if settlement is not None:
        refund_check = verify_refund_consistency(payment, context)
        if refund_check is not None and not refund_check.consistent and refund_check.unexplained_delta == sum(
            (r.amount for r in context.refunds_by_payment_id.get(payment.payment_id, [])), Decimal("0.00")
        ):
            # Not even partially evidenced -- the claimed refund has no
            # supporting debit whatsoever.
            return RootCauseResult(
                exception_id=exception_id, root_cause="refund_conflict", status=CONTRADICTED,
                financial_delta=m2_result.financial_impact, explained_amount=Decimal("0.00"),
                unexplained_amount=m2_result.financial_impact, hypotheses=hypotheses, decomposition=decomposition,
                evidence_ids=[r.refund_id for r in context.refunds_by_payment_id.get(payment.payment_id, [])],
            )

    if decomposition is not None and not decomposition.fully_explained and any(v > 0 for v in decomposition.components.values()):
        # Some deductions applied (and genuinely explain a non-zero amount),
        # but a residual remains after them.
        explained = decomposition.difference.copy_abs() - decomposition.residual
        return RootCauseResult(
            exception_id=exception_id, root_cause="partially_explained_residual", status=PARTIALLY_EXPLAINED,
            financial_delta=m2_result.financial_impact, explained_amount=explained,
            unexplained_amount=decomposition.residual, hypotheses=hypotheses, decomposition=decomposition,
        )

    root_cause = "over_settlement" if (
        settlement is not None and m2_result.financial_impact > 0
        and _observed_exceeds_expected(payment, settlement, context)
    ) else "unexplained_difference"

    return RootCauseResult(
        exception_id=exception_id, root_cause=root_cause, status=UNEXPLAINED,
        financial_delta=m2_result.financial_impact, explained_amount=Decimal("0.00"),
        unexplained_amount=m2_result.financial_impact, hypotheses=hypotheses, decomposition=decomposition,
    )


def _observed_exceeds_expected(payment: Payment, settlement: Settlement, context: ReconciliationContext) -> bool:
    from app.engines.reconciliation.verification import bank_credited_amount

    observed = bank_credited_amount(settlement, context)
    return observed is not None and observed > payment.amount
