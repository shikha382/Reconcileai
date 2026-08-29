"""Milestone 3 orchestrator: wires M2's reconciliation output into
classification -> negative evidence -> root-cause -> risk -> EvidenceBundle,
one per payment, for the whole dataset. This is the M3 analogue of
app.engines.reconciliation.engine.reconcile_all -- pure Python, no LLM
import anywhere in this module or anything it calls.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement
from app.engines.evidence.bundle import EvidenceBundle
from app.engines.evidence.candidates import why_not_matched
from app.engines.evidence.graph import EvidenceGraph, build_graph, connected_records
from app.engines.exceptions.classifier import classify_exception
from app.engines.reconciliation.candidate_generation import ReconciliationContext, build_context
from app.engines.reconciliation.engine import reconcile_all
from app.engines.reconciliation.types import ReconciliationResult
from app.engines.risk.scoring import build_financial_exposure, compute_risk_score
from app.engines.root_cause.result import determine_root_cause


def _resolve_settlement(payment: Payment, m2_result: ReconciliationResult, context: ReconciliationContext) -> tuple[Settlement | None, list[Settlement]]:
    linked = context.settlements_by_payment_id.get(payment.payment_id, [])

    settlement: Settlement | None = None
    if m2_result.matched_settlement_ids:
        settlement = next((s for s in linked if s.settlement_id in m2_result.matched_settlement_ids), None)
        if settlement is None:
            settlement = next((s for s in context.unlinked_settlements if s.settlement_id in m2_result.matched_settlement_ids), None)
    elif linked:
        settlement = linked[0]

    siblings = [s for s in linked if settlement is None or s.settlement_id != settlement.settlement_id]
    return settlement, siblings


def build_evidence_bundle(
    payment: Payment, m2_result: ReconciliationResult, context: ReconciliationContext,
    graph: EvidenceGraph, reference_now: datetime,
) -> EvidenceBundle:
    settlement, siblings = _resolve_settlement(payment, m2_result, context)

    category = classify_exception(payment, settlement, m2_result, context)
    negative_report = why_not_matched(payment, context)
    root_cause = determine_root_cause(payment, m2_result, context, settlement, siblings)

    actual_observed = None
    if m2_result.matched_settlement_ids and len(m2_result.matched_settlement_ids) > 1:
        # Split/aggregated: sum the confirmed credit across every matched
        # settlement, not just a single representative one. Checked BEFORE
        # the single-`settlement` case below, since `settlement` may have
        # resolved to just the first of several matched settlements.
        from decimal import Decimal

        from app.engines.reconciliation.verification import bank_credited_amount

        settlement_by_id = {s.settlement_id: s for s in context.settlements}
        total = Decimal("0.00")
        found_any = False
        for sid in m2_result.matched_settlement_ids:
            s = settlement_by_id.get(sid)
            if s is None:
                continue
            amt = bank_credited_amount(s, context)
            if amt is not None:
                total += amt
                found_any = True
        actual_observed = total if found_any else None
    elif settlement is not None and m2_result.relationship.value != "many_to_one":
        # For a many_to_one (aggregated) match, the settlement's confirmed
        # credit is the COMBINED total across multiple payments, not this
        # one payment's own share -- reporting it here would be wrong from
        # this payment's perspective. Leave actual_observed unset so
        # build_financial_exposure falls back to (payment.amount -
        # unexplained_amount), which correctly equals payment.amount for a
        # VERIFIED aggregation.
        from app.engines.reconciliation.verification import bank_credited_amount

        actual_observed = bank_credited_amount(settlement, context)

    exposure = build_financial_exposure(payment, root_cause, actual_observed)
    risk_score = compute_risk_score(payment, root_cause, reference_now)
    conn = connected_records("payment", payment.payment_id, graph)

    return EvidenceBundle(
        exception_id=f"EXC-{m2_result.reconciliation_id}",
        payment_id=payment.payment_id, order_id=payment.order_id,
        category=category.value if category else None,
        reconciliation_status=m2_result.status.value,
        connected_records=conn, negative_evidence_report=negative_report,
        root_cause=root_cause, financial_exposure=exposure, risk_score=risk_score,
    )


def run_exception_intelligence(
    payments: list[Payment], settlements: list[Settlement],
    bank_transactions: list[BankTransaction], refunds: list[Refund], fee_rules: list[FeeRule],
) -> tuple[list[ReconciliationResult], list[EvidenceBundle]]:
    """Runs M2 (reconcile_all, untouched/reused as-is) then builds one
    EvidenceBundle per payment on top of its result. reference_now for SLA
    aging is the latest captured_at across the batch, since a synthetic
    dataset has no real wall-clock 'now' to compare against."""
    m2_results = reconcile_all(payments, settlements, bank_transactions, refunds, fee_rules)
    context = build_context(payments, settlements, bank_transactions, refunds, fee_rules)
    graph = build_graph(payments, settlements, bank_transactions, refunds)
    reference_now = max((p.captured_at for p in payments), default=datetime.now(timezone.utc).replace(tzinfo=None))

    bundles = [
        build_evidence_bundle(payment, result, context, graph, reference_now)
        for payment, result in zip(payments, m2_results)
    ]
    return m2_results, bundles
