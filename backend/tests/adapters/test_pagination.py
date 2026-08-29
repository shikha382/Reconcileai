"""Phase 13/32: pagination tests, using MOCK mode (a caller-supplied page
sequence) so exact page-boundary/token behavior is fully controllable and
deterministic -- no network, no fixture file dependency.
"""
import pytest

from app.adapters.config import ProviderSettings
from app.adapters.errors import ProviderPaginationError
from app.adapters.razorpay_adapter import Page, RazorpayAdapter


def _settings(**overrides) -> ProviderSettings:
    s = ProviderSettings()
    s.provider_mode = "mock"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_single_page_returns_all_records():
    pages = {"payment": [Page(records=[{"id": 1}, {"id": 2}], next_page_token=None)]}
    adapter = RazorpayAdapter(_settings(), mock_pages=pages)
    records = adapter.fetch_records("payment")
    assert records == [{"id": 1}, {"id": 2}]


def test_multiple_pages_are_all_fetched_in_order():
    pages = {
        "payment": [
            Page(records=[{"id": 1}], next_page_token="1"),
            Page(records=[{"id": 2}], next_page_token="2"),
            Page(records=[{"id": 3}], next_page_token=None),
        ]
    }
    adapter = RazorpayAdapter(_settings(), mock_pages=pages)
    records = adapter.fetch_records("payment")
    assert records == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_empty_page_is_handled_without_error():
    pages = {"payment": [Page(records=[], next_page_token=None)]}
    adapter = RazorpayAdapter(_settings(), mock_pages=pages)
    assert adapter.fetch_records("payment") == []


def test_last_page_stops_fetching():
    pages = {"payment": [Page(records=[{"id": 1}], next_page_token=None)]}
    adapter = RazorpayAdapter(_settings(), mock_pages=pages)
    adapter.fetch_records("payment")  # would raise if it tried to fetch a nonexistent page 2


def test_missing_page_token_starts_from_the_beginning():
    pages = {"payment": [Page(records=[{"id": 1}], next_page_token=None)]}
    adapter = RazorpayAdapter(_settings(), mock_pages=pages)
    assert adapter.fetch_records("payment") == [{"id": 1}]


def test_invalid_page_token_raises_a_pagination_error():
    pages = {"payment": [Page(records=[{"id": 1}], next_page_token="99")]}
    adapter = RazorpayAdapter(_settings(), mock_pages=pages)
    with pytest.raises(ProviderPaginationError):
        adapter.fetch_records("payment")


def test_unbounded_pagination_is_capped_by_max_pages_per_fetch():
    # A page sequence that (bug or malicious provider) never terminates --
    # the adapter must stop itself rather than loop/allocate forever.
    infinite_pages = []
    for i in range(10):
        infinite_pages.append(Page(records=[{"id": i}], next_page_token=str(i + 1)))
    adapter = RazorpayAdapter(_settings(max_pages_per_fetch=3), mock_pages={"payment": infinite_pages})
    with pytest.raises(ProviderPaginationError, match="max_pages_per_fetch"):
        adapter.fetch_records("payment")


def test_fixture_mode_paginates_using_max_page_size():
    settings = ProviderSettings()
    settings.provider_mode = "fixture"
    settings.max_page_size = 1  # force 3 pages for the 3-record razorpay_payments.json fixture
    adapter = RazorpayAdapter(settings)
    records = adapter.fetch_records("payment")
    assert len(records) == 3
    assert len({r["id"] for r in records}) == 3  # no duplicate records across pages
