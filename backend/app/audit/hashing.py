"""Deterministic canonical serialization and hash-chaining for the audit
ledger. Per CLAUDE.md's original audit-hash-chaining decision (M1
planning): tamper-EVIDENT, not a cryptographic non-repudiation system --
never oversell it as more than that.

Algorithm (documented precisely, per the M6 brief's instruction):

    event_hash = SHA256(canonical_event_data_utf8 + previous_event_hash_utf8)

`canonical_event_data` is produced by `canonical_json`: UTF-8, sorted keys,
compact deterministic separators (`,` / `:`, no extra whitespace), Decimal
values serialized as fixed-point strings (never float/repr), and an
explicit `schema_version` field included in what gets hashed. Never hash
Python `repr()` -- object identity/memory addresses would make the hash
irreproducible and worthless as evidence.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

SCHEMA_VERSION = "1.0.0"
GENESIS_SEED = "RECONCILEAI-AUDIT-GENESIS-v1"
GENESIS_HASH = hashlib.sha256(GENESIS_SEED.encode("utf-8")).hexdigest()


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable in an audit event")


def canonical_json(data: dict) -> str:
    """Sorted keys, compact separators, UTF-8-safe, Decimal-as-string.
    The SAME input always produces the SAME bytes, on any machine, any
    Python version -- this is the property the hash chain depends on."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_json_default, ensure_ascii=True)


def compute_event_hash(canonical_event_data: str, previous_event_hash: str) -> str:
    payload = (canonical_event_data + previous_event_hash).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_hashable_payload(
    event_id: str, event_type: str, timestamp_iso: str, entity_type: str, entity_id: str,
    actor_type: str, actor_id: str | None, source: str, correlation_id: str, payload: dict,
) -> dict:
    """Exactly what gets hashed -- every field that would need to be
    tamper-evident. `schema_version` is included explicitly so a future
    schema change can never silently reinterpret an old event's bytes."""
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id, "event_type": event_type, "timestamp": timestamp_iso,
        "entity_type": entity_type, "entity_id": entity_id, "actor_type": actor_type,
        "actor_id": actor_id, "source": source, "correlation_id": correlation_id, "payload": payload,
    }
