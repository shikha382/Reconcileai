"""GET /sources/status -- Milestone 14, Phase 21. Read-only; calls
`app.adapters.status.get_source_statuses` directly, which itself performs
no financial matching/verification/policy/decision logic -- it only reads
real fixture files and the real `ProviderSettings` and reports what it
finds. No POST/PUT/PATCH/DELETE route exists here or anywhere in this
package.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.adapters.status import get_source_statuses
from app.api.dependencies import require_capability
from app.api.schemas import SourceStatusResponse, SourcesStatusResponse
from app.policy.schemas import Capability

router = APIRouter(tags=["sources"])


@router.get(
    "/sources/status", response_model=SourcesStatusResponse,
    summary="Get the status of every configured data source",
    description=(
        "Milestone 14: reports each configured source's mode (SYNTHETIC DATA / MOCK PROVIDER / LIVE READ-ONLY / "
        "UNAVAILABLE), whether it is configured/available, and its real record count where knowable -- never "
        "reports LIVE unless real Razorpay credentials are actually configured, and never exposes those "
        "credentials themselves. Read-only; performs no matching/verification/policy/decision logic."
    ),
)
def get_sources_status(
    actor=Depends(require_capability(Capability.VIEW_RUN)),
) -> SourcesStatusResponse:
    statuses = get_source_statuses()
    return SourcesStatusResponse(
        sources=[
            SourceStatusResponse(
                name=s.name, mode=s.mode, configured=s.configured,
                available=s.available, record_count=s.record_count, detail=s.detail,
            )
            for s in statuses
        ]
    )
