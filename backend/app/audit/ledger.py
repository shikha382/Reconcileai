"""The AuditLedger -- the ONLY code path allowed to write to the audit_events
table. Deliberately has no update/delete method at all (not merely
"unauthorized" -- structurally absent, the same design discipline M4 used
for `test_hypothesis` not being a callable tool). Every append computes the
hash chain itself; callers cannot supply `previous_event_hash`/`event_hash`.

Transactional consistency (Phase 15): `append` takes the caller's SQLAlchemy
`Session` and adds the row to it but does NOT commit -- the caller commits
the audit event in the SAME transaction as whatever decision/state change it
documents (decision state change + audit event succeed or fail together).
If the caller's commit fails, both roll back together; the ledger never
silently swallows a persistence failure and reports success. See
docs/audit-ledger.md's "transaction boundary" section for the exact
guarantee and its limits.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.hashing import GENESIS_HASH, build_hashable_payload, canonical_json, compute_event_hash
from app.db.models import AuditEventRecord
from shared.money import dumps


class AuditAppendError(Exception):
    """Raised when an event cannot be safely appended (e.g. the caller
    attempted to supply a hash field, or the ledger's own state couldn't be
    read to determine the next sequence/previous hash). Callers MUST NOT
    catch this and proceed as if the decision succeeded -- see Phase 15."""


_FORBIDDEN_CALLER_FIELDS = {"previous_event_hash", "event_hash", "sequence", "event_id"}


class AuditLedger:
    def __init__(self, session: Session):
        self._session = session

    def _last_event(self) -> AuditEventRecord | None:
        stmt = select(AuditEventRecord).order_by(AuditEventRecord.sequence.desc()).limit(1)
        return self._session.execute(stmt).scalar_one_or_none()

    def append(
        self, event_type: str, entity_type: str, entity_id: str, actor_type: str, source: str,
        payload: dict, correlation_id: str, actor_id: str | None = None,
    ) -> AuditEventRecord:
        for forbidden in _FORBIDDEN_CALLER_FIELDS:
            if forbidden in payload:
                raise AuditAppendError(f"payload must not include {forbidden!r} -- the ledger computes it")

        try:
            last = self._last_event()
        except Exception as exc:  # defensive: a read failure must not be treated as "no history"
            raise AuditAppendError(f"could not determine ledger state before append: {exc}") from exc

        previous_hash = last.event_hash if last is not None else GENESIS_HASH
        next_sequence = (last.sequence + 1) if last is not None else 1

        event_id = f"EVT-{uuid4().hex[:16]}"
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None)
        timestamp_iso = timestamp.isoformat()

        hashable = build_hashable_payload(
            event_id, event_type, timestamp_iso, entity_type, entity_id,
            actor_type, actor_id, source, correlation_id, payload,
        )
        canonical = canonical_json(hashable)
        event_hash = compute_event_hash(canonical, previous_hash)

        record = AuditEventRecord(
            event_id=event_id, sequence=next_sequence, event_type=event_type, timestamp=timestamp,
            entity_type=entity_type, entity_id=entity_id, actor_type=actor_type, actor_id=actor_id,
            source=source, correlation_id=correlation_id, payload_json=dumps(payload),
            schema_version=hashable["schema_version"], previous_event_hash=previous_hash, event_hash=event_hash,
        )
        self._session.add(record)
        return record

    def events_for_correlation(self, correlation_id: str) -> list[AuditEventRecord]:
        stmt = select(AuditEventRecord).where(AuditEventRecord.correlation_id == correlation_id).order_by(AuditEventRecord.sequence)
        return list(self._session.execute(stmt).scalars().all())

    def events_for_entity(self, entity_id: str) -> list[AuditEventRecord]:
        stmt = select(AuditEventRecord).where(AuditEventRecord.entity_id == entity_id).order_by(AuditEventRecord.sequence)
        return list(self._session.execute(stmt).scalars().all())

    def all_events(self) -> list[AuditEventRecord]:
        stmt = select(AuditEventRecord).order_by(AuditEventRecord.sequence)
        return list(self._session.execute(stmt).scalars().all())

    def count(self) -> int:
        return self._session.execute(select(func.count()).select_from(AuditEventRecord)).scalar_one()
