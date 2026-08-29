"""The bounded AI investigation loop -- the architectural spine of M4.

EXCEPTION -> STRUCTURED EVIDENCE -> AI HYPOTHESIS -> CONTROLLED TOOLS ->
EVIDENCE RETRIEVAL -> DETERMINISTIC VERIFICATION -> POLICY GATE ->
SAFE_TO_RESOLVE / HUMAN_REVIEW / REJECTED / UNRESOLVED.

The AI never touches this boundary directly: it can only request a tool
call (validated, allow-listed) or submit a hypothesis (grounded, then
independently verified). The loop is hard-bounded by MAX_TOOL_CALLS /
MAX_INVESTIGATION_STEPS -- no infinite agent loop is possible.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import uuid4

from app.ai.config import settings
from app.ai.policy import HypothesisOutcome, decide_final_outcome, decide_hypothesis_outcome
from app.ai.provider import LLMProvider, ProviderError
from app.ai.schemas import (
    AIInvestigationTrace,
    ConcludeAction,
    HypothesisAction,
    InvestigationState,
    ObservedToolCall,
    RecommendedAction,
    TestHypothesisInput,
    ToolCallAction,
    TraceStep,
    TraceStepType,
)
from app.ai.tools import InvestigationContext, ToolAuthorizationError, invoke_tool
from app.ai.verifier import validate_grounding, verify_hypothesis

PROMPT_VERSION = "m4-controller-0.1.0"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _extract_ids_by_prefix(record_ids: list[str], prefix: str) -> list[str]:
    return [r for r in record_ids if r.startswith(prefix)]


def _build_test_hypothesis_input(hypothesis, ctx: InvestigationContext) -> TestHypothesisInput:
    settlement_ids = _extract_ids_by_prefix(hypothesis.record_ids, "STL-")
    payment_ids = _extract_ids_by_prefix(hypothesis.record_ids, "PAY-")
    other_payment_ids = [p for p in payment_ids if p != ctx.payment.payment_id]

    return TestHypothesisInput(
        exception_id=hypothesis.exception_id,
        payment_id=ctx.payment.payment_id,
        hypothesis_type=hypothesis.hypothesis_type,
        settlement_id=settlement_ids[0] if settlement_ids else None,
        candidate_payment_ids=[ctx.payment.payment_id, *other_payment_ids] if other_payment_ids else [],
        candidate_settlement_ids=settlement_ids,
    )


class AIInvestigationResult:
    def __init__(self, final_decision: RecommendedAction, reason: str, outcomes: list[HypothesisOutcome], trace: AIInvestigationTrace):
        self.final_decision = final_decision
        self.reason = reason
        self.outcomes = outcomes
        self.trace = trace


def investigate(exception_id: str, ctx: InvestigationContext, provider: LLMProvider) -> AIInvestigationResult:
    started_at = _now()
    t0 = time.perf_counter()

    trace = AIInvestigationTrace(
        investigation_id=str(uuid4()), exception_id=exception_id,
        provider=type(provider).__name__, model=getattr(provider, "model", "n/a"),
        prompt_version=PROMPT_VERSION, started_at=started_at,
    )
    trace.steps.append(TraceStep(
        type=TraceStepType.OBSERVATION, timestamp=_now(),
        message=f"Investigating exception {exception_id} for payment {ctx.payment.payment_id}.",
    ))

    state = InvestigationState(exception_id=exception_id, payment_id=ctx.payment.payment_id)
    outcomes: list[HypothesisOutcome] = []

    while state.step_count < settings.max_investigation_steps and state.tool_call_count < settings.max_tool_calls:
        state.step_count += 1
        try:
            action = provider.decide_next_action(state)
        except ProviderError as exc:
            trace.errors.append(str(exc))
            trace.steps.append(TraceStep(type=TraceStepType.ERROR, timestamp=_now(), message=f"Provider failure: {exc}"))
            break  # degrade safely -- final decision below defaults to HUMAN_REVIEW

        if isinstance(action, ToolCallAction):
            trace.steps.append(TraceStep(
                type=TraceStepType.TOOL_CALL, timestamp=_now(),
                message=f"Calling tool {action.tool_name}", payload={"tool_input": action.tool_input},
            ))
            try:
                output = invoke_tool(action.tool_name, action.tool_input, ctx)
            except ToolAuthorizationError as exc:
                trace.steps.append(TraceStep(
                    type=TraceStepType.REJECTION, timestamp=_now(),
                    message=f"Tool call rejected: {exc}",
                ))
                continue
            state.tool_call_count += 1
            state.observations.append(ObservedToolCall(tool_name=action.tool_name, tool_input=action.tool_input, tool_output=output))
            trace.tool_call_count = state.tool_call_count
            trace.steps.append(TraceStep(type=TraceStepType.TOOL_RESULT, timestamp=_now(), message=f"{action.tool_name} returned.", payload={"tool_output": output}))
            continue

        if isinstance(action, HypothesisAction):
            hypothesis = action.hypothesis
            trace.steps.append(TraceStep(
                type=TraceStepType.HYPOTHESIS, timestamp=_now(),
                message=f"Proposing {hypothesis.hypothesis_type.value}: {hypothesis.claim}",
                payload=hypothesis.model_dump(mode="json"),
            ))
            trace.hypotheses_tested.append(hypothesis.hypothesis_type.value)

            grounding_violations = validate_grounding(hypothesis, state.known_record_ids())
            test_input = _build_test_hypothesis_input(hypothesis, ctx)
            verifier_result = verify_hypothesis(test_input, ctx) if not grounding_violations else None

            if grounding_violations:
                trace.steps.append(TraceStep(
                    type=TraceStepType.REJECTION, timestamp=_now(),
                    message="Hypothesis rejected: cites unretrieved/hallucinated record IDs.",
                    payload={"violations": grounding_violations},
                ))
                from app.ai.schemas import TestHypothesisOutput

                verifier_result = TestHypothesisOutput(hypothesis_type=hypothesis.hypothesis_type, passed=False, reason="ungrounded hypothesis")
            else:
                trace.steps.append(TraceStep(
                    type=TraceStepType.VERIFICATION, timestamp=_now(),
                    message=f"Verifier: {'PASSED' if verifier_result.passed else 'REJECTED'} -- {verifier_result.reason}",
                    payload=verifier_result.model_dump(mode="json"),
                ))

            financial_delta = ctx.payment.amount
            outcome = decide_hypothesis_outcome(hypothesis, verifier_result, grounding_violations, financial_delta)
            outcomes.append(outcome)
            state.hypotheses_tested.append({
                "hypothesis": hypothesis.model_dump(mode="json"),
                "verifier_result": verifier_result.model_dump(mode="json"),
                "decision": outcome.decision.value,
            })
            trace.steps.append(TraceStep(type=TraceStepType.POLICY, timestamp=_now(), message=f"Policy: {outcome.decision.value} -- {outcome.reason}"))

            if outcome.decision in (RecommendedAction.SAFE_TO_RESOLVE, RecommendedAction.UNRESOLVED):
                break
            continue

        if isinstance(action, ConcludeAction):
            trace.steps.append(TraceStep(type=TraceStepType.OBSERVATION, timestamp=_now(), message=f"Provider concluded: {action.reason}"))
            break

        # Malformed/unrecognized provider output: not one of the three
        # valid action types (a real provider integration validates its
        # response into one of these schemas -- see app.ai.provider -- and
        # would itself raise ProviderError before ever getting here; this
        # branch is the last-resort safety net if some future provider
        # implementation returns something unvalidated).
        trace.errors.append(f"provider returned an unrecognized action type: {type(action)!r}")
        trace.steps.append(TraceStep(type=TraceStepType.ERROR, timestamp=_now(), message="Provider returned a malformed/unrecognized action; ignoring and ending the investigation."))
        break

    final_decision, reason = decide_final_outcome(outcomes)
    trace.final_decision = final_decision
    trace.completed_at = _now()
    trace.duration_seconds = time.perf_counter() - t0

    return AIInvestigationResult(final_decision=final_decision, reason=reason, outcomes=outcomes, trace=trace)
