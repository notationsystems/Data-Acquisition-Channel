"""Tests for daf.adapters.usgs_earthquakes.UsgsEarthquakeSourceAdapter.

Every test here uses SYNTHETIC fixtures (tests/fixtures/usgs_*synthetic*
and tests/fixtures/usgs_event_detail_*) -- clearly fabricated event ids/
places, never real USGS Earthquake Catalog content. The live network
demonstration is performed manually and documented in
docs/DAF_USGS_EARTHQUAKE_ADAPTER.md, never mixed into these fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from daf.adapters.usgs_earthquakes import (
    EVENT_QUERY_BASE,
    UsgsEarthquakeSourceAdapter,
    UsgsFetchError,
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
        "&limit=500": (FIXTURES / "usgs_listing_synthetic.json").read_bytes(),
        "eventid=synth00000001&format=geojson": (FIXTURES / "usgs_event_detail_synth00000001.json").read_bytes(),
        "eventid=synth00000002&format=geojson": (FIXTURES / "usgs_event_detail_synth00000002.json").read_bytes(),
        "eventid=synth00000003&format=geojson": (FIXTURES / "usgs_event_detail_synth00000003.json").read_bytes(),
    }


def test_fetch_from_the_beginning_returns_every_available_event_oldest_revised_first():
    adapter = UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_fixture_router(_standard_routes()),
    )
    documents = adapter.fetch()
    assert [d.locator for d in documents] == ["synth00000001", "synth00000002", "synth00000003"]
    assert all(d.source_name == "USGS Earthquake Catalog" for d in documents)
    assert all(d.source_kind == "event-detail" for d in documents)
    assert all(d.retrieval_method == "http:usgs_earthquake_v1" for d in documents)


def test_fetch_preserves_raw_bytes_verbatim():
    adapter = UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_fixture_router(_standard_routes()),
    )
    documents = adapter.fetch()
    expected = (FIXTURES / "usgs_event_detail_synth00000001.json").read_text()
    assert documents[0].content == expected


def test_fetch_since_a_timestamp_returns_only_more_recently_revised_events():
    routes = _standard_routes()
    routes["&limit=500&updatedafter=2026-01-01T00:00:01.000Z"] = routes.pop("&limit=500")
    adapter = UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
        retrieved_at="2026-08-25T00:00:00Z", updated_after="2026-01-01T00:00:01.000Z",
        fetch_bytes=_fixture_router(routes),
    )
    documents = adapter.fetch()
    # The adapter must have appended updatedafter to the listing URL --
    # proven by the fixture router only answering that exact suffix.
    assert [d.locator for d in documents] == ["synth00000001", "synth00000002", "synth00000003"]


def test_max_events_per_fetch_bounds_a_large_backlog_oldest_revised_first():
    adapter = UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
        retrieved_at="2026-08-25T00:00:00Z", max_events_per_fetch=2,
        fetch_bytes=_fixture_router(_standard_routes()),
    )
    documents = adapter.fetch()
    # Three events available (updated at :101, :202, :303), capped to the
    # two LEAST-recently-revised -- gradual, bounded catch-up, mirroring
    # EDGAR's max_dates_per_fetch idiom but ordered by revision time.
    assert [d.locator for d in documents] == ["synth00000001", "synth00000002"]


def test_fetch_raises_a_clear_error_when_listing_has_no_features_array():
    def _fetch(url: str) -> bytes:
        return b'{"type":"FeatureCollection"}'

    adapter = UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_fetch,
    )
    with pytest.raises(UsgsFetchError):
        adapter.fetch()


def test_fetch_raises_a_clear_error_on_a_feature_missing_id_or_updated():
    def _fetch(url: str) -> bytes:
        return b'{"features":[{"properties":{"mag":4.0}}]}'

    adapter = UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_fetch,
    )
    with pytest.raises(UsgsFetchError):
        adapter.fetch()


def test_fetch_propagates_underlying_error_uncaught():
    def _broken(url: str) -> bytes:
        raise ConnectionError("simulated network failure")

    adapter = UsgsEarthquakeSourceAdapter(
        start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
        retrieved_at="2026-08-25T00:00:00Z", fetch_bytes=_broken,
    )
    with pytest.raises(ConnectionError):
        adapter.fetch()


def test_urls_are_constructed_against_the_documented_base():
    requested_urls = []

    def _fetch(url: str) -> bytes:
        requested_urls.append(url)
        if "eventid" not in url:
            return (FIXTURES / "usgs_listing_synthetic.json").read_bytes()
        return b"unused"

    adapter = UsgsEarthquakeSourceAdapter(
        start_time="2026-07-01", end_time="2026-07-02", min_magnitude=4.5,
        retrieved_at="2026-08-25T00:00:00Z", max_events_per_fetch=1, fetch_bytes=_fetch,
    )
    adapter.fetch()
    assert requested_urls[0] == (
        f"{EVENT_QUERY_BASE}?format=geojson&starttime=2026-07-01&endtime=2026-07-02"
        f"&minmagnitude=4.5&limit=500"
    )
    assert requested_urls[1] == f"{EVENT_QUERY_BASE}?eventid=synth00000001&format=geojson"


# -- retry logic (_fetch_with_retries), tested directly via injected opener/sleep --
# Identical policy to daf.adapters.edgar_daily_index's own retry tests --
# proving the two independently-written adapters converged on the same
# responsible-HTTP shape without sharing code.


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
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    with pytest.raises(UsgsFetchError):
        _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)

    assert calls["count"] == 1


def test_retry_gives_up_after_exhausting_the_retry_budget():
    import urllib.error

    calls = {"count": 0}

    def _opener(request, timeout=30):
        calls["count"] += 1
        raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

    with pytest.raises(UsgsFetchError):
        _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)

    assert calls["count"] == 3


def test_request_carries_the_documented_user_agent():
    import urllib.request

    from daf.adapters.usgs_earthquakes import USGS_USER_AGENT

    captured = {}

    def _opener(request: "urllib.request.Request", timeout: int = 30):
        captured["user_agent"] = request.get_header("User-agent")
        return _FakeResponse(b"ok")

    _fetch_with_retries("https://example.invalid/x", opener=_opener, sleep=lambda seconds: None)
    assert captured["user_agent"] == USGS_USER_AGENT
