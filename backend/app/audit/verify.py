"""Chain verification. Recomputes every event's hash from its own stored
fields and checks it against the stored `event_hash`, AND checks that each
event's stored `previous_event_hash` actually equals the prior event's
`event_hash` (catches reordering/insertion/deletion, which a per-event hash
check alone would miss if an attacker recomputed a single event's hash
in isolation without fixing up its neighbors), AND checks the `sequence`
column is perfectly contiguous starting at 1 (catches deletion/insertion/
reordering even more directly, independent of the hash check).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.audit.hashing import GENESIS_HASH, build_hashable_payload, canonical_json, compute_event_hash
from app.audit.ledger import AuditLedger
from shared.money import loads


@dataclass
class ChainVerificationResult:
    valid: bool
    events_checked: int
    first_invalid_event_id: str | None = None
    reason: str | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid, "events_checked": self.events_checked,
            "first_invalid_event_id": self.first_invalid_event_id, "reason": self.reason, "details": self.details,
        }


def verify_chain(session: Session) -> ChainVerificationResult:
    events = AuditLedger(session).all_events()

    if not events:
        return ChainVerificationResult(valid=True, events_checked=0, reason="EMPTY_LEDGER")

    expected_sequence = 1
    expected_previous_hash = GENESIS_HASH

    for event in events:
        if event.sequence != expected_sequence:
            return ChainVerificationResult(
                valid=False, events_checked=expected_sequence - 1, first_invalid_event_id=event.event_id,
                reason="SEQUENCE_GAP_OR_REORDER",
                details={"expected_sequence": expected_sequence, "actual_sequence": event.sequence},
            )

        if event.previous_event_hash != expected_previous_hash:
            return ChainVerificationResult(
                valid=False, events_checked=expected_sequence - 1, first_invalid_event_id=event.event_id,
                reason="PREVIOUS_HASH_MISMATCH",
                details={"expected_previous_hash": expected_previous_hash, "actual_previous_hash": event.previous_event_hash},
            )

        try:
            payload = loads(event.payload_json)
        except (ValueError, TypeError) as exc:
            # A tampered payload isn't guaranteed to still be valid JSON --
            # this must be reported as an invalid chain, never an unhandled
            # crash (fail-safe: verification itself must not blow up on
            # exactly the input it exists to catch).
            return ChainVerificationResult(
                valid=False, events_checked=expected_sequence - 1, first_invalid_event_id=event.event_id,
                reason="PAYLOAD_UNPARSEABLE", details={"error": str(exc)},
            )
        hashable = build_hashable_payload(
            event.event_id, event.event_type, event.timestamp.isoformat(), event.entity_type, event.entity_id,
            event.actor_type, event.actor_id, event.source, event.correlation_id, payload,
        )
        # The stored schema_version must be used for recomputation, not the
        # current SCHEMA_VERSION constant -- an old event hashed under an
        # older schema must still reproduce its original hash.
        hashable["schema_version"] = event.schema_version
        recomputed_hash = compute_event_hash(canonical_json(hashable), event.previous_event_hash)

        if recomputed_hash != event.event_hash:
            return ChainVerificationResult(
                valid=False, events_checked=expected_sequence - 1, first_invalid_event_id=event.event_id,
                reason="HASH_MISMATCH",
                details={"expected_hash": event.event_hash, "recomputed_hash": recomputed_hash},
            )

        expected_previous_hash = event.event_hash
        expected_sequence += 1

    return ChainVerificationResult(valid=True, events_checked=len(events))
