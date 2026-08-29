"""Stage 0/9: the reconciliation engine's public entry point. Ties together
candidate_generation, matching (single direct link), relationships (splits,
aggregations, ambiguous/unlinked candidates), producing one ReconciliationResult
per payment. Pure Python, no DB session required -- callers load ORM objects
(e.g. via a query) and pass them in; persistence is a separate, optional step
(persistence.py).

The engine never lets an LLM anywhere near this decision (there is no LLM
import in this whole package) and never marks a low-confidence or
insufficiently-evidenced case as MATCHED -- see relationships.py's ambiguity
handling and matching.py's fee/refund verification for where that's enforced.
"""
from __future__ import annotations

from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement
from app.engines.reconciliation.candidate_generation import ReconciliationContext, build_context
from app.engines.reconciliation.matching import resolve_single_linked_settlement
from app.engines.reconciliation.relationships import (
    find_aggregations,
    resolve_multiple_linked_settlements,
    resolve_unlinked_payment,
)
from app.engines.reconciliation.types import ReconciliationResult


def reconcile_payment(payment: Payment, context: ReconciliationContext, aggregation_results: dict[str, ReconciliationResult]) -> ReconciliationResult:
    linked = context.settlements_by_payment_id.get(payment.payment_id, [])

    if len(linked) == 1:
        return resolve_single_linked_settlement(payment, linked[0], context)
    if len(linked) > 1:
        return resolve_multiple_linked_settlements(payment, linked, context)

    # No direct link at all.
    if payment.payment_id in aggregation_results:
        return aggregation_results[payment.payment_id]
    return resolve_unlinked_payment(payment, context)


def reconcile_all(
    payments: list[Payment],
    settlements: list[Settlement],
    bank_transactions: list[BankTransaction],
    refunds: list[Refund],
    fee_rules: list[FeeRule],
) -> list[ReconciliationResult]:
    context = build_context(payments, settlements, bank_transactions, refunds, fee_rules)
    aggregation_results = find_aggregations(context)
    return [reconcile_payment(p, context, aggregation_results) for p in payments]
