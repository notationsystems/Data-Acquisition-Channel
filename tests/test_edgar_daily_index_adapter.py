"""Tests for daf.adapters.edgar_daily_index.EdgarDailyIndexSourceAdapter.

Every test here uses SYNTHETIC fixtures (tests/fixtures/edgar_*synthetic*
and tests/fixtures/edgar_daily_index_malformed.idx) -- clearly fabricated
company names/CIKs, never real SEC EDGAR content. The one test that
touches the real, live EDGAR API is in
tests/test_edgar_daily_index_live.py, kept separate and skip-on-failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from daf.adapters.edgar_daily_index import (
    DAILY_INDEX_BASE,
    EdgarDailyIndexSourceAdapter,
    EdgarFetchError,
    _fetch_with_retries,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_router(routes: Dict[str, bytes]):
    def _fetch(url: str) -> bytes:
        for suffix, content in routes.items():
            if url.endswith(suffix):
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return _fetch


def _standard_routes() -> Dict[str, bytes]:
    return {
        "index.json": (FIXTURES / "edgar_index_listing_synthetic.json").read_bytes(),
        "company.20260701.idx": (FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_bytes(),
        "company.20260702.idx": (FIXTURES / "edgar_daily_index_synthetic_20260702.idx").read_bytes(),
        "company.20260703.idx": (FIXTURES / "edgar_daily_index_synthetic_20260703.idx").read_bytes(),
    }


def test_fetch_from_the_beginning_returns_every_available_date():
    adapter = EdgarDailyIndexSourceAdapter(
        year=2026, quarter=3, retrieved_at="2026-08-24T00:00:00Z", fetch_bytes=_fixture_router(_standard_routes())
    )
    documents = adapter.fetch()
    assert [d.locator for d in documents] == ["20260701", "20260702", "20260703"]
    assert all(d.source_name == "SEC EDGAR" for d in documents)
    assert all(d.source_kind == "daily-index" for d in documents)
    assert all(d.retrieval_method == "http:edgar_daily_index_v1" for d in documents)


def test_fetch_preserves_raw_bytes_verbatim():
    adapter = EdgarDailyIndexSourceAdapter(
        year=2026, quarter=3, retrieved_at="2026-08-24T00:00:00Z", fetch_bytes=_fixture_router(_standard_routes())
    )
    documents = adapter.fetch()
    expected = (FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_text()
    assert documents[0].content == expected


def test_fetch_since_a_date_returns_only_later_dates():
    adapter = EdgarDailyIndexSourceAdapter(
        year=2026, quarter=3, retrieved_at="2026-08-24T00:00:00Z",
        since_date="20260701", fetch_bytes=_fixture_router(_standard_routes()),
    )
    documents = adapter.fetch()
    assert [d.locator for d in documents] == ["20260702", "20260703"]


def test_fetch_since_the_latest_date_returns_nothing():
    adapter = EdgarDailyIndexSourceAdapter(
        year=2026, quarter=3, retrieved_at="2026-08-24T00:00:00Z",
        since_date="20260703", fetch_bytes=_fixture_router(_standard_routes()),
    )
    assert adapter.fetch() == ()


def test_max_dates_per_fetch_bounds_a_large_backlog():
    adapter = EdgarDailyIndexSourceAdapter(
        year=2026, quarter=3, retrieved_at="2026-08-24T00:00:00Z",
        max_dates_per_fetch=2, fetch_bytes=_fixture_router(_standard_routes()),
    )
    documents = adapter.fetch()
    # Three dates available, capped to the OLDEST two -- gradual, bounded
    # catch-up, never a burst, per docs/DAF_EDGAR_ADAPTER.md.
    assert [d.locator for d in documents] == ["20260701", "20260702"]


def test_fetch_raises_a_clear_error_when_listing_names_no_index_files():
    def _fetch(url: str) -> bytes:
        return b'{"directory":{"item":[]}}'

    adapter = EdgarDailyIndexSourceAdapter(year=2026, quarter=3, retrieved_at="2026-08-24T00:00:00Z", fetch_bytes=_fetch)
    with pytest.raises(EdgarFetchError):
        adapter.fetch()


def test_fetch_propagates_underlying_error_uncaught():
    def _broken(url: str) -> bytes:
        raise ConnectionError("simulated network failure")

    adapter = EdgarDailyIndexSourceAdapter(year=2026, quarter=3, retrieved_at="2026-08-24T00:00:00Z", fetch_bytes=_broken)
    with pytest.raises(ConnectionError):
        adapter.fetch()


def test_urls_are_constructed_against_the_documented_base():
    requested_urls = []

    def _fetch(url: str) -> bytes:
        requested_urls.append(url)
        return _standard_routes()["index.json"] if url.endswith("index.json") else b"unused"

    adapter = EdgarDailyIndexSourceAdapter(
        year=2026, quarter=3, retrieved_at="2026-08-24T00:00:00Z",
        since_date="20260702", fetch_bytes=_fetch,
    )
    adapter.fetch()
    assert requested_urls[0] == f"{DAILY_INDEX_BASE}/2026/QTR3/index.json"
    assert requested_urls[1] == f"{DAILY_INDEX_BASE}/2026/QTR3/company.20260703.idx"


# -- retry logic (_fetch_with_retries), tested directly via injected opener/sleep --


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._data


def test_retry_succeeds_after_transient_failures():
    import urllib.error

    calls = {"count": 0}
    sleeps = []

    def _opener(request, timeout=30):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)
        return _FakeResponse(b"ok")

    result = _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=sleeps.append)

    assert result == b"ok"
    assert calls["count"] == 3
    assert len(sleeps) == 2  # backed off exactly twice, before the 2nd and 3rd attempts


def test_retry_does_not_retry_a_non_transient_http_error():
    import urllib.error

    calls = {"count": 0}

    def _opener(request, timeout=30):
        calls["count"] += 1
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    with pytest.raises(EdgarFetchError):
        _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)

    assert calls["count"] == 1  # no retry for a non-transient status


def test_retry_gives_up_after_exhausting_the_retry_budget():
    import urllib.error

    calls = {"count": 0}

    def _opener(request, timeout=30):
        calls["count"] += 1
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

    with pytest.raises(EdgarFetchError):
        _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)

    assert calls["count"] == 3  # initial attempt + 2 retries, then gives up


def test_request_carries_the_documented_user_agent():
    import urllib.request

    from daf.adapters.edgar_daily_index import EDGAR_USER_AGENT

    captured = {}

    def _opener(request: "urllib.request.Request", timeout: int = 30):
        captured["user_agent"] = request.get_header("User-agent")
        return _FakeResponse(b"ok")

    _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)
    assert captured["user_agent"] == EDGAR_USER_AGENT
