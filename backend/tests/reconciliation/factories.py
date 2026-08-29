"""Small object builders for hand-constructed M2 unit tests. These build
plain (unattached-to-any-session) SQLAlchemy model instances directly --
no database required, matching the engine's own "pure Python, no session
needed" design (see engine.py's module docstring).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.db.models import BankTransaction, FeeRule, Payment, Settlement

BASE_DATE = datetime(2026, 6, 1, 10, 0, 0)

ZERO_FEE_RULE = FeeRule(
    fee_rule_id="FEE-UPI-001", method="upi",
    mdr_percent=Decimal("0.000"), fixed_fee=Decimal("0.00"), tax_percent=Decimal("0.000"),
    effective_from=BASE_DATE,
)
CARD_FEE_RULE = FeeRule(
    fee_rule_id="FEE-CARD-001", method="card",
    mdr_percent=Decimal("0.018"), fixed_fee=Decimal("2.00"), tax_percent=Decimal("0.180"),
    effective_from=BASE_DATE,
)


def make_payment(payment_id="PAY-00001", order_id="ORD-00001", amount="1000.00", currency="INR", method="upi", captured_at=None, metadata=None) -> Payment:
    import json

    return Payment(
        payment_id=payment_id, order_id=order_id, amount=Decimal(amount), currency=currency,
        method=method, captured_at=captured_at or BASE_DATE, status="captured",
        gateway_ref=f"GWREF{payment_id.split('-')[1]}", metadata_json=json.dumps(metadata or {}),
    )


def make_settlement(settlement_id="STL-00001", payment_id="PAY-00001", amount="1000.00", fee="0.00", tax="0.00", net_amount=None, currency="INR", settled_at=None, utr_reference=None, status="settled", metadata=None) -> Settlement:
    import json

    amt = Decimal(amount)
    net = Decimal(net_amount) if net_amount is not None else (amt - Decimal(fee) - Decimal(tax))
    return Settlement(
        settlement_id=settlement_id, payment_id=payment_id, settlement_batch_id="BATCH-TEST",
        amount=amt, fee=Decimal(fee), tax=Decimal(tax), net_amount=net, currency=currency,
        settled_at=settled_at or BASE_DATE, utr_reference=utr_reference or f"UTR{settlement_id.split('-')[1]}{(payment_id or 'NA').replace('-', '')}",
        status=status, metadata_json=json.dumps(metadata or {}),
    )


def make_bank_txn(bank_txn_id="BANKTXN-00001", settlement_id="STL-00001", amount="1000.00", currency="INR", value_date=None, direction="credit") -> BankTransaction:
    return BankTransaction(
        bank_txn_id=bank_txn_id, amount=Decimal(amount), currency=currency,
        value_date=value_date or BASE_DATE, narration=f"NEFT {settlement_id}",
        direction=direction, matched_settlement_id=settlement_id, metadata_json="{}",
    )
