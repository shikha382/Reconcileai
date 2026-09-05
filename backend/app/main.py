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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.router import api_router
from app.config import settings

# Optional single-origin production serving: if the frontend has been built
# (`npm run build` -> frontend/dist), FastAPI serves it directly so the
# deployed app has exactly one origin -- no CORS configuration and no
# frontend-side API base URL are needed in production, mirroring the same
# single-origin assumption the dev-time Vite proxy already makes (see
# frontend/vite.config.ts). When no build exists (e.g. plain `pytest`, or a
# backend-only dev server with the frontend run separately via `npm run
# dev`), this is a no-op and "/" keeps returning the existing JSON pointer.
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist"

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


# Mirrors the exact fix from frontend/vite.config.ts's `apiProxy` (M16,
# Phase 7): `/health`, `/runs`, `/exceptions`, and `/sources` are BOTH real
# API path prefixes and real SPA client-side routes (System Health, Runs,
# Exceptions list/detail). In dev, Vite's proxy tells the two apart by the
# `Accept` header a full-page navigation sends that a `fetch()` call never
# does. There is no separate proxy layer in single-origin production
# serving, so the same check is applied here, directly in front of routing:
# a full-page GET (browser navigation/refresh/bookmark) to one of these
# paths gets the SPA shell, not raw API JSON; every real `fetch()` call from
# already-loaded React code (no `Accept: text/html`) is unaffected and
# reaches the real API route exactly as before.
_SPA_COLLIDING_PREFIXES = ("/health", "/runs", "/exceptions", "/sources")


@app.middleware("http")
async def _spa_full_page_navigation_middleware(request: Request, call_next):
    if (
        _FRONTEND_DIST.is_dir()
        and request.method == "GET"
        and "text/html" in request.headers.get("accept", "")
        and any(
            request.url.path == prefix or request.url.path.startswith(prefix + "/")
            for prefix in _SPA_COLLIDING_PREFIXES
        )
    ):
        return FileResponse(_FRONTEND_DIST / "index.html")
    return await call_next(request)


register_exception_handlers(app)
app.include_router(api_router)

if _FRONTEND_DIST.is_dir():
    _ASSETS_DIR = _FRONTEND_DIST / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def _root() -> FileResponse:
        return FileResponse(_FRONTEND_DIST / "index.html")

    # SPA fallback: registered last, so every real API route above (and the
    # /assets mount) matches first. Only a real browser navigation (Accept:
    # text/html) to an otherwise-unmatched path is treated as a client-side
    # route (e.g. /about, /exceptions/EXC-123) and gets index.html so React
    # Router renders it; any other unmatched request (a `fetch()`-style call,
    # a malformed/probing path with no html Accept header) falls through to
    # the existing structured 404 handler unchanged -- this is required so a
    # path-traversal or injection-shaped probe still gets the same clean,
    # non-leaking 404 contract the M13/M14 security tests require, rather
    # than a misleading 200. `full_path` is resolved and containment-checked
    # against `_FRONTEND_DIST` before ever calling `is_file()`, since joining
    # untrusted path segments onto a directory is a classic traversal
    # vector (e.g. `full_path="../../etc/passwd"`).
    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str, request: Request):
        dist_root = _FRONTEND_DIST.resolve()
        candidate = (dist_root / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(dist_root):
            return FileResponse(candidate)
        if "text/html" in request.headers.get("accept", ""):
            return FileResponse(dist_root / "index.html")
        raise HTTPException(status_code=404, detail="Not Found")
else:

    @app.get("/", include_in_schema=False)
    def _root() -> dict:
        return {"service": "reconcileai", "docs": "/docs"}
