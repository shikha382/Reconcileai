"""Phase 14/15/18/32: retry safety, rate-limit handling, and the provider
error model -- exercised entirely against a monkeypatched `urlopen`, NEVER
a real network call (per the M14 brief's own explicit prohibition on
calling production Razorpay APIs during automated tests).
"""
from __future__ import annotations

import io
import urllib.error

import pytest

from app.adapters.config import ProviderSettings
from app.adapters.errors import (
    ProviderAuthenticationError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from app.adapters.razorpay_adapter import RazorpayAdapter


def _live_settings(**overrides) -> ProviderSettings:
    s = ProviderSettings()
    s.provider_mode = "live"
    s.razorpay_api_key = "test_key_not_real"
    s.razorpay_api_secret = "test_secret_not_real"
    s.max_retries = 3
    s.retry_base_delay_seconds = 0.001  # keep tests fast
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


def test_live_mode_without_credentials_is_a_clean_authentication_error():
    settings = _live_settings(razorpay_api_key="", razorpay_api_secret="")
    adapter = RazorpayAdapter(settings)
    with pytest.raises(ProviderAuthenticationError):
        adapter.fetch_records("payment")


def test_401_from_provider_is_a_clean_authentication_error(monkeypatch):
    def fake_urlopen(request, timeout=10):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(ProviderAuthenticationError):
        adapter.fetch_records("payment")


def test_403_from_provider_is_a_clean_authentication_error(monkeypatch):
    def fake_urlopen(request, timeout=10):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(ProviderAuthenticationError):
        adapter.fetch_records("payment")


def test_429_from_provider_is_a_clean_rate_limit_error_not_retried_forever(monkeypatch):
    call_count = {"n": 0}

    def fake_urlopen(request, timeout=10):
        call_count["n"] += 1
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {"Retry-After": "2"}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(ProviderRateLimitError) as excinfo:
        adapter.fetch_records("payment")
    assert excinfo.value.retry_after_seconds == 2.0
    assert call_count["n"] == 1  # a 429 is not blindly retried -- it's surfaced immediately


def test_500_is_retried_up_to_max_retries_then_raises_network_error(monkeypatch):
    call_count = {"n": 0}

    def fake_urlopen(request, timeout=10):
        call_count["n"] += 1
        raise urllib.error.HTTPError(request.full_url, 500, "Internal Server Error", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings(max_retries=3))
    with pytest.raises(ProviderNetworkError):
        adapter.fetch_records("payment")
    assert call_count["n"] == 3  # bounded -- not infinite


def test_500_then_success_recovers(monkeypatch):
    call_count = {"n": 0}

    def fake_urlopen(request, timeout=10):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, io.BytesIO(b""))
        return _FakeResponse(b'{"items": [{"id": "pay_1"}], "count": 1}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings(max_retries=5))
    records = adapter.fetch_records("payment")
    assert records == [{"id": "pay_1"}]
    assert call_count["n"] == 2


def test_timeout_is_bounded_and_surfaced_as_a_clean_timeout_error(monkeypatch):
    call_count = {"n": 0}

    def fake_urlopen(request, timeout=10):
        call_count["n"] += 1
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings(max_retries=2))
    with pytest.raises(ProviderTimeoutError):
        adapter.fetch_records("payment")
    assert call_count["n"] == 2


def test_unexpected_status_code_is_a_clean_response_error_not_retried(monkeypatch):
    def fake_urlopen(request, timeout=10):
        raise urllib.error.HTTPError(request.full_url, 418, "I'm a teapot", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(ProviderResponseError):
        adapter.fetch_records("payment")


def test_no_error_message_ever_contains_the_configured_secret(monkeypatch):
    def fake_urlopen(request, timeout=10):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings(razorpay_api_secret="totally_secret_value_12345"))
    try:
        adapter.fetch_records("payment")
    except ProviderAuthenticationError as exc:
        assert "totally_secret_value_12345" not in str(exc)
