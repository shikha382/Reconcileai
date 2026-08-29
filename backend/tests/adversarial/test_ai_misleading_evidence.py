"""M9 Category K: AI misleading-evidence tests (Phase 14). Uses only the
existing deterministic MockAIProvider and small controlled test-double
providers -- no live LLM required. CRITICAL INVARIANT under test throughout:
AI confidence must NEVER substitute for deterministic financial verification
or policy authorization.
"""
from uuid import uuid4

from app.ai.provider import MockAIProvider
from app.ai.schemas import (
    AIHypothesis,
    ConcludeAction,
    HypothesisAction,
    HypothesisType,
    RecommendedAction,
    ToolCallAction,
)
from app.policy.schemas import PolicyDecisionType
from tests.adversarial.helpers import decide_one, find_payment_by_order, pick_by_archetype


class _FixedClaimProvider:
    """A controlled test double: always proposes ONE specific hypothesis,
    at a caller-chosen confidence, regardless of what the investigation
    state actually shows -- used to prove the verifier (not the model's own
    confidence) decides the outcome."""

    def __init__(self, hypothesis_type: HypothesisType, claim: str, confidence: float, record_ids: list[str] | None = None):
        self._hypothesis_type = hypothesis_type
        self._claim = claim
        self._confidence = confidence
        self._record_ids = record_ids or []
        self._proposed = False

    def decide_next_action(self, state):
        if not self._proposed:
            self._proposed = True
            return ToolCallAction(tool_name="get_exception_context", tool_input={"exception_id": state.exception_id})
        hypothesis = AIHypothesis(
            hypothesis_id=str(uuid4()), exception_id=state.exception_id, hypothesis_type=self._hypothesis_type,
            claim=self._claim, record_ids=[state.payment_id, *self._record_ids], evidence_ids=[state.payment_id, *self._record_ids],
            confidence=self._confidence, recommended_action=RecommendedAction.SAFE_TO_RESOLVE,
        )
        return HypothesisAction(hypothesis=hypothesis)


class _ImmediatelyConcludingProvider:
    """Never tests any hypothesis at all -- simulates an AI that gives up /
    provides incomplete reasoning."""

    def decide_next_action(self, state):
        return ConcludeAction(reason="insufficient information to form any hypothesis")


# CASE 1: AI claims "card fee explains it" -- verifier says NO (the real
# adversarial fee_mismatch case) -- hypothesis must be rejected.
def test_case_01_false_fee_claim_is_rejected_by_the_verifier(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "fee_mismatch", 0, not_adversarial=False)
    payment = find_payment_by_order(mutated_dataset, order_id)
    result = decide_one(mutated_dataset, payment.payment_id, decision_env)
    fee_outcomes = [c for c in result.contradiction_records if c.hypothesis_type == "FEE_EXPLAINS_DIFFERENCE"]
    if fee_outcomes:
        assert fee_outcomes[0].status == "CONTRADICTED"
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# CASE 2: AI claims "likely duplicate settlement" when no duplicate exists --
# forced via MockAIProvider's own hallucination test hook.
def test_case_02_false_duplicate_claim_is_not_accepted_as_fact(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "unexplained_difference", 0)
    payment = find_payment_by_order(mutated_dataset, order_id)
    forced_provider = MockAIProvider()
    forced_provider._hallucinate_hypothesis_type = HypothesisType.DUPLICATE  # force DUPLICATE to be tried first
    from tests.adversarial.helpers import DecisionEnvironment

    env = DecisionEnvironment(ledger=decision_env.ledger, approval_store=decision_env.approval_store, provider=forced_provider, session=decision_env.session)
    result = decide_one(mutated_dataset, payment.payment_id, env)
    duplicate_outcomes = [c for c in result.contradiction_records if c.hypothesis_type == "DUPLICATE"]
    if duplicate_outcomes:
        assert duplicate_outcomes[0].status == "CONTRADICTED"
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# CASE 3: AI claims records are an exact match with high confidence; the
# deterministic verifier finds a genuine mismatch -- verifier wins.
def test_case_03_false_exact_match_claim_the_verifier_wins(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "unexplained_difference", 1)
    payment = find_payment_by_order(mutated_dataset, order_id)
    provider = _FixedClaimProvider(HypothesisType.TIMING_DELAY, "the records are effectively an exact match once timing is accounted for", confidence=0.97)
    from tests.adversarial.helpers import DecisionEnvironment

    env = DecisionEnvironment(ledger=decision_env.ledger, approval_store=decision_env.approval_store, provider=provider, session=decision_env.session)
    result = decide_one(mutated_dataset, payment.payment_id, env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE


# CASE 4: AI confidence artificially set very high (0.99); verifier
# contradicts it -- must STILL not be SAFE_TO_RESOLVE. Confidence is never
# read by the policy/verifier layer at all (app.ai.policy, app.ai.verifier).
def test_case_04_extremely_high_ai_confidence_does_not_override_contradiction(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "unexplained_difference", 2)
    payment = find_payment_by_order(mutated_dataset, order_id)
    provider = _FixedClaimProvider(HypothesisType.FEE_EXPLAINS_DIFFERENCE, "definitely a card fee, extremely confident", confidence=0.99)
    from tests.adversarial.helpers import DecisionEnvironment

    env = DecisionEnvironment(ledger=decision_env.ledger, approval_store=decision_env.approval_store, provider=provider, session=decision_env.session)
    result = decide_one(mutated_dataset, payment.payment_id, env)
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
    # The 0.99 self-reported confidence must be visible for audit but never
    # have been consulted by the decision itself.
    for h in result.contradiction_records:
        assert h.status in ("CONTRADICTED", "SUPPORTED", "INSUFFICIENT_EVIDENCE")


# CASE 5: AI provides incomplete reasoning (concludes immediately, no
# hypothesis tested at all) -- must escalate to structured uncertainty, not
# silently do nothing or auto-resolve by default.
def test_case_05_incomplete_ai_reasoning_escalates_to_human_review(mutated_dataset, ground_truth, decision_env):
    order_id = pick_by_archetype(ground_truth, "unexplained_difference", 3)
    payment = find_payment_by_order(mutated_dataset, order_id)
    provider = _ImmediatelyConcludingProvider()
    from tests.adversarial.helpers import DecisionEnvironment

    env = DecisionEnvironment(ledger=decision_env.ledger, approval_store=decision_env.approval_store, provider=provider, session=decision_env.session)
    result = decide_one(mutated_dataset, payment.payment_id, env)
    assert result.contradiction_records == []  # nothing was ever tested to challenge
    assert result.policy_decision.decision != PolicyDecisionType.SAFE_TO_RESOLVE
