from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import audit, exceptions, health, runs, sources

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(runs.router)
api_router.include_router(exceptions.router)
api_router.include_router(audit.router)
api_router.include_router(sources.router)
