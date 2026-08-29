"""M4 test builders -- reuses M2/M3 factories (not duplicated) plus a
helper to build an InvestigationContext directly from hand-built records.
"""
from __future__ import annotations

from app.ai.tools import InvestigationContext
from app.engines.evidence.candidates import why_not_matched
from app.engines.evidence.graph import build_graph
from app.engines.reconciliation.candidate_generation import build_context

from ..reconciliation.factories import BASE_DATE, CARD_FEE_RULE, ZERO_FEE_RULE, make_bank_txn, make_payment, make_settlement  # noqa: F401
from ..exceptions.factories import make_refund  # noqa: F401


def make_investigation_context(payment, settlements=(), bank_txns=(), refunds=(), fee_rules=(ZERO_FEE_RULE,), exception_id="EXC-TEST-1") -> InvestigationContext:
    reconciliation_context = build_context([payment], list(settlements), list(bank_txns), list(refunds), list(fee_rules))
    graph = build_graph([payment], list(settlements), list(bank_txns), list(refunds))
    report = why_not_matched(payment, reconciliation_context)
    return InvestigationContext(
        exception_id=exception_id, payment=payment, reconciliation_context=reconciliation_context,
        graph=graph, negative_evidence_report=report,
    )
