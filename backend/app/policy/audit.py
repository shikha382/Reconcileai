"""Audit-ready decision events. NOT the final immutable hash-chain ledger
(that's a later milestone) -- these are the structured events that ledger
will eventually seal. Every important state change in the M5 flow produces
one of these, with a correlation_id tying every event for one exception
together.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.policy.schemas import Actor, AuditEvent, AuditEventType


def make_event(event_type: AuditEventType, entity_id: str, actor: Actor, payload: dict, correlation_id: str, source: str = "reconcileai") -> AuditEvent:
    return AuditEvent(
        event_type=event_type, entity_id=entity_id, actor_type=actor.actor_type, actor_id=actor.actor_id,
        source=source, payload=payload, correlation_id=correlation_id,
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
    )
