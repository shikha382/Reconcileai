"""Environment-driven AI settings. No secrets hardcoded. Matches the
LLMProvider abstraction already documented in docs/ai-design.md and the
LLM_PROVIDER/LLM_MODEL/LLM_API_KEY env vars declared (unused, forward-
compatible) in app.config since Milestone 1.
"""
from __future__ import annotations

import os


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class AISettings:
    provider: str = _env("AI_PROVIDER", _env("LLM_PROVIDER", "mock"))
    model: str = _env("AI_MODEL", _env("LLM_MODEL", "unset"))
    api_key: str = _env("AI_API_KEY", _env("LLM_API_KEY", ""))

    # Bounded investigation loop -- never allow an unbounded agent loop.
    max_tool_calls: int = int(_env("AI_MAX_TOOL_CALLS", "8"))
    max_investigation_steps: int = int(_env("AI_MAX_INVESTIGATION_STEPS", "16"))
    max_token_budget: int = int(_env("AI_MAX_TOKEN_BUDGET", "8000"))  # advisory; enforced where the provider reports usage

    # Provider network behavior (real providers only; irrelevant to the mock).
    request_timeout_seconds: float = float(_env("AI_REQUEST_TIMEOUT_SECONDS", "20"))


settings = AISettings()
