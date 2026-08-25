# Phase H — Real-World Acquisition Topology Validation (USGS Earthquake Catalog)

**Status:** implemented, passing, and validated against the real, live
USGS Earthquake Catalog API. Seventh DAF phase: a second real,
publicly-accessible external source, deliberately chosen to differ from
SEC EDGAR (Phase G) in acquisition unit, cursor semantics, and
mutability — specifically to test whether the DAF's core primitives
genuinely generalize, per this phase's own stop condition (outcome B:
"precise recurring mismatch justifies the smallest new domain-independent
primitive").

**Result up front:** the DAF core did NOT need a new abstraction, a new
checkpoint concept, or a new adapter contract. It needed exactly **one**
additive field, `AcquiredArtifact.raw_content: str`, because Phase E's
`locator`-only design (reasonably) assumed a source's stable identity
and its incremental cursor value are the same thing — true for EDGAR and
`incremental_dataset`, false for USGS. Everything else — `SourceDefinition`,
`SourceCatalog`, `AdapterRegistry`, `AdapterBinding`, `AcquisitionPlan`,
`AcquisitionRequest`, `AcquisitionCheckpoint`, `AcquisitionOrchestrator`,
`ArtifactStore`, `DurablePool`, `daf.scheduling.runner` — is completely
unmodified.

---

## Pre-implementation report

### 1–2. Candidate sources investigated

**Candidate A — USGS Earthquake Catalog** (`https://earthquake.usgs.gov/fdsnws/event/1/`,
scientific dataset). Investigated live before any code was written:
- `.../query?format=geojson&starttime=...&endtime=...&minmagnitude=...`
  returns a GeoJSON `FeatureCollection` of event summaries.
- `updatedafter=<ISO-8601>` genuinely filters by **revision time**, not
  publication order — confirmed by querying with a specific event's own
  `updated` timestamp and observing it correctly excluded (strictly
  "after", not "at-or-after").
- `.../query?eventid=<id>&format=geojson` returns one complete,
  standalone GeoJSON `Feature` for exactly that event — a clean raw
  artifact boundary at the individual-record level.
- No authentication; USGS's public-access guidance asks for a real
  identifying User-Agent and non-aggressive polling, same posture as
  SEC EDGAR.
- Critically: `status` moves from `"automatic"` to `"reviewed"` and
  `mag` gets corrected after human review — the **same event id**
  legitimately reappears with **different content** days or weeks
  later. This is a real, common, documented behavior of this catalog,
  not a hypothetical.

**Candidate B — GBIF Occurrence API** (`https://api.gbif.org/v1/occurrence/search`,
scientific dataset). Also investigated live: offset-based pagination
over a corpus of 300M+ records, a `lastInterpreted`/`modified` pair of
timestamps per record (DAF-side re-crawl time vs. source-side edit
time), no authentication required for search. Real correction behavior
exists here too (GBIF's interpretation pipeline revises records).
Rejected as this phase's selected source because: (a) offset-based
search pagination is documented by GBIF itself to become unreliable
past roughly 100,000 results, pushing a *real* production integration
toward GBIF's separate bulk-download API — more infrastructure than this
phase's validation goal warrants; (b) its record schema is an order of
magnitude larger/more complex than USGS's, adding noise without adding
architectural contrast; (c) USGS's `updatedafter` cursor is a cleaner,
more clearly-documented instance of the exact "identity ≠ cursor"
pattern this phase set out to stress-test.

### 3. Comparison: EDGAR vs. USGS

| Dimension | SEC EDGAR (Phase G) | USGS Earthquake Catalog (Phase H) |
|---|---|---|
| Acquisition unit | one whole daily index **file** (many filings inside) | one individual event **record** (one HTTP fetch each) |
| Source identity | one date string per file | one event id per record |
| Artifact identity (locator) | the date (`YYYYMMDD`) | the event id (e.g. `us6000thj0`) |
| Incremental cursor | the date itself — locator IS the cursor | a separate "last revised" timestamp — **locator is NOT the cursor** |
| Version semantics | never revised — immutable once published | genuinely mutable — same locator, new content, new version, over time |
| Pagination | none (whole directory listing in one call) | listing query returns many summaries in one call; details fetched individually |
| Ordering | filenames sorted by date, oldest-first | candidates sorted by revision time (client-side), oldest-revised-first |
| Corrections | none — SEC publishes exactly once per day | routine — magnitude/status revised after review |
| Late-arriving data | not applicable (Phase F's trailing-safety-window idiom deliberately not used) | not applicable in the classic sense either — but *revision* plays the role late-arrival plays elsewhere: content changes after first observation |
| Raw format | fixed-width text | structured JSON |
| Raw artifact boundary | whole file, byte-for-byte | one event's own JSON document, byte-for-byte |
| Extraction | text parsing (regex) | JSON projection |
| Auth/rate limits | none; documented User-Agent requested | none; documented User-Agent requested |

The informative contrast is precise: **EDGAR's locator IS its cursor;
USGS's locator and cursor are two different values that happen to
describe the same record.**

### 4. Current-DAF-first attempt

Every primitive except one fit without modification:
`SourceDefinition`/`SourceCatalog` needed no change (`starttime`/
`endtime`/`minmagnitude` are just more `required_parameters`, exactly
like EDGAR's `year`/`quarter`). `AdapterBinding`/`AcquisitionPlan`/
`AcquisitionRequest`/`AcquisitionCheckpoint`/`AcquisitionOrchestrator`/
`ArtifactStore`/`DurablePool`/`daf.scheduling.runner` all worked
unmodified in a first implementation attempt.

The ONE place it broke: `_advance_usgs_position` (the binding function
`execute_plan` calls to compute the next checkpoint) needs the
per-artifact "last revised" timestamp — but `AcquiredArtifact` (Phase E)
exposed only `locator`, which for USGS is an event id that carries no
temporal information at all. This was a genuine dead end, not a design
oversight to route around casually — see the next section.

### 5–8. Acquisition topology / artifact semantics / checkpoint semantics / correction-ordering behavior

Covered in detail in the comparison table (item 3) and the "Design"
section below. In short: acquisition unit = one event; artifact = one
event's own detail document; checkpoint = max revision-time seen;
corrections are first-class or ordinary revisions, handled by the
existing artifact_id/version_id split with no new machinery.

### 9. Current DAF compatibility — the precise mismatch, and why workarounds were rejected

Three ways to avoid a core change were considered and rejected, each
for a concrete, checkable reason — not because they were merely
inconvenient:

1. **Encode the cursor value into the locator itself** (e.g.
   `locator = f"{updated}:{event_id}"`), the way `incremental_dataset`
   encodes its sequence number into its locator. Rejected: `locator` is
   also the input to `ArtifactStore.artifact_id = content_hash({source_id,
   locator})` — the whole point of choosing USGS was to prove a REVISED
   record keeps the SAME artifact id across versions. Embedding the
   (changing) revision timestamp into the locator would make every
   revision look like a brand new artifact, destroying exactly the
   version semantics this phase exists to validate.
2. **Have the adapter instance remember cursor data in memory between
   `fetch()` and `advance_position`.** Rejected: `AdapterBinding`s are
   constructed once and reused across many separate `execute_plan`
   calls, including across process restarts (Phase E/G's whole point).
   Any such in-memory state would silently break exactly the
   restart-survival guarantee Phase G's live demonstration proved.
3. **Use the request's `requested_at` ("poll time") as the next
   checkpoint instead of "max value actually seen."** Rejected: this is
   unsafe under `max_events_per_fetch`'s bounded, gradual catch-up (the
   same idiom EDGAR established) — it would skip over not-yet-fetched
   backlog whose revision time is earlier than "now" but later than the
   old checkpoint, exactly the bug EDGAR's own `_advance_edgar_position`
   was designed to avoid by using "max of what was ACTUALLY acquired."

With all three ruled out, the actual constraint was traced precisely:
`daf.orchestration.orchestrator.AcquisitionOrchestrator.run` already has
access to `finding.record.raw_content` (a vendored `Record` field, never
modified) when it builds each `AcquiredArtifact` — it simply wasn't
copying it through. No vendored SCOUT type needed to change.

### 10. Core change justified? — evaluated against all five gate conditions

1. **Genuinely different from EDGAR**: yes — locator ≠ cursor for USGS,
   locator = cursor for every source so far.
2. **Existing primitives cannot express it**: yes — demonstrated
   concretely above (three rejected workarounds, precise root cause).
3. **Recurring concept, not a one-off quirk**: yes — "stable identity
   distinct from a mutable sync watermark" is one of the most common
   real-world incremental-sync patterns (CDC watermark columns,
   `modified_since`-style REST APIs, GBIF's own `lastInterpreted`/
   `modified` pair investigated as Candidate B above) — not invented for
   USGS.
4. **Change can remain domain-independent**: yes — `raw_content` is an
   opaque string the orchestrator copies through without interpreting;
   exactly the same posture as the existing `locator` field.
5. **At least two concrete behaviors justify it**: yes, from the one
   source — (a) computing the correct incremental checkpoint at all
   requires content-derived cursor data no existing field carries, and
   (b) that same content-mutability is what makes the artifact_id/
   version_id split (Phase B) meaningful for the first time against a
   real external source — two distinct concrete requirements, one root
   cause.

**Decision: justified.** Implemented as the smallest possible additive
change (below).

---

## Design

```
UsgsEarthquakeSourceAdapter(start_time, end_time, min_magnitude, retrieved_at, updated_after, max_events_per_fetch, fetch_bytes)
                    |
        fetch_bytes(f"{EVENT_QUERY_BASE}?format=geojson&starttime=...&endtime=...&minmagnitude=...&limit=500[&updatedafter=...]")
                    |
        parse `features[].{id, properties.updated}` -> candidate (event_id, updated) pairs
        sort by `updated` ascending, cap at max_events_per_fetch (oldest-revised-first)
                    |
        for each selected event_id:
            fetch_bytes(f"{EVENT_QUERY_BASE}?eventid={event_id}&format=geojson")  -- one RawDocument per event, raw bytes verbatim
                    |
                    v
        UsgsEarthquakeExtractor.extract(record)
            -- pure JSON projection: id/properties/geometry -> content dict
                    |
                    v
        scout.pipeline.run_scout -> evidence.admission -> DurablePool -> ArtifactStore   [all unmodified]
                    |
                    v  only on ACQUIRED / DUPLICATE (daf.scheduling.runner.execute_plan, unmodified)
        _advance_usgs_position(artifacts, previous_position):
            max_updated_ms = max(json.loads(a.raw_content)["properties"]["updated"] for a in artifacts)
            -- Phase H's ONE core addition made this possible: raw_content
               is available on AcquiredArtifact, so a binding whose cursor
               is content-derived doesn't need the locator to carry it.
            new_position = max(iso8601(max_updated_ms), previous_position)
        checkpoints.advance(AcquisitionCheckpoint(position=new_position, ...))
```

`daf.orchestration.bindings.usgs_earthquakes_binding()` is the sole seam
wiring this adapter/extractor pair in, exactly like every prior source.

### The one core change, precisely

```python
# daf/orchestration/result.py
@dataclass(frozen=True)
class AcquiredArtifact:
    artifact_id: str
    version_id: str
    is_new: bool
    locator: str
    raw_content: str   # <-- new, Phase H, additive, no default needed (one construction site)

# daf/orchestration/orchestrator.py -- one line changed
AcquiredArtifact(
    artifact_id=..., version_id=..., is_new=..., locator=finding.record.locator,
    raw_content=finding.record.raw_content,   # <-- new
)
```

`AdapterBinding`'s type signature did not change at all — `advance_position`
already received `Tuple[AcquiredArtifact, ...]`; it now simply has one
more (still opaque, still adapter-interpreted-only) field available on
each element. No new callable, no new abstraction, no vendored change.
`daf/orchestration/adapter_registry.py`'s docstring was updated to
document this; its actual code is unchanged.

Backward compatibility was verified, not assumed: the full pre-existing
suite (169 tests, Phases A–G) passes unmodified after this change, and a
new test (`test_acquired_artifact_exposes_raw_content_generically`,
`tests/test_acquisition_orchestrator.py`) proves the field is populated
generically for `local-dataset` too — not specially wired for USGS.

---

## Live demonstration (required proof, performed against the real network)

Executed manually, once, against `https://earthquake.usgs.gov/fdsnws/event/1/`,
identifying via `USGS_USER_AGENT`, bounded to a small, deterministic,
significant-events-only window (`starttime=2026-08-01`,
`endtime=2026-08-10`, `minmagnitude=5.5`), `max_events_per_fetch` left at
its default (5):

1. **Run 1** (fresh evidence/checkpoint stores, no prior checkpoint):
   `execute_plan` against the real network → `outcome=acquired`, 5 real
   events (`us6000ti8i`, `us6000thl3`, `us6000tj8t`, `us6000tif5`,
   `us6000ti49`), each a genuine content-addressed
   `artifact_id`/`version_id`, `is_new=True`. Checkpoint persisted at
   `2026-08-20T17:50:29.637Z` — a real revision timestamp, not a
   locator, not a date in the acquisition window.
2. **Restart resume**: a **brand-new process** (fresh `SourceRegistry`/
   `AdapterRegistry`/`DurablePool.restore(...)`/`CheckpointStore`, same
   on-disk paths only) re-ran the same plan. The checkpoint correctly
   restored from disk; the run queried
   `updatedafter=2026-08-20T17:50:29.637Z` against the live API and
   fetched 5 more real events, advancing the checkpoint to
   `2026-08-22T14:42:49.249Z`.
3. **An organic duplicate, caught live**: the pool ended with 9 distinct
   records, not 10, after two runs of 5 fetches each — one event was
   fetched in both runs yet correctly resulted in exactly one persisted
   version (verified directly against the on-disk store: every locator
   maps to exactly one document id, no locator has two versions). This
   is the existing content-addressed dedup (Phase A/B) working
   correctly under a real, unpredictable live condition neither
   fixture could have manufactured: a bounded-catch-up window's edge
   interacting with an actively-updating real catalog. Nothing was lost
   or corrupted; the DAF's duplicate-detection absorbed it exactly as
   designed. See "Known limitations" for the precise, honest boundary
   this draws.

Total real HTTP requests made across the entire live demonstration: 12
(one listing + five detail fetches, twice), each carrying the documented
`USGS_USER_AGENT`, well within USGS's stated fair-use expectations.

---

## Post-implementation report

### 1. Selected source

USGS Earthquake Catalog's FDSN event web service
(`https://earthquake.usgs.gov/fdsnws/event/1/`), scientific dataset
category.

### 2. Why it differs materially from EDGAR

Locator (event id) and incremental cursor (revision timestamp) are
different values for the same record — the first real source in this
project where that is true. EDGAR's daily-index locator IS its own
cursor; USGS's is not. USGS's content is also genuinely mutable (real
corrections), letting Phase B's artifact_id/version_id split be
exercised against live external data for the first time.

### 3. Adapter architecture

`daf/adapters/usgs_earthquakes.py` — `UsgsEarthquakeSourceAdapter`,
mirroring EDGAR's "list, then fetch each selected unit" two-step shape
and identical bounded-retry policy (`_fetch_with_retries`, independently
re-derived, not shared code — see the adapter test file's own note on
this), applied at the individual-event granularity instead of the
whole-file granularity.

### 4. Extractor architecture

`daf/extractors/usgs_earthquakes.py` — `UsgsEarthquakeExtractor`, pure
JSON projection (no regex/text parsing needed, unlike EDGAR): `id`,
`properties.{mag, place, time, updated, status, magType}`,
`geometry.coordinates` → a flat content dict. Zero entities/relations,
matching EDGAR's own posture of proving the extraction contract, not a
domain ontology.

### 5. DAF core changes

Exactly one additive field: `AcquiredArtifact.raw_content: str`
(`daf/orchestration/result.py`), populated by one new line in
`daf/orchestration/orchestrator.py` from an already-available (vendored,
unmodified) `finding.record.raw_content`. `daf/orchestration/
adapter_registry.py`'s docstring updated to document the new option;
its code is unchanged. No vendored SCOUT/evidence code touched. No new
`AdapterBinding` callable. Verified fully backward-compatible: all 169
pre-existing tests pass unmodified, plus one new generic test proving
the field works for a non-USGS adapter too.

### 6. Raw artifact semantics

One `RawDocument`/artifact per individual USGS event-detail HTTP
response, preserved byte-for-byte (not re-serialized, not reduced to
normalized fields before persistence) — `daf.extractors.usgs_earthquakes`
only ever reads `record.raw_content`, never mutates or replaces it.

### 7. Checkpoint semantics

`position` = an opaque ISO-8601 string (the maximum `properties.updated`
seen, converted from epoch milliseconds), read back only by
`_advance_usgs_position` and by `UsgsEarthquakeSourceAdapter` (as
`updated_after`, re-injected into the `updatedafter` query parameter).
`daf.catalog.checkpoint`/`daf.scheduling.runner` never parse or compare
it — same opacity discipline as EDGAR's date-string position.

### 8. Live acquisition result

5 real events acquired in one bounded call against the live API; see
"Live demonstration" above for exact ids and checkpoint values.

### 9. Restart result

Fresh-process restart correctly restored the checkpoint from disk and
fetched only the next batch of genuinely more-recently-revised real
events — see "Live demonstration" step 2.

### 10. Failure result

Four categories tested (synthetic, deterministic, matching EDGAR's own
coverage exactly): `SOURCE_UNAVAILABLE` (raw `OSError` subclass reaching
the adapter boundary), `ADAPTER_FAILURE` (a listing response with no
`features` array), `EXTRACTION_FAILURE` (an event detail missing a
required field), `PERSISTENCE_FAILURE` (a broken evidence store). All
four leave the checkpoint untouched
(`test_transient_http_failure_is_reported_as_source_unavailable`,
`test_adapter_side_failure_is_reported_as_adapter_failure`,
`test_malformed_response_is_an_extraction_failure_not_silently_admitted`,
`test_persistence_failure_leaves_checkpoint_unadvanced`).

### 11. Duplicate/version result

`test_incremental_second_run_acquires_only_the_revised_event` is this
phase's central proof: the same locator, revised content, produces the
SAME `artifact_id` and a DIFFERENT `version_id`, correctly reported
`is_new=True`, with the checkpoint advancing by content-derived revision
time rather than by locator. `test_repeated_acquisition_is_reported_as_duplicate`
covers the ordinary unrevised-repeat case. The live demonstration's
organic duplicate (item 3 above) confirms the same machinery holds
against real, unscripted conditions.

### 12. One-door proof

`test_one_door_invariant_for_usgs_modules` (AST-level, both new
modules): no import of `evidence.admission`, `materials`, `experiment`,
`workbench`, `core`, `morpho`, `backends`, or `runtime`; no direct
`.put_*` call anywhere in `daf/adapters/usgs_earthquakes.py` or
`daf/extractors/usgs_earthquakes.py`.

### 13. Full test results

`pytest tests/` (DAF, all seven phases): **199 passed** — 169 (Phases
A–G) + 30 new (Phase H: 12 adapter + 4 extractor + 13 integration + 1
generic orchestrator `raw_content` test).

Full vendored State-Space suite: **1273 passed, 0 failed, 0 files
modified.**

### 14. ruff

`mypy daf/` → **Success: no issues found in 37 source files.**

`ruff check` on this phase's new/changed files: zero correctness
findings. Remaining findings (`UP006`/`UP035`/`UP045`/`UP037`/`I001`/
`PYI034`/`RUF059`) are exclusively pre-existing style-modernization
patterns already present throughout the codebase since Phase A (see
Phase G's own report for the same finding) — this phase matched the
established convention rather than introducing a one-off inconsistency
or undertaking an unrelated repo-wide refactor.

### 15. mypy

`mypy daf/` → **Success: no issues found in 37 source files.**

### 16. Architectural lessons

- **The stop condition's outcome B was the honest answer, and it was
  small.** The temptation with "the second source doesn't quite fit" is
  to reach for a general-purpose escape hatch (a `Dict[str, Any]` bag of
  adapter metadata on every result object, a new `CursorExtractor`
  protocol, etc.). The actual fix was one field, already-available data,
  zero new concepts. Section 12's gate ("do not build a primitive merely
  because the second source is different") did real work here: two of
  the three rejected workarounds (items 9.1 and 9.2 above) would have
  been *easier* to write than the real fix, and both were unsound.
- **Locator and cursor are not the same concept, even though every
  source examined before this phase made them look identical.** Phase E's
  own docstrings said "purely by inspecting `AcquiredArtifact.locator`"
  as if that were the general case; it was actually the *coincidental*
  case for the two sources examined so far. This is exactly the kind of
  finding this phase's reconnaissance-first posture exists to surface.
- **Live validation earns its keep every time it's used.** Phase G's
  live run caught a text-parsing assumption; this phase's live run
  caught nothing wrong in the code, but it DID surface a real operational
  subtlety (the organic duplicate across two runs) that no fixture could
  have manufactured, and confirmed the existing dedup machinery handles
  it correctly without any special-casing.
- **A source's raw artifact boundary is a real design decision, not a
  given.** USGS could have been modeled as "one artifact per listing
  page" (mirroring EDGAR's shape exactly) instead of "one artifact per
  event." The finer-grained choice was deliberately made because it is
  what let the artifact_id/version_id split be tested meaningfully —
  the coarser choice would have hidden the exact contrast this phase
  was designed to find.

### 17. Known limitations

- The organic duplicate observed in the live demonstration (item 3)
  means the adapter's bounded, bucketed catch-up (`max_events_per_fetch`)
  is not proven gap-free at its exact boundary against a live,
  concurrently-updating catalog — it is proven *safe* (existing
  content-addressed dedup absorbs any overlap with zero corruption and
  zero duplication in the pool), which is the guarantee that actually
  matters, but a re-fetched event at a boundary is a real, observed cost
  worth naming rather than glossing over.
- `_LISTING_LIMIT` (500) bounds the summary listing query itself,
  independent of `max_events_per_fetch`; a catalog window with more than
  500 matching events between two checkpoints would silently truncate
  the candidate pool for that run rather than erroring — a documented,
  deliberate pacing choice, not a correctness bug (nothing is lost
  permanently; the next run's `updatedafter` still catches up
  gradually), but worth flagging explicitly per this project's "no
  silent caps" discipline.
- `USGS_USER_AGENT` is a placeholder contact string, same posture and
  same caveat as EDGAR's — a deployment-configuration detail.
- This phase does not fetch the earthquake "products" sub-resources
  (shakemap, moment tensor, etc.) linked from each event's detail
  document — only the event-detail document's own top-level fields.
  That would be a separate, deeper acquisition decision, out of this
  phase's stated scope.
- What is source-specific vs. DAF-general: everything in
  `daf/adapters/usgs_earthquakes.py` and
  `daf/extractors/usgs_earthquakes.py` (URL shape, retry/backoff policy,
  User-Agent, JSON projection, the ISO-8601 revision-time checkpoint
  format) is USGS-specific. `AcquiredArtifact.raw_content` is the one
  piece of DAF-general infrastructure this phase added, and it is
  general precisely because the orchestrator never interprets it — only
  a binding that needs it (currently only USGS's) ever reads it.

### 18. Recommended Phase I

Per this task's own stop condition, this phase is complete: one
genuinely different real-world acquisition topology (content-mutable,
identity-distinct-from-cursor, individual-record-granularity) proven
through the DAF, with the smallest justified core addition rather than a
speculative one. Two natural directions for a future phase: (a) a third
source stressing PAGINATION specifically (a true opaque-token cursor,
not a timestamp or date — neither EDGAR nor USGS exercises this), which
would test whether `position`'s opacity discipline holds for a value
that isn't even human-readable; or (b) begin the FEP/information-gap-
driven `AcquisitionRequest` work every prior phase's report has flagged
as the next real architectural frontier. Both remain untouched here, as
does the separate Rust/zkVM/Morpho/CUDA execution plane and any change
to State-Space's own semantic core.
