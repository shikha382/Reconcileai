"""EvidenceBundle: the single object a future AI layer will consume instead
of directly querying the database for arbitrary information. This is the
controlled boundary between DETERMINISTIC EVIDENCE (everything in this
bundle, all computed in M1-M3) and later AI REASONING (M8+) -- the AI agent
proposes over this bundle's contents, it never gets to go fishing in the
raw tables for whatever it wants.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.engines.evidence.candidates import NegativeEvidenceReport
from app.engines.evidence.graph import connected_records
from app.engines.reconciliation.types import ReconciliationResult
from app.engines.risk.scoring import FinancialExposure
from app.engines.root_cause.result import RootCauseResult
from shared.money import dumps


@dataclass
class EvidenceBundle:
    exception_id: str
    payment_id: str
    order_id: str
    category: str | None  # ExceptionCategory value, or None for a clean match
    reconciliation_status: str
    connected_records: dict
    negative_evidence_report: NegativeEvidenceReport
    root_cause: RootCauseResult
    financial_exposure: FinancialExposure
    risk_score: Decimal

    def to_dict(self) -> dict:
        return {
            "exception_id": self.exception_id,
            "payment_id": self.payment_id,
            "order_id": self.order_id,
            "category": self.category,
            "reconciliation_status": self.reconciliation_status,
            "connected_records": self.connected_records,
            "negative_evidence_report": self.negative_evidence_report.to_dict(),
            "root_cause": self.root_cause.to_dict(),
            "financial_exposure": self.financial_exposure.to_dict(),
            "risk_score": str(self.risk_score),
        }

    def to_json(self) -> str:
        return dumps(self.to_dict())
