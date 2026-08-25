"""Real scout.interface.SourceAdapter implementation against the USGS
Earthquake Catalog's public FDSN event web service
(https://earthquake.usgs.gov/fdsnws/event/1/).

Chosen for Phase H specifically because it exhibits an acquisition
topology that materially differs from `daf.adapters.edgar_daily_index`
(see docs/DAF_USGS_EARTHQUAKE_ADAPTER.md's "EDGAR vs. USGS" comparison
for the full record):

    EDGAR                                   USGS
    -------------------------------------   -------------------------------------
    acquisition unit = one whole daily      acquisition unit = one individual
      index FILE (many filings inside)        event RECORD (one per fetch)
    checkpoint cursor = a date string       checkpoint cursor = a "last revised"
      that IS the locator itself              timestamp -- NOT the locator (the
                                               locator is a stable event id that
                                               never changes across revisions)
    content is immutable once published     content is MUTABLE: the same event
      -- no corrections, ever                 id can be re-fetched days later
                                               with a revised magnitude/status,
                                               producing a genuinely new version
                                               under the SAME stable artifact id
    listing = a JSON directory of           listing = a JSON FeatureCollection
      filenames                               of event summaries (used only to
                                               discover which ids changed)

INVESTIGATED, NOT ASSUMED: the real endpoints were fetched directly
before writing this module.
`.../query?format=geojson&starttime=...&endtime=...&minmagnitude=...`
returns a GeoJSON FeatureCollection of event summaries,
`updatedafter=<ISO-8601>` filters to events revised strictly after that
instant (confirmed live -- this is a content-revision cursor, not a
publication-order cursor). `.../query?eventid=<id>&format=geojson`
returns one complete, standalone GeoJSON Feature for exactly that event
-- this per-event document is what gets preserved as this adapter's raw
artifact, exactly as EDGAR preserves one whole daily-index file per
RawDocument (same "whole HTTP response, byte-for-byte" discipline, at a
different, finer granularity).

Two-step fetch per `fetch()` call, deliberately mirroring EDGAR's own
"list, then fetch each selected unit" shape:
    1. GET the bulk listing query, filtered by `updated_after` (if any).
    2. Sort candidate (event_id, updated) pairs by `updated` ascending
       and take the oldest-revised `max_events_per_fetch` (a deliberate,
       bounded, gradual-catch-up choice -- see
       docs/DAF_USGS_EARTHQUAKE_ADAPTER.md section "Rate limiting").
    3. GET each selected event's own detail document, one RawDocument
       per event, raw bytes verbatim.

USGS's terms of service ask automated clients to identify themselves and
avoid aggressive polling; no credentials are used or required -- this is
a public, unauthenticated feed.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

from scout.interface import RawDocument

EVENT_QUERY_BASE = "https://earthquake.usgs.gov/fdsnws/event/1/query"

# USGS's terms of service (https://www.usgs.gov/programs/earthquake-hazards/web-services)
# ask every automated client to identify itself -- a public identification
# string, not a credential.
USGS_USER_AGENT = "Data-Acquisition-Fabric research-adapter contact@example.com"

_TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 0.5
_DEFAULT_MAX_EVENTS_PER_FETCH = 5  # bounded, gradual incremental catch-up -- see module docstring
_LISTING_LIMIT = 500  # caps the summary listing query itself -- a second, independent bound

Fetcher = Callable[[str], bytes]
Opener = Callable[..., Any]
Sleeper = Callable[[float], None]

_UNSAFE_QUERY_CHARS_RE = re.compile(r"[^A-Za-z0-9_.:+-]")


class UsgsFetchError(RuntimeError):
    """Raised for any acquisition-time failure: a non-transient HTTP
    error, a transient error that exhausted its retry budget, a
    connection failure, an undecodable/unparseable response body, or a
    listing response with no `features` array."""


def _fetch_with_retries(
    url: str, opener: Opener = urllib.request.urlopen, sleep: Sleeper = time.sleep
) -> bytes:
    """Bounded, deterministic retry -- identical policy to
    `daf.adapters.edgar_daily_index._fetch_with_retries`: up to
    `_MAX_RETRIES` additional attempts, fixed backoff, only for
    statuses conventionally treated as transient (429, 5xx). A
    non-transient error (e.g. 404) never retries. `opener`/`sleep` are
    injectable purely for unit-testability -- the default `fetch_bytes`
    used in production never overrides them.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USGS_USER_AGENT})
    last_error: BaseException = UsgsFetchError(f"USGS request to {url!r} never attempted")

    for attempt in range(_MAX_RETRIES + 1):
        try:
            with opener(request, timeout=30) as response:
                return response.read()  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in _TRANSIENT_HTTP_STATUSES or attempt == _MAX_RETRIES:
                raise UsgsFetchError(f"USGS request to {url!r} failed: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == _MAX_RETRIES:
                raise UsgsFetchError(f"USGS request to {url!r} failed: {exc}") from exc
        if attempt < _MAX_RETRIES:
            sleep(_RETRY_DELAY_SECONDS)

    raise UsgsFetchError(f"USGS request to {url!r} failed after {_MAX_RETRIES} retries: {last_error}")


def _default_fetch(url: str) -> bytes:
    return _fetch_with_retries(url)


def _query_encode(value: str) -> str:
    """Minimal, dependency-free query-string escaping sufficient for the
    fixed vocabulary of values this adapter ever substitutes (dates,
    ISO-8601 timestamps, magnitudes, event ids) -- never free user text."""
    return _UNSAFE_QUERY_CHARS_RE.sub(lambda m: f"%{ord(m.group()):02X}", value)


@dataclass(frozen=True)
class UsgsEarthquakeSourceAdapter:
    start_time: str  # YYYY-MM-DD, the catalog window's lower bound (inclusive)
    end_time: str  # YYYY-MM-DD, the catalog window's upper bound (inclusive)
    min_magnitude: float
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock
    updated_after: Optional[str] = None  # ISO-8601, opaque to the DAF core -- see AdapterBinding.advance_position
    max_events_per_fetch: int = _DEFAULT_MAX_EVENTS_PER_FETCH
    fetch_bytes: Fetcher = field(default=_default_fetch)

    def fetch(self) -> Tuple[RawDocument, ...]:
        listing_url = (
            f"{EVENT_QUERY_BASE}?format=geojson"
            f"&starttime={_query_encode(self.start_time)}"
            f"&endtime={_query_encode(self.end_time)}"
            f"&minmagnitude={_query_encode(str(self.min_magnitude))}"
            f"&limit={_LISTING_LIMIT}"
        )
        if self.updated_after is not None:
            listing_url += f"&updatedafter={_query_encode(self.updated_after)}"

        listing_bytes = self.fetch_bytes(listing_url)
        try:
            listing = json.loads(listing_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UsgsFetchError(f"USGS listing at {listing_url!r} was not valid JSON") from exc

        features = listing.get("features") if isinstance(listing, dict) else None
        if not isinstance(features, list):
            raise UsgsFetchError(f"USGS listing at {listing_url!r} had no 'features' array")

        candidates: List[Tuple[str, int]] = []
        for feature in features:
            try:
                candidates.append((feature["id"], feature["properties"]["updated"]))
            except (KeyError, TypeError) as exc:
                raise UsgsFetchError(
                    f"USGS listing at {listing_url!r} contained a feature with no id/properties.updated"
                ) from exc

        # Bounded, gradual catch-up, oldest-revised-first -- see module docstring.
        candidates.sort(key=lambda pair: pair[1])
        selected = candidates[: self.max_events_per_fetch]

        documents = []
        for event_id, _updated in selected:
            detail_url = f"{EVENT_QUERY_BASE}?eventid={_query_encode(event_id)}&format=geojson"
            raw_bytes = self.fetch_bytes(detail_url)
            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise UsgsFetchError(f"USGS event detail at {detail_url!r} was not valid UTF-8") from exc
            documents.append(
                RawDocument(
                    source_name="USGS Earthquake Catalog",
                    source_kind="event-detail",
                    content=content,
                    locator=event_id,
                    retrieval_method="http:usgs_earthquake_v1",
                    retrieved_at=self.retrieved_at,
                )
            )
        return tuple(documents)
