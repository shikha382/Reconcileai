"""Phase 17/32: secret safety at the adapter layer. API-endpoint-level
secret-safety checks (/health, /sources/status, audit events) live in
`backend/tests/api/test_m14_sources_status.py` instead, alongside the
other API tests that already share those fixtures.
"""
from __future__ import annotations

import io
import urllib.error

import pytest

from app.adapters.config import ProviderSettings
from app.adapters.errors import ProviderAuthenticationError
from app.adapters.razorpay_adapter import RazorpayAdapter

SECRET = "sk_live_totally_fake_secret_do_not_use_ABC123"
KEY = "rzp_live_totally_fake_key_do_not_use_XYZ789"


def _live_settings() -> ProviderSettings:
    s = ProviderSettings()
    s.provider_mode = "live"
    s.razorpay_api_key = KEY
    s.razorpay_api_secret = SECRET
    s.max_retries = 1
    return s


def test_default_settings_have_no_hardcoded_credential():
    settings = ProviderSettings()
    assert settings.razorpay_api_key == ""
    assert settings.razorpay_api_secret == ""
    assert settings.has_live_credentials is False


def test_settings_repr_never_includes_the_key_or_secret():
    settings = _live_settings()
    text = repr(settings)
    assert SECRET not in text
    assert KEY not in text
    assert "has_live_credentials=True" in text


def test_default_provider_mode_is_never_live():
    # A fresh checkout with no environment configured must never attempt a
    # real network call by default.
    assert ProviderSettings().provider_mode == "fixture"


def test_provider_error_message_never_includes_the_secret_on_auth_failure(monkeypatch):
    def fake_urlopen(request, timeout=10):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(ProviderAuthenticationError) as excinfo:
        adapter.fetch_records("payment")
    assert SECRET not in str(excinfo.value)
    assert KEY not in str(excinfo.value)


def test_provider_error_message_never_includes_the_secret_on_network_failure(monkeypatch):
    def fake_urlopen(request, timeout=10):
        raise urllib.error.HTTPError(request.full_url, 500, "Internal Server Error", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    adapter = RazorpayAdapter(_live_settings())
    with pytest.raises(Exception) as excinfo:
        adapter.fetch_records("payment")
    assert SECRET not in str(excinfo.value)
    assert KEY not in str(excinfo.value)
