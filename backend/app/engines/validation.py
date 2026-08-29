"""Validation stage: runs each normalized record through its Pydantic schema
and collects every failure, rather than raising on the first bad record --
so a batch-level validation report can show everything wrong at once.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ValidationError

from app.schemas.records import SCHEMA_BY_SOURCE


@dataclass
class RecordValidationError:
    source_type: str
    record_ref: str | None
    errors: list[str]


@dataclass
class ValidationReport:
    valid_records: list[tuple[str, object]] = field(default_factory=list)  # (source_type, validated_model)
    failures: list[RecordValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.failures


class DataValidationError(Exception):
    """Raised when validate_batch(..., raise_on_error=True) finds any failure.
    Carries the full ValidationReport so callers can inspect every issue."""

    def __init__(self, report: ValidationReport):
        self.report = report
        summary = "; ".join(
            f"{f.source_type}:{f.record_ref}: {f.errors}" for f in report.failures
        )
        super().__init__(f"{len(report.failures)} record(s) failed validation: {summary}")


def _record_ref(source_type: str, raw: dict) -> str | None:
    id_field = {
        "order": "order_id",
        "payment": "payment_id",
        "settlement": "settlement_id",
        "bank_transaction": "bank_txn_id",
        "refund": "refund_id",
        "fee_rule": "fee_rule_id",
    }.get(source_type)
    return raw.get(id_field) if id_field else None


def validate_record(source_type: str, normalized: dict):
    """Validates a single normalized record. Returns the validated Pydantic
    model on success; raises pydantic.ValidationError on failure."""
    schema = SCHEMA_BY_SOURCE[source_type]
    return schema.model_validate(normalized)


def validate_batch(source_type: str, normalized_records: list[dict], *, raise_on_error: bool = False) -> ValidationReport:
    report = ValidationReport()
    for raw in normalized_records:
        try:
            model = validate_record(source_type, raw)
            report.valid_records.append((source_type, model))
        except ValidationError as exc:
            report.failures.append(
                RecordValidationError(
                    source_type=source_type,
                    record_ref=_record_ref(source_type, raw),
                    errors=[e["msg"] for e in exc.errors()],
                )
            )
    if raise_on_error and report.failures:
        raise DataValidationError(report)
    return report
