# Phase G — First Production External Source Adapter (SEC EDGAR)

**Status:** implemented, passing, and validated against the real, live
SEC EDGAR API. Sixth DAF phase: exactly one real, publicly accessible,
structured external source — SEC EDGAR's daily-index feed — implemented
entirely through the existing DAF architecture (Phases A–E), with zero
changes to `AcquisitionOrchestrator`, `EvidencePool`, the checkpoint
machinery, or any vendored SCOUT/evidence code.

---

## Pre-implementation report

1. **Source chosen and why**: SEC EDGAR's daily-index feed
   (`https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{n}/`),
   over the alternative company-submissions JSON API
   (`https://data.sec.gov/submissions/CIK##########.json`). The
   submissions API is per-company and effectively a snapshot each call;
   the daily index is *genuinely* incremental — SEC publishes exactly one
   new, immutable file per business day, in order — which is what lets
   this adapter exercise real `AcquisitionCheckpoint` resume behavior
   against a real external source, not just prove snapshot acquisition
   (already covered by `daf.adapters.arxiv` and `daf.adapters.local_dataset`).
2. **Access mechanism investigated, not assumed**: before writing any
   code, the real endpoints were fetched directly (`curl`, then Python's
   `urllib`) — both `index.json` (a JSON directory listing) and a real
   `company.YYYYMMDD.idx` file. This mattered: the real header block
   turned out to wrap the column labels across **two** physical lines
   (`Company Name ... Form Type   CIK` then `      Date Filed  File
   Name` on the next line), and — more importantly — a live regression
   pass (see item 8 below) surfaced that company names occasionally
   contain internal runs of 2+ spaces, which a naive
   split-on-whitespace-runs parser misreads.
3. **Existing primitives reused verbatim, unmodified**: `scout.interface.
   RawDocument`/`Extractor`/`ExtractionCandidate`, `AdapterBinding`
   (including the Phase E `advance_position` hook), `SourceDefinition`,
   `AcquisitionPlan.mode="incremental"`, `daf.scheduling.runner.
   execute_plan`, `CheckpointStore`, `DurablePool`/`ArtifactStore`. No new
   abstraction was introduced anywhere in `daf.orchestration`,
   `daf.catalog`, `daf.scheduling`, or `daf.storage`.
4. **Checkpoint position representation**: an EDGAR daily-index locator
   *is* a `YYYYMMDD` date string, and dates sort correctly as strings —
   so `position` for this source is simply the maximum date string
   acquired so far. No decoding/re-encoding step is needed (unlike
   `incremental_dataset`'s zero-padded integer sequences), but the
   checkpoint/runner/scheduler layers still never parse or compare it —
   only `_advance_edgar_position` (this phase's one
   `AdapterBinding.advance_position` implementation) ever reads it.
5. **Late-arrival / out-of-order risk (Phase F's trailing-safety-window
   idiom) — investigated, found inapplicable**: SEC publishes each
   business day's index exactly once, as a complete, immutable file,
   after that day's filings have closed. There is no revision-in-place
   and no partial/incomplete file published early. The daily-index feed
   does not exhibit the late-arrival problem Phase F's idiom exists for,
   so no safety window was added — using one here would only needlessly
   re-fetch already-complete days.
6. **Responsible HTTP behavior required**: SEC's public-access fair-use
   policy requires every automated client to send a real identifying
   `User-Agent` (SEC blocks/throttles requests without one) and asks for
   restrained request rates. This is implemented as a bounded,
   deterministic retry (`_fetch_with_retries`: up to 2 additional
   attempts, fixed 0.5s backoff, only for statuses SEC's own guidance
   treats as transient — 429/500/502/503/504; a 404 or other
   non-transient status never retries) plus a documented
   `EDGAR_USER_AGENT` string, plus a `max_dates_per_fetch` cap (default
   5) so a plan that is far behind catches up gradually across several
   runs instead of bursting dozens of requests in one call.
7. **Test strategy**: two independent test files against exclusively
   *synthetic* fixtures (`tests/fixtures/edgar_*` — fabricated company
   names/CIKs, headers explicitly labeled "SYNTHETIC TEST DATA -- NOT
   REAL SEC EDGAR CONTENT") for CI (`test_edgar_daily_index_adapter.py`,
   `test_edgar_daily_index_extractor.py`), a separate integration suite
   exercising the full DAF path plus the existing operator CLI as real
   subprocesses (`test_edgar_daily_index_integration.py`), and a
   standalone, manual live demonstration against the real network (this
   phase's required proof, documented in "Live demonstration" below) —
   never mixed into the synthetic/CI fixtures.
8. **A real bug the live demonstration exists to catch — and did**: the
   first extractor implementation split each data row on runs of 2+
   whitespace characters, assuming exactly five fields would result.
   Run against real EDGAR content for 2026-07-01, this raised
   `EdgarDailyIndexExtractionError` on `PRICHEP PATRICIA  B` — a real
   individual filer name containing two internal spaces before a middle
   initial — which the naive split misread as six fields. The synthetic
   fixtures never exposed this because they were fabricated with
   single-space company names. The extractor was corrected to a
   right-anchored regex (the last four fields — Form Type, CIK, Date
   Filed, File Name — are always single whitespace-delimited tokens;
   everything remaining on the left, however many internal spaces it
   contains, is the company name), re-validated against **9,843 real
   data rows across two independent real days (2026-07-01, 2026-07-15)
   with zero parse failures**, and a permanent regression fixture/test
   (`edgar_daily_index_synthetic_double_space_name.idx`,
   `test_extract_handles_a_company_name_containing_a_double_space`) was
   added so this exact edge case can never silently regress. This is
   exactly the "fixtures for CI, live demonstration to catch what
   fixtures cannot" split the task called for, working as intended.

---

## Design

```
EdgarDailyIndexSourceAdapter(year, quarter, retrieved_at, since_date, max_dates_per_fetch, fetch_bytes)
                    |
        fetch_bytes(f"{DAILY_INDEX_BASE}/{year}/QTR{quarter}/index.json")   -- directory listing
                    |
        parse out every "company.YYYYMMDD.idx" name -> sorted date list
        filter to dates > since_date, cap at max_dates_per_fetch (oldest first)
                    |
        for each selected date:
            fetch_bytes(f".../company.{date}.idx")  -- one RawDocument per date, raw bytes verbatim
                    |
                    v
        EdgarDailyIndexExtractor.extract(record)
            -- right-anchored regex per data row: company_name (free text,
               may contain internal whitespace) / form_type / cik /
               date_filed / file_name
            -- content: {date_filed, filing_count, form_type_counts, filings: [...]}
                    |
                    v
        scout.pipeline.run_scout -> evidence.admission -> DurablePool -> ArtifactStore   [all unmodified]
                    |
                    v  only on ACQUIRED / DUPLICATE (daf.scheduling.runner.execute_plan, unmodified this phase)
        _advance_edgar_position(artifacts, previous_position) = max(locators, previous_position)
        checkpoints.advance(AcquisitionCheckpoint(position=new_max_date, ...))
```

`daf.orchestration.bindings.edgar_daily_index_binding()` is the sole seam
wiring this adapter/extractor pair in — `daf/adapters/edgar_daily_index.py`
and `daf/extractors/edgar_daily_index.py` are the only two new modules
that know anything about SEC EDGAR; nothing else in the DAF core changed
its behavior for this source's sake.

### Retry logic

`_fetch_with_retries(url, opener=urllib.request.urlopen, sleep=time.sleep)`
is injectable purely for unit-testability (no mocking library, matching
the codebase's established style): tests substitute a fake `opener` that
raises a controlled sequence of `urllib.error.HTTPError`s and a `sleep`
that just records calls, so retry/backoff logic is proven deterministically
in milliseconds, with no real network I/O or real delay. The production
`fetch_bytes` default never overrides either.

### Failure classification (unchanged orchestrator logic, exercised two new ways)

- A raw `OSError`/`ConnectionError`/`TimeoutError` reaching the adapter
  boundary (e.g. `urllib.error.URLError`, which is an `OSError` subclass)
  is classified `SOURCE_UNAVAILABLE` — a transient/environmental failure.
- `EdgarFetchError` (a `RuntimeError`) — raised when retries are
  exhausted, a non-transient HTTP status is hit, or (as tested) the
  directory listing names no index files at all — is classified
  `ADAPTER_FAILURE`, the orchestrator's existing broad
  `except Exception` branch. Both paths are covered by dedicated tests
  (`test_transient_http_failure_is_reported_as_source_unavailable`,
  `test_adapter_side_failure_is_reported_as_adapter_failure`) — no
  orchestrator code changed to support either.

---

## Live demonstration (required proof, performed against the real network)

Executed manually, once, against `https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/`,
identifying via the same `EDGAR_USER_AGENT` production code sends, with
`max_dates_per_fetch` left at its default (5) so no single call fetched
more than five real files:

1. **Run 1** (fresh evidence/checkpoint stores, no prior checkpoint):
   `execute_plan` against the real network → `outcome=acquired`, 5 real
   documents (`20260701, 20260702, 20260706, 20260707, 20260708` — note
   2026-07-04 is a US holiday and correctly absent from SEC's own
   listing), each an `is_new=True` `AcquiredArtifact` with a genuine
   content-addressed `artifact_id`/`version_id`. Checkpoint persisted to
   disk at `20260708`.
2. **Identity/persistence**: the first document's raw content (967,575
   real bytes for 2026-07-01) was read back from `pool.get_document(...)`
   verbatim, and independently from the on-disk `FilesystemEvidenceStore`
   record — `retrieval_method="http:edgar_daily_index_v1"`,
   `locator="20260701"`, matching the adapter's own output exactly.
3. **Restart resume**: a **brand-new process** (fresh `SourceRegistry`/
   `AdapterRegistry`/`DurablePool.restore(...)`/`CheckpointStore`, same
   on-disk paths only) re-ran the same plan. The checkpoint correctly
   restored `20260708` from disk; the run fetched only the next 5
   genuinely new real dates (`20260709` through `20260715`), advancing
   the checkpoint to `20260715` and growing the pool from 5 to 10
   observations — real restart-survival, real incremental resume,
   against a real external source, not a mock.
4. **Duplicate/dedup proof against real content**: the checkpoint was
   deliberately rewound to `20260630` and the same plan re-executed
   against the real network a third time. All 5 previously-acquired real
   documents were re-fetched, re-hashed, and correctly reported
   `is_new=False` / `outcome=duplicate` — the pool stayed at 10
   observations (no duplication), entirely via Phase A/B's existing
   content-addressed identity, with zero source-specific dedup code.
5. **The double-space company-name bug** (pre-implementation report item
   8) was discovered during step 1 of this exact live run, fixed, and
   re-verified against 9,843 real rows across two separate real days
   before the demonstration above was repeated to completion.

Total real HTTP requests made across the entire live demonstration: on
the order of 15–20 (one `index.json` listing fetch per run, one
`company.*.idx` fetch per newly-requested date) — well within SEC's
stated fair-use expectations, each carrying the documented `User-Agent`.

---

## Post-implementation report

### 1. Files changed

```
daf/adapters/edgar_daily_index.py                          (new)
daf/extractors/edgar_daily_index.py                        (new)
daf/orchestration/bindings.py                               (extended: edgar_daily_index_binding, _advance_edgar_position)
daf/catalog/cli.py                                           (fixed: execute-plan now goes through daf.scheduling.runner.execute_plan
                                                               + CheckpointStore instead of calling AcquisitionOrchestrator.run
                                                               directly -- a pre-existing Phase D gap that silently meant the CLI
                                                               never read or advanced checkpoints at all; registered
                                                               edgar_daily_index_binding in _default_adapters)
tests/fixtures/edgar_index_listing_synthetic.json            (new, synthetic)
tests/fixtures/edgar_daily_index_synthetic_20260701.idx      (new, synthetic)
tests/fixtures/edgar_daily_index_synthetic_20260702.idx      (new, synthetic)
tests/fixtures/edgar_daily_index_synthetic_20260703.idx      (new, synthetic)
tests/fixtures/edgar_daily_index_synthetic_double_space_name.idx  (new, synthetic -- regression fixture for the live-discovered bug)
tests/fixtures/edgar_daily_index_malformed.idx               (new, synthetic)
tests/test_edgar_daily_index_adapter.py                       (new, 12 tests)
tests/test_edgar_daily_index_extractor.py                     (new, 5 tests)
tests/test_edgar_daily_index_integration.py                   (new, 13 tests)
docs/DAF_EDGAR_ADAPTER.md                                     (this file)
```

### 2. Checkpoint abstraction

No new abstraction. `_advance_edgar_position` is this phase's one
`AdapterBinding.advance_position` implementation: `position` for EDGAR is
simply the maximum `YYYYMMDD` locator string acquired (string comparison
is correct for zero-padded, fixed-width dates), taken together with the
previous position so a no-op run never regresses it.

### 3. Snapshot/incremental semantics demonstrated

The EDGAR source is registered `capabilities=("incremental",)` and every
test/demonstration plan uses `mode="incremental"`. A snapshot-mode plan
against this same adapter would still work correctly (it would simply
never inject `since`, re-fetching up to `max_dates_per_fetch` dates from
the beginning every run, deduplicated by existing identity) but was not
the point of this phase — Phase F already proved SNAPSHOT/INCREMENTAL
sufficiency; this phase proves INCREMENTAL against a real source.

### 4. Scheduler behavior

`daf.scheduling.runner.execute_plan` and `daf.scheduling.due` are used
completely unmodified. The only DAF-core change this phase made anywhere
was the CLI wiring fix described above (item 1) — a bug found, not new
scheduling behavior.

### 5. Persistence ordering

`test_persistence_failure_leaves_checkpoint_unadvanced` and
`test_transient_http_failure_is_reported_as_source_unavailable` /
`test_adapter_side_failure_is_reported_as_adapter_failure` /
`test_malformed_response_is_an_extraction_failure_not_silently_admitted`
each assert `checkpoints.get("edgar-plan") is None` after their
respective failure — the same ordering invariant Phase E established,
now proven for a real-shaped external adapter's own failure modes
(network failure, adapter-side failure, extraction failure,
persistence-store failure), not just synthetic local ones.

### 6. Restart demonstration

`test_restart_resumes_incremental_acquisition_correctly` (synthetic,
CI-safe) plus the manual live demonstration above (real network) both
prove: process A acquires N days and exits; process B — brand-new
registries, `DurablePool.restore`, `CheckpointStore`, same on-disk paths
only — resumes and fetches only the genuinely new days.

### 7. Failure behavior

Four categories tested end-to-end for this source specifically:
`SOURCE_UNAVAILABLE` (raw `OSError` subclass reaching the adapter
boundary), `ADAPTER_FAILURE` (an `EdgarFetchError` — no index files
listed), `EXTRACTION_FAILURE` (a malformed `.idx` file body),
`PERSISTENCE_FAILURE` (a broken evidence store). All four leave the
checkpoint untouched.

### 8. Duplicate behavior

`test_repeated_acquisition_is_reported_as_duplicate` (synthetic) and the
live demonstration's step 4 (real, previously-acquired content
deliberately re-fetched via a rewound checkpoint) both confirm
`outcome=duplicate`, zero pool growth — entirely via Phase A/B's
existing content-addressed identity.

### 9. One-door proof

`test_one_door_invariant_for_edgar_modules` (AST-level, both new
modules): no import of `evidence.admission`, `materials`, `experiment`,
`workbench`, `core`, `morpho`, `backends`, or `runtime`; no direct
`.put_*` call anywhere in `daf/adapters/edgar_daily_index.py` or
`daf/extractors/edgar_daily_index.py`.

### 10. Full test results

`pytest tests/` (DAF, all six phases): **169 passed** — 139 (Phases
A–F) + 30 new (Phase G: 12 adapter + 5 extractor + 13 integration).

Full vendored State-Space suite: **1273 passed, 0 failed, 0 files
modified.**

### 11. ruff / mypy

`mypy daf/` → **Success: no issues found in 35 source files.**

`ruff check` on this phase's new/changed files specifically (after
fixing this phase's own two genuine findings — an unused import and a
missing explicit `check=` on a `subprocess.run` call, both in the new
integration test file): zero correctness findings. The remaining ruff
findings across the wider repository (this phase's files included) are
exclusively pre-existing style-modernization suggestions (`UP006`/`UP035`/
`UP045`/`UP037` — `typing.Optional`/`Tuple`/`Dict` vs. PEP 604/585 syntax)
consistent with the typing style every prior phase (A–F) already used
throughout the codebase; this phase matched that established convention
rather than introducing a one-off inconsistency, and did not undertake an
unrelated repo-wide typing-syntax refactor.

### 12. Known limitations

- `max_dates_per_fetch` (default 5) means a plan that has fallen far
  behind catches up gradually across several `execute_plan` calls rather
  than in one — a deliberate, documented pacing choice, not an
  oversight.
- The right-anchored extraction regex assumes Form Type, CIK, and Date
  Filed never themselves contain whitespace, and that Date Filed is
  always exactly 8 digits. Both are true of every real row inspected
  (9,843 rows, two separate real days) and of SEC's own documented
  format, but a future, genuinely different EDGAR index variant could
  violate this — the extractor raises `EdgarDailyIndexExtractionError`
  rather than silently misparsing if a row doesn't match.
- `EDGAR_USER_AGENT` is a placeholder contact string
  (`contact@example.com`); a real production deployment would replace it
  with a real maintainer contact, per SEC's fair-use policy — this is a
  deployment-configuration detail, not an architectural one.
- This phase deliberately touches only the daily-index feed's directory
  listing and per-day filing list — it does not fetch or parse the
  filings' own document contents (the `.txt`/`.htm` bodies each
  `file_name` points to). That would be a second, separate source/adapter
  decision, out of this phase's stated scope.
- What is source-specific vs. DAF-general: everything in
  `daf/adapters/edgar_daily_index.py` and
  `daf/extractors/edgar_daily_index.py` (URL shape, retry/backoff
  policy, User-Agent, the fixed-format text parsing, date-string
  checkpoint semantics) is EDGAR-specific. Everything it runs through —
  `RawDocument`/`Extractor`/`ExtractionCandidate`, `AdapterBinding`,
  `SourceDefinition`, `AcquisitionPlan`, `execute_plan`,
  `AcquisitionCheckpoint`/`CheckpointStore`, `DurablePool`/
  `ArtifactStore`, the operator CLI — is unmodified, domain-general DAF
  infrastructure already proven by Phases A–F.

### 13. Recommended Phase H

Per this task's own stop condition, this phase is complete: one real,
production-style external adapter, genuine incremental checkpoint resume
against a live source, responsible HTTP behavior, synthetic fixtures for
CI plus a real live demonstration (which caught and fixed a real parsing
bug), wired into the existing CLI with no new CLI surface. A natural
Phase H would either (a) add a second, genuinely different real source
(e.g. one requiring pagination tokens rather than date cursors, to stress
`position` opacity further) or (b) begin the FEP/information-gap-driven
`AcquisitionRequest` work this and every prior phase's reports have
flagged as the next real architectural frontier — both remain untouched
here, as does the separate Rust/zkVM/Morpho/CUDA execution plane and any
change to State-Space's own semantic core.
