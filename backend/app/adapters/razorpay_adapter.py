"""Phase 1/3/13/14/15: the Razorpay-compatible read-only adapter.

Three modes (`app.adapters.base.ProviderMode`), selected via
`PROVIDER_MODE` (`app.adapters.config`):

- `fixture` (default): reads realistic, clearly-labeled SYNTHETIC JSON
  fixtures from disk (`data/synthetic/provider_fixtures/`). Fully offline,
  fully deterministic -- what every automated test in this project uses.
- `mock`: an in-memory, caller-supplied page sequence (used by tests that
  need to control exactly what a "provider" returns per page, e.g. to
  exercise pagination/retry/rate-limit/schema-drift scenarios without a
  real fixture file).
- `live`: makes a real, read-only HTTP GET against the configured
  Razorpay API base URL, using HTTP Basic auth (Razorpay's own documented
  scheme: API key as username, API secret as password) via the standard
  library only (no vendor SDK dependency, matching this project's existing
  `LLMProvider` precedent, docs/ai-design.md). NEVER exercised by any
  automated test in this repository -- there are no real credentials
  checked in, and CI/local test runs never set PROVIDER_MODE=live.

No mode performs anything beyond a read (GET). There is no method on this
class that creates, updates, captures, refunds, or pays out anything --
structurally absent, the same discipline this project already applies to
`AuditLedger` having no update/delete method (CLAUDE.md, M6).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from base64 import b64encode
from dataclasses import dataclass

from app.adapters.base import ProviderMode
from app.adapters.config import ProviderSettings
from app.adapters.errors import (
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderNotFoundError,
    ProviderPaginationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)

_FIXTURE_FILES = {
    "payment": "razorpay_payments.json",
    "settlement": "razorpay_settlements.json",
    "bank_transaction": "bank_transactions.json",
    "order": "internal_orders.json",
    "refund": "razorpay_refunds.json",
}


@dataclass
class Page:
    records: list[dict]
    next_page_token: str | None


class RazorpayAdapter:
    """Fetches raw (not-yet-canonical) provider records, one bounded page
    at a time. Mapping into canonical dicts is a separate step
    (`app.adapters.razorpay_mapping`) -- this class's only job is
    retrieval + pagination + retry/error handling."""

    def __init__(self, settings: ProviderSettings, *, mock_pages: dict[str, list[Page]] | None = None):
        self._settings = settings
        try:
            self._mode = ProviderMode(settings.provider_mode.upper())
        except ValueError:
            self._mode = ProviderMode.FIXTURE
        self._mock_pages = mock_pages or {}

    @property
    def mode(self) -> ProviderMode:
        return self._mode

    # --- Fixture mode -----------------------------------------------------

    def _fetch_fixture_page(self, source_type: str, page: int, page_size: int) -> Page:
        filename = _FIXTURE_FILES.get(source_type)
        if filename is None:
            raise ProviderNotFoundError(f"no fixture configured for source_type {source_type!r}")
        path = self._settings.fixtures_dir / filename
        if not path.exists():
            raise ProviderNotFoundError(f"fixture file not found: {filename}")
        try:
            all_records = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(f"fixture {filename} is not valid JSON: {exc}")
        if not isinstance(all_records, list):
            raise ProviderResponseError(f"fixture {filename} must contain a JSON array")

        start = page * page_size
        chunk = all_records[start:start + page_size]
        has_more = start + page_size < len(all_records)
        return Page(records=chunk, next_page_token=str(page + 1) if has_more else None)

    # --- Mock mode (test-controlled) ---------------------------------------

    def _fetch_mock_page(self, source_type: str, page_token: str | None) -> Page:
        pages = self._mock_pages.get(source_type)
        if pages is None:
            raise ProviderNotFoundError(f"no mock pages configured for source_type {source_type!r}")
        index = int(page_token) if page_token else 0
        if index < 0 or index >= len(pages):
            raise ProviderPaginationError(f"invalid page_token {page_token!r} for source_type {source_type!r}")
        return pages[index]

    # --- Live mode ----------------------------------------------------------

    def _fetch_live_page(self, source_type: str, page_token: str | None) -> Page:
        if not self._settings.has_live_credentials:
            raise ProviderAuthenticationError("PROVIDER_MODE=live requires RAZORPAY_API_KEY and RAZORPAY_API_SECRET to be set")

        skip = int(page_token) if page_token else 0
        page_size = self._settings.max_page_size
        # Razorpay's real, documented pagination convention: request a
        # bounded `count` (page size) and `skip` offset; a response whose
        # own `count` (items actually returned) is smaller than the
        # requested page size means this was the last page -- NOT "items
        # returned == items returned" (a comparison that is always true and
        # would loop forever, an earlier bug caught by this file's own
        # `test_500_then_success_recovers` test terminating correctly).
        url = f"{self._settings.razorpay_api_base_url.rstrip('/')}/{source_type}s?count={page_size}&skip={skip}"

        credentials = b64encode(f"{self._settings.razorpay_api_key}:{self._settings.razorpay_api_secret}".encode()).decode()
        request = urllib.request.Request(url, headers={"Authorization": f"Basic {credentials}"})

        last_error: Exception | None = None
        for attempt in range(self._settings.max_retries):
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    raw_body = response.read().decode("utf-8")
                try:
                    body = json.loads(raw_body)
                except json.JSONDecodeError as exc:
                    # Milestone 16, Phase 4 finding: malformed JSON from an
                    # otherwise-successful HTTP response is not a transient
                    # network failure -- retrying won't fix it, and it must
                    # never escape as a raw, uncaught JSONDecodeError. Fails
                    # immediately as a clean, typed provider error instead.
                    raise ProviderResponseError("Razorpay response was not valid JSON") from exc
                items = body.get("items", [])
                next_token = str(skip + len(items)) if len(items) == page_size else None
                return Page(records=items, next_page_token=next_token)
            except urllib.error.HTTPError as exc:
                if exc.code == 401 or exc.code == 403:
                    raise ProviderAuthenticationError("Razorpay rejected the configured API key/secret")
                if exc.code == 429:
                    retry_after = exc.headers.get("Retry-After")
                    raise ProviderRateLimitError("Razorpay rate limit exceeded", retry_after_seconds=float(retry_after) if retry_after else None)
                if 500 <= exc.code < 600:
                    last_error = exc
                    time.sleep(self._settings.retry_base_delay_seconds * (2 ** attempt))
                    continue
                raise ProviderResponseError(f"unexpected HTTP {exc.code} from Razorpay")
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, TimeoutError):
                    last_error = exc
                else:
                    last_error = exc
                time.sleep(self._settings.retry_base_delay_seconds * (2 ** attempt))
                continue
            except TimeoutError as exc:
                last_error = exc
                time.sleep(self._settings.retry_base_delay_seconds * (2 ** attempt))
                continue

        if isinstance(last_error, TimeoutError):
            raise ProviderTimeoutError(f"Razorpay request timed out after {self._settings.max_retries} attempts") from last_error
        raise ProviderNetworkError(f"Razorpay request failed after {self._settings.max_retries} attempts: network error") from last_error

    # --- Public, mode-dispatching entry point -------------------------------

    def fetch_records(self, source_type: str) -> list[dict]:
        """Fetches every page for one source type, bounded by
        `max_pages_per_fetch` (Phase 13: never load unlimited data into
        memory blindly). Returns raw, not-yet-canonical provider dicts."""
        records: list[dict] = []
        page_token: str | None = None
        pages_fetched = 0
        page_index = 0

        while pages_fetched < self._settings.max_pages_per_fetch:
            if self._mode == ProviderMode.FIXTURE:
                page = self._fetch_fixture_page(source_type, page_index, self._settings.max_page_size)
            elif self._mode == ProviderMode.MOCK:
                page = self._fetch_mock_page(source_type, page_token)
            else:
                page = self._fetch_live_page(source_type, page_token)

            records.extend(page.records)
            pages_fetched += 1
            page_index += 1
            page_token = page.next_page_token
            if page_token is None:
                break
        else:
            raise ProviderPaginationError(f"exceeded max_pages_per_fetch ({self._settings.max_pages_per_fetch}) for source_type {source_type!r} -- provider may be returning an unbounded stream")

        return records
