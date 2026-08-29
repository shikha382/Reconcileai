"""Phase 9/10/19: wires the adapter (retrieval + mapping) into the
EXISTING, unmodified M1 ingestion path (`app.ingestion.pipeline.ingest_records`)
-- never a parallel database-insert path. The flow is exactly:

EXTERNAL DATA -> ADAPTER (fetch) -> MAPPING (translate) -> ingest_records
    (store raw, normalize, validate, persist -- all pre-existing M1 code)

A record that fails mapping (Phase 5: "if a field cannot be mapped safely,
mark it unsupported/missing, do not guess") never reaches `ingest_records`
at all -- it is counted and reported as a mapping rejection, distinct from
a validation rejection, so the two failure classes are never conflated.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy.orm import Session

from app.adapters.base import CANONICAL_SOURCE_KEY, SourceType
from app.adapters.errors import ProviderError
from app.adapters.razorpay_adapter import RazorpayAdapter
from app.adapters.razorpay_mapping import MAPPERS
from app.engines.validation import ValidationReport
from app.ingestion.pipeline import ingest_records


@dataclass
class ProviderOperationLog:
    """Phase 19 observability record -- NOT a second audit mechanism (Phase
    20's own instruction). This is plain, in-memory, structured operational
    metadata about one provider fetch: never a financial-decision event, so
    it is deliberately never written to app.audit.ledger.AuditLedger (that
    ledger's meaning is decision provenance, not infrastructure operations,
    and mixing the two would blur it). Contains no secret, no raw
    authorization header, no full financial payload -- only counts and
    category-level outcome."""

    provider: str
    operation: str
    correlation_id: str
    duration_seconds: float
    record_count: int
    success: bool
    error_category: str | None = None


@dataclass
class ProviderIngestionReport:
    mapping_rejections: dict[str, list[str]] = field(default_factory=dict)  # source_type -> [rejection reasons]
    validation_reports: dict[str, ValidationReport] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    operation_logs: list[ProviderOperationLog] = field(default_factory=list)

    @property
    def total_ingested(self) -> int:
        return sum(self.counts.values())

    @property
    def all_valid(self) -> bool:
        return all(r.is_valid for r in self.validation_reports.values())


def ingest_from_provider(
    session: Session,
    adapter: RazorpayAdapter,
    source_types: list[SourceType] | None = None,
    *,
    raise_on_invalid: bool = False,
) -> ProviderIngestionReport:
    """Fetches every configured source type from `adapter`, maps each raw
    record into the canonical shape, and feeds the mapped records through
    the EXACT SAME `ingest_records` (app.ingestion.pipeline, M1, unmodified)
    every file-based ingestion already uses. `raise_on_invalid` defaults to
    False here (unlike the file-based entry point) because a live/fixture
    provider feed is expected to occasionally contain a record this system
    correctly refuses -- that is a normal, safe outcome (Phase 11: "safe
    validation failure"), not a reason to abort the whole batch."""
    report = ProviderIngestionReport()
    correlation_id = f"PROV-{uuid4().hex[:16]}"

    for source_type_enum in source_types or list(SourceType):
        canonical_key = CANONICAL_SOURCE_KEY[source_type_enum]
        mapper = MAPPERS[canonical_key]
        started = time.monotonic()
        try:
            raw_records = adapter.fetch_records(canonical_key)
        except ProviderError as exc:
            report.operation_logs.append(
                ProviderOperationLog(
                    provider="razorpay", operation=f"fetch:{canonical_key}", correlation_id=correlation_id,
                    duration_seconds=time.monotonic() - started, record_count=0, success=False, error_category=exc.category,
                )
            )
            report.counts[canonical_key] = 0
            continue

        canonical_records: list[dict] = []
        rejections: list[str] = []
        for raw in raw_records:
            result = mapper(raw)
            if result.ok:
                canonical_records.append(result.canonical)
            else:
                rejections.append(result.rejection_reason or "unknown mapping failure")
        report.mapping_rejections[canonical_key] = rejections

        validation_report = ingest_records(session, canonical_key, canonical_records, raise_on_invalid=raise_on_invalid)
        report.validation_reports[canonical_key] = validation_report
        report.counts[canonical_key] = len(validation_report.valid_records)

        report.operation_logs.append(
            ProviderOperationLog(
                provider="razorpay", operation=f"fetch:{canonical_key}", correlation_id=correlation_id,
                duration_seconds=time.monotonic() - started, record_count=len(raw_records), success=True,
            )
        )

    return report
