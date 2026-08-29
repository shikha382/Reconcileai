"""Section 16 (explainability test): for at least 10 representative
exceptions, a complete human-readable explanation generated FROM structured
evidence -- NOT an LLM. Proves the evidence engine is useful on its own
before any AI layer exists.
"""
from app.engines.evidence.narrative import generate_explanation


def test_ten_representative_explanations_are_generated_from_templates_only(full_exception_intelligence):
    ground_truth = full_exception_intelligence["ground_truth"]
    bundles_by_order = {b.order_id: b for b in full_exception_intelligence["bundles"]}

    representative_archetypes = [
        "exact_match", "fee_mismatch", "timing_mismatch", "refund_mismatch", "partial_settlement",
        "over_settlement", "unexplained_difference", "missing_transaction", "duplicate", "ambiguous_match",
    ]
    picked = {}
    for gt in ground_truth:
        if gt["archetype"] in representative_archetypes and gt["archetype"] not in picked and not gt["is_adversarial"]:
            picked[gt["archetype"]] = gt["order_id"]
    assert len(picked) == 10

    explanations = {}
    for archetype, order_id in picked.items():
        bundle = bundles_by_order[order_id]
        text = generate_explanation(bundle)
        explanations[archetype] = text

        assert isinstance(text, str)
        assert len(text) > 20
        # Must reference the actual payment/order id -- proving it's built
        # from THIS record's real data, not a generic template stub.
        assert bundle.payment_id in text
        assert bundle.order_id in text

    # No two of these 10 explanations are identical -- each reflects its
    # own record's actual evidence.
    assert len(set(explanations.values())) == 10


def test_adversarial_fee_mismatch_explanation_names_the_specific_residual(full_exception_intelligence):
    ground_truth = full_exception_intelligence["ground_truth"]
    bundles_by_order = {b.order_id: b for b in full_exception_intelligence["bundles"]}
    adversarial_fee = next(g for g in ground_truth if g["is_adversarial"] and g["archetype"] == "fee_mismatch")

    text = generate_explanation(bundles_by_order[adversarial_fee["order_id"]])
    assert "fee" in text.lower()
    assert "does not explain" in text.lower()
