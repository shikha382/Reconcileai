from __future__ import annotations

from fastapi import APIRouter

from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health", response_model=HealthResponse,
    summary="Health check", description="Confirms the API process is running. Exposes no internal state or secrets.",
)
def health() -> HealthResponse:
    return HealthResponse()
