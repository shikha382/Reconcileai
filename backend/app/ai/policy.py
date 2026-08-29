"""The deterministic policy gate. Sits after verification, before any
decision is finalized -- the AI cannot override this, cannot see its
thresholds change based on anything it says, and cannot skip it.

Two levels:
- `decide_hypothesis_outcome`: per single tested hypothesis -- REJECTED
  (disproven or ungrounded), HUMAN_REVIEW (verified but policy blocks
  auto-resolution), or SAFE_TO_RESOLVE.
- `decide_final_outcome`: what the controller reports for the WHOLE
  investigation once its loop ends (one or more hypotheses tested).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.ai.schemas import AIHypothesis, HypothesisType, RecommendedAction, TestHypothesisOutput

# Categories that are policy-blocked from auto-resolution even when the
# underlying claim is deterministically VERIFIED -- mirrors the M3 finding
# that root-cause certainty and auto-resolution eligibility are different
# questions (CLAUDE.md: reversed_transaction/duplicate divergence).
NEVER_AUTO_RESOLVE_TYPES = frozenset({
    HypothesisType.DUPLICATE,
    HypothesisType.AMBIGUOUS,
    HypothesisType.UNEXPLAINED_RESIDUAL,
    HypothesisType.MISSING_RECORD,
    HypothesisType.PARTIAL_SETTLEMENT,
})

# Same categorical rule, applied to M3's ExceptionCategory instead of an AI
# hypothesis type -- for exceptions M3 already root-cause-VERIFIED (so they
# never reach the AI at all, see app.ai.routing), the categorical
# human-review rule must still apply. Root-cause CERTAINTY and
# auto-resolution ELIGIBILITY are different questions (CLAUDE.md's M3
# architectural decision on reversed_transaction/duplicate) -- caught
# empirically while building this milestone: without this, a confirmed
# reversed_transaction (a fully-understood, VERIFIED reversal) skipped AI
# and fell straight through to SAFE_TO_RESOLVE, an undocumented false
# auto-resolution. See CLAUDE.md's M4 architectural decision.
NEVER_AUTO_RESOLVE_CATEGORIES = frozenset({"reversed_transaction", "duplicate"})

# Any single exception above this exposure is always routed to a human,
# regardless of how confident the verified hypothesis is (docs/ai-design.md's
# policy engine section: "any exception with amount_at_risk above a
# configured value always requires human review, regardless of confidence").
MAX_AUTO_RESOLVE_AMOUNT = Decimal("100000.00")


@dataclass
class HypothesisOutcome:
    hypothesis: AIHypothesis
    verifier_result: TestHypothesisOutput
    grounded: bool
    decision: RecommendedAction
    reason: str


def decide_hypothesis_outcome(hypothesis: AIHypothesis, verifier_result: TestHypothesisOutput, grounding_violations: list[str], financial_delta: Decimal) -> HypothesisOutcome:
    if grounding_violations:
        return HypothesisOutcome(
            hypothesis=hypothesis, verifier_result=verifier_result, grounded=False,
            decision=RecommendedAction.REJECTED,
            reason=f"hypothesis cites unretrieved/hallucinated IDs: {'; '.join(grounding_violations)}",
        )

    if not verifier_result.passed:
        return HypothesisOutcome(
            hypothesis=hypothesis, verifier_result=verifier_result, grounded=True,
            decision=RecommendedAction.REJECTED,
            reason=f"deterministic verification failed: {verifier_result.reason}",
        )

    if hypothesis.hypothesis_type == HypothesisType.MISSING_RECORD:
        return HypothesisOutcome(
            hypothesis=hypothesis, verifier_result=verifier_result, grounded=True,
            decision=RecommendedAction.UNRESOLVED,
            reason="confirmed no settlement or candidate exists yet -- nothing to review, correctly unresolved",
        )

    if hypothesis.hypothesis_type in NEVER_AUTO_RESOLVE_TYPES:
        return HypothesisOutcome(
            hypothesis=hypothesis, verifier_result=verifier_result, grounded=True,
            decision=RecommendedAction.HUMAN_REVIEW,
            reason=f"{hypothesis.hypothesis_type.value} is policy-blocked from auto-resolution regardless of verification outcome",
        )

    residual = _safe_decimal(verifier_result.residual)
    if residual is not None and residual != Decimal("0.00"):
        return HypothesisOutcome(
            hypothesis=hypothesis, verifier_result=verifier_result, grounded=True,
            decision=RecommendedAction.HUMAN_REVIEW,
            reason=f"verified but a residual of {residual} remains -- only partially explained",
        )

    if financial_delta > MAX_AUTO_RESOLVE_AMOUNT:
        return HypothesisOutcome(
            hypothesis=hypothesis, verifier_result=verifier_result, grounded=True,
            decision=RecommendedAction.HUMAN_REVIEW,
            reason=f"financial exposure {financial_delta} exceeds the auto-resolve threshold {MAX_AUTO_RESOLVE_AMOUNT}, regardless of confidence",
        )

    return HypothesisOutcome(
        hypothesis=hypothesis, verifier_result=verifier_result, grounded=True,
        decision=RecommendedAction.SAFE_TO_RESOLVE,
        reason="hypothesis deterministically verified, zero residual, auto-resolvable category, within risk threshold",
    )


def _safe_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def decide_final_outcome(outcomes: list[HypothesisOutcome]) -> tuple[RecommendedAction, str]:
    """What the controller reports once its bounded loop ends. Never
    silently defaults to auto-resolve; the safe fallback is always
    HUMAN_REVIEW unless a hypothesis was actually verified SAFE_TO_RESOLVE,
    or the record is confirmed genuinely missing (UNRESOLVED)."""
    for outcome in outcomes:
        if outcome.decision == RecommendedAction.SAFE_TO_RESOLVE:
            return RecommendedAction.SAFE_TO_RESOLVE, outcome.reason

    for outcome in outcomes:
        if outcome.decision == RecommendedAction.UNRESOLVED:
            return RecommendedAction.UNRESOLVED, outcome.reason

    if not outcomes:
        return RecommendedAction.HUMAN_REVIEW, "no hypothesis was tested (investigation loop exhausted before any proposal)"

    return RecommendedAction.HUMAN_REVIEW, "no hypothesis was safely verifiable -- escalating rather than guessing"
