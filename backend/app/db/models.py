"""SQLAlchemy models for the six source-of-truth entities, per docs/data-model.md.

Milestone 1 scope only: Order, Payment, Settlement, BankTransaction, Refund,
FeeRule, plus a generic RawRecord table used to preserve untouched raw payloads
alongside their normalized counterparts (CLAUDE.md: "raw ingested records are
preserved unmodified alongside normalized versions -- never overwrite the
source-of-truth raw value").

The reconciliation-result entities from docs/data-model.md (ReconciliationMatch,
Exception, Evidence, AIHypothesis, Decision, Approval, AuditEvent) are NOT
defined here -- they belong to later milestones (matching, exception detection,
AI investigation, policy, audit) that don't exist yet. Adding them now would be
speculative schema no engine currently writes to.

All monetary columns use SQLAlchemy Numeric with asdecimal=True, so values
round-trip as Decimal in Python regardless of backend (SQLite for dev/demo,
Postgres-compatible types used throughout so a swap is a connection-string
change only). See backend/tests/test_models.py for a round-trip precision test
that would fail loudly if this assumption ever stopped holding.

Note: columns are named `metadata_json` rather than `metadata` because
SQLAlchemy's DeclarativeBase reserves the attribute name `metadata` for the
schema registry itself -- this is a deliberate, minor naming deviation from
the plain "metadata" field name used in docs/data-model.md.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY = Numeric(14, 2, asdecimal=True)
RATE = Numeric(8, 6, asdecimal=True)  # percentages stored as fractions, e.g. 0.003 = 0.3%


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_ref: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    source: Mapped[str] = mapped_column(String, nullable=False, default="internal_ledger")


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.order_id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    gateway_ref: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    source: Mapped[str] = mapped_column(String, nullable=False, default="payment_gateway")


class Settlement(Base):
    __tablename__ = "settlements"

    settlement_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Nullable: aggregated settlements (many payments -> one settlement) and
    # split settlements (one payment -> many settlements) mean this is not
    # always a clean 1:1 FK; the actual linkage is recorded in ground truth
    # for now and will live in ReconciliationMatch once matching exists.
    payment_id: Mapped[str | None] = mapped_column(String, ForeignKey("payments.payment_id"), nullable=True)
    settlement_batch_id: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    fee: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    tax: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    net_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    utr_reference: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    source: Mapped[str] = mapped_column(String, nullable=False, default="settlement_export")


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    bank_txn_id: Mapped[str] = mapped_column(String, primary_key=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    value_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    narration: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    matched_settlement_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("settlements.settlement_id"), nullable=True
    )
    metadata_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    source: Mapped[str] = mapped_column(String, nullable=False, default="bank_statement")


class Refund(Base):
    __tablename__ = "refunds"

    refund_id: Mapped[str] = mapped_column(String, primary_key=True)
    payment_id: Mapped[str] = mapped_column(String, ForeignKey("payments.payment_id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    initiated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reference: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[str] = mapped_column(String, nullable=False, default="{}")
    source: Mapped[str] = mapped_column(String, nullable=False, default="refund_records")


class FeeRule(Base):
    __tablename__ = "fee_rules"

    fee_rule_id: Mapped[str] = mapped_column(String, primary_key=True)
    method: Mapped[str] = mapped_column(String, nullable=False)
    mdr_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    fixed_fee: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    tax_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReconciliationMatch(Base):
    """Persisted output of the M2 deterministic reconciliation engine (see
    app.engines.reconciliation). One row per ReconciliationResult produced by
    engine.reconcile_all -- added in M2, not M1; no M1 table above was
    changed to make room for this. Structured fields (evidence/differences/
    candidates) are stored as Decimal-safe JSON text, matching the
    metadata_json pattern already used elsewhere in this file.
    """

    __tablename__ = "reconciliation_matches"

    reconciliation_id: Mapped[str] = mapped_column(String, primary_key=True)
    payment_id: Mapped[str] = mapped_column(String, ForeignKey("payments.payment_id"), nullable=False)
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.order_id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # ReconciliationStatus value
    method: Mapped[str] = mapped_column(String, nullable=False)
    relationship_type: Mapped[str] = mapped_column(String, nullable=False)  # RelationshipType value
    matched_settlement_ids_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    matched_bank_txn_ids_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    matched_refund_ids_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    score: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    candidates_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    why_matched_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    why_not_matched_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    differences_json: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    financial_impact: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    engine_version: Mapped[str] = mapped_column(String, nullable=False)


class AuditEventRecord(Base):
    """The persistent, append-only audit ledger (M6). Every row is written
    exactly once by `app.audit.ledger.AuditLedger.append` -- no code path
    anywhere in this project issues an UPDATE or DELETE against this table;
    a correction is always a NEW event, never a mutation of an old one.

    `previous_event_hash`/`event_hash` are computed by the ledger itself
    (see app.audit.hashing) -- callers never supply these directly.
    """

    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Explicitly assigned by AuditLedger.append (max(sequence)+1), NOT relied
    # on as a DB autoincrement -- `event_id` is already the primary key, and
    # SQLite/SQLAlchemy autoincrement semantics only apply to a single
    # integer primary key column, not a secondary one. `sequence` exists so
    # chain order can be verified even if timestamps ever tie.
    sequence: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    # Indexed: get_decision_provenance/events_for_entity and
    # events_for_correlation are the two hot query paths a demo/UI actually
    # calls per-exception; without an index both were full-table scans that
    # grew linearly with total ledger size (found via the 100,000-event
    # benchmark: get_decision_provenance rose to ~1.5s unindexed). This is a
    # plain B-tree index, not new infrastructure.
    entity_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(String, nullable=False)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    previous_event_hash: Mapped[str] = mapped_column(String, nullable=False)
    event_hash: Mapped[str] = mapped_column(String, nullable=False)


class RawRecord(Base):
    """Untouched original payload for every ingested row, in every source.
    Never updated once written -- normalization/validation results live only
    in the typed tables above, never here."""

    __tablename__ = "raw_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)  # "order" | "payment" | ...
    record_ref: Mapped[str] = mapped_column(String, nullable=False)  # the stable id, e.g. ORD-00001
    raw_json: Mapped[str] = mapped_column(String, nullable=False)  # Decimal-safe JSON, untouched
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
