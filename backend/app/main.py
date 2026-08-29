"""ReconcileAI API entry point (Milestone 8).

This is a TRANSPORT boundary only -- see docs/api.md. It exposes M1-M7's
existing capabilities (ingestion, deterministic reconciliation, exception
intelligence, AI investigation, self-challenge, verification, risk, policy,
resolution/review, audit, provenance) through a typed HTTP surface. No
route in app/api/ performs financial matching, verification, risk scoring,
policy evaluation, or audit-chain logic itself -- every one of those calls
straight into the existing M1-M7 service layer.

Run (from the backend/ directory): uvicorn app.main:app --host <API_HOST> --port <API_PORT>
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Same repo-root/backend sys.path bootstrap every scripts/*.py entry point
# already does before importing app.*/shared -- needed here too since
# `uvicorn app.main:app` imports this module directly, with no pytest
# conftest.py to have set sys.path up first (shared.money is imported
# transitively by app.audit.ledger and others).
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT, _REPO_ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.config import settings

app = FastAPI(
    title="ReconcileAI API",
    description=(
        "Explainable multi-source settlement reconciliation controller. "
        "AI proposes, a deterministic verifier checks, a policy engine decides, "
        "humans approve when required, and every step is recorded on a tamper-evident audit ledger. "
        "This API is a window into that system -- it never becomes a second decision authority."
    ),
    version="0.1.0",
)

# CORS is configuration-driven and closed by default (Phase 17) -- never
# allow_origins=["*"] with credentials. An empty CORS_ALLOWED_ORIGINS list
# (the default) means no cross-origin requests are permitted at all.
if settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    # Phase 8: every request gets a request_id, distinct from any run_id a
    # POST /runs call might create. Honors a caller-supplied X-Request-ID
    # (so a client's own tracing correlates with ours); generates one
    # otherwise. Never confused with run_id: a single HTTP request creates
    # at most one run_id, but carries exactly one request_id regardless.
    request_id = request.headers.get("x-request-id") or f"REQ-{uuid.uuid4().hex[:16]}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


register_exception_handlers(app)
app.include_router(api_router)


@app.get("/", include_in_schema=False)
def _root():
    return {"service": "reconcileai", "docs": "/docs"}
