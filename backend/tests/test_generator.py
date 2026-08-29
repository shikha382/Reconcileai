from decimal import Decimal

from shared.taxonomy import ExceptionCategory, RecordArchetype

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data" / "synthetic"))
from generator import (  # noqa: E402
    ARCHETYPE_COUNTS,
    DEFAULT_SEED,
    TOTAL_ADVERSARIAL,
    TOTAL_RECORDS,
    generate_dataset,
)


def test_archetype_counts_sum_to_total():
    assert sum(ARCHETYPE_COUNTS.values()) == TOTAL_RECORDS == 300


def test_every_archetype_is_a_valid_taxonomy_value():
    valid = {a.value for a in RecordArchetype}
    assert set(ARCHETYPE_COUNTS.keys()) <= valid


def test_generation_is_deterministic_for_a_fixed_seed():
    d1 = generate_dataset(DEFAULT_SEED)
    d2 = generate_dataset(DEFAULT_SEED)
    assert d1.orders == d2.orders
    assert d1.payments == d2.payments
    assert d1.settlements == d2.settlements
    assert d1.bank_transactions == d2.bank_transactions
    assert d1.refunds == d2.refunds
    assert d1.ground_truth == d2.ground_truth


def test_different_seed_produces_different_output():
    d1 = generate_dataset(DEFAULT_SEED)
    d2 = generate_dataset(DEFAULT_SEED + 1)
    assert d1.orders != d2.orders


def test_dataset_has_exactly_300_orders_and_ground_truth_entries(small_dataset):
    assert len(small_dataset.orders) == 300
    assert len(small_dataset.ground_truth) == 300


def test_every_order_has_exactly_one_ground_truth_entry(small_dataset):
    order_ids = {o["order_id"] for o in small_dataset.orders}
    gt_order_ids = [g["order_id"] for g in small_dataset.ground_truth]
    assert len(gt_order_ids) == len(set(gt_order_ids)), "duplicate ground-truth entries found"
    assert set(gt_order_ids) == order_ids


def test_all_ids_are_unique_within_their_entity(small_dataset):
    assert len({o["order_id"] for o in small_dataset.orders}) == len(small_dataset.orders)
    assert len({p["payment_id"] for p in small_dataset.payments}) == len(small_dataset.payments)
    assert len({s["settlement_id"] for s in small_dataset.settlements}) == len(small_dataset.settlements)
    assert len({b["bank_txn_id"] for b in small_dataset.bank_transactions}) == len(small_dataset.bank_transactions)
    assert len({r["refund_id"] for r in small_dataset.refunds}) == len(small_dataset.refunds)


def test_every_exception_ground_truth_category_is_in_the_shared_taxonomy(small_dataset):
    valid_categories = {c.value for c in ExceptionCategory}
    for gt in small_dataset.ground_truth:
        if gt["category"] is not None:
            assert gt["category"] in valid_categories, gt


def test_exact_match_entries_have_no_category(small_dataset):
    exact = [g for g in small_dataset.ground_truth if g["archetype"] == "exact_match"]
    assert len(exact) == ARCHETYPE_COUNTS["exact_match"]
    assert all(g["category"] is None for g in exact)


def test_adversarial_count_matches_design(small_dataset):
    adversarial = [g for g in small_dataset.ground_truth if g["is_adversarial"]]
    assert len(adversarial) == TOTAL_ADVERSARIAL == 5
    # every adversarial case must NOT be expected to auto-resolve
    assert all(g["expected_action"] != "auto_resolve" for g in adversarial)


def test_missing_transaction_cases_have_no_settlement_or_bank_txn(small_dataset):
    missing = [g for g in small_dataset.ground_truth if g["archetype"] == "missing_transaction"]
    assert len(missing) == ARCHETYPE_COUNTS["missing_transaction"]
    for g in missing:
        assert g["true_matches"]["settlement_ids"] == []
        assert g["true_matches"]["bank_txn_ids"] == []
        assert g["expected_action"] == "unresolved"


def test_split_settlement_amounts_sum_exactly_to_payment(small_dataset):
    payments_by_id = {p["payment_id"]: p for p in small_dataset.payments}
    settlements_by_id = {s["settlement_id"]: s for s in small_dataset.settlements}
    split_cases = [g for g in small_dataset.ground_truth if g["archetype"] == "split_settlement"]
    assert len(split_cases) == ARCHETYPE_COUNTS["split_settlement"]
    for g in split_cases:
        payment = payments_by_id[g["true_matches"]["payment_id"]]
        total = sum(
            (settlements_by_id[sid]["amount"] for sid in g["true_matches"]["settlement_ids"]),
            Decimal("0"),
        )
        assert total == payment["amount"], g


def test_aggregated_settlement_amount_equals_sum_of_both_payments(small_dataset):
    payments_by_id = {p["payment_id"]: p for p in small_dataset.payments}
    settlements_by_id = {s["settlement_id"]: s for s in small_dataset.settlements}
    agg_cases = [g for g in small_dataset.ground_truth if g["archetype"] == "aggregated_settlement"]
    assert len(agg_cases) == ARCHETYPE_COUNTS["aggregated_settlement"]

    settlement_to_orders: dict[str, list[dict]] = {}
    for g in agg_cases:
        sid = g["true_matches"]["settlement_ids"][0]
        settlement_to_orders.setdefault(sid, []).append(g)

    for sid, entries in settlement_to_orders.items():
        assert len(entries) == 2, "each aggregated settlement should be the true match for exactly 2 orders"
        total_payments = sum(
            (payments_by_id[g["true_matches"]["payment_id"]]["amount"] for g in entries), Decimal("0")
        )
        assert settlements_by_id[sid]["amount"] == total_payments


def test_fee_mismatch_non_adversarial_cases_reconcile_exactly_against_fee_rule(small_dataset):
    from generator import FEE_RULES_BY_METHOD, apply_fee

    payments_by_id = {p["payment_id"]: p for p in small_dataset.payments}
    settlements_by_id = {s["settlement_id"]: s for s in small_dataset.settlements}
    fee_cases = [g for g in small_dataset.ground_truth if g["archetype"] == "fee_mismatch" and not g["is_adversarial"]]
    assert len(fee_cases) == ARCHETYPE_COUNTS["fee_mismatch"] - 2

    for g in fee_cases:
        payment = payments_by_id[g["true_matches"]["payment_id"]]
        settlement = settlements_by_id[g["true_matches"]["settlement_ids"][0]]
        _, _, expected_net = apply_fee(payment["amount"], FEE_RULES_BY_METHOD["card"])
        assert settlement["net_amount"] == expected_net


def test_fee_mismatch_adversarial_cases_do_not_reconcile_against_fee_rule(small_dataset):
    from generator import FEE_RULES_BY_METHOD, apply_fee

    payments_by_id = {p["payment_id"]: p for p in small_dataset.payments}
    settlements_by_id = {s["settlement_id"]: s for s in small_dataset.settlements}
    fee_cases = [g for g in small_dataset.ground_truth if g["archetype"] == "fee_mismatch" and g["is_adversarial"]]
    assert len(fee_cases) == 2

    for g in fee_cases:
        payment = payments_by_id[g["true_matches"]["payment_id"]]
        settlement = settlements_by_id[g["true_matches"]["settlement_ids"][0]]
        _, _, expected_net = apply_fee(payment["amount"], FEE_RULES_BY_METHOD["card"])
        assert settlement["net_amount"] != expected_net, "adversarial case must NOT reconcile, that's the trap"
        assert g["expected_action"] == "human_review"


def test_no_amount_field_is_a_float(small_dataset):
    money_fields = {
        "orders": ["amount"],
        "payments": ["amount"],
        "settlements": ["amount", "fee", "tax", "net_amount"],
        "bank_transactions": ["amount"],
        "refunds": ["amount"],
        "fee_rules": ["mdr_percent", "fixed_fee", "tax_percent"],
    }
    for source_name, fields_ in money_fields.items():
        records = getattr(small_dataset, source_name)
        for record in records:
            for field_name in fields_:
                value = record[field_name]
                assert isinstance(value, Decimal), f"{source_name}.{field_name} is {type(value)}, not Decimal"
