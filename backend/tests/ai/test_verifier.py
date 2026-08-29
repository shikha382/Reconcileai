"""Deterministic hypothesis verification -- including the three
single-settlement-selection conflict guards found empirically while
building this milestone (see CLAUDE.md's M4 architectural decision)."""
from decimal import Decimal

from app.ai.schemas import AIHypothesis, HypothesisType, RecommendedAction, TestHypothesisInput
from app.ai.verifier import validate_grounding, verify_hypothesis

from .factories import CARD_FEE_RULE, ZERO_FEE_RULE, make_bank_txn, make_investigation_context, make_payment, make_settlement


def test_valid_fee_hypothesis_verifies():
    payment = make_payment(amount="5000.00", method="card")
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4891.44")
    bank_txn = make_bank_txn(amount="4891.44")
    ctx = make_investigation_context(payment, [settlement], [bank_txn], fee_rules=[CARD_FEE_RULE])

    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, settlement_id="STL-00001"), ctx)
    assert result.passed


def test_invalid_fee_hypothesis_is_rejected():
    payment = make_payment(amount="5000.00", method="card")
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4870.00")
    bank_txn = make_bank_txn(amount="4870.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn], fee_rules=[CARD_FEE_RULE])

    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, settlement_id="STL-00001"), ctx)
    assert not result.passed


def test_timing_hypothesis_requires_amount_to_also_match():
    """The exact bug caught while building M4: date-in-window alone must
    NOT verify a TIMING_DELAY hypothesis if the amount doesn't also match."""
    payment = make_payment(amount="5000.00", method="card")
    settlement = make_settlement(amount="5000.00", fee="92.00", tax="16.56", net_amount="4870.00")  # wrong, adversarial-style
    bank_txn = make_bank_txn(amount="4870.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn], fee_rules=[CARD_FEE_RULE])

    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.TIMING_DELAY, settlement_id="STL-00001"), ctx)
    assert not result.passed
    assert "amount" in result.reason.lower()


def test_timing_hypothesis_verifies_when_amount_also_matches():
    from datetime import timedelta

    from .factories import BASE_DATE

    payment = make_payment(amount="1000.00", captured_at=BASE_DATE)
    settlement = make_settlement(amount="1000.00", net_amount="1000.00", settled_at=BASE_DATE + timedelta(days=3))
    bank_txn = make_bank_txn(amount="1000.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.TIMING_DELAY, settlement_id="STL-00001"), ctx)
    assert result.passed


def test_reversed_settlement_blocks_single_settlement_hypotheses():
    payment = make_payment(amount="1000.00")
    settlement = make_settlement(amount="1000.00", net_amount="1000.00", status="reversed")
    bank_txn = make_bank_txn(amount="1000.00")
    ctx = make_investigation_context(payment, [settlement], [bank_txn])

    for hyp_type in (HypothesisType.TIMING_DELAY, HypothesisType.FEE_EXPLAINS_DIFFERENCE, HypothesisType.REFERENCE_ERROR):
        result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=hyp_type, settlement_id="STL-00001"), ctx)
        assert not result.passed, f"{hyp_type} must not verify against a reversed settlement"
        assert "reversed" in result.reason.lower()


def test_duplicate_sibling_blocks_single_settlement_hypotheses():
    """Two settlements linked to the same payment -- a single-settlement
    hypothesis about EITHER one, checked in isolation, must not verify."""
    payment = make_payment(amount="1000.00")
    settlement_1 = make_settlement(settlement_id="STL-00001", amount="1000.00", net_amount="1000.00")
    settlement_2 = make_settlement(settlement_id="STL-00002", amount="1000.00", net_amount="1000.00")
    bank_txn = make_bank_txn(settlement_id="STL-00001", amount="1000.00")
    ctx = make_investigation_context(payment, [settlement_1, settlement_2], [bank_txn])

    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.TIMING_DELAY, settlement_id="STL-00001"), ctx)
    assert not result.passed
    assert "other linked settlement" in result.reason.lower() or "duplicate" in result.reason.lower()


def test_ambiguous_unlinked_candidates_block_single_settlement_hypotheses():
    payment = make_payment(amount="1000.00")
    candidate_a = make_settlement(settlement_id="STL-A", payment_id=None, amount="1000.00")
    candidate_b = make_settlement(settlement_id="STL-B", payment_id=None, amount="1000.00")
    bank_txn = make_bank_txn(settlement_id="STL-A", amount="1000.00")
    ctx = make_investigation_context(payment, [candidate_a, candidate_b], [bank_txn])

    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.TIMING_DELAY, settlement_id="STL-A"), ctx)
    assert not result.passed


def test_split_settlement_verifies_when_sum_matches():
    payment = make_payment(amount="5000.00")
    settlement_1 = make_settlement(settlement_id="STL-00001", amount="2000.00", net_amount="2000.00")
    settlement_2 = make_settlement(settlement_id="STL-00002", amount="3000.00", net_amount="3000.00")
    bank_1 = make_bank_txn(bank_txn_id="BANKTXN-00001", settlement_id="STL-00001", amount="2000.00")
    bank_2 = make_bank_txn(bank_txn_id="BANKTXN-00002", settlement_id="STL-00002", amount="3000.00")
    ctx = make_investigation_context(payment, [settlement_1, settlement_2], [bank_1, bank_2])

    result = verify_hypothesis(TestHypothesisInput(
        exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.SPLIT_SETTLEMENT,
        candidate_settlement_ids=["STL-00001", "STL-00002"],
    ), ctx)
    assert result.passed


def test_aggregation_hypothesis_verifies_when_sum_matches():
    payment_a = make_payment(payment_id="PAY-00001", amount="2000.00")
    payment_b = make_payment(payment_id="PAY-00002", amount="3000.00")
    settlement = make_settlement(settlement_id="STL-00001", payment_id=None, amount="5000.00", net_amount="5000.00")
    bank_txn = make_bank_txn(amount="5000.00")
    from app.engines.reconciliation.candidate_generation import build_context
    from app.engines.evidence.graph import build_graph
    from app.engines.evidence.candidates import why_not_matched
    from app.ai.tools import InvestigationContext

    reconciliation_context = build_context([payment_a, payment_b], [settlement], [bank_txn], [], [ZERO_FEE_RULE])
    graph = build_graph([payment_a, payment_b], [settlement], [bank_txn], [])
    report = why_not_matched(payment_a, reconciliation_context)
    ctx = InvestigationContext(exception_id="EXC-1", payment=payment_a, reconciliation_context=reconciliation_context, graph=graph, negative_evidence_report=report)

    result = verify_hypothesis(TestHypothesisInput(
        exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.AGGREGATED_SETTLEMENT,
        settlement_id="STL-00001", candidate_payment_ids=["PAY-00001", "PAY-00002"],
    ), ctx)
    assert result.passed


def test_missing_record_verifies_when_nothing_exists():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment, [])
    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.MISSING_RECORD), ctx)
    assert result.passed


def test_hallucinated_settlement_id_fails_verification():
    payment = make_payment(amount="1000.00")
    ctx = make_investigation_context(payment, [])
    result = verify_hypothesis(TestHypothesisInput(exception_id="EXC-1", payment_id="PAY-00001", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE, settlement_id="STL-99999"), ctx)
    assert not result.passed
    assert "does not exist" in result.reason


def test_grounding_rejects_ids_never_retrieved():
    hypothesis = AIHypothesis(
        hypothesis_id="H-1", exception_id="EXC-1", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE,
        claim="x", record_ids=["STL-99999"], evidence_ids=["STL-99999"],
        confidence=0.9, recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
    )
    violations = validate_grounding(hypothesis, known_record_ids={"PAY-00001"})
    assert len(violations) == 2


def test_grounding_accepts_ids_that_were_retrieved():
    hypothesis = AIHypothesis(
        hypothesis_id="H-1", exception_id="EXC-1", hypothesis_type=HypothesisType.FEE_EXPLAINS_DIFFERENCE,
        claim="x", record_ids=["STL-00001"], evidence_ids=["STL-00001"],
        confidence=0.9, recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
    )
    violations = validate_grounding(hypothesis, known_record_ids={"PAY-00001", "STL-00001"})
    assert violations == []
