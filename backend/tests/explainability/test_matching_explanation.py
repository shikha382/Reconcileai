"""M10 Phase 6: matching explanation must use the project's actual
taxonomy and must distinguish exact/normalized/fuzzy/ambiguous/rejected/
unmatched -- never describe a deterministic match as AI-suggested."""
from app.explainability.builder import build_explanation


def test_exact_match_is_labeled_exact(get_decision):
    result, payment, settlement, context = get_decision("exact_match", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.matching_evidence.match_status in ("EXACT_MATCH", "NORMALIZED_MATCH")
    assert explanation.matching_evidence.accepted_settlement_id == settlement.settlement_id


def test_reference_mismatch_that_still_matches_is_labeled_verified_not_exact(get_decision):
    result, payment, settlement, context = get_decision("reference_mismatch", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    # A reference_mismatch archetype matches on amount/date, not identical
    # reference text -- must not be mislabeled EXACT_MATCH.
    assert explanation.matching_evidence.match_status != "EXACT_MATCH"


def test_ambiguous_match_is_labeled_ambiguous_never_a_deterministic_match(get_decision):
    result, payment, settlement, context = get_decision("ambiguous_match", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.matching_evidence.match_status == "AMBIGUOUS"
    assert explanation.matching_evidence.accepted_settlement_id is None


def test_missing_transaction_is_labeled_unmatched(get_decision):
    result, payment, settlement, context = get_decision("missing_transaction", 0)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.matching_evidence.match_status == "UNMATCHED"


def test_fee_verified_match_is_labeled_verified_not_exact(get_decision):
    result, payment, settlement, context = get_decision("fee_mismatch", 0, not_adversarial=True)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert explanation.matching_evidence.match_status == "VERIFIED_MATCH"


def test_every_candidate_evidence_item_is_tagged_with_a_real_status(get_decision):
    result, payment, settlement, context = get_decision("ambiguous_match", 0, not_adversarial=False)
    explanation = build_explanation(result, context=context, payment=payment, settlement=settlement)
    assert len(explanation.matching_evidence.candidates) >= 1
    for candidate in explanation.matching_evidence.candidates:
        assert candidate.verdict in ("ACCEPTED", "REJECTED")
        assert candidate.match_class in ("ACCEPTED", "REJECTED")
