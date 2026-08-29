"""The LLMProvider abstraction (named and shaped per docs/ai-design.md,
written before any AI code existed). The rest of the codebase depends only
on this interface -- no module outside app.ai.provider imports a vendor SDK
or calls a vendor HTTP endpoint directly.

Three implementations:
- MockAIProvider: fully deterministic, scripted, no network access at all.
  This is what the entire test suite and the 300-record evaluation run
  against -- CI never needs a live API key (explicit M4 requirement).
- GeminiProvider: a real implementation, calling Gemini's REST API directly
  via the standard library (no SDK dependency added -- see docs/ai-controller.md's
  OSS-governance note on why). NOT exercised in this environment (no
  GEMINI_API_KEY available here); structurally complete and unit-testable
  for its request/response shaping, but its live network path is untested.
- OpenAICompatibleProvider: same shape, for any OpenAI-compatible chat-completions
  endpoint. Also untested live here.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol
from uuid import uuid4

from app.ai.schemas import (
    AIHypothesis,
    ConcludeAction,
    HypothesisAction,
    HypothesisType,
    InvestigationState,
    RecommendedAction,
    ToolCallAction,
)


class ProviderError(Exception):
    """Raised for any provider-side failure (timeout, malformed response,
    rate limit, unavailable) -- the controller catches this and degrades
    safely to HUMAN_REVIEW, never to auto-resolve. See app.ai.controller."""


class LLMProvider(Protocol):
    def decide_next_action(self, state: InvestigationState) -> ToolCallAction | HypothesisAction | ConcludeAction: ...


# --- Mock provider: deterministic, scripted, no network ------------------

_INVESTIGATION_PLAN = [
    ("get_exception_context", lambda pid: {}),
    ("get_related_records", lambda pid: {"record_id": pid, "relationship_types": ["payment", "settlement", "refund", "bank_transaction"]}),
    ("get_refunds", lambda pid: {"payment_id": pid}),
    ("get_candidate_matches", lambda pid: {"payment_id": pid}),
    ("get_negative_evidence", lambda pid: {"payment_id": pid}),
]

# The priority order a systematic investigator tries hypothesis types in.
# MISSING_RECORD goes FIRST: if nothing exists for this payment at all,
# every other hypothesis type would presuppose a settlement that isn't
# there, wasting the bounded step budget on hypotheses that can't possibly
# verify (caught empirically while building this milestone -- with
# MISSING_RECORD last in the list, a genuinely-missing-record investigation
# exhausted its step budget on doomed REFUND/FEE/... attempts before ever
# reaching the one hypothesis that would have verified). The MOCK provider
# follows this fixed order; it does not "know" the answer in advance, it
# proposes each type in turn and lets the deterministic verifier
# (app.ai.verifier) decide.
_HYPOTHESIS_PRIORITY = [
    HypothesisType.MISSING_RECORD,
    HypothesisType.REFUND_EXPLAINS_DIFFERENCE,
    HypothesisType.FEE_EXPLAINS_DIFFERENCE,
    HypothesisType.TIMING_DELAY,
    HypothesisType.REFERENCE_ERROR,
    HypothesisType.SPLIT_SETTLEMENT,
    HypothesisType.DUPLICATE,
    HypothesisType.AGGREGATED_SETTLEMENT,
    HypothesisType.AMBIGUOUS,
    HypothesisType.UNEXPLAINED_RESIDUAL,
]


class MockAIProvider:
    """A deterministic stand-in for a real model: follows a fixed,
    systematic evidence-gathering plan, then proposes hypotheses in a fixed
    priority order, one at a time, waiting for the verifier's answer before
    trying the next. It has no real inference -- every safety property this
    milestone demonstrates comes from the verifier/policy layer downstream,
    not from this mock being "smart". This is precisely what makes it a
    fair, honest test double: it forces the SAME architecture a real model
    would have to go through.
    """

    def __init__(self, hallucinate_record_id: str | None = None, hallucinate_hypothesis_type: HypothesisType | None = None):
        # Test hooks ONLY -- used by the hallucination/adversarial test
        # suite to simulate a misbehaving model without needing a live one.
        self._hallucinate_record_id = hallucinate_record_id
        self._hallucinate_hypothesis_type = hallucinate_hypothesis_type

    def decide_next_action(self, state: InvestigationState):
        if state.tool_call_count < len(_INVESTIGATION_PLAN):
            tool_name, build_input = _INVESTIGATION_PLAN[state.tool_call_count]
            tool_input = build_input(state.payment_id)
            if tool_name == "get_exception_context":
                tool_input["exception_id"] = state.exception_id
            return ToolCallAction(tool_name=tool_name, tool_input=tool_input)

        already_tried = {h["hypothesis"]["hypothesis_type"] for h in state.hypotheses_tested}
        remaining = [h for h in _HYPOTHESIS_PRIORITY if h.value not in already_tried]
        if not remaining:
            return ConcludeAction(reason="exhausted all hypothesis types without a verified explanation")

        next_type = self._hallucinate_hypothesis_type or remaining[0]

        if self._hallucinate_record_id:
            record_ids = [state.payment_id, self._hallucinate_record_id]
        else:
            record_ids = [state.payment_id, *self._relevant_settlement_ids(state, next_type)]

        hypothesis = AIHypothesis(
            hypothesis_id=str(uuid4()), exception_id=state.exception_id, hypothesis_type=next_type,
            claim=f"proposing {next_type.value} for {state.payment_id}",
            record_ids=record_ids, evidence_ids=record_ids,
            confidence=0.75, recommended_action=self._advisory_action(next_type),
        )
        return HypothesisAction(hypothesis=hypothesis)

    @staticmethod
    def _relevant_settlement_ids(state: InvestigationState, hypothesis_type: HypothesisType) -> list[str]:
        """Pulls settlement IDs the session has ACTUALLY retrieved via tool
        calls so far (get_related_records' linked settlement, or
        get_candidate_matches' unlinked pool) -- never invents one."""
        related_settlements: list[str] = []
        candidate_settlements: list[str] = []
        for obs in state.observations:
            if obs.tool_name == "get_related_records":
                related_settlements = obs.tool_output.get("settlement_ids", [])
            if obs.tool_name == "get_candidate_matches":
                candidate_settlements = [c["settlement_id"] for c in obs.tool_output.get("candidates", [])]

        if hypothesis_type in (HypothesisType.DUPLICATE, HypothesisType.SPLIT_SETTLEMENT):
            return related_settlements or candidate_settlements
        if hypothesis_type == HypothesisType.AGGREGATED_SETTLEMENT:
            return candidate_settlements[:1] or related_settlements[:1]
        # Single-settlement hypotheses (refund/fee/tax/timing/reference_error):
        # prefer the one directly linked settlement if there is exactly one.
        if len(related_settlements) == 1:
            return related_settlements
        return candidate_settlements[:1] or related_settlements[:1]

    @staticmethod
    def _advisory_action(hypothesis_type: HypothesisType) -> RecommendedAction:
        if hypothesis_type in (HypothesisType.AMBIGUOUS, HypothesisType.DUPLICATE, HypothesisType.UNEXPLAINED_RESIDUAL):
            return RecommendedAction.HUMAN_REVIEW
        if hypothesis_type == HypothesisType.MISSING_RECORD:
            return RecommendedAction.UNRESOLVED
        return RecommendedAction.SAFE_TO_RESOLVE


# --- Real providers: REST calls via the standard library, no SDK ---------

class GeminiProvider:
    """Calls Gemini's generateContent REST endpoint directly (no
    google-generativeai SDK dependency -- see docs/ai-controller.md's
    OSS-governance note). NOT exercised in this environment: no
    GEMINI_API_KEY is configured, so this path has never made a live call
    here. Structurally implements the same decide_next_action contract as
    MockAIProvider; a real deployment would parse the model's function-call
    response into the same ToolCallAction/HypothesisAction/ConcludeAction
    union this module defines.
    """

    ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

    def __init__(self, model: str, api_key: str, timeout_seconds: float = 20.0):
        if not api_key:
            raise ProviderError("GeminiProvider requires an API key (AI_API_KEY/LLM_API_KEY) -- none configured")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def decide_next_action(self, state: InvestigationState):
        payload = self._build_request(state)
        try:
            request = urllib.request.Request(
                self.ENDPOINT_TEMPLATE.format(model=self.model, key=self.api_key),
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ProviderError(f"Gemini request failed: {exc}") from exc
        except TimeoutError as exc:
            raise ProviderError(f"Gemini request timed out: {exc}") from exc

        return self._parse_response(raw)

    def _build_request(self, state: InvestigationState) -> dict:
        # A real implementation would include the system prompt (see
        # docs/ai-controller.md's evidence-first prompting section) and the
        # tool/function declarations here. Kept minimal since this path is
        # not exercised without a live key.
        return {
            "contents": [{"role": "user", "parts": [{"text": state.model_dump_json()}]}],
        }

    def _parse_response(self, raw: dict):
        try:
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ProviderError(f"malformed Gemini response: {exc}") from exc

        action_type = parsed.get("action_type")
        if action_type == "tool_call":
            return ToolCallAction.model_validate(parsed)
        if action_type == "hypothesis":
            return HypothesisAction.model_validate(parsed)
        return ConcludeAction(reason=parsed.get("reason", "model concluded"))


class OpenAICompatibleProvider:
    """Same shape as GeminiProvider, for any OpenAI-compatible
    chat-completions endpoint. Also NOT exercised in this environment."""

    def __init__(self, model: str, api_key: str, base_url: str = "https://api.openai.com/v1", timeout_seconds: float = 20.0):
        if not api_key:
            raise ProviderError("OpenAICompatibleProvider requires an API key -- none configured")
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def decide_next_action(self, state: InvestigationState):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": state.model_dump_json()}],
            "response_format": {"type": "json_object"},
        }
        try:
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ProviderError(f"OpenAI-compatible request failed: {exc}") from exc
        except TimeoutError as exc:
            raise ProviderError(f"OpenAI-compatible request timed out: {exc}") from exc

        try:
            text = raw["choices"][0]["message"]["content"]
            parsed = json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ProviderError(f"malformed response: {exc}") from exc

        action_type = parsed.get("action_type")
        if action_type == "tool_call":
            return ToolCallAction.model_validate(parsed)
        if action_type == "hypothesis":
            return HypothesisAction.model_validate(parsed)
        return ConcludeAction(reason=parsed.get("reason", "model concluded"))


def build_provider(provider_name: str, model: str, api_key: str) -> LLMProvider:
    if provider_name == "mock":
        return MockAIProvider()
    if provider_name == "gemini":
        return GeminiProvider(model=model, api_key=api_key)
    if provider_name in ("openai", "openai_compatible"):
        return OpenAICompatibleProvider(model=model, api_key=api_key)
    raise ProviderError(f"unknown AI_PROVIDER {provider_name!r}")
