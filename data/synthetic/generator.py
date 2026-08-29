"""Deterministic synthetic dataset generator for ReconcileAI, Milestone 1.

Produces six raw source files (orders/payments/settlements/bank_transactions/
refunds/fee_rules) plus a hidden ground_truth.json, covering every taxonomy
archetype in shared.taxonomy multiple times, at a fixed seed, so the same
seed always regenerates byte-identical output (see backend/tests/test_generator.py).

Design choices (documented, not accidental):
- UPI is modeled with zero MDR/fixed-fee/tax (real-world UPI in India carries
  no merchant discount rate under current RBI/NPCI rules) and is used as the
  baseline method for every archetype EXCEPT `fee_mismatch`, so each archetype
  demonstrates exactly one anomaly at a time instead of confounding fee
  behavior with whatever else the case is testing. `fee_mismatch` cases use
  the card fee rule specifically to produce a genuine, verifiable deduction.
  Fee figures are illustrative and are not asserted to be Razorpay's actual
  published rates.
- "Records" (the ≥50/300-record unit Track 04 names) map to Order rows here
  -- the natural primary unit ground truth is indexed by. Multi-order
  archetypes (aggregated_settlement) contribute their order count to the
  target total the same way single-order archetypes do.
- Every generated record is clearly a simulation: metadata carries
  {"simulated": True} and shared.taxonomy.SIMULATED documents this globally.
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.money import dumps, quantize  # noqa: E402

DEFAULT_SEED = 20260825
BASE_DATE = datetime(2026, 6, 1, 9, 0, 0)
METHODS = ["upi", "card", "netbanking"]

# Archetype -> target ORDER count contributed. Sums to exactly 300; enforced
# by an assertion in generate_dataset() so this can never silently drift.
ARCHETYPE_COUNTS: dict[str, int] = {
    "exact_match": 138,
    "timing_mismatch": 18,
    "fee_mismatch": 18,
    "refund_mismatch": 15,
    "duplicate": 12,
    "missing_transaction": 12,
    "partial_settlement": 12,
    "over_settlement": 8,
    "under_settlement": 8,
    "reference_mismatch": 12,
    "split_settlement": 10,
    "aggregated_settlement": 10,
    "reversed_transaction": 7,
    "ambiguous_match": 10,
    "unexplained_difference": 10,
}
TOTAL_RECORDS = 300

# Which iteration indices (0-based, within their own archetype loop) are
# deliberately adversarial: a plausible-looking hypothesis that a correct
# system must NOT auto-resolve. See docs/demo-script.md's "wow moment".
ADVERSARIAL_INDICES: dict[str, set[int]] = {
    "fee_mismatch": {0, 1},
    "duplicate": {0, 1},
    "ambiguous_match": {0},
}
TOTAL_ADVERSARIAL = sum(len(v) for v in ADVERSARIAL_INDICES.values())


class IdSequence:
    def __init__(self, prefix: str, width: int = 5):
        self.prefix = prefix
        self.width = width
        self.counter = 0

    def next(self) -> str:
        self.counter += 1
        return f"{self.prefix}-{self.counter:0{self.width}d}"


def new_ids() -> dict[str, IdSequence]:
    return {
        "order": IdSequence("ORD"),
        "payment": IdSequence("PAY"),
        "settlement": IdSequence("STL"),
        "bank_txn": IdSequence("BANKTXN"),
        "refund": IdSequence("REF"),
    }


FEE_RULES: list[dict] = [
    {
        "fee_rule_id": "FEE-UPI-001",
        "method": "upi",
        "mdr_percent": Decimal("0.000"),
        "fixed_fee": Decimal("0.00"),
        "tax_percent": Decimal("0.000"),
        "effective_from": BASE_DATE - timedelta(days=365),
        "effective_to": None,
    },
    {
        "fee_rule_id": "FEE-CARD-001",
        "method": "card",
        "mdr_percent": Decimal("0.018"),
        "fixed_fee": Decimal("2.00"),
        "tax_percent": Decimal("0.180"),
        "effective_from": BASE_DATE - timedelta(days=365),
        "effective_to": None,
    },
    {
        "fee_rule_id": "FEE-NETBANKING-001",
        "method": "netbanking",
        "mdr_percent": Decimal("0.009"),
        "fixed_fee": Decimal("0.00"),
        "tax_percent": Decimal("0.180"),
        "effective_from": BASE_DATE - timedelta(days=365),
        "effective_to": None,
    },
]
FEE_RULES_BY_METHOD = {r["method"]: r for r in FEE_RULES}


@dataclass
class Case:
    orders: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    settlements: list[dict] = field(default_factory=list)
    bank_transactions: list[dict] = field(default_factory=list)
    refunds: list[dict] = field(default_factory=list)
    ground_truth_entries: list[dict] = field(default_factory=list)


@dataclass
class GeneratedDataset:
    seed: int
    orders: list[dict]
    payments: list[dict]
    settlements: list[dict]
    bank_transactions: list[dict]
    refunds: list[dict]
    fee_rules: list[dict]
    ground_truth: list[dict]


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------

def rand_amount(rng: random.Random, low: int = 100, high: int = 50000) -> Decimal:
    paise = rng.randint(low * 100, high * 100)
    return quantize(Decimal(paise) / Decimal(100))


def apply_fee(amount: Decimal, fee_rule: dict) -> tuple[Decimal, Decimal, Decimal]:
    fee = quantize(amount * fee_rule["mdr_percent"] + fee_rule["fixed_fee"])
    tax = quantize(fee * fee_rule["tax_percent"])
    net = quantize(amount - fee - tax)
    return fee, tax, net


def messify(s: str, rng: random.Random) -> str:
    """Injects whitespace/case noise that shared.money-independent
    normalization (app.engines.normalization.normalize_reference) can still
    collapse back to the same canonical token -- used to prove normalization
    actually does something, on a subset of otherwise-clean exact matches."""
    noisy = " ".join(s[i : i + 3] for i in range(0, len(s), 3))
    return noisy.lower() if rng.random() < 0.5 else noisy


def new_order(rng: random.Random, ids: dict[str, IdSequence], day_offset: int, amount: Decimal | None = None) -> dict:
    order_id = ids["order"].next()
    created_at = BASE_DATE + timedelta(days=day_offset, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
    return {
        "order_id": order_id,
        "customer_ref": f"CUST-{rng.randint(1000, 9999)}",
        "amount": amount if amount is not None else rand_amount(rng),
        "currency": "INR",
        "created_at": created_at,
        "status": "paid",
        "metadata": {"simulated": True},
    }


def new_payment(rng: random.Random, ids: dict[str, IdSequence], order: dict, method: str | None = None, amount: Decimal | None = None) -> dict:
    payment_id = ids["payment"].next()
    method = method or "upi"
    captured_at = order["created_at"] + timedelta(minutes=rng.randint(1, 30))
    return {
        "payment_id": payment_id,
        "order_id": order["order_id"],
        "amount": amount if amount is not None else order["amount"],
        "currency": "INR",
        "method": method,
        "captured_at": captured_at,
        "status": "captured",
        "gateway_ref": f"GWREF{payment_id.split('-')[1]}",
        "metadata": {"simulated": True},
    }


def new_settlement(
    rng: random.Random,
    ids: dict[str, IdSequence],
    payment: dict | None,
    fee_rule: dict,
    *,
    settled_offset_days: int = 1,
    amount: Decimal | None = None,
    net_amount_override: Decimal | None = None,
    status: str = "settled",
    payment_id_override: str | None = "__USE_PAYMENT__",
) -> dict:
    settlement_id = ids["settlement"].next()
    base_amount = amount if amount is not None else (payment["amount"] if payment else rand_amount(rng))
    fee, tax, net = apply_fee(base_amount, fee_rule)
    if net_amount_override is not None:
        net = net_amount_override
    anchor = payment["captured_at"] if payment else BASE_DATE
    settled_at = anchor + timedelta(days=settled_offset_days)
    pid = payment["payment_id"] if (payment_id_override == "__USE_PAYMENT__" and payment) else payment_id_override
    return {
        "settlement_id": settlement_id,
        "payment_id": pid,
        "settlement_batch_id": f"BATCH-{settled_at.strftime('%Y%m%d')}",
        "amount": base_amount,
        "fee": fee,
        "tax": tax,
        "net_amount": net,
        "currency": "INR",
        "settled_at": settled_at,
        "utr_reference": f"UTR{settlement_id.split('-')[1]}{(pid or 'NA').replace('-', '')}",
        "status": status,
        "metadata": {"simulated": True},
    }


def new_bank_txn(
    rng: random.Random,
    ids: dict[str, IdSequence],
    settlement: dict,
    *,
    direction: str = "credit",
    amount: Decimal | None = None,
    value_offset_days: int = 1,
) -> dict:
    bank_txn_id = ids["bank_txn"].next()
    value_date = settlement["settled_at"] + timedelta(days=value_offset_days)
    return {
        "bank_txn_id": bank_txn_id,
        "amount": amount if amount is not None else settlement["net_amount"],
        "currency": "INR",
        "value_date": value_date,
        "narration": f"NEFT SETTLEMENT {settlement['utr_reference']}",
        "direction": direction,
        "matched_settlement_id": settlement["settlement_id"],
        "metadata": {"simulated": True},
    }


def new_refund(rng: random.Random, ids: dict[str, IdSequence], payment: dict, amount: Decimal, *, initiated_offset_days: int = 2) -> dict:
    refund_id = ids["refund"].next()
    initiated_at = payment["captured_at"] + timedelta(days=initiated_offset_days)
    return {
        "refund_id": refund_id,
        "payment_id": payment["payment_id"],
        "amount": amount,
        "currency": "INR",
        "initiated_at": initiated_at,
        "processed_at": initiated_at + timedelta(days=1),
        "status": "processed",
        "reference": f"RFND{refund_id.split('-')[1]}",
        "metadata": {"simulated": True},
    }


def gt_entry(order: dict, archetype: str, category: str | None, true_matches: dict, expected_action: str, is_adversarial: bool, notes: str) -> dict:
    return {
        "order_id": order["order_id"],
        "archetype": archetype,
        "category": category,
        "true_matches": true_matches,
        "expected_action": expected_action,
        "is_adversarial": is_adversarial,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Archetype generators -- each returns exactly one Case
# ---------------------------------------------------------------------------

def gen_exact_match(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    settlement = new_settlement(rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1)
    if rng.random() < 0.1:
        settlement["utr_reference"] = messify(settlement["utr_reference"], rng)
    bank_txn = new_bank_txn(rng, ids, settlement)
    gt = gt_entry(
        order, "exact_match", None,
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "auto_resolve", False,
        "Clean match: zero-MDR UPI settlement equals payment amount exactly; bank credit confirms it.",
    )
    return Case([order], [payment], [settlement], [bank_txn], [], [gt])


def gen_timing_mismatch(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    lag = rng.randint(2, 5)
    settlement = new_settlement(rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=lag)
    bank_txn = new_bank_txn(rng, ids, settlement)
    gt = gt_entry(
        order, "timing_mismatch", "timing_mismatch",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "auto_resolve", False,
        f"Settlement lagged the payment by {lag} days; amount matches exactly, only timing differs.",
    )
    return Case([order], [payment], [settlement], [bank_txn], [], [gt])


def gen_fee_mismatch(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day, amount=rand_amount(rng, 1000, 20000))
    payment = new_payment(rng, ids, order, method="card")
    fee_rule = FEE_RULES_BY_METHOD["card"]

    if not is_adversarial:
        settlement = new_settlement(rng, ids, payment, fee_rule, settled_offset_days=1)
        bank_txn = new_bank_txn(rng, ids, settlement)
        gt = gt_entry(
            order, "fee_mismatch", "fee_mismatch",
            {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
             "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
            "auto_resolve", False,
            "Net settlement equals payment amount minus the card MDR + tax per FEE-CARD-001; verifiable exactly.",
        )
        return Case([order], [payment], [settlement], [bank_txn], [], [gt])

    # Adversarial: the settlement's stated fee/net_amount do NOT actually
    # match FEE-CARD-001's formula -- a plausible "looks like a card fee"
    # deduction that deterministic verification (recomputing via the real
    # rule) must catch and refuse to auto-resolve.
    correct_fee, correct_tax, correct_net = apply_fee(payment["amount"], fee_rule)
    bogus_extra = quantize(Decimal(rng.randint(500, 1500)) / Decimal(100))
    bogus_net = quantize(correct_net - bogus_extra)
    settlement = new_settlement(
        rng, ids, payment, fee_rule, settled_offset_days=1, net_amount_override=bogus_net,
    )
    bank_txn = new_bank_txn(rng, ids, settlement)
    gt = gt_entry(
        order, "fee_mismatch", "fee_mismatch",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "human_review", True,
        (
            f"ADVERSARIAL: net_amount ({bogus_net}) does not equal payment.amount - FEE-CARD-001 fee/tax "
            f"({correct_net} expected); a naive system could plausibly explain the difference as 'the card fee' "
            f"since a fee WAS deducted, but the deterministic verification engine must recompute the exact "
            f"FEE-CARD-001 formula and reject this as unexplained (short by an extra {bogus_extra})."
        ),
    )
    return Case([order], [payment], [settlement], [bank_txn], [], [gt])


def gen_refund_mismatch(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day, amount=rand_amount(rng, 500, 10000))
    payment = new_payment(rng, ids, order, method="upi")
    settlement = new_settlement(rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1)
    bank_credit = new_bank_txn(rng, ids, settlement, direction="credit")

    refund_amount = quantize(payment["amount"] * Decimal(rng.choice(["0.25", "0.5", "1.0"])))
    refund = new_refund(rng, ids, payment, refund_amount, initiated_offset_days=3)
    refund_bank_txn = new_bank_txn(
        rng, ids, settlement, direction="debit", amount=refund_amount, value_offset_days=4,
    )
    gt = gt_entry(
        order, "refund_mismatch", "refund_mismatch",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_credit["bank_txn_id"], refund_bank_txn["bank_txn_id"]],
         "refund_ids": [refund["refund_id"]]},
        "auto_resolve", False,
        f"Full settlement of {payment['amount']} followed by a {refund_amount} refund debit; refund record fully explains the net position.",
    )
    return Case([order], [payment], [settlement], [bank_credit, refund_bank_txn], [refund], [gt])


def gen_duplicate(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")

    amount_2 = payment["amount"]
    if is_adversarial:
        amount_2 = quantize(payment["amount"] + Decimal("1.00"))

    settlement_1 = new_settlement(rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1)
    settlement_2 = new_settlement(
        rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=2, amount=amount_2,
    )
    bank_txn = new_bank_txn(rng, ids, settlement_1)  # only ONE of the two ever actually got paid out

    note = (
        "Two settlement records reference the same payment; only settlement_1 has a confirmed bank credit "
        "-- settlement_2 is an erroneous duplicate and must not be treated as a second legitimate payout."
    )
    if is_adversarial:
        note = (
            f"ADVERSARIAL: the duplicate settlement's amount ({amount_2}) differs from the original "
            f"({payment['amount']}) by only Rs 1.00, which could tempt a naive system into treating them as "
            "two distinct legitimate settlements rather than recognizing settlement_2 as a duplicate with no "
            "actual bank credit behind it."
        )

    gt = gt_entry(
        order, "duplicate", "duplicate",
        {"payment_id": payment["payment_id"],
         "settlement_ids": [settlement_1["settlement_id"], settlement_2["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "human_review", is_adversarial, note,
    )
    return Case([order], [payment], [settlement_1, settlement_2], [bank_txn], [], [gt])


def gen_missing_transaction(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    gt = gt_entry(
        order, "missing_transaction", "missing_transaction",
        {"payment_id": payment["payment_id"], "settlement_ids": [], "bank_txn_ids": [], "refund_ids": []},
        "unresolved", False,
        "Payment captured but genuinely has no settlement or bank transaction yet -- correctly left unresolved, not force-matched.",
    )
    return Case([order], [payment], [], [], [], [gt])


def gen_partial_settlement(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day, amount=rand_amount(rng, 2000, 20000))
    payment = new_payment(rng, ids, order, method="upi")
    fraction = Decimal(rng.choice(["0.55", "0.60", "0.70", "0.75"]))
    partial_amount = quantize(payment["amount"] * fraction)
    settlement = new_settlement(
        rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1, amount=partial_amount,
    )
    bank_txn = new_bank_txn(rng, ids, settlement)
    gt = gt_entry(
        order, "partial_settlement", "partial_settlement",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "human_review", False,
        f"Only {partial_amount} of {payment['amount']} has settled so far; remainder is still outstanding.",
    )
    return Case([order], [payment], [settlement], [bank_txn], [], [gt])


def gen_over_settlement(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    extra = quantize(payment["amount"] * Decimal(rng.choice(["0.02", "0.03", "0.05"])))
    over_amount = quantize(payment["amount"] + extra)
    settlement = new_settlement(
        rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1, amount=over_amount,
    )
    bank_txn = new_bank_txn(rng, ids, settlement)
    gt = gt_entry(
        order, "over_settlement", "over_settlement",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "human_review", False,
        f"Settlement ({over_amount}) exceeds the payment ({payment['amount']}) by {extra}; overpayment needs human confirmation.",
    )
    return Case([order], [payment], [settlement], [bank_txn], [], [gt])


def gen_under_settlement(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    shortfall = quantize(payment["amount"] * Decimal(rng.choice(["0.04", "0.06", "0.08"])))
    under_amount = quantize(payment["amount"] - shortfall)
    settlement = new_settlement(
        rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1, amount=under_amount,
    )
    bank_txn = new_bank_txn(rng, ids, settlement)
    gt = gt_entry(
        order, "under_settlement", "under_settlement",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "human_review", False,
        f"Settlement ({under_amount}) is short of the payment ({payment['amount']}) by {shortfall}, with zero-MDR UPI so no fee explains it.",
    )
    return Case([order], [payment], [settlement], [bank_txn], [], [gt])


def gen_reference_mismatch(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    settlement = new_settlement(rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1)
    # Overwrite with a genuinely unrelated reference -- survives normalization,
    # unlike the whitespace/case noise gen_exact_match sometimes injects.
    settlement["utr_reference"] = f"UTRUNRELATED{rng.randint(100000, 999999)}"
    bank_txn = new_bank_txn(rng, ids, settlement)
    gt = gt_entry(
        order, "reference_mismatch", "reference_mismatch",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "auto_resolve", False,
        "Amount and date proximity agree, but the settlement's own UTR reference bears no resemblance to the payment's -- needs multi-field scoring, not reference matching alone.",
    )
    return Case([order], [payment], [settlement], [bank_txn], [], [gt])


def gen_split_settlement(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day, amount=rand_amount(rng, 2000, 20000))
    payment = new_payment(rng, ids, order, method="upi")
    fraction = Decimal(rng.choice(["0.4", "0.5", "0.6"]))
    part_1 = quantize(payment["amount"] * fraction)
    part_2 = quantize(payment["amount"] - part_1)  # exact remainder, guarantees exact sum
    settlement_1 = new_settlement(rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1, amount=part_1)
    settlement_2 = new_settlement(rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1, amount=part_2)
    bank_txn_1 = new_bank_txn(rng, ids, settlement_1)
    bank_txn_2 = new_bank_txn(rng, ids, settlement_2)
    gt = gt_entry(
        order, "split_settlement", "split_settlement",
        {"payment_id": payment["payment_id"],
         "settlement_ids": [settlement_1["settlement_id"], settlement_2["settlement_id"]],
         "bank_txn_ids": [bank_txn_1["bank_txn_id"], bank_txn_2["bank_txn_id"]], "refund_ids": []},
        "auto_resolve", False,
        f"One payment split across two settlements ({part_1} + {part_2}) that sum exactly to {payment['amount']}.",
    )
    return Case([order], [payment], [settlement_1, settlement_2], [bank_txn_1, bank_txn_2], [], [gt])


def gen_aggregated_settlement(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order_1 = new_order(rng, ids, day, amount=rand_amount(rng, 500, 10000))
    order_2 = new_order(rng, ids, day, amount=rand_amount(rng, 500, 10000))
    payment_1 = new_payment(rng, ids, order_1, method="upi")
    payment_2 = new_payment(rng, ids, order_2, method="upi")
    combined = quantize(payment_1["amount"] + payment_2["amount"])
    settlement = new_settlement(
        rng, ids, payment_1, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1,
        amount=combined, payment_id_override=None,
    )
    bank_txn = new_bank_txn(rng, ids, settlement)
    note = (
        f"Settlement ({combined}) aggregates two payments ({payment_1['amount']} + {payment_2['amount']}); "
        "not linked via a single payment_id FK -- both must be matched to the same settlement."
    )
    gt1 = gt_entry(
        order_1, "aggregated_settlement", "aggregated_settlement",
        {"payment_id": payment_1["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "auto_resolve", False, note,
    )
    gt2 = gt_entry(
        order_2, "aggregated_settlement", "aggregated_settlement",
        {"payment_id": payment_2["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "auto_resolve", False, note,
    )
    return Case([order_1, order_2], [payment_1, payment_2], [settlement], [bank_txn], [], [gt1, gt2])


def gen_reversed_transaction(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    settlement = new_settlement(
        rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1, status="reversed",
    )
    credit = new_bank_txn(rng, ids, settlement, direction="credit", value_offset_days=1)
    debit = new_bank_txn(rng, ids, settlement, direction="debit", value_offset_days=3)
    gt = gt_entry(
        order, "reversed_transaction", "reversed_transaction",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [credit["bank_txn_id"], debit["bank_txn_id"]], "refund_ids": []},
        "human_review", False,
        "Settlement credited then reversed by an equal-amount debit; net position is zero and needs human confirmation of cause.",
    )
    return Case([order], [payment], [settlement], [credit, debit], [], [gt])


def gen_ambiguous_match(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    payment["metadata"] = {"simulated": True, "merchant": "Merchant-A"}

    # Candidate A: right amount, date 4 days off, unrelated reference, wrong merchant.
    candidate_a = new_settlement(
        rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=4, payment_id_override=None,
    )
    candidate_a["utr_reference"] = f"UTRALT{rng.randint(100000, 999999)}"
    candidate_a["metadata"] = {"simulated": True, "merchant": "Merchant-B"}

    # Candidate B: right amount, date 1 day off, reference closely resembles
    # the canonical form, merchant matches -- the true counterpart.
    candidate_b = new_settlement(
        rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1, payment_id_override=None,
    )
    candidate_b["metadata"] = {"simulated": True, "merchant": "Merchant-A"}

    bank_txn = new_bank_txn(rng, ids, candidate_b)

    note = (
        "Two unlinked settlement candidates share the same amount. Candidate A: date differs by 4 days, "
        "reference unrelated, merchant mismatch. Candidate B: date differs by 1 day, reference closely "
        "resembles the canonical form, merchant matches, and has a confirmed bank credit -- B is the true "
        "match, but evidence is not overwhelming enough to clear the auto-resolve confidence threshold."
    )
    if is_adversarial:
        note = (
            "ADVERSARIAL variant of the ambiguous-match case: both candidates are plausible on amount alone; "
            "a system that only checks amount could pick either. Only Candidate B has a confirmed bank credit "
            "and merchant/reference consistency -- correct resolution requires weighing multiple signals, "
            "not just amount, and even then should not exceed human-review confidence."
        )

    gt = gt_entry(
        order, "ambiguous_match", "ambiguous_match",
        {"payment_id": payment["payment_id"], "settlement_ids": [candidate_b["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": [],
         "rejected_candidate_settlement_ids": [candidate_a["settlement_id"]]},
        "human_review", is_adversarial, note,
    )
    return Case([order], [payment], [candidate_a, candidate_b], [bank_txn], [], [gt])


def gen_unexplained_difference(rng, ids, idx, is_adversarial=False):
    day = rng.randint(0, 59)
    order = new_order(rng, ids, day)
    payment = new_payment(rng, ids, order, method="upi")
    settlement = new_settlement(rng, ids, payment, FEE_RULES_BY_METHOD["upi"], settled_offset_days=1)
    # The settlement's OWN stated fee/tax don't even reconcile against its own
    # net_amount -- a data-integrity anomaly, distinct from under_settlement
    # (which is internally consistent, just short relative to the payment).
    stray_delta = quantize(Decimal(rng.randint(300, 900)) / Decimal(100))
    settlement["net_amount"] = quantize(settlement["net_amount"] - stray_delta)
    bank_txn = new_bank_txn(rng, ids, settlement)
    gt = gt_entry(
        order, "unexplained_difference", "unexplained_difference",
        {"payment_id": payment["payment_id"], "settlement_ids": [settlement["settlement_id"]],
         "bank_txn_ids": [bank_txn["bank_txn_id"]], "refund_ids": []},
        "human_review", False,
        f"Settlement's own net_amount doesn't reconcile against its stated fee/tax by {stray_delta}; no fee rule, refund, or duplicate explains it.",
    )
    return Case([order], [payment], [settlement], [bank_txn], [], [gt])


GENERATORS = {
    "exact_match": gen_exact_match,
    "timing_mismatch": gen_timing_mismatch,
    "fee_mismatch": gen_fee_mismatch,
    "refund_mismatch": gen_refund_mismatch,
    "duplicate": gen_duplicate,
    "missing_transaction": gen_missing_transaction,
    "partial_settlement": gen_partial_settlement,
    "over_settlement": gen_over_settlement,
    "under_settlement": gen_under_settlement,
    "reference_mismatch": gen_reference_mismatch,
    "split_settlement": gen_split_settlement,
    "aggregated_settlement": gen_aggregated_settlement,
    "reversed_transaction": gen_reversed_transaction,
    "ambiguous_match": gen_ambiguous_match,
    "unexplained_difference": gen_unexplained_difference,
}


def generate_dataset(seed: int = DEFAULT_SEED) -> GeneratedDataset:
    assert sum(ARCHETYPE_COUNTS.values()) == TOTAL_RECORDS, "ARCHETYPE_COUNTS must sum to TOTAL_RECORDS"

    rng = random.Random(seed)
    ids = new_ids()

    orders: list[dict] = []
    payments: list[dict] = []
    settlements: list[dict] = []
    bank_transactions: list[dict] = []
    refunds: list[dict] = []
    ground_truth: list[dict] = []

    for archetype, target_order_count in ARCHETYPE_COUNTS.items():
        produced = 0
        idx = 0
        generator_fn = GENERATORS[archetype]
        adversarial_idx = ADVERSARIAL_INDICES.get(archetype, set())
        while produced < target_order_count:
            is_adversarial = idx in adversarial_idx
            case = generator_fn(rng, ids, idx, is_adversarial=is_adversarial)
            orders.extend(case.orders)
            payments.extend(case.payments)
            settlements.extend(case.settlements)
            bank_transactions.extend(case.bank_transactions)
            refunds.extend(case.refunds)
            ground_truth.extend(case.ground_truth_entries)
            produced += len(case.orders)
            idx += 1
        assert produced == target_order_count, f"{archetype} produced {produced}, expected {target_order_count}"

    assert len(orders) == TOTAL_RECORDS
    assert len({o["order_id"] for o in orders}) == TOTAL_RECORDS, "order_id collision detected"
    assert sum(1 for g in ground_truth if g["is_adversarial"]) == TOTAL_ADVERSARIAL

    return GeneratedDataset(
        seed=seed,
        orders=orders,
        payments=payments,
        settlements=settlements,
        bank_transactions=bank_transactions,
        refunds=refunds,
        fee_rules=FEE_RULES,
        ground_truth=ground_truth,
    )


def write_dataset(dataset: GeneratedDataset, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "orders.json": dataset.orders,
        "payments.json": dataset.payments,
        "settlements.json": dataset.settlements,
        "bank_transactions.json": dataset.bank_transactions,
        "refunds.json": dataset.refunds,
        "fee_rules.json": dataset.fee_rules,
        "ground_truth.json": dataset.ground_truth,
    }
    for filename, payload in files.items():
        (out_dir / filename).write_text(dumps(payload), encoding="utf-8")
    (out_dir / "GENERATION_INFO.json").write_text(
        dumps({"seed": dataset.seed, "total_records": TOTAL_RECORDS, "archetype_counts": ARCHETYPE_COUNTS, "simulated": True}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    seed_arg = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SEED
    dataset = generate_dataset(seed_arg)
    out_dir = Path(__file__).resolve().parent / "seeds"
    write_dataset(dataset, out_dir)
    print(f"Wrote {TOTAL_RECORDS} records (seed={seed_arg}) to {out_dir}")
