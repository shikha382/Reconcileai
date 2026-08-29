"""Milestone 16, Phase 4: provider failure simulation gaps not already
covered by tests/adapters/test_retry_and_errors.py (401/403/429/500/
timeout) or test_mapping.py (schema drift / adversarial payloads). Every
scenario here is exercised via a monkeypatched `urlopen` -- never a real
network call, per this project's own standing rule that `live` mode is
never exercised against a real Razorpay endpoint in this environment.

Core principle under test throughout: a provider failure must NEVER turn
into fabricated financial data -- it must fail safely and visibly (a typed
`ProviderError`), never a silently-guessed or partially-filled record.
"""
from __future__ import annotations

import io
import json
import urllib.error

import pytest

from app.adapters.config import ProviderSettings
from app.adapters.errors import ProviderError, ProviderNetworkError, ProviderResponseError
from app.adapters.razorpay_adapter import RazorpayAdapter


def _live_settings(**overrides) -> ProviderSettings:
    s = ProviderSettings()
    s.provider_mode = "live"
    s.razorpay_api_key = "test_key_not_real"
    s.razorpay_api_secret = "test_secret_not_real"
    s.max_retries = 2
    s.retry_base_delay_seconds = 0.001
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_502_bad_gateway_is_retried_then_fails_safely_not_fabricated(monkeypatch):
    def fake_urlopen(request, timeout=10):
        raise urllib.error.HTTPError(request.full_url, 502, "Bad Gateway", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(ProviderNetworkError):
        adapter.fetch_records("payment")


def test_503_service_unavailable_is_retried_then_fails_safely(monkeypatch):
    def fake_urlopen(request, timeout=10):
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(ProviderNetworkError):
        adapter.fetch_records("payment")


def test_malformed_json_from_a_live_response_is_a_clean_provider_error_not_a_raw_crash(monkeypatch):
    def fake_urlopen(request, timeout=10):
        return _FakeResponse(b"{not valid json at all")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(ProviderError):
        adapter.fetch_records("payment")


def test_response_missing_items_field_entirely_is_treated_as_no_records_not_guessed(monkeypatch):
    def fake_urlopen(request, timeout=10):
        return _FakeResponse(json.dumps({"count": 0}).encode())  # no "items" key at all

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    records = adapter.fetch_records("payment")
    assert records == []  # defaults to empty, never fabricates a record


def test_response_claiming_full_page_but_returning_fewer_items_terminates_pagination(monkeypatch):
    """Inconsistent `count` reporting (a real provider quirk): if the
    response's own item count is less than the requested page size, the
    adapter must treat that as the last page -- never loop forever waiting
    for a full page that will never arrive."""
    call_count = {"n": 0}

    def fake_urlopen(request, timeout=10):
        call_count["n"] += 1
        return _FakeResponse(json.dumps({"items": [{"id": f"pay_{call_count['n']}"}], "count": 1}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())  # default max_page_size (100) >> 1 returned item
    records = adapter.fetch_records("payment")
    assert len(records) == 1
    assert call_count["n"] == 1  # never re-requested believing there might be more
