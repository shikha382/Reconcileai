"""Lightweight cross-source evidence graph -- plain Python dicts, not a
graph database (explicitly out of scope: "the purpose is NOT to create a
fancy graph database... use the simplest appropriate structure"). Answers:
"given this unmatched settlement, show me every connected financial record
that could explain it", by walking ORDER <-> PAYMENT <-> SETTLEMENT <->
BANK_TRANSACTION and PAYMENT <-> REFUND / FEE_RULE.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement


@dataclass
class EvidenceGraph:
    payment_by_id: dict[str, Payment] = field(default_factory=dict)
    settlement_by_id: dict[str, Settlement] = field(default_factory=dict)
    bank_txn_by_id: dict[str, BankTransaction] = field(default_factory=dict)
    refund_by_id: dict[str, Refund] = field(default_factory=dict)

    order_to_payment: dict[str, str] = field(default_factory=dict)
    payment_to_order: dict[str, str] = field(default_factory=dict)
    payment_to_settlements: dict[str, list[str]] = field(default_factory=dict)
    settlement_to_payment: dict[str, str | None] = field(default_factory=dict)
    settlement_to_bank_txns: dict[str, list[str]] = field(default_factory=dict)
    payment_to_refunds: dict[str, list[str]] = field(default_factory=dict)
    payment_to_fee_rule_method: dict[str, str] = field(default_factory=dict)


def build_graph(
    payments: list[Payment], settlements: list[Settlement],
    bank_transactions: list[BankTransaction], refunds: list[Refund],
) -> EvidenceGraph:
    g = EvidenceGraph()

    for p in payments:
        g.payment_by_id[p.payment_id] = p
        g.order_to_payment[p.order_id] = p.payment_id
        g.payment_to_order[p.payment_id] = p.order_id
        g.payment_to_fee_rule_method[p.payment_id] = p.method

    for s in settlements:
        g.settlement_by_id[s.settlement_id] = s
        g.settlement_to_payment[s.settlement_id] = s.payment_id
        if s.payment_id:
            g.payment_to_settlements.setdefault(s.payment_id, []).append(s.settlement_id)

    for b in bank_transactions:
        g.bank_txn_by_id[b.bank_txn_id] = b
        if b.matched_settlement_id:
            g.settlement_to_bank_txns.setdefault(b.matched_settlement_id, []).append(b.bank_txn_id)

    for r in refunds:
        g.refund_by_id[r.refund_id] = r
        g.payment_to_refunds.setdefault(r.payment_id, []).append(r.refund_id)

    return g


def connected_records(entity_type: str, entity_id: str, graph: EvidenceGraph) -> dict:
    """BFS-style traversal (small, fixed-depth graph -- a simple dict walk
    is sufficient) returning every record reachable from the given entity,
    grouped by type. Works from any entry point (order/payment/settlement)."""
    if entity_type == "settlement":
        payment_id = graph.settlement_to_payment.get(entity_id)
        return _from_payment(payment_id, graph, anchor_settlement_id=entity_id)
    if entity_type == "payment":
        return _from_payment(entity_id, graph)
    if entity_type == "order":
        payment_id = graph.order_to_payment.get(entity_id)
        return _from_payment(payment_id, graph)
    raise ValueError(f"unknown entity_type {entity_type!r}")


def _from_payment(payment_id: str | None, graph: EvidenceGraph, *, anchor_settlement_id: str | None = None) -> dict:
    if payment_id is None:
        result: dict = {"order_id": None, "payment_id": None, "settlements": [], "bank_transactions": [], "refunds": [], "fee_rule_method": None}
        if anchor_settlement_id:
            result["settlements"] = [anchor_settlement_id]
            result["bank_transactions"] = list(graph.settlement_to_bank_txns.get(anchor_settlement_id, []))
        return result

    settlement_ids = list(graph.payment_to_settlements.get(payment_id, []))
    if anchor_settlement_id and anchor_settlement_id not in settlement_ids:
        settlement_ids.append(anchor_settlement_id)

    bank_txn_ids: list[str] = []
    for sid in settlement_ids:
        bank_txn_ids.extend(graph.settlement_to_bank_txns.get(sid, []))

    return {
        "order_id": graph.payment_to_order.get(payment_id),
        "payment_id": payment_id,
        "settlements": settlement_ids,
        "bank_transactions": bank_txn_ids,
        "refunds": list(graph.payment_to_refunds.get(payment_id, [])),
        "fee_rule_method": graph.payment_to_fee_rule_method.get(payment_id),
    }
