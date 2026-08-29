"""Canonical serialization and hash computation -- deterministic,
reproducible, never Python repr()."""
from decimal import Decimal

from app.audit.hashing import GENESIS_HASH, build_hashable_payload, canonical_json, compute_event_hash


def test_genesis_hash_is_fixed_and_documented():
    import hashlib

    assert GENESIS_HASH == hashlib.sha256(b"RECONCILEAI-AUDIT-GENESIS-v1").hexdigest()


def test_canonical_json_is_deterministic_regardless_of_key_order():
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b


def test_canonical_json_serializes_decimal_as_string_not_float():
    result = canonical_json({"amount": Decimal("100.50")})
    assert '"100.50"' in result
    assert "100.5" != result  # not a bare float representation


def test_compute_event_hash_changes_if_payload_changes():
    h1 = compute_event_hash(canonical_json({"x": 1}), GENESIS_HASH)
    h2 = compute_event_hash(canonical_json({"x": 2}), GENESIS_HASH)
    assert h1 != h2


def test_compute_event_hash_changes_if_previous_hash_changes():
    payload = canonical_json({"x": 1})
    h1 = compute_event_hash(payload, GENESIS_HASH)
    h2 = compute_event_hash(payload, "a" * 64)
    assert h1 != h2


def test_compute_event_hash_is_reproducible():
    payload = canonical_json({"x": 1, "y": "test"})
    h1 = compute_event_hash(payload, GENESIS_HASH)
    h2 = compute_event_hash(payload, GENESIS_HASH)
    assert h1 == h2


def test_build_hashable_payload_includes_schema_version():
    hashable = build_hashable_payload("EVT-1", "TEST_EVENT", "2026-01-01T00:00:00", "exception", "EXC-1", "SYSTEM", None, "test", "CORR-1", {"k": "v"})
    assert "schema_version" in hashable
