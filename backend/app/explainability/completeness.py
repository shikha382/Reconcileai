"""Phase 14: the explanation completeness validator. Checks that an
`ExplanationReport` actually contains the evidence its own decision type
requires -- an explanation must never claim completeness while missing the
one thing that would justify it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.explainability.schemas import ExplanationReport


@dataclass
class CompletenessResult:
    explanation_complete: bool
    missing_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"explanation_complete": self.explanation_complete, "missing_sections": self.missing_sections}


def check_explanation_completeness(report: ExplanationReport) -> CompletenessResult:
    missing: list[str] = []
    decision = report.decision

    if decision == "SAFE_TO_RESOLVE":
        if report.financial_summary.unexplained_amount != "0.00":
            missing.append("auto-resolve explanation must show a zero unexplained residual")
        if report.matching_evidence.match_status in ("AMBIGUOUS", "UNMATCHED", "REJECTED"):
            missing.append("auto-resolve explanation must show a genuine matched/verified relationship")
        if not report.policy.rules_passed:
            missing.append("auto-resolve explanation must cite which policy rule permitted automation")

    elif decision == "HUMAN_REVIEW":
        if not (report.policy.reasons or report.contradictions or report.missing_evidence):
            missing.append("human-review explanation must identify why automation was not allowed")

    elif decision == "REJECTED":
        if not (report.policy.blocked_reasons or report.policy.reasons):
            missing.append("rejected/blocked explanation must identify the blocking reason")

    elif decision == "UNRESOLVED":
        if not report.missing_evidence:
            missing.append("unresolved explanation must identify what evidence remains unknown")

    # Universal requirements, regardless of decision type.
    if not report.audit_references.correlation_id:
        missing.append("explanation must reference a correlation_id for audit traceability")
    if not report.human_readable:
        missing.append("explanation must include a rendered human-readable summary")

    return CompletenessResult(explanation_complete=not missing, missing_sections=missing)
