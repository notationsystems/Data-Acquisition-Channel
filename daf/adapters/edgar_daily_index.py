"""Real scout.interface.SourceAdapter implementation against SEC EDGAR's
public daily-index feed
(https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/).

Chosen for Phase G over the company-submissions JSON API
(`https://data.sec.gov/submissions/CIK##########.json`) because the
daily index is a genuinely INCREMENTAL source in its own right -- SEC
publishes exactly one new, immutable index file per business day, in
order -- letting this adapter exercise real `AcquisitionCheckpoint`
resume behavior against a real external source, rather than only
proving snapshot acquisition (which `daf.adapters.arxiv` and
`daf.adapters.local_dataset` already cover).

INVESTIGATED, NOT ASSUMED (see docs/DAF_EDGAR_ADAPTER.md section
"Source semantics" for the full record): fetched
`https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/index.json`
and a real `company.YYYYMMDD.idx` file directly before writing this
module. The directory listing is JSON
(`{"directory":{"item":[{"name":"company.20260701.idx",...}, ...]}}`);
each daily index file is a fixed header block, a dashed separator line,
then whitespace-column-aligned data rows: Company Name, Form Type, CIK,
Date Filed (YYYYMMDD), File Name (a path embedding the filing's own
accession number).

Two-step fetch per `fetch()` call:
    1. GET the quarter's `index.json` directory listing.
    2. Filter `company.YYYYMMDD.idx` filenames to dates > since_date,
       bounded by `max_dates_per_fetch` (a deliberate, responsible
       acquisition-pacing choice -- see docs/DAF_EDGAR_ADAPTER.md
       section "Rate limiting").
    3. GET each selected day's `.idx` file, one RawDocument per day
       (the whole file's raw bytes, verbatim -- see
       daf.extractors.edgar_daily_index for what happens to it next).

SEC's public-access fair-use policy requires a real identifying
User-Agent header on every request (SEC blocks/throttles requests that
omit one) -- see `EDGAR_USER_AGENT` below. No credentials are used or
required; this is a public, unauthenticated feed.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

from scout.interface import RawDocument

DAILY_INDEX_BASE = "https://www.sec.gov/Archives/edgar/daily-index"

# SEC's fair-access policy (https://www.sec.gov/os/webmaster-faq#developers)
# requires requests to identify a real contact -- this is not a secret, and
# is not a credential; it is a public identification string SEC's own
# documentation asks every automated client to send.
EDGAR_USER_AGENT = "Data-Acquisition-Fabric research-adapter contact@example.com"

_TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 0.5
_DEFAULT_MAX_DATES_PER_FETCH = 5  # bounded, gradual incremental catch-up -- see module docstring

Fetcher = Callable[[str], bytes]
Opener = Callable[..., Any]
Sleeper = Callable[[float], None]

_DATE_IN_FILENAME_RE = re.compile(r'"name":\s*"company\.(\d{8})\.idx"')


class EdgarFetchError(RuntimeError):
    """Raised for any acquisition-time failure: a non-transient HTTP
    error, a transient error that exhausted its retry budget, a
    connection failure, or an undecodable response body."""


def _fetch_with_retries(
    url: str, opener: Opener = urllib.request.urlopen, sleep: Sleeper = time.sleep
) -> bytes:
    """Bounded, deterministic retry: up to `_MAX_RETRIES` additional
    attempts, fixed backoff (no jitter), only for the HTTP statuses SEC's
    own guidance treats as transient (429 rate-limited, 5xx). A
    non-transient error (e.g. 404 -- the date genuinely doesn't exist)
    never retries. `opener`/`sleep` are injectable purely so this
    function is unit-testable without real network I/O or real delays --
    the default `fetch_bytes` used in production never overrides them.
    """
    request = urllib.request.Request(url, headers={"User-Agent": EDGAR_USER_AGENT})
    last_error: BaseException = EdgarFetchError(f"EDGAR request to {url!r} never attempted")

    for attempt in range(_MAX_RETRIES + 1):
        try:
            with opener(request, timeout=30) as response:
                return response.read()  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in _TRANSIENT_HTTP_STATUSES or attempt == _MAX_RETRIES:
                raise EdgarFetchError(f"EDGAR request to {url!r} failed: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == _MAX_RETRIES:
                raise EdgarFetchError(f"EDGAR request to {url!r} failed: {exc}") from exc
        if attempt < _MAX_RETRIES:
            sleep(_RETRY_DELAY_SECONDS)

    raise EdgarFetchError(f"EDGAR request to {url!r} failed after {_MAX_RETRIES} retries: {last_error}")


def _default_fetch(url: str) -> bytes:
    return _fetch_with_retries(url)


@dataclass(frozen=True)
class EdgarDailyIndexSourceAdapter:
    year: int
    quarter: int
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock
    since_date: Optional[str] = None  # YYYYMMDD, opaque to the DAF core -- see AdapterBinding.advance_position
    max_dates_per_fetch: int = _DEFAULT_MAX_DATES_PER_FETCH
    fetch_bytes: Fetcher = field(default=_default_fetch)

    def fetch(self) -> Tuple[RawDocument, ...]:
        listing_url = f"{DAILY_INDEX_BASE}/{self.year}/QTR{self.quarter}/index.json"
        listing_bytes = self.fetch_bytes(listing_url)
        try:
            listing_text = listing_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EdgarFetchError(f"EDGAR directory listing at {listing_url!r} was not valid UTF-8") from exc

        available_dates = sorted(set(_DATE_IN_FILENAME_RE.findall(listing_text)))
        if not available_dates:
            raise EdgarFetchError(f"EDGAR directory listing at {listing_url!r} named no company.*.idx files")

        if self.since_date is not None:
            available_dates = [date for date in available_dates if date > self.since_date]

        # Bounded, gradual catch-up: never fetch more than max_dates_per_fetch
        # in one call, even if far behind -- see module docstring.
        dates_to_fetch = available_dates[: self.max_dates_per_fetch]

        documents = []
        for date in dates_to_fetch:
            file_url = f"{DAILY_INDEX_BASE}/{self.year}/QTR{self.quarter}/company.{date}.idx"
            raw_bytes = self.fetch_bytes(file_url)
            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise EdgarFetchError(f"EDGAR daily index at {file_url!r} was not valid UTF-8") from exc
            documents.append(
                RawDocument(
                    source_name="SEC EDGAR",
                    source_kind="daily-index",
                    content=content,
                    locator=date,
                    retrieval_method="http:edgar_daily_index_v1",
                    retrieved_at=self.retrieved_at,
                )
            )
        return tuple(documents)
