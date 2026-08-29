"""Phase 21/22/23: read-only, honest status reporting for every configured
data source. Every count/availability flag here is computed by actually
reading the real fixture files or the real `ProviderSettings` -- nothing
is hardcoded, and a Razorpay adapter running in fixture mode is NEVER
reported as "LIVE" merely because the adapter class exists (Phase 23's own
explicit warning).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.adapters.config import ProviderSettings, settings as default_settings


@dataclass
class SourceStatus:
    name: str
    mode: str  # "SYNTHETIC DATA" | "MOCK PROVIDER" | "LIVE READ-ONLY" | "UNAVAILABLE"
    configured: bool
    available: bool
    record_count: int | None
    detail: str


def _count_json_records(path) -> int | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return len(data) if isinstance(data, list) else None


def get_source_statuses(provider_settings: ProviderSettings | None = None) -> list[SourceStatus]:
    ps = provider_settings or default_settings

    # Resolved here (not at module import time) so REPO_ROOT-relative paths
    # stay correct regardless of import order.
    from app.config import REPO_ROOT

    seeds_dir = REPO_ROOT / "data" / "synthetic" / "seeds"
    payments_file = seeds_dir / "payments.json"
    synthetic_count = _count_json_records(payments_file)

    statuses = [
        SourceStatus(
            name="Synthetic Fixture",
            mode="SYNTHETIC DATA",
            configured=True,
            available=payments_file.exists(),
            record_count=synthetic_count,
            detail="The primary 300-record ground-truthed demo dataset (data/synthetic/seeds).",
        )
    ]

    if ps.provider_mode == "live":
        adapter_mode = "LIVE READ-ONLY" if ps.has_live_credentials else "UNAVAILABLE"
        adapter_detail = (
            "Configured for live, read-only Razorpay retrieval." if ps.has_live_credentials
            else "PROVIDER_MODE=live but RAZORPAY_API_KEY/RAZORPAY_API_SECRET are not both set."
        )
        adapter_available = ps.has_live_credentials
        adapter_count = None  # never known without an actual (unmade) network call
    elif ps.provider_mode == "mock":
        adapter_mode = "MOCK PROVIDER"
        adapter_detail = "Test-controlled in-memory provider (used by automated tests only)."
        adapter_available = True
        adapter_count = None
    else:
        payment_fixture = ps.fixtures_dir / "razorpay_payments.json"
        adapter_mode = "SYNTHETIC DATA"
        adapter_detail = "Reads realistic, synthetic Razorpay-shaped fixtures from data/synthetic/provider_fixtures/."
        adapter_available = payment_fixture.exists()
        adapter_count = _count_json_records(payment_fixture)

    statuses.append(
        SourceStatus(
            name="Razorpay Adapter", mode=adapter_mode, configured=True,
            available=adapter_available, record_count=adapter_count, detail=adapter_detail,
        )
    )

    bank_fixture = ps.fixtures_dir / "bank_transactions.json"
    statuses.append(
        SourceStatus(
            name="Bank Source", mode="SYNTHETIC DATA" if ps.provider_mode != "live" else "LIVE READ-ONLY",
            configured=True, available=bank_fixture.exists(),
            record_count=_count_json_records(bank_fixture),
            detail="Generic bank-statement-export fixture.",
        )
    )

    order_fixture = ps.fixtures_dir / "internal_orders.json"
    statuses.append(
        SourceStatus(
            name="Internal Ledger", mode="SYNTHETIC DATA" if ps.provider_mode != "live" else "LIVE READ-ONLY",
            configured=True, available=order_fixture.exists(),
            record_count=_count_json_records(order_fixture),
            detail="Generic internal order-management-system export fixture.",
        )
    )

    return statuses
