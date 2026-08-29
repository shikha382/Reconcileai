"""Template/rule-generated human-readable explanations -- explicitly NOT an
LLM. Every sentence here is assembled from fields already computed and
stored in an EvidenceBundle; nothing is inferred or phrased by a model. This
proves the evidence engine is useful on its own, before any AI layer exists
(see CLAUDE.md's core principle: the future AI agent's explanations must be
held to the same evidentiary standard this module already demonstrates
deterministically).
"""
from __future__ import annotations

from app.engines.evidence.bundle import EvidenceBundle


def generate_explanation(bundle: EvidenceBundle) -> str:
    rc = bundle.root_cause
    exposure = bundle.financial_exposure
    report = bundle.negative_evidence_report

    lines: list[str] = []

    # root_cause.status is authoritative for "was this reconciled" -- it
    # reflects M2's full relationship-aware result (including split-sum and
    # aggregation-sum matches spanning MULTIPLE settlements), which the
    # generic per-candidate NegativeEvidenceReport below does not model (it
    # evaluates one settlement against the payment at a time, so a
    # split/aggregated settlement correctly fails a single-candidate
    # amount_balance check even though the record IS fully reconciled).
    if rc.status == "VERIFIED":
        settlement_note = f"settlement {report.accepted_settlement_id}" if report.accepted_settlement_id else "its settlement(s)"
        lines.append(
            f"Payment {bundle.payment_id} (order {bundle.order_id}) was reconciled with {settlement_note}."
        )
        lines.append(f"Root cause: {rc.root_cause}.")
        if exposure.gross_amount != exposure.observed_amount:
            lines.append(
                f"Expected amount: Rs {exposure.expected_amount}. Observed (bank-confirmed) amount: "
                f"Rs {exposure.observed_amount}. Fully explained by {rc.root_cause}, no unexplained residual."
            )
        else:
            lines.append(f"Amount matched exactly: Rs {exposure.gross_amount}.")
        return " ".join(lines)

    # Not cleanly matched -- describe the strongest rejected candidate, if any.
    candidates = sorted(report.candidates, key=lambda c: c.score, reverse=True)
    top = candidates[0] if candidates else None

    lines.append(f"Payment {bundle.payment_id} (order {bundle.order_id}) was NOT reconciled.")

    if top is not None:
        positive_summary = ", ".join(
            f"{e.constraint}={e.observed}" for e in top.positive_evidence
        ) or "no supporting signals"
        lines.append(f"Best candidate: settlement {top.settlement_id} ({positive_summary}).")

        negative = top.negative_evidence
        if negative:
            failure = negative[0]
            lines.append(
                f"But the candidate failed the {failure.constraint} constraint "
                f"(expected {failure.expected}, observed {failure.observed}, "
                f"delta {failure.delta}, reason: {failure.reason_code})."
            )
    else:
        lines.append("No candidate settlement was found at all.")

    lines.append(
        f"Expected amount: Rs {exposure.expected_amount}. Observed amount: Rs {exposure.observed_amount}."
    )
    lines.append(
        f"Explained amount: Rs {exposure.explained_amount}. Unexplained residual: Rs {exposure.unexplained_amount}."
    )

    if rc.status == "CONTRADICTED":
        lines.append(f"Therefore the {rc.root_cause.replace('_', ' ')} does not explain the discrepancy.")
    elif rc.status == "AMBIGUOUS":
        lines.append("Therefore this remains ambiguous and requires human review -- no candidate was auto-selected.")
    elif rc.status == "PARTIALLY_EXPLAINED":
        lines.append("Therefore this is only partially explained; the remainder is still outstanding.")
    else:
        lines.append("Therefore no deterministic root cause could be verified for this exception.")

    return " ".join(lines)
