"""The "Why NOT Matched" engine -- the most important part of M3.

For every payment, gathers ALL plausible candidate settlements (reusing
M2's candidate_generation.py blocking, not a new O(N*M) scan), runs the full
constraint battery against each, and produces a ranked, structured
negative-evidence report: not "unmatched", but "unmatched because candidate
X violated constraints A, B and C" -- for every candidate, including ones
M2's simpler single-linked-settlement path never had to evaluate against
rivals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.db.models import Payment, Settlement
from app.engines.evidence.constraints import (
    ConstraintResult,
    amount_balance_constraint,
    currency_match_constraint,
    duplicate_check_constraint,
    fee_rule_constraint,
    reference_match_constraint,
    refund_balance_constraint,
    relationship_consistency_constraint,
    settlement_window_constraint,
)
from app.engines.reconciliation.candidate_generation import ReconciliationContext
from app.engines.reconciliation.scoring import score_candidate
from app.engines.reconciliation.verification import bank_credited_amount

# Constraints that MUST pass for a candidate to be ACCEPTED. reference_match
# is deliberately excluded: M2's own design accepts a candidate on amount +
# date + fee agreement alone when reference doesn't match (the
# reference_mismatch archetype) -- reference is positive evidence, not a
# hard gate. duplicate_check is added dynamically per payment (see below)
# since it depends on the full candidate set, not a single pair.
REQUIRED_CONSTRAINTS = ("currency_match", "settlement_window", "relationship_consistency")


@dataclass
class CandidateEvidence:
    settlement_id: str
    constraints: list[ConstraintResult]
    verdict: str  # "ACCEPTED" | "REJECTED"
    reason_code: str | None
    score: Decimal

    @property
    def positive_evidence(self) -> list[ConstraintResult]:
        return [c for c in self.constraints if c.passed]

    @property
    def negative_evidence(self) -> list[ConstraintResult]:
        return [c for c in self.constraints if not c.passed]


@dataclass
class NegativeEvidenceReport:
    payment_id: str
    order_id: str
    candidates: list[CandidateEvidence]
    verdict: str  # "MATCHED" | "NO_VALID_CANDIDATE"
    accepted_settlement_id: str | None

    def to_dict(self) -> dict:
        return {
            "payment_id": self.payment_id,
            "order_id": self.order_id,
            "verdict": self.verdict,
            "accepted_settlement_id": self.accepted_settlement_id,
            "candidates": [
                {
                    "settlement_id": c.settlement_id,
                    "verdict": c.verdict,
                    "reason_code": c.reason_code,
                    "score": str(c.score),
                    "positive_evidence": [e.to_dict() for e in c.positive_evidence],
                    "negative_evidence": [e.to_dict() for e in c.negative_evidence],
                }
                for c in self.candidates
            ],
        }


def evaluate_candidate(
    payment: Payment, settlement: Settlement, context: ReconciliationContext, sibling_settlement_ids: list[str]
) -> CandidateEvidence:
    observed_amount = bank_credited_amount(settlement, context)
    constraints = [
        currency_match_constraint(payment, settlement),
        reference_match_constraint(payment, settlement),
        amount_balance_constraint(payment, observed_amount),
        settlement_window_constraint(payment, settlement),
        fee_rule_constraint(payment, settlement, context),
        refund_balance_constraint(payment, context),
        relationship_consistency_constraint(settlement),
        duplicate_check_constraint(settlement, sibling_settlement_ids),
    ]
    by_name = {c.constraint: c for c in constraints}

    # fee_rule.passed is TRUE both when a fee genuinely explains the amount
    # gap (reason_code is None) AND, vacuously, when there was no fee gap to
    # check at all (reason_code == "NO_FEE_RULE_APPLICABLE"). Only the
    # former should count as "the amount is explained via fee" -- otherwise
    # a genuinely-wrong amount with nothing to do with fees would be
    # incorrectly accepted just because the fee check had nothing to say.
    fee_actively_explains = by_name["fee_rule"].passed and by_name["fee_rule"].reason_code is None
    amount_ok = by_name["amount_balance"].passed or fee_actively_explains
    refund_ok = by_name["refund_balance"].passed
    duplicate_ok = by_name["duplicate_check"].passed
    hard_ok = all(by_name[name].passed for name in REQUIRED_CONSTRAINTS) and amount_ok and refund_ok and duplicate_ok

    if hard_ok:
        verdict, reason_code = "ACCEPTED", None
    else:
        failing = [c for c in constraints if not c.passed]
        # Prefer the most specific/diagnostic failure over a generic one.
        priority = ["fee_rule", "amount_balance", "duplicate_check", "settlement_window", "currency_match", "refund_balance", "relationship_consistency"]
        failing.sort(key=lambda c: priority.index(c.constraint) if c.constraint in priority else 99)
        verdict = "REJECTED"
        reason_code = failing[0].reason_code if failing else "UNKNOWN"

    score = score_candidate(payment, settlement, context).total
    return CandidateEvidence(settlement_id=settlement.settlement_id, constraints=constraints, verdict=verdict, reason_code=reason_code, score=score)


def why_not_matched(payment: Payment, context: ReconciliationContext) -> NegativeEvidenceReport:
    """Gathers every plausible candidate (direct-linked or blocked/unlinked
    pool, via M2's own candidate generation), evaluates each independently,
    and ranks them -- multi-candidate rejection, not a single yes/no."""
    linked = context.settlements_by_payment_id.get(payment.payment_id, [])
    blocked = [s for s in context.candidates_for(payment) if s.payment_id is None]
    all_candidates = linked + blocked

    if not all_candidates:
        return NegativeEvidenceReport(payment.payment_id, payment.order_id, [], "NO_VALID_CANDIDATE", None)

    sibling_ids_by_settlement = {
        s.settlement_id: [o.settlement_id for o in linked if o.settlement_id != s.settlement_id]
        for s in linked
    }

    evidences = [
        evaluate_candidate(payment, s, context, sibling_ids_by_settlement.get(s.settlement_id, []))
        for s in all_candidates
    ]
    evidences.sort(key=lambda e: e.score, reverse=True)

    accepted = [e for e in evidences if e.verdict == "ACCEPTED"]
    if len(accepted) == 1:
        return NegativeEvidenceReport(payment.payment_id, payment.order_id, evidences, "MATCHED", accepted[0].settlement_id)
    # zero or multiple accepted candidates -> no single valid, safe candidate
    return NegativeEvidenceReport(payment.payment_id, payment.order_id, evidences, "NO_VALID_CANDIDATE", None)
