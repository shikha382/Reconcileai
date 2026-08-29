"""Environment-driven settings. No secrets are ever hardcoded here.

Milestone 1 only needs a database location; the LLM_* variables are declared
now (matching docs/ai-design.md's provider-abstraction design) but are not
read or used by any code yet -- the LLM is explicitly out of scope until a
later milestone (CLAUDE.md: "Do not add the LLM yet").
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class Settings:
    database_path: Path = REPO_ROOT / _env("RECONCILEAI_DB_PATH", "backend/reconcileai.db")

    # Declared for forward-compatibility with docs/ai-design.md; unused until
    # the AI Investigation Agent milestone.
    llm_provider: str = _env("LLM_PROVIDER", "unset")
    llm_model: str = _env("LLM_MODEL", "unset")
    llm_api_key: str = _env("LLM_API_KEY", "")

    # M8 API settings. Only what's actually needed -- no secrets here, and
    # CORS defaults closed (empty allow-list) rather than "*", per the M8
    # brief's explicit instruction.
    api_host: str = _env("API_HOST", "127.0.0.1")
    api_port: int = int(_env("API_PORT", "8000"))
    environment: str = _env("ENVIRONMENT", "development")
    cors_allowed_origins: list[str] = [o for o in _env("CORS_ALLOWED_ORIGINS", "").split(",") if o]

    # The only directory an API caller may request reconciliation against --
    # requests name a subdirectory (e.g. "seeds") relative to this base, never
    # an absolute or ".."-escaping path (see app.api.routes.runs's path-safety
    # check). Keeps POST /runs on the same "supported dataset/input mechanism"
    # M7 already established, without accepting an arbitrary filesystem path
    # from an HTTP client.
    dataset_base_dir: Path = REPO_ROOT / "data" / "synthetic"


settings = Settings()
