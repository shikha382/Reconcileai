"""verify_chain: must detect every tamper type from the M6 brief's Phase 18
list -- payload modification, timestamp modification, actor modification,
event_type modification, forged previous_hash, deletion, insertion,
reordering -- plus malformed JSON, and must confirm VALID on an untouched
chain and on an empty ledger."""
import json

from app.audit.ledger import AuditLedger
from app.audit.verify import verify_chain
from app.db.models import AuditEventRecord


def _build_chain(session, n=5):
    ledger = AuditLedger(session)
    records = []
    for i in range(n):
        records.append(ledger.append(
            "EXCEPTION_CREATED", "exception", f"EXC-{i}", "SYSTEM", "test", {"i": i}, f"CORR-{i}", "tester",
        ))
    session.commit()
    return records


def test_empty_ledger_is_valid(db_session):
    result = verify_chain(db_session)
    assert result.valid is True
    assert result.events_checked == 0
    assert result.reason == "EMPTY_LEDGER"


def test_untouched_chain_is_valid(db_session):
    _build_chain(db_session, n=5)
    result = verify_chain(db_session)
    assert result.valid is True
    assert result.events_checked == 5


def test_detects_payload_modification(db_session):
    records = _build_chain(db_session)
    victim = records[2]
    payload = json.loads(victim.payload_json)
    payload["i"] = "tampered"
    victim.payload_json = json.dumps(payload, sort_keys=True)
    db_session.commit()

    result = verify_chain(db_session)
    assert result.valid is False
    assert result.reason == "HASH_MISMATCH"
    assert result.first_invalid_event_id == victim.event_id


def test_detects_timestamp_modification(db_session):
    from datetime import timedelta
    records = _build_chain(db_session)
    victim = records[1]
    victim.timestamp = victim.timestamp + timedelta(days=1)
    db_session.commit()

    result = verify_chain(db_session)
    assert result.valid is False
    assert result.reason == "HASH_MISMATCH"
    assert result.first_invalid_event_id == victim.event_id


def test_detects_actor_modification(db_session):
    records = _build_chain(db_session)
    victim = records[3]
    victim.actor_type = "AI"  # was SYSTEM
    db_session.commit()

    result = verify_chain(db_session)
    assert result.valid is False
    assert result.reason == "HASH_MISMATCH"
    assert result.first_invalid_event_id == victim.event_id


def test_detects_event_type_modification(db_session):
    records = _build_chain(db_session)
    victim = records[0]
    victim.event_type = "SOMETHING_ELSE"
    db_session.commit()

    result = verify_chain(db_session)
    assert result.valid is False
    assert result.reason == "HASH_MISMATCH"
    assert result.first_invalid_event_id == victim.event_id


def test_detects_forged_previous_hash(db_session):
    records = _build_chain(db_session)
    victim = records[2]
    victim.previous_event_hash = "f" * 64
    db_session.commit()

    result = verify_chain(db_session)
    assert result.valid is False
    assert result.reason == "PREVIOUS_HASH_MISMATCH"
    assert result.first_invalid_event_id == victim.event_id


def test_detects_event_deletion(db_session):
    records = _build_chain(db_session)
    victim = records[2]
    db_session.delete(victim)
    db_session.commit()

    result = verify_chain(db_session)
    assert result.valid is False
    # Deleting a middle event leaves a gap in the sequence column (the
    # surviving next event's sequence number is no longer contiguous) --
    # caught before the hash/previous-hash checks even run.
    assert result.reason == "SEQUENCE_GAP_OR_REORDER"


def test_detects_event_reordering(db_session):
    records = _build_chain(db_session)
    a, b = records[1], records[2]
    a_seq, b_seq = a.sequence, b.sequence
    # A direct a<->b swap would transiently violate the sequence column's
    # unique constraint, so swap via an unused placeholder value, flushing
    # between steps (this is purely a test-harness mechanic to construct the
    # tampered state -- verify_chain itself is what's under test).
    a.sequence = -1
    db_session.flush()
    b.sequence = a_seq
    db_session.flush()
    a.sequence = b_seq
    db_session.commit()

    result = verify_chain(db_session)
    assert result.valid is False
    assert result.reason in ("SEQUENCE_GAP_OR_REORDER", "PREVIOUS_HASH_MISMATCH", "HASH_MISMATCH")


def test_detects_sequence_gap_from_manual_insertion(db_session):
    from datetime import datetime, timezone

    records = _build_chain(db_session)
    # Manually insert a row that skips a sequence number, bypassing
    # AuditLedger.append entirely (simulating direct table tampering).
    rogue = AuditEventRecord(
        event_id="EVT-rogue0000000", sequence=records[-1].sequence + 2, event_type="FORGED",
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None), entity_type="exception", entity_id="EXC-rogue",
        actor_type="SYSTEM", actor_id=None, source="attacker", correlation_id="CORR-rogue",
        payload_json="{}", schema_version="1.0.0", previous_event_hash=records[-1].event_hash, event_hash="0" * 64,
    )
    db_session.add(rogue)
    db_session.commit()

    result = verify_chain(db_session)
    assert result.valid is False
    assert result.reason == "SEQUENCE_GAP_OR_REORDER"


def test_detects_malformed_json_payload_without_crashing(db_session):
    records = _build_chain(db_session)
    victim = records[1]
    victim.payload_json = "{not valid json"
    db_session.commit()

    result = verify_chain(db_session)  # must not raise
    assert result.valid is False
    assert result.reason == "PAYLOAD_UNPARSEABLE"
    assert result.first_invalid_event_id == victim.event_id
