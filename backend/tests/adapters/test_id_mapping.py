"""Phase 8/32: identifier translation tests."""
import re

import pytest

from app.adapters.id_mapping import external_id_to_canonical


def test_mapping_is_deterministic():
    a = external_id_to_canonical("payment", "pay_RAZ0000001AA")
    b = external_id_to_canonical("payment", "pay_RAZ0000001AA")
    assert a == b


def test_different_external_ids_map_differently():
    a = external_id_to_canonical("payment", "pay_RAZ0000001AA")
    b = external_id_to_canonical("payment", "pay_RAZ0000002BB")
    assert a != b


def test_output_matches_the_required_schema_regex():
    canonical = external_id_to_canonical("payment", "pay_RAZ0000001AA")
    assert re.match(r"^PAY-\d{5}$", canonical)

    assert re.match(r"^ORD-\d{5}$", external_id_to_canonical("order", "order_x"))
    assert re.match(r"^STL-\d{5}$", external_id_to_canonical("settlement", "setl_x"))
    assert re.match(r"^BANKTXN-\d{5}$", external_id_to_canonical("bank_transaction", "txn_x"))
    assert re.match(r"^REF-\d{5}$", external_id_to_canonical("refund", "rfnd_x"))


def test_same_external_id_different_source_types_do_not_collide_in_meaning():
    # Same raw string, different source_type -- the prefix alone already
    # prevents any cross-entity confusion, and the hash also differs
    # because source_type is part of the hashed input.
    payment_side = external_id_to_canonical("payment", "shared_string")
    order_side = external_id_to_canonical("order", "shared_string")
    assert payment_side.split("-")[0] != order_side.split("-")[0]


def test_unknown_source_type_is_rejected():
    with pytest.raises(ValueError):
        external_id_to_canonical("not_a_real_type", "x")


def test_empty_external_id_is_rejected():
    with pytest.raises(ValueError):
        external_id_to_canonical("payment", "")


def test_harmless_formatting_noise_does_not_collapse_genuinely_different_ids():
    # Phase 8's own requirement: normalization must not accidentally treat
    # two DIFFERENT real external IDs as the same record merely because
    # id_mapping (unlike normalize_reference) performs no fuzzy collapsing
    # at all -- it is an exact-string hash, so even a single differing
    # character produces an unrelated canonical ID.
    a = external_id_to_canonical("payment", "pay_ABCDEFGHIJKLM")
    b = external_id_to_canonical("payment", "pay_ABCDEFGHIJKLN")  # one character different
    assert a != b
