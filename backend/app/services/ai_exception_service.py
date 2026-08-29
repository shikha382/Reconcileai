"""Milestone 4 orchestrator: wires M3's EvidenceBundle output into the AI
routing/investigation/policy chain, one exception at a time or for the
whole dataset. Deterministically-VERIFIED exceptions (M3) never reach the
AI at all -- see app.ai.routing.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ai.controller import AIInvestigationResult, investigate
from app.ai.policy import NEVER_AUTO_RESOLVE_CATEGORIES
from app.ai.provider import LLMProvider
from app.ai.routing import needs_ai_investigation
from app.ai.tools import InvestigationContext
from app.db.models import BankTransaction, FeeRule, Payment, Refund, Settlement
from app.engines.evidence.bundle import EvidenceBundle
from app.engines.evidence.graph import build_graph
from app.engines.reconciliation.candidate_generation import build_context
from app.services.exception_service import run_exception_intelligence


@dataclass
class ExceptionResolution:
    payment_id: str
    order_id: str
    used_ai: bool
    final_decision: str  # matches M2's status vocabulary when no AI was used, or the AI's RecommendedAction otherwise
    reason: str
    ai_result: AIInvestigationResult | None


def resolve_one(bundle: EvidenceBundle, payment: Payment, reconciliation_context, graph, provider: LLMProvider) -> ExceptionResolution:
    if not needs_ai_investigation(bundle.root_cause):
        # Root-cause CERTAINTY (M3) and auto-resolution ELIGIBILITY (policy)
        # are different questions -- a categorical policy rule can still
        # block auto-resolution even for a fully VERIFIED root cause (e.g.
        # reversed_transaction, duplicate). This is the same
        # NEVER_AUTO_RESOLVE_CATEGORIES check the AI path's policy gate
        # applies, just reached without needing an AI investigation at all.
        if bundle.category in NEVER_AUTO_RESOLVE_CATEGORIES:
            return ExceptionResolution(
                payment_id=payment.payment_id, order_id=payment.order_id, used_ai=False,
                final_decision="HUMAN_REVIEW",
                reason=f"M3 verified the root cause ({bundle.root_cause.root_cause}), but {bundle.category} is policy-blocked from auto-resolution regardless of certainty.",
                ai_result=None,
            )
        return ExceptionResolution(
            payment_id=payment.payment_id, order_id=payment.order_id, used_ai=False,
            final_decision="SAFE_TO_RESOLVE", reason=f"M3 already deterministically verified this ({bundle.root_cause.root_cause}) -- no AI needed.",
            ai_result=None,
        )

    ctx = InvestigationContext(
        exception_id=bundle.exception_id, payment=payment,
        reconciliation_context=reconciliation_context, graph=graph,
        negative_evidence_report=bundle.negative_evidence_report,
    )
    result = investigate(bundle.exception_id, ctx, provider)
    return ExceptionResolution(
        payment_id=payment.payment_id, order_id=payment.order_id, used_ai=True,
        final_decision=result.final_decision.value, reason=result.reason, ai_result=result,
    )


def resolve_all(
    payments: list[Payment], settlements: list[Settlement], bank_transactions: list[BankTransaction],
    refunds: list[Refund], fee_rules: list[FeeRule], provider: LLMProvider,
) -> list[ExceptionResolution]:
    m2_results, bundles = run_exception_intelligence(payments, settlements, bank_transactions, refunds, fee_rules)
    reconciliation_context = build_context(payments, settlements, bank_transactions, refunds, fee_rules)
    graph = build_graph(payments, settlements, bank_transactions, refunds)
    payments_by_id = {p.payment_id: p for p in payments}

    resolutions = []
    for bundle in bundles:
        payment = payments_by_id[bundle.payment_id]
        resolutions.append(resolve_one(bundle, payment, reconciliation_context, graph, provider))
    return resolutions
