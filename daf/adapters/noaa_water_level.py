"""Real scout.interface.SourceAdapter implementation against NOAA's
public CO-OPS Tides & Currents data API
(https://api.tidesandcurrents.noaa.gov/api/prod/datagetter).

Chosen for Phase I specifically because it exhibits a THIRD acquisition
topology, distinct from both prior real sources (see
docs/DAF_NOAA_WATER_LEVEL_ADAPTER.md's three-source comparison for the
full record):

    EDGAR (Phase G)          USGS (Phase H)              NOAA (Phase I)
    ----------------------   ----------------------      ----------------------
    unit = one whole daily   unit = one individual        unit = one bounded
      index FILE               event RECORD                TIME WINDOW of many
                                                             (timestamp, value)
                                                             readings -- no
                                                             reading has its
                                                             own identity at all
    locator IS the cursor    locator is NOT the cursor    locator IS the cursor
      (a date string)          (needs raw_content,           again (a window
                                Phase H's one addition)       descriptor string
                                                               that itself
                                                               encodes the
                                                               cursor value)
    never revised             individual records get       no per-reading
                                revised (status/magnitude)    identity to revise
                                                               -- but the SAME
                                                               WINDOW can be
                                                               re-fetched with
                                                               DIFFERENT bytes
                                                               once NOAA's QC
                                                               pipeline flips
                                                               readings from
                                                               "preliminary" to
                                                               "verified"

INVESTIGATED, NOT ASSUMED: the real endpoint was fetched directly before
writing this module. A `product=water_level` query for a RECENT date
returns readings flagged `"q": "p"` (preliminary); the identical query
for a date roughly eight months in the past returns `"q": "v"`
(verified) -- confirmed live, proving this source's real temporal-
integrity concern is REVISION (a window's content can change on
re-fetch), not classic late-arrival (a reading for an earlier timestamp
appearing after a later one was already published; not observed and not
assumed here). The API enforces a hard 31-day range limit per request
(confirmed live: a 90-day range is rejected with `Range Limit Exceeded`)
-- this is this source's real pagination-by-time-window boundary.

Whole-window raw artifact preservation (one HTTP response, byte-for-byte,
per RawDocument), matching EDGAR/USGS's own discipline, applied at a
THIRD boundary: not "one file with many aggregated filings" (EDGAR), not
"one individually-identified record" (USGS), but "one bounded time
window with many unidentified readings" -- deliberately avoiding
millions of per-reading artifacts.

Trailing-safety-window catch-up, reused directly from Phase F's own
documented idiom (`docs/DAF_DOMAIN_RECONNAISSANCE.md` section 11) but
applied here for a different root cause: instead of guarding against
late-ARRIVING data, `revision_lookback_days` guards against the SAME
already-acquired window later flipping from preliminary to verified.
Each `fetch()` call re-requests the trailing `revision_lookback_days`
days of the previous window along with the next `window_days` of new
coverage -- relying on the SAME existing content-addressed
identity/dedup machinery (Phase A/B) to safely re-absorb any overlap,
exactly as Phase F's idiom does, never a new dedup mechanism.
"""

from __future__ import annotations

import datetime
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

from scout.interface import RawDocument

DATAGETTER_BASE = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"

# NOAA's CO-OPS API usage guidance (https://api.tidesandcurrents.noaa.gov/api/prod/)
# asks automated clients to identify themselves -- a public identification
# string, not a credential. No API key is required or used.
NOAA_USER_AGENT = "Data-Acquisition-Fabric research-adapter contact@example.com"

_TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 0.5
_DEFAULT_WINDOW_DAYS = 3  # bounded, deterministic window size per fetch() call
_DEFAULT_REVISION_LOOKBACK_DAYS = 2  # trailing safety window -- see module docstring

Fetcher = Callable[[str], bytes]
Opener = Callable[..., Any]
Sleeper = Callable[[float], None]


class NoaaFetchError(RuntimeError):
    """Raised for any acquisition-time failure: a non-transient HTTP
    error, a transient error that exhausted its retry budget, a
    connection failure, an undecodable response body, or a response
    shaped as `{"error": {...}}` (NOAA's own error envelope -- returned
    with HTTP 200 in some cases, so it must be checked explicitly, not
    inferred from status code alone)."""


def _fetch_with_retries(
    url: str, opener: Opener = urllib.request.urlopen, sleep: Sleeper = time.sleep
) -> bytes:
    """Bounded, deterministic retry -- identical policy to the EDGAR and
    USGS adapters' own retry helpers, independently re-derived each
    time rather than shared: up to `_MAX_RETRIES` additional attempts,
    fixed backoff, only for conventionally-transient statuses (429,
    5xx). `opener`/`sleep` are injectable purely for unit-testability.
    """
    request = urllib.request.Request(url, headers={"User-Agent": NOAA_USER_AGENT})
    last_error: BaseException = NoaaFetchError(f"NOAA request to {url!r} never attempted")

    for attempt in range(_MAX_RETRIES + 1):
        try:
            with opener(request, timeout=30) as response:
                return response.read()  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in _TRANSIENT_HTTP_STATUSES or attempt == _MAX_RETRIES:
                raise NoaaFetchError(f"NOAA request to {url!r} failed: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == _MAX_RETRIES:
                raise NoaaFetchError(f"NOAA request to {url!r} failed: {exc}") from exc
        if attempt < _MAX_RETRIES:
            sleep(_RETRY_DELAY_SECONDS)

    raise NoaaFetchError(f"NOAA request to {url!r} failed after {_MAX_RETRIES} retries: {last_error}")


def _default_fetch(url: str) -> bytes:
    return _fetch_with_retries(url)


def _parse_date(value: str) -> datetime.date:
    # A plain calendar date, never a timestamp -- constructed directly
    # (not via datetime.strptime) so there is no naive-datetime/timezone
    # ambiguity to reason about at all.
    return datetime.date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def _format_date(value: datetime.date) -> str:
    return f"{value.year:04d}{value.month:02d}{value.day:02d}"


def window_end_of(locator: str) -> str:
    """The end date embedded in a NOAA window locator
    (`"{station}:{product}:{datum}:{units}:{begin}:{end}"`) -- this IS the checkpoint
    cursor value for this source (unlike USGS, where the cursor could
    not be recovered from the locator at all). Kept adapter-local, never
    imported by DAF core, exactly like EDGAR's own date-string locators
    and `incremental_dataset`'s `sequence_of`."""
    return locator.rsplit(":", 1)[-1]


@dataclass(frozen=True)
class NoaaWaterLevelSourceAdapter:
    station: str
    product: str
    start_date: str  # YYYYMMDD, the overall acquisition scope's lower bound
    end_date: str  # YYYYMMDD, the overall acquisition scope's upper bound (inclusive)
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock
    since_window_end: Optional[str] = None  # YYYYMMDD, opaque to DAF core -- see AdapterBinding.advance_position
    window_days: int = _DEFAULT_WINDOW_DAYS
    revision_lookback_days: int = _DEFAULT_REVISION_LOOKBACK_DAYS
    datum: str = "MLLW"
    units: str = "metric"
    fetch_bytes: Fetcher = field(default=_default_fetch)

    def fetch(self) -> Tuple[RawDocument, ...]:
        scope_end = _parse_date(self.end_date)

        if self.since_window_end is None:
            window_start = _parse_date(self.start_date)
        else:
            previous_end = _parse_date(self.since_window_end)
            # Trailing safety window: re-verify the last `revision_lookback_days`
            # of the previous window along with new coverage -- see module docstring.
            window_start = previous_end - datetime.timedelta(days=self.revision_lookback_days - 1)

        if window_start > scope_end:
            return ()  # scope fully covered -- nothing left to acquire

        window_end = min(window_start + datetime.timedelta(days=self.window_days - 1), scope_end)

        url = (
            f"{DATAGETTER_BASE}?product={self.product}"
            f"&station={self.station}"
            f"&begin_date={_format_date(window_start)}"
            f"&end_date={_format_date(window_end)}"
            f"&datum={self.datum}&units={self.units}&time_zone=gmt&format=json"
        )
        raw_bytes = self.fetch_bytes(url)
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NoaaFetchError(f"NOAA response for {url!r} was not valid UTF-8") from exc

        # NOAA returns its own {"error": {...}} envelope, sometimes with
        # HTTP 200 -- must be checked explicitly (confirmed live), by
        # parsing, never by a brittle substring/prefix check.
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise NoaaFetchError(f"NOAA response for {url!r} was not valid JSON") from exc
        if isinstance(payload, dict) and "error" in payload:
            raise NoaaFetchError(f"NOAA request to {url!r} returned an error envelope: {payload['error']!r}")

        # Phase R: `datum` and `units` are part of the locator because they
        # are part of WHAT WAS ACQUIRED, not how. NOAA returns genuinely
        # different physical quantities for the same station/product/window
        # under different datums -- measured live, MLLW 0.136 m vs STND
        # 1.2 m at the same instant. `artifact_id` is
        # content_hash({source_id, locator}) and the adapter's source
        # identity is fixed, so omitting them collapsed two distinct
        # quantities onto one logical artifact, where the second read as a
        # REVISION of the first.
        #
        # This completes the existing scheme rather than introducing a new
        # coupling: the locator already carried `station` and `product`,
        # which are scientific identity dimensions of exactly the same
        # kind. The checkpoint cursor is unaffected -- `window_end_of`
        # reads the LAST component (`rsplit(":", 1)`), and checkpoint
        # positions are bare date strings, never locators.
        locator = (
            f"{self.station}:{self.product}:{self.datum}:{self.units}"
            f":{_format_date(window_start)}:{_format_date(window_end)}"
        )
        document = RawDocument(
            source_name="NOAA CO-OPS Tides & Currents",
            source_kind="tide-station-window",
            content=content,
            locator=locator,
            retrieval_method="http:noaa_water_level_v1",
            retrieved_at=self.retrieved_at,
        )
        return (document,)
