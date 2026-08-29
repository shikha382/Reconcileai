"""Phase 16/17: environment-driven provider configuration. Mirrors
`app.config.Settings`'s own discipline exactly -- no secret is ever
hardcoded, logged, or given a real-looking default. Default mode is always
`fixture` (never `live`), so a fresh checkout with no environment
configured at all cannot accidentally attempt a real network call.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class ProviderSettings:
    # "fixture" | "mock" | "live" -- see app.adapters.base.ProviderMode.
    # Never defaults to "live": a real integration requires an explicit,
    # deliberate opt-in, per the M14 brief's own "default should use fixture/
    # mock provider, not production" instruction.
    provider_mode: str = _env("PROVIDER_MODE", "fixture").strip().lower()

    razorpay_api_base_url: str = _env("RAZORPAY_API_BASE_URL", "https://api.razorpay.com/v1")
    # Read from the environment only -- NEVER given a real-looking fallback
    # value, never logged, never returned by any API response or error
    # message, and never present in any audit-ledger payload (see
    # docs/provider-adapters.md's secret-safety section and
    # backend/tests/adapters/test_secret_safety.py).
    razorpay_api_key: str = _env("RAZORPAY_API_KEY", "")
    razorpay_api_secret: str = _env("RAZORPAY_API_SECRET", "")

    fixtures_dir: Path = REPO_ROOT / "data" / "synthetic" / "provider_fixtures"

    # Phase 13/14/15: bounded, conservative defaults -- never unlimited.
    max_page_size: int = int(_env("PROVIDER_MAX_PAGE_SIZE", "100"))
    max_pages_per_fetch: int = int(_env("PROVIDER_MAX_PAGES", "50"))
    max_retries: int = int(_env("PROVIDER_MAX_RETRIES", "3"))
    retry_base_delay_seconds: float = float(_env("PROVIDER_RETRY_BASE_DELAY", "0.5"))

    @property
    def has_live_credentials(self) -> bool:
        return bool(self.razorpay_api_key and self.razorpay_api_secret)

    def __repr__(self) -> str:
        # Deliberately never includes razorpay_api_key/razorpay_api_secret --
        # even a repr()/log line must not be able to leak them by accident.
        return (
            f"ProviderSettings(provider_mode={self.provider_mode!r}, "
            f"razorpay_api_base_url={self.razorpay_api_base_url!r}, "
            f"has_live_credentials={self.has_live_credentials})"
        )


settings = ProviderSettings()
