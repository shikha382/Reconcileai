"""Result types the reconciliation engine produces. Plain dataclasses, not
SQLAlchemy models -- the engine is independently testable as ordinary Python
without touching a database (persistence is a thin adapter in
app.engines.reconciliation.persistence, layered on top of these).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from shared.taxonomy import RelationshipType, ReconciliationStatus


@dataclass
class ScoreBreakdown:
    """Every component of a candidate's score, so a developer (or, in a
    demo, a reviewer) can see exactly why a score is what it is -- never a
    single opaque number."""
    reference: Decimal
    amount: Decimal
    date: Decimal
    fee: Decimal
    merchant: Decimal
    link: Decimal
    total: Decimal


@dataclass
class CandidateExplanation:
    """One considered candidate settlement, matched or not. Every candidate
    the engine looked at is kept, not just the winner -- this is what makes
    'Why NOT Matched' possible without recomputation later."""
    settlement_id: str
    score: ScoreBreakdown
    accepted: bool
    why_matched: list[str] = field(default_factory=list)
    why_not_matched: list[str] = field(default_factory=list)


@dataclass
class ReconciliationResult:
    reconciliation_id: str
    payment_id: str
    order_id: str
    status: ReconciliationStatus
    method: str  # e.g. "exact_reference", "normalized_reference", "fee_verified",
                 # "timing_tolerance", "split_settlement_sum", "aggregated_settlement_sum",
                 # "candidate_scoring", "none"
    relationship: RelationshipType
    matched_settlement_ids: list[str]
    matched_bank_txn_ids: list[str]
    matched_refund_ids: list[str]
    score: Decimal | None
    candidates: list[CandidateExplanation]
    why_matched: list[str]
    why_not_matched: list[str]
    differences: list[str]
    financial_impact: Decimal  # the ₹ amount that is unexplained/at risk, 0 if fully matched
    created_at: datetime
    engine_version: str

    @property
    def rejected_candidates(self) -> list[CandidateExplanation]:
        return [c for c in self.candidates if not c.accepted]
