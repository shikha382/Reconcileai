"""Milestone 16, Phase 3: concurrency/replay/idempotency hardening.
Exercises the REAL API (via the existing api_client_with_run/api_client
fixtures) with genuinely concurrent requests (ThreadPoolExecutor against
FastAPI's TestClient, which is safe to call from multiple threads) --
never a new mutation endpoint invented merely to test it. Confirms the
existing, intentional M7 design (each POST /runs creates its own
independently-auditable run) still holds, and that read-heavy concurrent
access never corrupts the audit chain or produces inconsistent data.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.adapters.config import ProviderSettings
from app.adapters.pipeline import ingest_from_provider
from app.adapters.razorpay_adapter import Page, RazorpayAdapter
from app.db.models import Payment


def test_repeated_post_runs_creates_independent_runs_not_corruption(api_client):
    """Documented, intentional M7 behavior (CLAUDE.md's Phase-18 idempotency
    decision): each POST /runs is its own new, independently-auditable run
    -- never merged, never corrupted by a second call."""
    first = api_client.post("/runs", json={"dataset": "seeds"})
    second = api_client.post("/runs", json={"dataset": "seeds"})
    assert first.status_code == second.status_code == 201
    assert first.json()["run_id"] != second.json()["run_id"]
    # Both runs independently report the exact same real, deterministic distribution.
    for body in (first.json(), second.json()):
        assert body["auto_resolved"] == 219
        assert body["human_review"] == 67
        assert body["blocked"] == 2
        assert body["unresolved"] == 12

    listed = api_client.get("/runs").json()
    assert listed["total"] == 2
    ids = {r["run_id"] for r in listed["items"]}
    assert ids == {first.json()["run_id"], second.json()["run_id"]}


def test_concurrent_get_runs_list_returns_consistent_data(api_client_with_run):
    client, state = api_client_with_run

    def _fetch():
        return client.get("/runs").json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _fetch(), range(16)))

    assert all(r["total"] == results[0]["total"] for r in results)
    assert all({i["run_id"] for i in r["items"]} == {state["run_id"]} for r in results)


def test_concurrent_queue_reads_return_identical_ordering(api_client_with_run):
    client, state = api_client_with_run

    def _fetch():
        return client.get("/exceptions/queue", params={"run_id": state["run_id"], "page_size": 10}).json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _fetch(), range(16)))

    first_order = [item["exception_id"] for item in results[0]["items"]]
    for r in results[1:]:
        assert [item["exception_id"] for item in r["items"]] == first_order


def test_concurrent_mixed_requests_against_the_same_run_do_not_corrupt_it(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]

    def _hit(i: int):
        if i % 3 == 0:
            return client.get(f"/runs/{run_id}").status_code
        if i % 3 == 1:
            return client.get(f"/runs/{run_id}/audit").status_code
        return client.get("/exceptions/queue", params={"run_id": run_id, "page_size": 5}).status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(_hit, range(30)))
    assert all(s == 200 for s in statuses)

    # The run itself is unchanged after all that concurrent read traffic.
    after = client.get(f"/runs/{run_id}").json()
    assert after["auto_resolved"] == 219
    assert after["human_review"] == 67


def test_audit_chain_remains_valid_under_concurrent_reads(api_client_with_run):
    client, state = api_client_with_run
    run_id = state["run_id"]

    def _fetch():
        return client.get(f"/runs/{run_id}/audit").json()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _fetch(), range(20)))

    assert all(r["chain_valid"] is True for r in results)
    assert all(r["event_count"] == results[0]["event_count"] for r in results)


def test_duplicate_provider_pages_do_not_duplicate_ingested_records(db_session):
    """Phase 3: a provider re-sending the identical page (e.g. a retried
    request whose response wasn't lost, just re-delivered) must not double-
    ingest -- the SAME idempotency guarantee `ingest_records` already gives
    file-based ingestion (M1) applies here too."""
    settings = ProviderSettings()
    settings.provider_mode = "mock"
    duplicate_payment = {
        "id": "pay_REPLAY0001", "entity": "payment", "amount": 100000, "currency": "INR",
        "status": "captured", "order_id": "order_REPLAY0001", "method": "upi",
        "captured": True, "created_at": 1785574800, "notes": {},
    }
    # The identical record appears on BOTH pages -- simulating a provider
    # that redelivers the same page content (a real replay scenario, not a
    # hypothetical one: at-least-once delivery semantics are common).
    mock_pages = {
        "payment": [
            Page(records=[duplicate_payment], next_page_token="1"),
            Page(records=[duplicate_payment], next_page_token=None),
        ]
    }
    adapter = RazorpayAdapter(settings, mock_pages=mock_pages)
    from app.adapters.base import SourceType

    report = ingest_from_provider(db_session, adapter, source_types=[SourceType.RAZORPAY_PAYMENT])
    db_session.commit()

    # Both raw (duplicate) records are independently valid -- `report.counts`
    # reflects that (2 validated records) -- but they map to the SAME
    # deterministic canonical ID, so `session.merge()` (M1's existing
    # idempotency guarantee, reused unchanged) collapses them into ONE row.
    # The row count, not the validation count, is the real idempotency check.
    assert report.counts["payment"] == 2
    assert db_session.query(Payment).count() == 1


def test_duplicate_provider_records_within_one_page_do_not_duplicate(db_session):
    settings = ProviderSettings()
    settings.provider_mode = "mock"
    record = {
        "id": "pay_REPLAY0002", "entity": "payment", "amount": 200000, "currency": "INR",
        "status": "captured", "order_id": "order_REPLAY0002", "method": "upi",
        "captured": True, "created_at": 1785574800, "notes": {},
    }
    mock_pages = {"payment": [Page(records=[record, dict(record)], next_page_token=None)]}
    adapter = RazorpayAdapter(settings, mock_pages=mock_pages)
    from app.adapters.base import SourceType

    report = ingest_from_provider(db_session, adapter, source_types=[SourceType.RAZORPAY_PAYMENT])
    db_session.commit()

    assert db_session.query(Payment).filter(Payment.metadata_json.like("%pay_REPLAY0002%")).count() == 1
