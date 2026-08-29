"""Phase 15: provenance integrity validation. Confirms every evidence item
and reference in an `ExplanationReport` actually traces back to something
real -- the exact `DecisionResult` it was built from, and (when a ledger is
supplied) the real, persisted audit trail. Never trusts the explanation's
own claims at face value.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.explainability.schemas import ExplanationReport
from app.services.decision_service import DecisionResult


@dataclass
class ProvenanceValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"valid": self.valid, "errors": self.errors}


def validate_provenance(report: ExplanationReport, decision: DecisionResult, ledger=None) -> ProvenanceValidationResult:
    errors: list[str] = []
    bundle = decision.bundle
    connected = bundle.connected_records

    # 1. The explanation's own identifiers must match the DecisionResult it
    # claims to have been built from -- not a different, unrelated decision.
    if report.exception_id != decision.exception_id:
        errors.append(f"exception_id mismatch: report={report.exception_id!r} decision={decision.exception_id!r}")
    if report.audit_references.correlation_id != decision.correlation_id:
        errors.append(f"correlation_id mismatch: report={report.audit_references.correlation_id!r} decision={decision.correlation_id!r}")
    if report.payment_id != bundle.payment_id:
        errors.append(f"payment_id mismatch: report={report.payment_id!r} bundle={bundle.payment_id!r}")

    # 2. Every settlement/bank/refund ID the explanation names must be a
    # settlement/bank/refund ID the evidence graph actually connected to
    # this payment -- never an invented or unrelated record ID.
    known_settlements = set(connected.get("settlements", []))
    known_bank_txns = set(connected.get("bank_transactions", []))
    known_refunds = set(connected.get("refunds", []))

    for sid in report.source_records.settlement_ids:
        if sid not in known_settlements:
            errors.append(f"source_records cites settlement {sid!r} not present in the evidence graph")
    for bid in report.source_records.bank_transaction_ids:
        if bid not in known_bank_txns:
            errors.append(f"source_records cites bank transaction {bid!r} not present in the evidence graph")
    for rid in report.source_records.refund_ids:
        if rid not in known_refunds:
            errors.append(f"source_records cites refund {rid!r} not present in the evidence graph")

    known_candidate_settlement_ids = {c.settlement_id for c in bundle.negative_evidence_report.candidates}
    for candidate in report.matching_evidence.candidates:
        if candidate.settlement_id not in known_candidate_settlement_ids:
            errors.append(f"matching_evidence cites candidate {candidate.settlement_id!r} never evaluated by the negative-evidence report")

    # 3. Every AI hypothesis_id the explanation names must be one the real
    # investigation actually produced -- never fabricated.
    if decision.ai_investigation is not None:
        real_hypothesis_ids = {o.hypothesis.hypothesis_id for o in decision.ai_investigation.outcomes}
        for h in report.ai_hypotheses:
            if h.hypothesis_id not in real_hypothesis_ids:
                errors.append(f"ai_hypotheses cites hypothesis_id {h.hypothesis_id!r} not produced by the real investigation")
    elif report.ai_hypotheses:
        errors.append("ai_hypotheses is non-empty but decision.ai_investigation is None -- fabricated AI evidence")

    # 4. Every contradiction/self-challenge entry must correspond to a real
    # ContradictionRecord this decision actually produced.
    real_contradiction_ids = {c.hypothesis_id for c in decision.contradiction_records}
    for s in report.self_challenge:
        if s.hypothesis_id not in real_contradiction_ids:
            errors.append(f"self_challenge cites hypothesis_id {s.hypothesis_id!r} with no matching ContradictionRecord")

    # 5. When a real audit ledger is available, confirm the explanation's
    # OWN claimed correlation_id (not the underlying decision object's --
    # the whole point is to check what the report itself asserts) actually
    # resolves to real, persisted events belonging to the claimed exception.
    if ledger is not None:
        claimed_correlation_id = report.audit_references.correlation_id
        events = ledger.events_for_correlation(claimed_correlation_id)
        if not events:
            errors.append(f"correlation_id {claimed_correlation_id!r} has no matching audit events in the ledger")
        elif any(e.entity_id != report.exception_id for e in events):
            errors.append("audit ledger events for this correlation_id do not all belong to the claimed exception_id")

    return ProvenanceValidationResult(valid=not errors, errors=errors)
