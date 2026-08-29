"""Deterministic triage: do not send every exception to the LLM. Simple
exact matches and anything M3 already deterministically VERIFIED never
reach the AI at all -- there is nothing left to investigate, and every
unnecessary AI call is cost, latency, and hallucination surface for no
benefit. Only the residual cases M2/M3's own deterministic hypothesis
testing couldn't fully verify go to AI investigation.
"""
from __future__ import annotations

from app.engines.root_cause.result import VERIFIED, RootCauseResult


def needs_ai_investigation(root_cause: RootCauseResult) -> bool:
    """True for PARTIALLY_EXPLAINED / UNEXPLAINED / CONTRADICTED / AMBIGUOUS
    -- the cases M3's own deterministic hypothesis testing did not fully
    verify. False for VERIFIED -- already safely resolved, no AI needed."""
    return root_cause.status != VERIFIED
