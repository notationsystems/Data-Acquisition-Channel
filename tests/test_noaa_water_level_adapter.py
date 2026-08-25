"""Tests for daf.adapters.noaa_water_level.NoaaWaterLevelSourceAdapter.

Every test here uses SYNTHETIC fixtures (tests/fixtures/noaa_window_*) --
a clearly fabricated station id/name, never real NOAA CO-OPS content.
The live network demonstration is performed manually and documented in
docs/DAF_NOAA_WATER_LEVEL_ADAPTER.md, never mixed into these fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from daf.adapters.noaa_water_level import (
    DATAGETTER_BASE,
    NoaaFetchError,
    NoaaWaterLevelSourceAdapter,
    _fetch_with_retries,
    window_end_of,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_window_end_of_extracts_the_trailing_date():
    assert window_end_of("9999999:water_level:MLLW:metric:20260101:20260103") == "20260103"


def test_first_fetch_covers_window_days_from_start_date():
    requested = []

    def _fetch(url: str) -> bytes:
        requested.append(url)
        return (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_bytes()

    adapter = NoaaWaterLevelSourceAdapter(
        station="9999999", product="water_level", start_date="20260101", end_date="20260201",
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_fetch,
    )
    documents = adapter.fetch()

    assert len(documents) == 1
    assert documents[0].locator == "9999999:water_level:MLLW:metric:20260101:20260103"
    assert documents[0].source_name == "NOAA CO-OPS Tides & Currents"
    assert documents[0].source_kind == "tide-station-window"
    assert documents[0].retrieval_method == "http:noaa_water_level_v1"
    assert requested[0] == (
        f"{DATAGETTER_BASE}?product=water_level&station=9999999"
        f"&begin_date=20260101&end_date=20260103&datum=MLLW&units=metric&time_zone=gmt&format=json"
    )


def test_fetch_preserves_raw_bytes_verbatim():
    def _fetch(url: str) -> bytes:
        return (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_bytes()

    adapter = NoaaWaterLevelSourceAdapter(
        station="9999999", product="water_level", start_date="20260101", end_date="20260201",
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_fetch,
    )
    documents = adapter.fetch()
    expected = (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_text()
    assert documents[0].content == expected


def test_second_fetch_rewinds_by_the_revision_lookback():
    requested = []

    def _fetch(url: str) -> bytes:
        requested.append(url)
        return (FIXTURES / "noaa_window_synthetic_20260102_20260104.json").read_bytes()

    adapter = NoaaWaterLevelSourceAdapter(
        station="9999999", product="water_level", start_date="20260101", end_date="20260201",
        retrieved_at="2026-08-25T00:00:00Z", since_window_end="20260103", fetch_bytes=_fetch,
    )
    documents = adapter.fetch()

    # revision_lookback_days=2 -> window_start = previous_end - 1 day = 20260102
    assert documents[0].locator == "9999999:water_level:MLLW:metric:20260102:20260104"
    assert "begin_date=20260102&end_date=20260104" in requested[0]


def test_fetch_returns_nothing_once_the_scope_is_fully_covered():
    def _fetch(url: str) -> bytes:
        raise AssertionError("should not be called -- scope already exhausted")

    # since_window_end past end_date -> even after rewinding by the
    # revision lookback, window_start still exceeds the plan's scope.
    adapter = NoaaWaterLevelSourceAdapter(
        station="9999999", product="water_level", start_date="20260101", end_date="20260103",
        retrieved_at="2026-08-25T00:00:00Z", since_window_end="20260110", fetch_bytes=_fetch,
    )
    assert adapter.fetch() == ()


def test_window_days_and_revision_lookback_are_configurable():
    requested = []

    def _fetch(url: str) -> bytes:
        requested.append(url)
        return (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_bytes()

    adapter = NoaaWaterLevelSourceAdapter(
        station="9999999", product="water_level", start_date="20260101", end_date="20260201",
        retrieved_at="2026-08-25T00:00:00Z", window_days=1, fetch_bytes=_fetch,
    )
    adapter.fetch()
    assert "begin_date=20260101&end_date=20260101" in requested[0]


def test_fetch_raises_a_clear_error_on_the_noaa_error_envelope():
    def _fetch(url: str) -> bytes:
        return b'{"error": {"message": "The station is not a valid station or there is system error."}}'

    adapter = NoaaWaterLevelSourceAdapter(
        station="0000000", product="water_level", start_date="20260101", end_date="20260201",
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_fetch,
    )
    with pytest.raises(NoaaFetchError):
        adapter.fetch()


def test_fetch_raises_a_clear_error_on_invalid_json():
    def _fetch(url: str) -> bytes:
        return b"not json at all"

    adapter = NoaaWaterLevelSourceAdapter(
        station="9999999", product="water_level", start_date="20260101", end_date="20260201",
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_fetch,
    )
    with pytest.raises(NoaaFetchError):
        adapter.fetch()


def test_fetch_propagates_underlying_error_uncaught():
    def _broken(url: str) -> bytes:
        raise ConnectionError("simulated network failure")

    adapter = NoaaWaterLevelSourceAdapter(
        station="9999999", product="water_level", start_date="20260101", end_date="20260201",
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_broken,
    )
    with pytest.raises(ConnectionError):
        adapter.fetch()


# -- retry logic (_fetch_with_retries), tested directly via injected opener/sleep --
# Identical policy to the EDGAR and USGS adapters' own retry tests.


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
    assert len(sleeps) == 2


def test_retry_does_not_retry_a_non_transient_http_error():
    import urllib.error

    calls = {"count": 0}

    def _opener(request, timeout=30):
        calls["count"] += 1
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

    with pytest.raises(NoaaFetchError):
        _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)

    assert calls["count"] == 1


def test_retry_gives_up_after_exhausting_the_retry_budget():
    import urllib.error

    calls = {"count": 0}

    def _opener(request, timeout=30):
        calls["count"] += 1
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

    with pytest.raises(NoaaFetchError):
        _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)

    assert calls["count"] == 3


def test_request_carries_the_documented_user_agent():
    import urllib.request

    from daf.adapters.noaa_water_level import NOAA_USER_AGENT

    captured = {}

    def _opener(request: "urllib.request.Request", timeout: int = 30):
        captured["user_agent"] = request.get_header("User-agent")
        return _FakeResponse(b'{"metadata":{},"data":[]}')

    _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)
    assert captured["user_agent"] == NOAA_USER_AGENT
