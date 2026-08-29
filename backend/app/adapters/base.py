"""Milestone 14: the provider/source adapter boundary. Nothing in this
package (or any module under `app.adapters`) performs matching, risk
scoring, policy evaluation, decision-making, AI reasoning, or priority
calculation -- an adapter's only job is DATA TRANSLATION: external
provider payload -> the exact canonical dict shape `app.schemas.records`
already validates. Everything downstream of that (validation,
normalization, ingestion, reconciliation, exception intelligence,
decision) is the existing, unmodified M1-M13 system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SourceType(str, Enum):
    """Named external source types (Phase 2). Deliberately small and
    provider-neutral -- the canonical internal representation
    (app.schemas.records) never varies by source; only the mapping INTO it
    does."""

    RAZORPAY_PAYMENT = "RAZORPAY_PAYMENT"
    RAZORPAY_SETTLEMENT = "RAZORPAY_SETTLEMENT"
    BANK_TRANSACTION = "BANK_TRANSACTION"
    INTERNAL_ORDER = "INTERNAL_ORDER"
    REFUND = "REFUND"


# Maps each external SourceType onto the existing M1 canonical source_type
# key (app.ingestion.pipeline.SOURCE_FILES / app.schemas.records.SCHEMA_BY_SOURCE)
# -- no second taxonomy, just a name-to-name lookup.
CANONICAL_SOURCE_KEY = {
    SourceType.RAZORPAY_PAYMENT: "payment",
    SourceType.RAZORPAY_SETTLEMENT: "settlement",
    SourceType.BANK_TRANSACTION: "bank_transaction",
    SourceType.INTERNAL_ORDER: "order",
    SourceType.REFUND: "refund",
}


class ProviderMode(str, Enum):
    """Phase 16/23: the only three modes an adapter can honestly report.
    Default is always FIXTURE -- never LIVE unless real, working
    credentials were actually supplied AND a real call actually succeeded."""

    FIXTURE = "FIXTURE"
    MOCK = "MOCK"
    LIVE = "LIVE"


@dataclass
class FieldMapping:
    """Phase 5's own required shape for documenting a mapping: source field
    -> canonical field -> transformation -> validation. Populated by each
    mapping function so the mapping is inspectable, not just implicit code."""

    source_field: str
    canonical_field: str
    transformation: str
    validation: str


@dataclass
class MappingResult:
    """The result of mapping ONE external record. `canonical` is the dict
    ready for app.engines.normalization.normalize_record; `unsupported` lists
    any financially-meaningful field that could NOT be safely mapped
    (Phase 5: "if a field cannot be mapped safely: mark it as unsupported/
    missing. Do not guess.") -- never silently dropped."""

    canonical: dict | None
    field_mappings: list[FieldMapping] = field(default_factory=list)
    unsupported_fields: list[str] = field(default_factory=list)
    rejection_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.canonical is not None and self.rejection_reason is None
