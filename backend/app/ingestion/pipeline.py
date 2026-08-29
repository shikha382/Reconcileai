"""Ingestion pipeline: INGEST -> (store raw) -> NORMALIZE -> VALIDATE -> persist.

This is a plain, importable Python pipeline, not yet an HTTP endpoint -- no
caller (frontend/dashboard) exists yet to need one over HTTP. An API wrapper
belongs to whichever later milestone actually serves it (see PROJECT_PLAN.md
M2/M16); wrapping this in FastAPI now would be scaffolding nothing calls.

Idempotent: re-running against the same source directory does not create
duplicate rows, because every entity table is keyed on the same deterministic
ID the generator assigned, and persistence uses an upsert (session.merge).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import BankTransaction, FeeRule, Order, Payment, RawRecord, Refund, Settlement
from app.engines.normalization import normalize_record
from app.engines.validation import ValidationReport, validate_batch
from shared.money import dumps, loads

SOURCE_FILES = {
    "order": "orders.json",
    "payment": "payments.json",
    "settlement": "settlements.json",
    "bank_transaction": "bank_transactions.json",
    "refund": "refunds.json",
    "fee_rule": "fee_rules.json",
}

_ID_FIELD = {
    "order": "order_id",
    "payment": "payment_id",
    "settlement": "settlement_id",
    "bank_transaction": "bank_txn_id",
    "refund": "refund_id",
    "fee_rule": "fee_rule_id",
}


@dataclass
class IngestionReport:
    counts: dict[str, int] = field(default_factory=dict)
    validation_reports: dict[str, ValidationReport] = field(default_factory=dict)

    @property
    def total_ingested(self) -> int:
        return sum(self.counts.values())

    @property
    def all_valid(self) -> bool:
        return all(r.is_valid for r in self.validation_reports.values())


def _to_orm(source_type: str, model) -> object:
    m = model.model_dump()
    metadata_json = dumps(m.pop("metadata", {}))

    if source_type == "order":
        return Order(**m, metadata_json=metadata_json)
    if source_type == "payment":
        return Payment(**m, metadata_json=metadata_json)
    if source_type == "settlement":
        return Settlement(**m, metadata_json=metadata_json)
    if source_type == "bank_transaction":
        return BankTransaction(**m, metadata_json=metadata_json)
    if source_type == "refund":
        return Refund(**m, metadata_json=metadata_json)
    if source_type == "fee_rule":
        return FeeRule(**m)
    raise ValueError(f"unknown source_type {source_type!r}")


def _store_raw(session: Session, source_type: str, raw: dict) -> None:
    session.add(
        RawRecord(
            source_type=source_type,
            record_ref=raw.get(_ID_FIELD[source_type], ""),
            raw_json=dumps(raw),
            ingested_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )


def ingest_records(session: Session, source_type: str, raw_records: list[dict], *, raise_on_invalid: bool = True) -> ValidationReport:
    """The shared core of the INGEST -> (store raw) -> NORMALIZE -> VALIDATE
    -> persist flow, factored out (Milestone 14) so a caller with raw
    records already in memory -- e.g. `app.adapters.pipeline.ingest_from_provider`,
    which maps external provider payloads into this exact canonical shape --
    can reuse the IDENTICAL validation/normalization/persistence path
    `ingest_source_directory` already used, rather than a second,
    duplicate one. No behavior changed for the existing file-based caller
    below; this is a pure extraction."""
    for raw in raw_records:
        _store_raw(session, source_type, raw)

    normalized = [normalize_record(source_type, raw) for raw in raw_records]
    validation_report = validate_batch(source_type, normalized, raise_on_error=raise_on_invalid)

    for _, model in validation_report.valid_records:
        session.merge(_to_orm(source_type, model))

    return validation_report


def ingest_source_directory(session: Session, source_dir: Path, *, raise_on_invalid: bool = True) -> IngestionReport:
    report = IngestionReport()

    for source_type, filename in SOURCE_FILES.items():
        path = source_dir / filename
        if not path.exists():
            report.counts[source_type] = 0
            continue

        raw_records: list[dict] = loads(path.read_text(encoding="utf-8"))
        validation_report = ingest_records(session, source_type, raw_records, raise_on_invalid=raise_on_invalid)
        report.validation_reports[source_type] = validation_report
        report.counts[source_type] = len(validation_report.valid_records)

    return report
