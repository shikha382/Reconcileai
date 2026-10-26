"""Optional local paraphrasing adapter. Never imported by the decision pipeline.

Financial truth belongs to build_explanation/Decimal, not generated prose.
This module has no database session, tools, or financial mutation authority.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from decimal import Decimal
from threading import Lock
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import get_run_registry, require_capability
from app.api.errors import ApiError
from app.api.run_registry import RunRegistry
from app.explainability.builder import build_explanation
from app.policy.schemas import Capability

MODEL = "granite4:3b"
OLLAMA = "http://127.0.0.1:11434"
TIMEOUT = 120
_inference = Lock()
router = APIRouter(tags=["local-granite"])


def enabled() -> bool:
    return (os.getenv("GRANITE_ENABLED") == "1"
            and os.getenv("ENVIRONMENT", "development") == "development")


def local_access(request: Request) -> None:
    if not enabled():
        raise ApiError("Local experiment is disabled.", code="NOT_FOUND", status_code=404)
    # Do not trust forwarded headers: this experiment is not proxy-deployable.
    if (not request.client or request.client.host not in {"127.0.0.1", "::1"}
            or request.url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-forwarded-host"))):
        raise ApiError("Loopback access required.", code="LOCAL_ONLY", status_code=403)
    origin = request.headers.get("origin")
    if origin not in {None, "http://127.0.0.1:5173", "http://localhost:5173",
                      "http://127.0.0.1:8000", "http://localhost:8000"}:
        raise ApiError("Local origin required.", code="LOCAL_ONLY", status_code=403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise ApiError("Cross-site access refused.", code="LOCAL_ONLY", status_code=403)


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=10, max_length=650)
    decision: str
    fact_ids: list[str] = Field(min_length=2, max_length=12)


class ExplanationAnswer(BaseModel):
    explanation: str
    fact_ids: list[str]
    model: str
    source: Literal["granite", "deterministic_fallback"]
    elapsed_ms: int
    snapshot_fingerprint: str
    fallback_reason: str | None = None
    load_ms: int | None = None


def snapshot(decision) -> dict[str, str]:
    """Allowlist only: no identifiers, source records, notes, or hypothesis prose."""
    report = build_explanation(decision)
    return {
        "category": str(decision.bundle.category or "clean_match"),
        "currency": report.financial_summary.currency,
        "expected": report.financial_summary.expected_amount,
        "observed": report.financial_summary.observed_amount,
        "residual": report.financial_summary.unexplained_amount,
        "verification": ("CONTRADICTED" if report.contradictions else
                         "INCOMPLETE" if report.ai_investigation_status == "UNAVAILABLE_OR_DEGRADED" else
                         "NOT_NEEDED" if not report.ai_hypotheses else
                         "INCOMPLETE" if any(h.verification_result != "PASSED" for h in report.ai_hypotheses)
                         else "PASSED"),
        "decision": report.policy.decision,
        "approval_required": str(report.policy.required_approval).lower(),
        # Rule identifiers are bounded structured codes, not user-authored text.
        "reason_codes": ", ".join(report.policy.rules_passed[:5])[:250],
    }


def fingerprint(facts: dict) -> str:
    return hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()


def grounding_statements(facts: dict[str, str]) -> dict[str, str]:
    """Give a small model explicit meanings, not overloaded codes or arithmetic.

    Values still come only from the existing snapshot. Exact monetary values
    stay in the authoritative UI; no raw policy IDs or numbers need paraphrasing.
    This is presentation wording, not a new financial decision engine.
    """
    verification = {
        "CONTRADICTED": "An AI hypothesis was checked and rejected. This describes the hypothesis, not the validity of all financial records.",
        "PASSED": "An AI hypothesis was checked and supported. This does not by itself clear the exception.",
        "INCOMPLETE": "AI hypothesis checks are incomplete; no additional verification conclusion is supported.",
        "NOT_NEEDED": "No AI hypothesis needed checking for this case.",
    }
    decisions = {
        "SAFE_TO_RESOLVE": "The existing policy marks this case safe to resolve. This explanation does not execute any financial action.",
        "HUMAN_REVIEW": "The existing policy requires human review. Automatic resolution is not authorized.",
        "REJECTED": "The existing policy rejected this case. Automatic resolution is not authorized.",
        "UNRESOLVED": "The case remains unresolved under the existing policy. It has not been cleared.",
        "ESCALATED": "The existing policy escalated this case. It has not been cleared for automatic resolution.",
    }
    return {
        "category": "The recorded classification is " + facts["category"].replace("_", " ") + ".",
        "verification": verification.get(facts["verification"], "The hypothesis verification status is unknown."),
        "decision": decisions.get(facts["decision"], "The existing policy decision is not recognized; do not infer permission to act."),
        "approval_required": ("Policy requires approval." if facts["approval_required"] == "true" else
                              "The approval-required flag is false; this does not override the policy decision."),
    }


def validate_answer(raw: str, facts: dict[str, str]) -> ModelAnswer:
    answer = ModelAnswer.model_validate_json(raw)
    if answer.decision != facts["decision"]:
        raise ValueError("decision_mismatch")
    if (not set(answer.fact_ids).issubset(facts)
            or "decision" not in answer.fact_ids
            or len(set(answer.fact_ids)) != len(answer.fact_ids)):
        raise ValueError("unsupported_facts")
    # Accept only existing monetary values, never new arithmetic or thresholds.
    # ASCII English also prevents hidden control characters/Unicode digit tricks.
    text = answer.summary
    if (not text.isascii() or any(ord(c) < 32 for c in text)
            or re.search(r"[<>$]|(?:https?://)", text) or len(text.split()) > 85):
        raise ValueError("unsupported_numbers_or_markup")
    allowed = {Decimal(facts[k]) for k in ("expected", "observed", "residual")}
    for number in re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", text):
        if Decimal(number.replace(",", "")) not in allowed:
            raise ValueError("unsupported_number")
    if re.search(r"\b(?:AMOUNT|PLACEHOLDER|REDACTED)\b|\*{2,}", text):
        raise ValueError("placeholder_text")
    # Explicit labels must agree; this is a guardrail, not a semantic proof.
    labels = {"SAFE_TO_RESOLVE", "HUMAN_REVIEW", "UNRESOLVED", "BLOCKED", "REJECTED"}
    if any(label in text and label != facts["decision"] for label in labels):
        raise ValueError("contradictory_label")
    if facts["decision"] != "SAFE_TO_RESOLVE" and re.search(
        r"\b(?:safe to resolve|auto.?resolv\w*|approved|reconciled|resolved successfully)\b", text, re.I
    ):
        raise ValueError("unsafe_resolution_claim")
    if facts["verification"] == "CONTRADICTED" and re.search(
        r"\b(?:verification passed|fully verified|hypothesis is correct)\b", text, re.I
    ):
        raise ValueError("contradictory_verification")
    if facts["approval_required"] == "true" and re.search(
        r"\b(?:no approval|approval is not required|without (?:human )?approval)\b", text, re.I
    ):
        raise ValueError("contradictory_approval")
    if facts["verification"] in {"PASSED", "CONTRADICTED", "INCOMPLETE"}:
        if re.search(r"verif|contradict", text, re.I) and not re.search(r"hypothes", text, re.I):
            raise ValueError("verification_scope_ambiguous")
    if re.search(r"result(?:s|ing)? in (?:a |an |the )?residual", text, re.I):
        raise ValueError("unsupported_residual_derivation")
    return answer


def fallback(facts: dict[str, str]) -> str:
    category = facts["category"].replace("_", " ")
    return (f"This exception concerns {category}. Expected: {facts['currency']} {facts['expected']}; "
            f"observed: {facts['currency']} {facts['observed']}; unexplained residual: "
            f"{facts['currency']} {facts['residual']}. Hypothesis verification: {facts['verification']}. "
            f"The existing policy decision remains {facts['decision']}. "
            f"Approval required: {facts['approval_required']}. No financial record was changed.")


async def status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
            response = await client.get(f"{OLLAMA}/api/tags")
            response.raise_for_status()
            installed = any(m.get("name") == MODEL for m in response.json().get("models", []))
        return {"available": installed, "ollama_connected": True, "model": MODEL,
                "reason": None if installed else "Model is not installed. No automatic download."}
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return {"available": False, "ollama_connected": False, "model": MODEL,
                "reason": "Ollama is unavailable. Start Ollama locally and retry."}


async def explain(facts: dict[str, str]) -> ExplanationAnswer:
    if not _inference.acquire(blocking=False):
        raise ApiError("Another local explanation is running.", code="GRANITE_BUSY", status_code=429)
    started = time.perf_counter()
    try:
        reason = None
        answer = None
        load_ms = None
        schema = ModelAnswer.model_json_schema()
        statements = grounding_statements(facts)
        schema["properties"]["decision"]["enum"] = [facts["decision"]]
        schema["properties"]["fact_ids"]["items"] = {"type": "string", "enum": list(statements)}
        try:
            async with asyncio.timeout(TIMEOUT), httpx.AsyncClient(timeout=TIMEOUT, trust_env=False) as client:
                # Bound the response before parsing to avoid unbounded provider output.
                async with client.stream("POST", f"{OLLAMA}/api/chat", json={
                    "model": MODEL, "stream": False, "format": schema,
                    "keep_alive": "60s", "options": {"num_ctx": 2048, "num_predict": 256, "temperature": 0},
                    "messages": [{"role": "system", "content": (
                        "Rewrite the supplied statements into a short, plain-English explanation, up to three sentences. "
                        "Keep their meaning exactly. Mention the recorded classification, AI hypothesis checking, "
                        "and existing policy outcome. A checked hypothesis is NOT a cleared transaction. "
                        "Do not infer causes, calculate amounts, give advice, or add facts. "
                        "Amounts are already visible elsewhere; omit numbers, IDs and policy codes. "
                        "Return JSON with summary, the exact decision label supplied, and fact_ids naming the "
                        "statement keys used. Include category, verification and decision in fact_ids."
                    )}, {"role": "user", "content": json.dumps({
                        "decision_label": facts["decision"], "statements": statements,
                    })}],
                }) as response:
                    response.raise_for_status()
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > 32768:
                            raise ValueError("oversized_response")
                payload = json.loads(chunks)
                load_ms = max(0, int(payload.get("load_duration", 0) / 1_000_000))
                answer = validate_answer(payload["message"]["content"], facts)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, OverflowError, TimeoutError):
            reason = "Model unavailable, timed out, or response failed validation."
        return ExplanationAnswer(
            explanation=answer.summary if answer else fallback(facts),
            fact_ids=answer.fact_ids if answer else list(facts), model=MODEL,
            source="granite" if answer else "deterministic_fallback",
            elapsed_ms=round((time.perf_counter() - started) * 1000),
            snapshot_fingerprint=fingerprint(facts), fallback_reason=reason, load_ms=load_ms,
        )
    finally:
        _inference.release()


@router.get("/granite/status", dependencies=[Depends(local_access)], include_in_schema=False)
async def granite_status(actor=Depends(require_capability(Capability.VIEW_EXCEPTION))):
    return await status()


@router.post("/exceptions/{exception_id}/granite-explanation", response_model=ExplanationAnswer,
             dependencies=[Depends(local_access)], include_in_schema=False)
async def granite_explanation(
    exception_id: str, request: Request,
    registry: RunRegistry = Depends(get_run_registry),
    actor=Depends(require_capability(Capability.VIEW_EXCEPTION)),
):
    if request.query_params:
        raise ApiError("No query parameters accepted.", code="INVALID_INPUT")
    # No body is necessary. Reject even small unsolicited prompts or facts.
    async for chunk in request.stream():
        if chunk:
            raise ApiError("Request body must be empty.", code="INVALID_INPUT")
    facts = snapshot(registry.get_exception(exception_id))
    task = asyncio.create_task(explain(facts))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.1)
            if await request.is_disconnected():
                raise asyncio.CancelledError()
        return await task
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
