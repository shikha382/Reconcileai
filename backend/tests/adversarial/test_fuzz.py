"""M9 Phase 23: seeded, deterministic randomized/fuzz testing. Generates a
manageable number of randomized amount/fee/reference perturbations against
real base records and confirms none of them ever produce an unsafe
auto-resolution. Every failure is reproducible from its seed; a failing
seed is promoted to a permanent regression test (see the bottom of this
file) rather than silently re-rolled away.
"""
import random
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype

FUZZ_SEED = 90210
FUZZ_CASE_COUNT = 60


def _random_nonzero_delta(rng: random.Random) -> Decimal:
    cents = 0
    while cents == 0:
        cents = rng.randint(-500000, 500000)  # up to +/- 5,000.00
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def _fuzz_case(dataset, ground_truth, rng: random.Random, case_index: int):
    archetype = rng.choice(["exact_match", "fee_mismatch"])
    not_adversarial = archetype == "exact_match" or rng.random() < 0.5
    pool_size = 138 if archetype == "exact_match" else 18
    order_index = rng.randrange(min(pool_size, 100))
    try:
        order_id = pick_by_archetype(ground_truth, archetype, order_index, not_adversarial=not_adversarial)
    except IndexError:
        order_id = pick_by_archetype(ground_truth, archetype, 0, not_adversarial=not_adversarial)

    payment = find_payment_by_order(dataset, order_id)
    settlement = next((s for s in dataset.settlements if s.payment_id == payment.payment_id), None)
    if settlement is None:
        return None, None

    mutation_kind = rng.choice(["bank_credit", "fee", "reference"])
    delta = _random_nonzero_delta(rng)

    if mutation_kind == "bank_credit":
        credit = next((b for b in dataset.bank_transactions if b.matched_settlement_id == settlement.settlement_id and b.direction == "credit"), None)
        if credit is None:
            return None, None
        credit.amount += delta
    elif mutation_kind == "fee":
        # `bank_credited_amount` (the confirmed CREDIT bank transaction) is
        # the sole authoritative "money actually moved" figure in this
        # system's own design (see test_amount_manipulation.py's module
        # docstring) -- settlement.fee/net_amount alone are cosmetic to the
        # matching engine. A real fee miscalculation would show up in what
        # was actually credited, so the fuzz mutation applies there too.
        credit = next((b for b in dataset.bank_transactions if b.matched_settlement_id == settlement.settlement_id and b.direction == "credit"), None)
        if credit is None:
            return None, None
        settlement.fee += delta
        settlement.net_amount -= delta
        credit.amount -= delta
    else:
        settlement.payment_id = None
        settlement.utr_reference = f"FUZZ-{case_index}-{rng.randint(0, 999999)}"

    return payment.payment_id, {"archetype": archetype, "order_id": order_id, "mutation_kind": mutation_kind, "delta": str(delta)}


def test_seeded_fuzz_never_produces_an_unsafe_auto_resolution(mutated_dataset, ground_truth, decision_env):
    rng = random.Random(FUZZ_SEED)
    unsafe = []

    for i in range(FUZZ_CASE_COUNT):
        dataset = mutated_dataset.clone_all()
        payment_id, meta = _fuzz_case(dataset, ground_truth, rng, i)
        if payment_id is None:
            continue
        result = decide_one(dataset, payment_id, decision_env)
        if result.policy_decision.decision == PolicyDecisionType.SAFE_TO_RESOLVE:
            unsafe.append({"case_index": i, "seed": FUZZ_SEED, **meta})

    assert unsafe == [], f"seeded fuzz found unsafe auto-resolutions (reproducible via seed {FUZZ_SEED}): {unsafe}"


# --- Regression lock: any seed/case index that ever fails the fuzz sweep
# above must be promoted here as its own permanent, minimal test -- none
# have been found yet, so this section is currently empty by design (a
# clean result, not an omission). If test_seeded_fuzz_... above ever finds
# a failure, add the exact reproduction here per Phase 26's regression-lock
# requirement, e.g.:
#
# def test_regression_fuzz_case_42_seed_90210():
#     ...reproduce case_index=42 exactly, assert the fix holds...
