"""FastAPI dependency boundary (Phase 4/9/14/15). Plain function-based
dependency injection -- no separate DI framework, matching Phase 15's "keep
it simple" instruction. Every route depends on these, never constructs its
own DB session/provider/registry.
"""
from __future__ import annotations

from typing import Iterator, Optional

from fastapi import Depends, Header, Request

from app.ai.config import settings as ai_settings
from app.ai.provider import LLMProvider, build_provider
from app.api.errors import ApiError
from app.api.run_registry import RunRegistry
from app.audit.ledger import AuditLedger
from app.config import settings
from app.db.session import init_db, make_engine, make_session_factory
from app.policy.approval import ApprovalWorkflowStore
from app.policy.authorization import require_authorization
from app.policy.schemas import Actor, ActorType, Capability
from sqlalchemy.orm import Session

# --- Process-lifetime singletons ---------------------------------------------
# One shared engine/session-factory for the whole API process (Phase 14):
# each request gets its own Session, but all requests read/write the SAME
# database file, so a run's audit trail (written by one request) is visible
# to a later GET request for provenance/audit status. Overridable via
# FastAPI's dependency_overrides for tests (see backend/tests/api/conftest.py)
# -- this module-level state is not itself test-friendly on its own, by design;
# tests never rely on it directly.
_engine = None
_session_factory = None
_run_registry = RunRegistry()
_approval_store = ApprovalWorkflowStore()
_provider: LLMProvider | None = None


def _ensure_engine():
    global _engine, _session_factory
    if _engine is None:
        _engine = make_engine(settings.database_path)
        init_db(_engine)
        _session_factory = make_session_factory(_engine)
    return _session_factory


def get_session() -> Iterator[Session]:
    session_factory = _ensure_engine()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_ledger(session: Session = Depends(get_session)) -> AuditLedger:
    return AuditLedger(session)


def get_run_registry() -> RunRegistry:
    return _run_registry


def get_approval_store() -> ApprovalWorkflowStore:
    return _approval_store


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = build_provider(ai_settings.provider, ai_settings.model, ai_settings.api_key)
    return _provider


# --- Actor identity / authorization ------------------------------------------
# No enterprise IAM here (Phase 9 explicitly rules that out) -- a single,
# clean boundary: every request resolves to one Actor (default: a HUMAN
# operator identity), and every route declares the ONE capability it needs
# via require_capability(...). Optional X-Actor-Type/X-Actor-Id headers let a
# caller (or a test) present a different identity, e.g. to prove that an
# ActorType.AI-labeled caller is correctly refused START_RECONCILIATION --
# this is NOT a real authentication mechanism, and must never be mistaken
# for one; it exists so the authorization boundary is exercisable and
# testable now, ready for a real auth layer to plug in later without
# changing any route.
DEFAULT_ACTOR_ID = "api-client"


def get_actor(
    x_actor_type: Optional[str] = Header(default=None),
    x_actor_id: Optional[str] = Header(default=None),
) -> Actor:
    if x_actor_type is None:
        return Actor(ActorType.HUMAN, x_actor_id or DEFAULT_ACTOR_ID)
    try:
        actor_type = ActorType(x_actor_type.upper())
    except ValueError:
        raise ApiError(f"Unknown actor type {x_actor_type!r}.", code="INVALID_ACTOR_TYPE", status_code=400)
    return Actor(actor_type, x_actor_id or DEFAULT_ACTOR_ID)


def require_capability(capability: Capability):
    def _dependency(actor: Actor = Depends(get_actor)) -> Actor:
        require_authorization(actor, capability)  # raises AuthorizationError -> 403 (see app.api.errors)
        return actor

    return _dependency


# --- Request ID (Phase 8) ----------------------------------------------------

def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None)
