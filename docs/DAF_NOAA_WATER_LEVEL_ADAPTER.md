# Phase I — Time-Series / Event Acquisition Validation (NOAA CO-OPS Water Level)

**Status:** implemented, passing, and validated against the real, live
NOAA CO-OPS Tides & Currents API. Eighth DAF phase: a THIRD real,
publicly-accessible external source, deliberately chosen to be neither a
publication/index source (EDGAR, Phase G) nor a mutable-identified-record
source (USGS, Phase H) but a genuine time-series where no individual
reading has any identity at all.

**Result up front:** **zero DAF core changes.** Every primitive —
including Phase H's one addition (`AcquiredArtifact.raw_content`) —
turned out unnecessary here, because this source's cursor value CAN be
recovered from its locator alone, the same way EDGAR's can (just via a
composite, window-shaped locator instead of a bare date string). This is
the empirical "outcome A" result the phase's stop condition allows for,
and it usefully calibrates Phase H's finding: the deficiency Phase H
fixed was real and necessary for USGS, but it was not a universal
requirement of "temporal/incremental sources" in general — it was
specific to sources where identity and cursor are stored in genuinely
different places. This phase's source has them collocated again, just
packed together differently than EDGAR's.

---

## Pre-implementation report

### 1–2. Candidate sources investigated

**Candidate A — CoinGecko `market_chart/range`** (crypto price
time-series, financial market data). Attempted live before any code was
written: `GET /api/v3/coins/bitcoin/market_chart/range?vs_currency=usd&from=...&to=...`
is documented to return `{"prices": [[timestamp, price], ...], ...}` --
architecturally exactly what this phase needs (pure numeric time-series,
no per-point identity). **Rejected**: the live request returned
`HTTP 429 Throttled` on the very first anonymous call, with CoinGecko's
public API having moved to requiring a demo API key for reliable access
as of recent policy changes. A source this phase cannot reliably and
respectfully demonstrate live is disqualified regardless of its
architectural fit — Phase A through H all required a working live
demonstration, and this phase does too (see "Live validation" section
11 of the task).

**Candidate B — NOAA CO-OPS Tides & Currents `datagetter`**
(environmental sensor observations). Investigated live: `GET
.../datagetter?product=water_level&station=...&begin_date=...&end_date=...&datum=...&units=...&time_zone=gmt&format=json`
returns `{"metadata": {...}, "data": [{"t","v","s","f","q"}, ...]}` — 6-
minute-interval sensor readings, no authentication required. Selected.

### 3. Selection rationale — strongest contrast with EDGAR and USGS

NOAA's `q` (quality) flag on each reading is either `"p"` (preliminary)
or `"v"` (verified) — confirmed live: a query for August 2026 (very
recent relative to this session's date) returns `q="p"` throughout;
the identical query shape for January 2026 (eight months in the past)
returns `q="v"` throughout. This proves NOAA's real QC pipeline
reprocesses readings over time — a genuine revision behavior — but
unlike USGS, **no individual reading has an id to revise**. The only
thing that can be said to have a stable identity here is the WINDOW
(station + product + date range) an adapter chooses to request, not any
row inside it. This is the strongest three-way contrast available:
EDGAR (unit = whole file, locator = cursor, never revised), USGS (unit =
individual record, locator ≠ cursor, individual records revised), NOAA
(unit = a whole time window, locator = cursor again, but the window's
CONTENTS can be revised even though no individual reading inside it has
identity).

The API's confirmed hard 31-day range limit per request (a 90-day
request returns `{"error": {"message": "... Range Limit Exceeded ..."}}`
with HTTP 400) is this source's own real pagination-by-time-window
constraint — genuinely different from EDGAR's "list once, fetch each
date" and USGS's "list once, fetch each event id" shapes.

### 4–5. Acquisition unit / raw artifact vs. event

**Acquisition unit = one bounded time window** (a `datagetter` response
for one `[begin_date, end_date]` request), **not** one API response
containing an aggregate of independently-identified sub-documents (like
EDGAR's filings) and **not** one artifact per reading (which would be
architecturally possible but was explicitly rejected — a `window_days=3`
window at 6-minute resolution holds up to 720 readings; making each its
own artifact would create exactly the "millions of tiny artifacts"
section 4 of the task warns against, for no benefit, since no reading
has independent identity to preserve anyway). One `RawDocument` per
`fetch()` call, raw bytes preserved byte-for-byte — same discipline as
EDGAR and USGS, applied at a third, coarser boundary.

### 6. Temporal semantics — event_time / ingestion_time / source_revision_time / acquisition_time, kept distinct

- **event_time**: each reading's own `t` field (e.g. `"2026-01-01 00:06"`)
  — never touched, extracted verbatim into content.
  `record.raw_content`/`Document.retrieved_at` are NOT substituted for
  it anywhere.
- **source_revision_time**: not directly exposed by NOAA as a
  timestamp — only the coarser `q` flag (`p`/`v`) is exposed. This is
  documented as a real, honest limitation (see "Known limitations"),
  not worked around by inventing a timestamp NOAA doesn't provide.
- **acquisition_time**: `RawDocument.retrieved_at`, caller-supplied
  (never wall-clock, matching every prior adapter's discipline).
- **ingestion_time**: not modeled separately from `acquisition_time` --
  this DAF has never distinguished the two (SCOUT's own
  `Document.retrieved_at` is the single acquisition-time field), and
  nothing about this source required inventing that distinction.

Investigated but **not confirmed present**: classic late-arrival (a
reading for an EARLIER timestamp appearing strictly after a LATER
timestamp was already published and acquired). NOAA publishes 6-minute
readings on a fixed schedule; nothing in the live investigation
suggested out-of-order publication. What IS confirmed is REVISION
(same timestamp, same window, later request returns different `v`/`q`
for that timestamp) — this is documented honestly as this source's real
temporal-integrity concern, distinct from late-arrival, per the task's
explicit instruction not to assume monotonicity or invent a late-arrival
narrative the source doesn't actually exhibit.

### 7. Checkpoint semantics

`position` = the just-fetched window's END DATE (`YYYYMMDD`), embedded
directly in the locator (`"{station}:{product}:{begin}:{end}"`) and
recovered by `window_end_of()` — a plain string split, adapter-local,
never imported by DAF core. **This is expressible entirely with the
EXISTING opaque-`position`/`AcquiredArtifact.locator` machinery from
Phase E — no composite-position type was needed.** The apparent
complexity (a station AND a product AND two dates) lives entirely
inside the locator string, which the checkpoint/orchestrator/scheduler
layers already treat as an opaque string; only `_advance_noaa_position`
(this adapter's own binding function) ever parses it.

### 8. Late-arriving data

See item 6: not confirmed present for this source. Not solved with an
arbitrary lookback window for that reason — what IS solved with a
lookback window is item 10 below (revision), a related but distinct
concern this source does exhibit.

### 9. Duplicates / overlapping windows — tested, both live and synthetic

Same window (identical station/product/begin/end) fetched twice with
unchanged upstream content → `AcquisitionOutcome.DUPLICATE`, zero pool
growth (`test_repeated_acquisition_of_an_unchanged_window_is_reported_as_duplicate`,
and confirmed live — see "Live validation" below). Two DIFFERENT,
deliberately-overlapping windows (the trailing-safety-window catch-up
described below legitimately re-requests some of the same calendar days
under a DIFFERENT locator) are correctly treated as two separate,
independently valid artifacts — not deduplicated at the day level, only
at the whole-window level, which is the correct behavior since they are
genuinely different acquisition units
(`test_incremental_second_run_rewinds_by_the_trailing_safety_window`).
No second deduplication mechanism was added; the existing
content-addressed identity (Phase A/B) handles both cases without
modification.

### 10. Revision behavior

**Confirmed present, and it generalizes Phase H's approach cleanly to a
window-shaped locator instead of an event-id locator**: re-requesting
the EXACT SAME window after NOAA's QC pipeline changes any reading
inside it produces different raw bytes under the SAME locator, hence
the SAME `artifact_id` (`content_hash({source_id, locator})`, Phase B)
and a NEW `version_id`
(`test_re_fetching_the_same_window_with_revised_readings_creates_a_new_version_same_artifact`).
Crucially, this needed **no new field** — unlike USGS, the window's end
date (the cursor) is already inside the locator, so
`AcquiredArtifact.raw_content` (Phase H) was never referenced by this
adapter's binding at all.

A genuine, source-driven mechanism for CATCHING revisions was still
needed (detecting a revision requires re-requesting an
already-acquired window, which nothing forces to happen automatically):
`revision_lookback_days` — the SAME trailing-safety-window idiom Phase F
documented (previously only exercised via a synthetic fixture, never a
live source) — rewinds each subsequent `fetch()` call's window start by
`revision_lookback_days - 1` days relative to the previous window's end,
so the trailing edge of every previously-acquired window gets
re-verified on the next run. This lives entirely inside
`daf/adapters/noaa_water_level.py` — the DAF core has no idea this
happens.

### 11. Current DAF compatibility

Every primitive fit without modification on the first implementation
attempt: `SourceDefinition`/`SourceCatalog` (station/product/start_date/
end_date as `required_parameters`, exactly like EDGAR's year/quarter and
USGS's starttime/endtime/minmagnitude), `AdapterBinding`/
`AcquisitionPlan`/`AcquisitionRequest`/`AcquisitionCheckpoint`/
`AcquisitionOrchestrator`/`ArtifactStore`/`DurablePool`/
`daf.scheduling.runner` all worked completely unmodified, including
Phase H's `AcquiredArtifact.raw_content` field, which this adapter's
binding never needed to read.

### 12. Core change justified?

**No.** Evaluated against all five gate conditions from the task:
1. Genuinely time-series/event-oriented: yes.
2. Current primitives cannot express it: **false** — they already do,
   as demonstrated by a full working implementation with zero core
   edits.
3–5. Moot given (2) is false. **Decision: implement only the
   adapter/extractor/binding, per the task's own instruction. No core
   abstraction added.**

---

## Design

```
NoaaWaterLevelSourceAdapter(station, product, start_date, end_date, retrieved_at, since_window_end, window_days, revision_lookback_days, fetch_bytes)
                    |
        since_window_end is None?
            window_start = start_date
        else:
            window_start = since_window_end - (revision_lookback_days - 1) days   [trailing safety window]
        window_end = min(window_start + window_days - 1, end_date)
        window_start > end_date?  -> return ()   [scope fully covered]
                    |
        fetch_bytes(f"{DATAGETTER_BASE}?product=...&station=...&begin_date=...&end_date=...&datum=...&units=...&time_zone=gmt&format=json")
        -- ONE RawDocument, locator = "{station}:{product}:{begin}:{end}", raw bytes verbatim
                    |
                    v
        NoaaWaterLevelExtractor.extract(record)
            -- projects metadata + per-reading {time, value, sigma, flags, quality}, counts quality flags
                    |
                    v
        scout.pipeline.run_scout -> evidence.admission -> DurablePool -> ArtifactStore   [all unmodified]
                    |
                    v  only on ACQUIRED / DUPLICATE (daf.scheduling.runner.execute_plan, unmodified)
        _advance_noaa_position(artifacts, previous_position):
            max_end = max(window_end_of(a.locator) for a in artifacts)   -- locator IS the cursor, like EDGAR
            new_position = max(max_end, previous_position)
        checkpoints.advance(AcquisitionCheckpoint(position=new_position, ...))
```

`daf.orchestration.bindings.noaa_water_level_binding()` is the sole seam
wiring this adapter/extractor pair in, exactly like every prior source.
No other file in `daf/orchestration`, `daf/catalog`, `daf/scheduling`,
or `daf/storage` was touched this phase.

---

## Live demonstration (required proof, performed against the real network)

Executed manually, once, against
`https://api.tidesandcurrents.noaa.gov/api/prod/datagetter`, identifying
via `NOAA_USER_AGENT`, bounded to a small, deterministic 10-day scope
(`station=8454000` — a real, publicly documented NOAA station in
Providence, RI — `product=water_level`, `start_date=20260101`,
`end_date=20260110`), `window_days`/`revision_lookback_days` left at
their defaults (3/2):

1. **Run 1** (fresh evidence/checkpoint stores, no prior checkpoint):
   `execute_plan` against the real network → `outcome=acquired`, one
   real window artifact (`8454000:water_level:20260101:20260103`,
   720 real 6-minute readings, 53,990 raw bytes), `is_new=True`.
   Checkpoint persisted at `20260103`.
2. **Restart resume**: a **brand-new process** (fresh `SourceRegistry`/
   `AdapterRegistry`/`DurablePool.restore(...)`/`CheckpointStore`, same
   on-disk paths only) re-ran the same plan. The checkpoint correctly
   restored `20260103`; the trailing-safety-window rule correctly
   computed the next window as `20260102:20260104` (rewound one day to
   re-verify Jan 2–3, extended one new day to Jan 4) against the live
   API, advancing the checkpoint to `20260104`.
3. **A third real window** (`20260103:20260105`) was acquired the same
   way on a subsequent call, bringing the on-disk store to 3 distinct
   real window-artifacts.
4. **Duplicate proof against real content**: the FIRST window
   (`20260101:20260103`) was deliberately re-requested via the
   orchestrator directly (bypassing the checkpoint, as an operator
   re-verification would). Because real NOAA content for that window had
   not changed in the few seconds between requests, the result was
   correctly `outcome=duplicate`, `is_new=False`, and the on-disk store
   stayed at exactly 3 records — zero duplication.

Total real HTTP requests made across the entire live demonstration: 4
(three forward windows + one duplicate re-check), each carrying the
documented `NOAA_USER_AGENT`, well within NOAA's stated fair-use
expectations.

---

## Post-implementation report

### 1. Selected source

NOAA CO-OPS Tides & Currents `datagetter` API
(`https://api.tidesandcurrents.noaa.gov/api/prod/datagetter`),
environmental observations / sensor time-series category.

### 2. Topology

Time-series acquisition: the unit is a bounded time WINDOW of many
unidentified (timestamp, value, quality) readings, not a document
(EDGAR) and not an individually-identified record (USGS). See the
three-source comparison table below.

### 3. Adapter

`daf/adapters/noaa_water_level.py` — `NoaaWaterLevelSourceAdapter`,
reusing the same bounded-retry policy shape as EDGAR/USGS
(`_fetch_with_retries`, independently re-derived), plus
window/trailing-safety-window arithmetic unique to this source.

### 4. Extractor

`daf/extractors/noaa_water_level.py` — `NoaaWaterLevelExtractor`, pure
JSON projection producing a per-window content dict (station metadata,
reading count, quality-flag counts, and the full per-reading list) —
zero entities/relations, matching every prior extractor's posture.

### 5. Acquisition boundary

One `fetch()` call = one HTTP request = one bounded time window
(`window_days`, default 3, capped further by the plan's own
`start_date`/`end_date` scope and NOAA's own 31-day hard limit) = one
`RawDocument`.

### 6. Artifact boundary

One artifact per window, locator = `"{station}:{product}:{begin}:{end}"`
— a third distinct boundary from EDGAR's whole-file and USGS's
individual-record artifacts, deliberately chosen to avoid
per-reading artifact explosion while still preserving the source's
exact acquired bytes.

### 7. Checkpoint semantics

`position` = the acquired window's end date, recoverable directly from
the locator (`window_end_of`) — no core change needed, unlike USGS.

### 8. Temporal semantics

event_time (`t` per reading), source_revision time (only the coarser
`q` flag is exposed by NOAA, not a timestamp — documented, not
invented), and acquisition_time (`retrieved_at`) kept fully distinct;
no substitution of one for another anywhere in the adapter or
extractor.

### 9. Duplicate behavior

Verified both synthetically and live: an unchanged, already-acquired
window re-fetched is `DUPLICATE` with zero pool growth. Two
deliberately-overlapping-but-differently-bounded windows are each
independently valid artifacts, not deduplicated against each other,
because they are genuinely different acquisition units.

### 10. Revision / late-arrival behavior

Revision: confirmed present and handled — see "Revision behavior"
above and the live demonstration. Late-arrival: investigated, not
confirmed present for this source, documented honestly rather than
assumed or invented.

### 11. Live acquisition

3 real windows acquired against the live API across a 10-day real
scope; see "Live demonstration" above for exact locators and byte
counts.

### 12. Restart acquisition

Fresh-process restart correctly restored the checkpoint and computed
the correct next (trailing-safety-window-adjusted) window against the
live API — see "Live demonstration" step 2.

### 13. SCOUT one-door proof

`test_one_door_invariant_for_noaa_modules` (AST-level, both new
modules): no import of `evidence.admission`, `materials`, `experiment`,
`workbench`, `core`, `morpho`, `backends`, or `runtime`; no direct
`.put_*` call anywhere in `daf/adapters/noaa_water_level.py` or
`daf/extractors/noaa_water_level.py`.

### 14. DAF core changes

**None.** `daf/orchestration/bindings.py` and `daf/catalog/cli.py` were
extended additively (one new binding function, one new registration
line) — the same kind of change every prior phase's binding-wiring
required, not a core-semantics change. No file under
`daf/orchestration/{result,orchestrator,adapter_registry,request,source_registry}.py`,
`daf/catalog/{checkpoint,plan,plan_catalog,source_catalog}.py`,
`daf/scheduling/*.py`, or `daf/storage/*.py` was touched this phase.

### 15. Full test results

`pytest tests/` (DAF, all eight phases): **231 passed** — 199 (Phases
A–H) + 32 new (Phase I: 13 adapter + 5 extractor + 14 integration).

Full vendored State-Space suite: **1273 passed, 0 failed, 0 files
modified.**

### 16. ruff

`ruff check` on this phase's new/changed files: one genuine finding was
found and fixed during development — `DTZ007` (naive
`datetime.strptime` without timezone) on the internal date-parsing
helper; resolved by constructing `datetime.date` directly from the
`YYYYMMDD` string's digit groups instead of routing through
`datetime.strptime`, which also removed a `datetime.datetime`→`.date()`
detour that wasn't needed anyway. Remaining findings
(`UP006`/`UP035`/`UP045`/`UP037`/`I001`/`PYI034`) are exclusively the
same pre-existing style-modernization patterns already present
throughout the codebase since Phase A (see Phases G and H's own
reports for the identical finding) — matched, not refactored away.

### 17. mypy

`mypy daf/` → **Success: no issues found in 39 source files.**

### 18. Three-source architectural comparison

| Property | EDGAR (Phase G) | USGS (Phase H) | NOAA (Phase I) |
|---|---|---|---|
| Acquisition unit | one whole daily index file | one individual event record | one bounded time window |
| Raw artifact | whole file, byte-for-byte | one event's own JSON document, byte-for-byte | one window response, byte-for-byte |
| Record/event | many filings inside one file (extracted, not separately acquired) | the artifact IS the record | many readings inside one window (extracted, not separately acquired) |
| Stable identity | the date | the event id | the window (station+product+date range) |
| Version identity | never varies (immutable source) | new version on content-changing revision | new version on content-changing revision |
| Cursor/checkpoint | = the locator (a date string) | ≠ the locator (needed `raw_content`, Phase H) | = the locator (a composite window string) |
| Ordering | filenames, sorted client-side | revision timestamp, sorted client-side | calendar time, computed client-side |
| Revision | none, ever | per-record (status/magnitude corrected) | per-window (readings inside flip preliminary→verified) |
| Late arrival | not applicable (Phase F idiom deliberately unused) | not confirmed | investigated, not confirmed (distinct from revision, which IS confirmed) |
| Duplicate behavior | existing content-hash dedup, unmodified | existing content-hash dedup, unmodified | existing content-hash dedup, unmodified |
| Replay behavior | re-run from an earlier checkpoint safely re-fetches, dedup absorbs it | same | same, plus a DELIBERATE trailing-window replay every run (not just on manual reset) |

**What is truly common** (validated three times, three genuinely
different topologies): the acquire → preserve-raw → extract → SCOUT-
admit → durably-persist → checkpoint-only-after-success pipeline itself;
content-addressed identity as the sole deduplication mechanism; an
opaque `position` string interpreted only by the adapter's own
`advance_position`; the one-door invariant; keeping all source-specific
policy (retry, pacing, window/lookback arithmetic) inside the adapter,
never the core.

**What remains adapter-specific**: the artifact-boundary decision
(file vs. record vs. window) is a real per-source judgment call the DAF
deliberately does not standardize; whether locator and cursor coincide
is empirically source-dependent, not assumable; whether "revision"
applies at the record level or the window level differs by source, and
the DAF does not need to know which.

**What belongs in DAF core** (as of three real sources): the seven
primitives listed in section 11 above, plus Phase H's one addition
(`AcquiredArtifact.raw_content`) — kept because USGS still needs it,
even though NOAA didn't. No further core surface is justified by the
evidence gathered so far.

**What must never enter DAF core** (per this phase's evidence, echoing
Phases F/G/H): a universal artifact-boundary policy, a universal
identity ontology, a generalized "revision" concept distinct from
"new version of an existing artifact_id," or any parsing of `position`
outside the adapter that produced it. Three sources in, the opaque-
string/locator-based design has needed exactly one addition, used by
exactly one of three adapters — evidence that the core is closer to
complete than to under-specified.

### 19. Recommended Phase J

Per this task's own stop condition, this phase is complete: three
structurally distinct real-world acquisition topologies (publication-
index, mutable-identified-record, unidentified-time-series) have now
been validated through the SAME DAF core (with one justified, minimal
addition along the way), and the resulting empirical acquisition
taxonomy above gives real evidence — not speculation — about what
belongs in the core versus what is legitimately adapter-specific. Per
the task's explicit instruction, this is the point to determine whether
the DAF has enough evidence to freeze its core acquisition contracts and
move toward industrial storage/indexing, rather than seeking a fourth
source purely for its own sake. A natural Phase J would either (a) treat
the acquisition contract as frozen and begin evaluating a real (but
still deliberately minimal) durable storage/indexing substrate against
the now-empirically-grounded requirements these three phases produced,
or (b) if one more contrast is wanted before freezing, target a source
with genuine opaque-token pagination (a cursor that is not a date,
timestamp, or sequence number at all) — the one dimension neither EDGAR,
USGS, nor NOAA exercised. Kafka/Iceberg/object storage/distributed
acquisition/GraphRAG/vector search/State-Space integration/FEP/active
learning/Morpho/CUDA/zkVM/execution provenance all remain untouched, per
this phase's explicit stop condition.
