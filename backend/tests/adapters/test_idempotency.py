"""Phase 12/32: idempotency of provider-sourced ingestion. Reuses the
EXISTING M1 idempotency guarantee (`session.merge()` keyed on the
deterministic canonical ID `app.ingestion.pipeline.ingest_records` already
provides) -- this file proves that guarantee still holds when records
arrive via the adapter/mapping path instead of a source-directory file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.config import ProviderSettings
from app.adapters.pipeline import ingest_from_provider
from app.adapters.razorpay_adapter import RazorpayAdapter
from app.db.models import Payment, Settlement
from app.db.session import init_db, make_engine, make_session_factory


@pytest.fixture()
def provider_db_session(tmp_path):
    engine = make_engine(tmp_path / "provider_idempotency.db")
    init_db(engine)
    return make_session_factory(engine)()


@pytest.fixture()
def fixture_adapter():
    settings = ProviderSettings()
    settings.provider_mode = "fixture"
    return RazorpayAdapter(settings)


def test_ingesting_the_same_fixture_twice_does_not_duplicate_records(provider_db_session, fixture_adapter):
    ingest_from_provider(provider_db_session, fixture_adapter)
    provider_db_session.commit()
    first_count = provider_db_session.query(Payment).count()

    ingest_from_provider(provider_db_session, fixture_adapter)
    provider_db_session.commit()
    second_count = provider_db_session.query(Payment).count()

    assert first_count == second_count == 3


def test_ingesting_twice_produces_identical_settlement_values(provider_db_session, fixture_adapter):
    ingest_from_provider(provider_db_session, fixture_adapter)
    provider_db_session.commit()
    before = {s.settlement_id: str(s.net_amount) for s in provider_db_session.query(Settlement).all()}

    ingest_from_provider(provider_db_session, fixture_adapter)
    provider_db_session.commit()
    after = {s.settlement_id: str(s.net_amount) for s in provider_db_session.query(Settlement).all()}

    assert before == after


def test_a_changed_payload_for_the_same_external_id_updates_in_place_not_duplicates(provider_db_session, tmp_path):
    # Simulate a provider re-sending the same payment with an updated
    # status (a legitimate update, not a duplicate financial event).
    import json

    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    payment = {
        "id": "pay_IDEMPOTENT001", "entity": "payment", "amount": 100000, "currency": "INR",
        "status": "authorized", "order_id": "order_IDEMPOTENT001", "method": "upi",
        "captured": False, "created_at": 1785574800, "notes": {},
    }
    (fixtures_dir / "razorpay_payments.json").write_text(json.dumps([payment]))
    (fixtures_dir / "razorpay_settlements.json").write_text("[]")
    (fixtures_dir / "bank_transactions.json").write_text("[]")
    (fixtures_dir / "internal_orders.json").write_text(json.dumps([
        {"order_ref": "order_IDEMPOTENT001", "customer_ref": "cust_1", "created_at": "2026-08-01T09:00:00+05:30", "status": "created", "amount": "1000.00", "currency": "INR"}
    ]))
    (fixtures_dir / "razorpay_refunds.json").write_text("[]")

    settings = ProviderSettings()
    settings.provider_mode = "fixture"
    settings.fixtures_dir = fixtures_dir
    adapter = RazorpayAdapter(settings)

    ingest_from_provider(provider_db_session, adapter)
    provider_db_session.commit()
    assert provider_db_session.query(Payment).count() == 1
    assert provider_db_session.query(Payment).one().status == "authorized"

    # Provider updates the SAME external id's status to "captured".
    payment["status"] = "captured"
    (fixtures_dir / "razorpay_payments.json").write_text(json.dumps([payment]))

    ingest_from_provider(provider_db_session, adapter)
    provider_db_session.commit()

    assert provider_db_session.query(Payment).count() == 1  # still one row, not two
    assert provider_db_session.query(Payment).one().status == "captured"  # updated in place
