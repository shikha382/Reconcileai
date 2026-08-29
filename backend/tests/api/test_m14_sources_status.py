"""Milestone 14: GET /sources/status -- read-only, honest, no secrets.
Reuses the existing tests/api/conftest.py fixtures (api_client,
api_client_with_run) exactly like every other API test file, rather than
adding a parallel fixture setup under tests/adapters/.
"""
from __future__ import annotations

SECRET = "sk_live_totally_fake_secret_do_not_use_ABC123"


def test_sources_status_returns_all_four_configured_sources(api_client):
    response = api_client.get("/sources/status")
    assert response.status_code == 200
    body = response.json()
    names = {s["name"] for s in body["sources"]}
    assert names == {"Synthetic Fixture", "Razorpay Adapter", "Bank Source", "Internal Ledger"}


def test_sources_status_never_reports_live_without_real_credentials(api_client):
    response = api_client.get("/sources/status")
    body = response.json()
    for source in body["sources"]:
        if source["mode"] == "LIVE READ-ONLY":
            assert source["configured"] is True and source["available"] is True


def test_sources_status_record_counts_are_real_not_hardcoded(api_client):
    response = api_client.get("/sources/status")
    body = response.json()
    synthetic = next(s for s in body["sources"] if s["name"] == "Synthetic Fixture")
    assert synthetic["record_count"] == 300  # the real 300-record dataset, read from disk


def test_sources_status_ai_actor_is_forbidden(api_client):
    response = api_client.get("/sources/status", headers={"X-Actor-Type": "AI"})
    assert response.status_code == 403


def test_sources_status_never_exposes_any_credential(api_client, monkeypatch):
    monkeypatch.setenv("RAZORPAY_API_KEY", "rzp_live_fake_key")
    monkeypatch.setenv("RAZORPAY_API_SECRET", SECRET)
    response = api_client.get("/sources/status")
    assert SECRET not in response.text
    assert "rzp_live_fake_key" not in response.text


def test_sources_status_is_read_only_no_mutation_verb_accepted(api_client):
    for method in ("post", "put", "patch", "delete"):
        response = getattr(api_client, method)("/sources/status")
        assert response.status_code in (404, 405)


def test_health_endpoint_still_never_exposes_provider_credentials(api_client, monkeypatch):
    # M13 regression continuation (Phase 27): /health must remain exactly
    # as minimal as M8 built it, even after M14 added provider config.
    monkeypatch.setenv("RAZORPAY_API_SECRET", SECRET)
    response = api_client.get("/health")
    assert SECRET not in response.text
    assert response.json() == {"status": "ok", "service": "reconcileai"}
