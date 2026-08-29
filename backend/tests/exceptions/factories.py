"""M3 test builders -- extends M2's reconciliation factories (reused, not
duplicated) with a Refund builder and context/graph convenience wrappers."""
from __future__ import annotations

from decimal import Decimal

from app.db.models import Refund
from app.engines.reconciliation.candidate_generation import build_context
from app.engines.evidence.graph import build_graph

from ..reconciliation.factories import BASE_DATE, CARD_FEE_RULE, ZERO_FEE_RULE, make_bank_txn, make_payment, make_settlement  # noqa: F401


def make_refund(refund_id="REF-00001", payment_id="PAY-00001", amount="400.00", initiated_at=None) -> Refund:
    return Refund(
        refund_id=refund_id, payment_id=payment_id, amount=Decimal(amount), currency="INR",
        initiated_at=initiated_at or BASE_DATE, processed_at=initiated_at or BASE_DATE, status="processed",
        reference=f"RFND{refund_id.split('-')[1]}", metadata_json="{}",
    )


def make_context(payments=(), settlements=(), bank_txns=(), refunds=(), fee_rules=(ZERO_FEE_RULE,)):
    return build_context(list(payments), list(settlements), list(bank_txns), list(refunds), list(fee_rules))


def make_graph(payments=(), settlements=(), bank_txns=(), refunds=()):
    return build_graph(list(payments), list(settlements), list(bank_txns), list(refunds))
