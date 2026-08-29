"""Pydantic validation schemas for the six source-of-truth entities.

This is the "validation" stage of the pipeline (docs/architecture.md): every
record is validated against these schemas before it is normalized further and
persisted. A record that fails validation is rejected with a specific,
collected error -- never silently coerced or dropped.

Deliberate MVP scope limits (documented, not accidental omissions):
- Currency is restricted to INR only. Multi-currency conversion is explicitly
  out of scope (see RECONCILEAI_CONTEXT_PACK.md and CLAUDE.md) -- a record in
  any other currency should be rejected here rather than silently mishandled.
- ID formats are fixed regexes matching the deterministic IDs the synthetic
  generator produces (data/synthetic/generator.py). A real integration would
  relax these to match whatever ID format the live source actually uses.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_CURRENCIES = {"INR"}

_ORDER_ID_RE = re.compile(r"^ORD-\d{5}$")
_PAYMENT_ID_RE = re.compile(r"^PAY-\d{5}$")
_SETTLEMENT_ID_RE = re.compile(r"^STL-\d{5}$")
_BANK_TXN_ID_RE = re.compile(r"^BANKTXN-\d{5}$")
_REFUND_ID_RE = re.compile(r"^REF-\d{5}$")
_FEE_RULE_ID_RE = re.compile(r"^FEE-[A-Z]+-\d{3}$")


def _require_id_format(value: str, pattern: re.Pattern, field_name: str) -> str:
    if not pattern.match(value):
        raise ValueError(f"{field_name}={value!r} does not match required format {pattern.pattern!r}")
    return value


class MoneyValidatedModel(BaseModel):
    """Base for any schema with a primary `amount` + `currency` pair."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: Decimal
    currency: str

    @field_validator("amount")
    @classmethod
    def _amount_positive_two_dp(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("amount must be > 0")
        if v.as_tuple().exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        return v

    @field_validator("currency")
    @classmethod
    def _currency_allowed(cls, v: str) -> str:
        v2 = v.strip().upper()
        if v2 not in ALLOWED_CURRENCIES:
            raise ValueError(f"unsupported currency {v!r}; allowed: {sorted(ALLOWED_CURRENCIES)}")
        return v2


class OrderRecord(MoneyValidatedModel):
    order_id: str
    customer_ref: str
    created_at: datetime
    status: str
    metadata: dict = Field(default_factory=dict)

    @field_validator("order_id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        return _require_id_format(v, _ORDER_ID_RE, "order_id")


class PaymentRecord(MoneyValidatedModel):
    payment_id: str
    order_id: str
    method: str
    captured_at: datetime
    status: str
    gateway_ref: str
    metadata: dict = Field(default_factory=dict)

    @field_validator("payment_id")
    @classmethod
    def _payment_id_format(cls, v: str) -> str:
        return _require_id_format(v, _PAYMENT_ID_RE, "payment_id")

    @field_validator("order_id")
    @classmethod
    def _order_id_format(cls, v: str) -> str:
        return _require_id_format(v, _ORDER_ID_RE, "order_id")


class SettlementRecord(MoneyValidatedModel):
    settlement_id: str
    payment_id: Optional[str] = None
    settlement_batch_id: str
    fee: Decimal
    tax: Decimal
    net_amount: Decimal
    settled_at: datetime
    utr_reference: str
    status: str
    metadata: dict = Field(default_factory=dict)

    @field_validator("settlement_id")
    @classmethod
    def _settlement_id_format(cls, v: str) -> str:
        return _require_id_format(v, _SETTLEMENT_ID_RE, "settlement_id")

    @field_validator("payment_id")
    @classmethod
    def _payment_id_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _require_id_format(v, _PAYMENT_ID_RE, "payment_id")

    @field_validator("fee", "tax")
    @classmethod
    def _non_negative_two_dp(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("fee/tax must be >= 0")
        if v.as_tuple().exponent < -2:
            raise ValueError("fee/tax must have at most 2 decimal places")
        return v

    @field_validator("net_amount")
    @classmethod
    def _net_amount_positive_two_dp(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("net_amount must be > 0")
        if v.as_tuple().exponent < -2:
            raise ValueError("net_amount must have at most 2 decimal places")
        return v


class BankTransactionRecord(MoneyValidatedModel):
    bank_txn_id: str
    value_date: datetime
    narration: str
    direction: str
    matched_settlement_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    @field_validator("bank_txn_id")
    @classmethod
    def _bank_txn_id_format(cls, v: str) -> str:
        return _require_id_format(v, _BANK_TXN_ID_RE, "bank_txn_id")

    @field_validator("direction")
    @classmethod
    def _direction_allowed(cls, v: str) -> str:
        v2 = v.strip().lower()
        if v2 not in {"credit", "debit"}:
            raise ValueError(f"direction must be 'credit' or 'debit', got {v!r}")
        return v2

    @field_validator("matched_settlement_id")
    @classmethod
    def _matched_settlement_id_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _require_id_format(v, _SETTLEMENT_ID_RE, "matched_settlement_id")


class RefundRecord(MoneyValidatedModel):
    refund_id: str
    payment_id: str
    initiated_at: datetime
    processed_at: Optional[datetime] = None
    status: str
    reference: str
    metadata: dict = Field(default_factory=dict)

    @field_validator("refund_id")
    @classmethod
    def _refund_id_format(cls, v: str) -> str:
        return _require_id_format(v, _REFUND_ID_RE, "refund_id")

    @field_validator("payment_id")
    @classmethod
    def _payment_id_format(cls, v: str) -> str:
        return _require_id_format(v, _PAYMENT_ID_RE, "payment_id")


class FeeRuleRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    fee_rule_id: str
    method: str
    mdr_percent: Decimal
    fixed_fee: Decimal
    tax_percent: Decimal
    effective_from: datetime
    effective_to: Optional[datetime] = None

    @field_validator("fee_rule_id")
    @classmethod
    def _fee_rule_id_format(cls, v: str) -> str:
        return _require_id_format(v, _FEE_RULE_ID_RE, "fee_rule_id")

    @field_validator("mdr_percent", "tax_percent")
    @classmethod
    def _rate_in_range(cls, v: Decimal) -> Decimal:
        if not (Decimal("0") <= v < Decimal("1")):
            raise ValueError("rate must be expressed as a fraction in [0, 1), e.g. 0.003 for 0.3%")
        return v

    @field_validator("fixed_fee")
    @classmethod
    def _fixed_fee_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("fixed_fee must be >= 0")
        return v


SCHEMA_BY_SOURCE = {
    "order": OrderRecord,
    "payment": PaymentRecord,
    "settlement": SettlementRecord,
    "bank_transaction": BankTransactionRecord,
    "refund": RefundRecord,
    "fee_rule": FeeRuleRecord,
}
