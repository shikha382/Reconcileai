"""AuditLedger: append-only enforcement, hash-chain construction, forbidden
caller fields, and the query surface (correlation/entity/all)."""
import pytest

from app.audit.hashing import GENESIS_HASH
from app.audit.ledger import AuditAppendError, AuditLedger
from app.db.models import AuditEventRecord


def _append(ledger, correlation_id="CORR-1", entity_id="EXC-1", payload=None):
    return ledger.append(
        "EXCEPTION_CREATED", "exception", entity_id, "SYSTEM", "test", payload or {"k": "v"}, correlation_id, "tester",
    )


def test_ledger_has_no_update_or_delete_method():
    # Structurally absent -- not merely unauthorized. Mirrors M4's
    # `test_hypothesis` not being an offered tool at all.
    assert not hasattr(AuditLedger, "update")
    assert not hasattr(AuditLedger, "delete")
    assert not hasattr(AuditLedger, "update_event")
    assert not hasattr(AuditLedger, "delete_event")


def test_first_event_chains_to_genesis_hash(db_session):
    ledger = AuditLedger(db_session)
    record = _append(ledger)
    db_session.commit()
    assert record.previous_event_hash == GENESIS_HASH
    assert record.sequence == 1


def test_second_event_chains_to_first_event_hash(db_session):
    ledger = AuditLedger(db_session)
    first = _append(ledger)
    db_session.commit()
    second = _append(ledger)
    db_session.commit()
    assert second.previous_event_hash == first.event_hash
    assert second.sequence == 2


@pytest.mark.parametrize("forbidden", ["previous_event_hash", "event_hash", "sequence", "event_id"])
def test_append_rejects_caller_supplied_hash_fields(db_session, forbidden):
    ledger = AuditLedger(db_session)
    with pytest.raises(AuditAppendError):
        ledger.append("EXCEPTION_CREATED", "exception", "EXC-1", "SYSTEM", "test", {forbidden: "attacker-supplied"}, "CORR-1")


def test_events_for_correlation_returns_only_matching_events_in_order(db_session):
    ledger = AuditLedger(db_session)
    _append(ledger, correlation_id="CORR-A", entity_id="EXC-A")
    _append(ledger, correlation_id="CORR-B", entity_id="EXC-B")
    _append(ledger, correlation_id="CORR-A", entity_id="EXC-A")
    db_session.commit()

    events = ledger.events_for_correlation("CORR-A")
    assert len(events) == 2
    assert [e.sequence for e in events] == sorted(e.sequence for e in events)


def test_events_for_entity_returns_only_matching_events(db_session):
    ledger = AuditLedger(db_session)
    _append(ledger, entity_id="EXC-X")
    _append(ledger, entity_id="EXC-Y")
    _append(ledger, entity_id="EXC-X")
    db_session.commit()

    events = ledger.events_for_entity("EXC-X")
    assert len(events) == 2
    assert all(e.entity_id == "EXC-X" for e in events)


def test_count_reflects_total_appended_events(db_session):
    ledger = AuditLedger(db_session)
    assert ledger.count() == 0
    _append(ledger)
    _append(ledger)
    db_session.commit()
    assert ledger.count() == 2


def test_event_ids_are_unique_across_appends(db_session):
    ledger = AuditLedger(db_session)
    ids = set()
    for _ in range(5):
        record = _append(ledger)
        ids.add(record.event_id)
    db_session.commit()
    assert len(ids) == 5


def test_sequence_is_explicit_not_autoincrement_pk(db_session):
    # event_id (a string) is the PK; sequence is a separately-assigned,
    # explicitly-tracked integer column -- SQLite autoincrement only
    # applies to a single-column integer PK, which event_id is not.
    ledger = AuditLedger(db_session)
    _append(ledger)
    _append(ledger)
    db_session.commit()
    rows = db_session.query(AuditEventRecord).order_by(AuditEventRecord.sequence).all()
    assert [r.sequence for r in rows] == [1, 2]
