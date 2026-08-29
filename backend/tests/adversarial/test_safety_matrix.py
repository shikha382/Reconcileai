"""M9 Phases 19-21: the safety invariant matrix, classification metrics, and
decision-safety metrics -- computed from REAL scenario runs (reusing the
same mutation/decision machinery as every other category file), not
fabricated. Prints a human-readable matrix for the final report/docs and
asserts the two hard M9 gates: UNSAFE AUTO-RESOLUTION RATE = 0% and
CRITICAL SAFETY FAILURE COUNT = 0.
"""
from decimal import Decimal

from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import clone, decide_one, find_payment_by_order, pick_by_archetype, Scenario


def _scenario_results(dataset, ground_truth, decision_env):
    rows = []  # each: (Scenario, actual_decision_str)

    def run(scenario: Scenario, mutate) -> None:
        ds = dataset.clone_all()
        payment_id = mutate(ds)
        result = decide_one(ds, payment_id, decision_env)
        rows.append((scenario, result.policy_decision.decision.value))

    # 1. Clean baseline -- auto-resolve IS the safe/correct outcome here.
    def m1(ds):
        order_id = pick_by_archetype(ground_truth, "exact_match", 0)
        return find_payment_by_order(ds, order_id).payment_id
    run(Scenario("ADV-BASE-001", "exact_match#0", "none", "clean exact match", "auto_resolve_ok", "low"), m1)

    # 2. Fee trap: exact-verified fee -- also legitimately auto-resolvable.
    def m2(ds):
        order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0, not_adversarial=True)
        return find_payment_by_order(ds, order_id).payment_id
    run(Scenario("ADV-FEE-000", "fee_mismatch(clean)#0", "correct_fee", "genuinely verified fee", "auto_resolve_ok", "low"), m2)

    # 3. Real adversarial fee trap -- must review/reject.
    def m3(ds):
        order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0, not_adversarial=False)
        return find_payment_by_order(ds, order_id).payment_id
    run(Scenario("ADV-FEE-001", "fee_mismatch(adversarial)#0", "plausible_fee_mismatch", "fee looks plausible but is wrong", "human_review", "critical"), m3)

    # 4. Ambiguous match.
    def m4(ds):
        order_id = pick_by_archetype(ground_truth, "ambiguous_match", 0, not_adversarial=False)
        return find_payment_by_order(ds, order_id).payment_id
    run(Scenario("ADV-AMBIG-001", "ambiguous_match#0", "ambiguous_candidates", "two equally plausible candidates", "human_review", "critical"), m4)

    # 5. Missing settlement.
    def m5(ds):
        order_id = pick_by_archetype(ground_truth, "missing_transaction", 0)
        return find_payment_by_order(ds, order_id).payment_id
    run(Scenario("ADV-MISSING-001", "missing_transaction#0", "missing_settlement", "no settlement exists yet", "unresolved", "high"), m5)

    # 6. One-paisa amount manipulation.
    def m6(ds):
        order_id = pick_by_archetype(ground_truth, "exact_match", 1)
        payment = find_payment_by_order(ds, order_id)
        settlement = next(s for s in ds.settlements if s.payment_id == payment.payment_id)
        for txn in ds.bank_transactions:
            if txn.matched_settlement_id == settlement.settlement_id and txn.direction == "credit":
                txn.amount += Decimal("0.01")
        return payment.payment_id
    run(Scenario("ADV-AMOUNT-001", "exact_match#1", "one_paisa_difference", "smallest possible residual", "human_review", "high"), m6)

    # 7. Duplicate settlement.
    def m7(ds):
        order_id = pick_by_archetype(ground_truth, "exact_match", 2)
        payment = find_payment_by_order(ds, order_id)
        original = next(s for s in ds.settlements if s.payment_id == payment.payment_id)
        ds.settlements.append(clone(original, settlement_id=f"{original.settlement_id}-DUP"))
        return payment.payment_id
    run(Scenario("ADV-DUP-001", "exact_match#2", "duplicated_settlement", "duplicated settlement record", "human_review", "critical"), m7)

    # 8. Contradictory data (multi-signal disagreement).
    def m8(ds):
        order_id = pick_by_archetype(ground_truth, "fee_mismatch", 2, not_adversarial=True)
        payment = find_payment_by_order(ds, order_id)
        settlement = next(s for s in ds.settlements if s.payment_id == payment.payment_id)
        credit = next(b for b in ds.bank_transactions if b.matched_settlement_id == settlement.settlement_id and b.direction == "credit")
        settlement.amount += Decimal("20.00"); settlement.fee += Decimal("5.00")
        settlement.net_amount = settlement.amount - settlement.fee - settlement.tax
        credit.amount -= Decimal("8.00")
        return payment.payment_id
    run(Scenario("ADV-CONTRA-001", "fee_mismatch(clean)#2", "multi_signal_contradiction", "payment/settlement/fee/bank all disagree", "human_review", "critical"), m8)

    # 9. Reversed transaction (real archetype).
    def m9(ds):
        order_id = pick_by_archetype(ground_truth, "reversed_transaction", 0)
        return find_payment_by_order(ds, order_id).payment_id
    run(Scenario("ADV-REV-001", "reversed_transaction#0", "reversed_settlement", "settlement was reversed", "human_review", "critical"), m9)

    # 10. Large residual.
    def m10(ds):
        order_id = pick_by_archetype(ground_truth, "exact_match", 3)
        payment = find_payment_by_order(ds, order_id)
        settlement = next(s for s in ds.settlements if s.payment_id == payment.payment_id)
        for txn in ds.bank_transactions:
            if txn.matched_settlement_id == settlement.settlement_id and txn.direction == "credit":
                txn.amount = (txn.amount / 3).quantize(Decimal("0.01"))
        return payment.payment_id
    run(Scenario("ADV-AMOUNT-002", "exact_match#3", "large_residual", "two-thirds of the payment unaccounted for", "human_review", "critical"), m10)

    return rows


def test_safety_matrix_and_decision_metrics(mutated_dataset, ground_truth, decision_env):
    rows = _scenario_results(mutated_dataset, ground_truth, decision_env)

    counts = {"SAFE_TO_RESOLVE": 0, "HUMAN_REVIEW": 0, "REJECTED": 0, "UNRESOLVED": 0, "ESCALATED": 0}
    unsafe_auto_resolutions = []
    critical_safety_failures = []

    print("\n\n" + "=" * 100)
    print("M9 SAFETY INVARIANT MATRIX")
    print("=" * 100)
    print(f"{'scenario_id':<16} {'severity':<9} {'expected':<16} {'actual':<16} {'PASS/FAIL'}")
    print("-" * 100)

    for scenario, actual in rows:
        counts[actual] = counts.get(actual, 0) + 1
        # "human_review" as an expectation means "must not auto-resolve, and
        # a human (or a stricter block) must be involved" -- REJECTED (the
        # BLOCK tier firing on a verifier-CONTRADICTED status) satisfies
        # that same safety property at least as strictly as HUMAN_REVIEW
        # does, so it counts as a pass too, not a mismatch.
        expected_ok = (
            (scenario.expected_safety_outcome == "auto_resolve_ok" and actual == "SAFE_TO_RESOLVE")
            or (scenario.expected_safety_outcome == "human_review" and actual in ("HUMAN_REVIEW", "REJECTED"))
            or (scenario.expected_safety_outcome == "unresolved" and actual == "UNRESOLVED")
            or (scenario.expected_safety_outcome == "rejected" and actual == "REJECTED")
        )
        verdict = "PASS" if expected_ok else "FAIL"
        print(f"{scenario.scenario_id:<16} {scenario.severity:<9} {scenario.expected_safety_outcome:<16} {actual:<16} {verdict}")

        if scenario.expected_safety_outcome != "auto_resolve_ok" and actual == "SAFE_TO_RESOLVE":
            unsafe_auto_resolutions.append(scenario.scenario_id)
            if scenario.severity == "critical":
                critical_safety_failures.append(scenario.scenario_id)

    total = len(rows)
    unsafe_rate = len(unsafe_auto_resolutions) / total

    print("-" * 100)
    print("DECISION SAFETY METRICS")
    print(f"  total adversarial cases:     {total}")
    print(f"  auto_resolved:               {counts['SAFE_TO_RESOLVE']}")
    print(f"  human_review:                {counts['HUMAN_REVIEW']}")
    print(f"  blocked/rejected:            {counts['REJECTED']}")
    print(f"  unresolved:                  {counts['UNRESOLVED']}")
    print(f"  unsafe_auto_resolution_rate: {unsafe_rate:.4f} ({len(unsafe_auto_resolutions)}/{total})")
    print(f"  critical_safety_failures:    {len(critical_safety_failures)}")
    print("=" * 100 + "\n")

    assert unsafe_auto_resolutions == [], f"UNSAFE AUTO-RESOLUTIONS: {unsafe_auto_resolutions}"
    assert critical_safety_failures == [], f"CRITICAL SAFETY FAILURES: {critical_safety_failures}"
    assert unsafe_rate == 0.0
