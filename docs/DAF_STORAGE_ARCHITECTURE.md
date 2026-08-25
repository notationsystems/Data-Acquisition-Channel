# Phase J — DAF Storage and Indexing Architecture Reconnaissance

**Status:** documentation/reconnaissance only. No code was changed this
phase, per the task's own stop condition ("Do NOT implement the chosen
production storage architecture in Phase J"). Every claim below is
grounded in the actual `daf/storage`/`daf/catalog` source and the real
acquisition evidence Phases G–I produced against SEC EDGAR, the USGS
Earthquake Catalog, and NOAA CO-OPS — not a hypothetical workload.

---

## Pre-implementation report

**Current storage boundary.** Two genuinely different persistence
models coexist today, correctly kept separate:

1. **Evidence** (`daf/storage/filesystem_store.py`,
   `daf/storage/durable_pool.py`, `daf/storage/artifact_store.py`) —
   content-addressed, immutable-once-written, one JSON file per object,
   filename = the object's own `evidence.identity.content_hash` id.
   Unbounded growth (grows with every acquisition, forever).
2. **Catalog/control state** (`daf/catalog/source_catalog.py`,
   `plan_catalog.py`, `checkpoint.py`) — operator-declared, mutable,
   last-write-wins, one JSON file per `source_id`/`plan_id`. Bounded,
   low cardinality (grows with the number of *sources and plans an
   operator configures*, not with acquisition volume).

**Storage pain points** (all found in the existing code, not
speculated): (a) `DurablePool.restore`/`load_pool` eagerly load **every**
persisted object of **every** evidence category into memory on every
process start — the cost of any CLI invocation grows linearly with total
historical acquisition volume, forever; (b) `ArtifactStore.list_versions`
and `daf.catalog.history.known_versions` answer "what versions exist for
this artifact" by scanning **every** persisted `Document` and **every**
persisted `Record` — there is no index from `artifact_id` (or
`source_id`, or `locator`, or a time range) to the objects that satisfy
it; (c) vendored `scout.pipeline.run_scout` stores the same raw content
string **twice** per acquisition (once as `Document.raw_content`, once
as `Record.raw_content` — confirmed by reading `run_scout` directly:
both are built from the identical `raw_doc.content`), and today's
per-object-JSON-file model cannot deduplicate that, because `Document.id`
and `Record.id` are different composite hashes even when they wrap
identical bytes.

**Workload characteristics** (from real Phases G–I evidence, detailed in
full below): acquisition-unit sizes range from ~54 KB (one NOAA 3-day
window) to ~968 KB (one EDGAR daily index file); EDGAR/NOAA both
deliberately keep *many* underlying rows/readings inside *one* Document/
Record/Observation triple (extraction produces one `ExtractionCandidate`
per fetched artifact, not one per row) — a real, already-present design
property that keeps evidence-object cardinality proportional to
*acquisitions*, not to *underlying facts*. USGS is the exception: its
acquisition unit *is* the individual record, so its object cardinality
scales with real-world event count directly.

**Candidate architectures evaluated:** PostgreSQL, SQLite, DuckDB,
Parquet, Iceberg, and object storage (S3/MinIO-shaped) — see sections
16–20 below for the full evaluation against this project's actual
retrieval patterns (identity lookup, artifact-history lookup,
duplicate detection, incremental-position lookup, operator inspection),
not generic feature comparison.

**Recommended architecture** (summary; full reasoning in section 21):
keep the filesystem as the canonical, content-addressed raw-artifact
store (it is already correct — immutable, content-addressed,
deterministic, restart-safe); add a local, embedded **metadata index**
(SQLite) alongside it to eliminate the full-scan/full-reload pain
points above; treat DuckDB + Parquet as a **derived, rebuildable
analytical projection**, never the system of record; defer object
storage, Iceberg, and PostgreSQL to explicitly-named future triggers
that have not yet occurred. See section 21 for the full decision.

**Is any code change justified this phase?** **No.** The evidence
supports a clear recommendation, but implementing it is explicitly
Phase K's job per the task's stop condition. This phase is
reconnaissance and produces this document only.

---

## 1. Current storage architecture

### What is stored, where, how it is keyed

| Object | Module | Location | Key (filename) | Mutable? |
|---|---|---|---|---|
| `Source` | `evidence.types` | `<root>/evidence/sources/` | `Source.id` = `content_hash({kind, name})` | No |
| `Document` | `evidence.types` | `<root>/evidence/documents/` | `Document.id` = `content_hash({source_id, content_hash(raw_content), retrieval_method})` | No |
| `Record` | `evidence.types` | `<root>/evidence/records/` | `Record.id` = `content_hash({document_id, locator, raw_content})` | No |
| `Observation` | `evidence.types` | `<root>/evidence/observations/` | content-hash of `{record_ids, extraction_method, content}` | No |
| `Referent`/`ClaimedRelationship`/`DerivedValue`/`DerivedGrounding` | `evidence.types` | `<root>/evidence/{category}/` | content-hash, category-specific | No |
| `SourceDefinition` | `daf.orchestration.source_registry` | `<root>/sources/` | `source_id` (operator-chosen) | Yes |
| `AcquisitionPlan` | `daf.catalog.plan` | `<root>/plans/` | `plan_id` (operator-chosen) | Yes |
| `AcquisitionCheckpoint` | `daf.catalog.checkpoint` | `<root>/checkpoints/` | `plan_id` (operator-chosen) | Yes |

Every evidence category is written by `FilesystemEvidenceStore._write`:
JSON payload → temp file → `os.replace` (atomic on POSIX). A duplicate
write to an existing content-hash filename is a no-op that re-verifies
the *existing* file's identity rather than comparing payloads (this is
correct — see the module's own docstring — content re-acquired at a
different `retrieved_at` legitimately shares an id, since `retrieved_at`
is deliberately excluded from the hash).

### How it is retrieved

Two access shapes exist today, and only one of them is indexed:

- **Direct id lookup** (`get_document(id)`, `has_document(id)`) — O(1),
  a single filesystem path check/read. This is genuinely fine at any
  scale; it is how `evidence.admission` checks "does this id already
  exist" during acquisition, and it stays O(1) forever.
- **Everything else** (`all_documents()`, `all_records()`, ...,
  `ArtifactStore.list_versions()`, `daf.catalog.history.known_versions()`)
  — a full `Path.glob("*.json")` directory listing, followed by reading
  and JSON-parsing **every** matching file, **every single call**. There
  is no secondary index by `source_id`, `locator`, `artifact_id`, or any
  temporal field.

### How it is replayed

`DurablePool.restore(store)` / `load_pool(store)` (`daf/storage/durable_pool.py`)
call `_replay_into`, which invokes `all_sources()`, `all_documents()`,
`all_records()`, and all five remaining `all_*()` calls, in that
dependency order, loading **the entire historical corpus** into a fresh
in-memory `EvidencePool` before any new acquisition work happens. This
is not a hypothetical concern — it is exactly what `daf.catalog.cli`'s
`execute-plan` command does on every single invocation (see that
module's own docstring, written in Phase D and never revisited since):
"so this fresh process's in-memory pool actually reflects what earlier
CLI invocations already persisted."

### How it is indexed

It isn't — beyond the filesystem's own directory listing (implicitly
sorted by filename, i.e. by content-hash, which carries no useful
ordering). This is the single largest architectural gap this phase's
reconnaissance found.

### Immutable / mutable / derived

- **Immutable**: everything under `evidence/` (Phase A/B's own
  invariant, unchanged since Phase B, and correctly never violated by
  any of Phases C–I).
- **Mutable**: `sources/`, `plans/`, `checkpoints/` — small, operator-
  or-scheduler-owned, last-write-wins, and correctly modeled as such.
- **Derived, not stored**: `artifact_id` (`ArtifactStore.artifact_id`,
  a `content_hash({source_id, locator})` computed on demand, never
  persisted as its own field — Phase B/C's own explicit design choice,
  reaffirmed here as still correct); `content_hash_of(document)`
  (computed on demand); `known_versions`/`has_ever_been_acquired`
  (`daf/catalog/history.py`, thin derivations over `ArtifactStore`, no
  second store).

---

## 2–4. Real workload evidence: EDGAR, USGS, NOAA

All figures below are from Phases G–I's actual live demonstrations and
fixture measurements — not estimates.

### EDGAR (Phase G)

- Acquisition unit: one whole daily index **file**.
- Real size: **967,575 bytes** for 2026-07-01's real `company.20260701.idx`
  (confirmed live); a second real day (2026-07-15) contained 3,250 data
  rows against 2026-07-01's 6,593 — combined, **9,843 real filing rows
  investigated across two real days**.
- Object cardinality per acquisition: **1** `Document` + **1** `Record`
  + **1** `Observation` (the extractor returns exactly one
  `ExtractionCandidate` per daily file, with all 6,593 filings packed
  into that single `Observation.content["filings"]` list) — row count
  does **not** multiply evidence-object count. This is a deliberate,
  already-correct design property (Phase G's own extractor design),
  not something this phase needs to add.
- Update cadence: at most 1 new immutable file per business day, ever
  (SEC never revises a published day) — append-only, no revision
  storage burden.

### USGS (Phase H)

- Acquisition unit: one individual **event record**.
- Real size: a few KB per event-detail document (the `products` section
  of a real reviewed event, e.g. `us6000thj0`, observed live to be
  several times larger than a bare summary record, due to embedded
  origin/phase-data provenance).
- Object cardinality per acquisition: **1:1** with real-world events —
  unlike EDGAR/NOAA, USGS's acquisition unit *is* the identified
  record, so `Document`/`Record`/`Observation` counts scale directly
  with earthquake count, not with acquisition-batch count.
- Revision burden: confirmed live — the same `locator` (event id) can
  legitimately produce a **new** `Document`/`Record`/`Observation`
  triple (a new version) when magnitude/status is revised, while
  `artifact_id` stays stable. Every revision is a **new** set of
  objects, never an in-place update (correct, and already handled by
  the existing immutable-append model) — but each revision that never
  gets pruned adds permanently to on-disk volume.

### NOAA (Phase I)

- Acquisition unit: one bounded time **window**.
- Real size: **53,990 bytes** for one real 3-day, 6-minute-interval
  window (720 readings) at station 8454000.
- Object cardinality per acquisition: **1** `Document` + **1** `Record`
  + **1** `Observation` per window, holding up to 720 readings inside
  one `Observation.content["readings"]` list — same "many rows, one
  evidence-object triple" property as EDGAR.
- Revision burden: confirmed live and via fixture — the *same* window
  locator can be re-fetched with different bytes once NOAA's QC
  pipeline reprocesses readings from `"preliminary"` to `"verified"`;
  the deliberate trailing-safety-window catch-up (Phase F's idiom,
  first exercised live in Phase I) means this source's adapter
  *intentionally* re-requests overlapping windows on every run, each a
  new, independently-persisted artifact.

### Cross-source synthesis

The "many rows packed into one Observation" property (EDGAR, NOAA) vs.
"one row is one acquisition unit" property (USGS) is the single most
important workload distinction for storage planning: it means
evidence-object *file count* growth is driven by **acquisition
frequency** for EDGAR/NOAA-shaped sources, but by **real-world event
rate** for USGS-shaped sources. A storage architecture must handle both
without assuming either.

---

## 3 (deliverable item 5). Storage object model

| Object | Immutable? | Identity | Lookup key(s) needed | Temporal attrs | Provenance attrs | Cardinality driver | Query patterns |
|---|---|---|---|---|---|---|---|
| Raw Artifact (= `Document.raw_content`, today inlined) | Yes | `content_hash(raw_content)` | content hash | none intrinsic | none intrinsic | acquisitions | fetch-by-hash, existence check |
| Artifact Version (= `Document`) | Yes | `Document.id` (`version_id`) | `version_id`; `(source_id, locator)` grouping | `retrieved_at` | `source_id`, `retrieval_method` | acquisitions | "get this exact version"; "all versions of X" |
| Content Hash | Yes | itself | itself | none | none | ≤ versions | dedup check |
| Extracted Record (= `Record`) | Yes | `Record.id` | `document_id`, `locator` | inherited from Document | `document_id` | 1:1 with Document today | "what locator does this Document have" |
| Observation | Yes | content-hash of `{record_ids, extraction_method, content}` | `record_ids`, `extraction_method` | `extracted_at` (epistemic, excluded from identity) | `record_ids`, `extraction_method`, `confidence` | acquisitions (EDGAR/NOAA) or events (USGS) | "what was extracted from record R" |
| Source | Yes | `content_hash({kind, name})` | `kind`+`name` | none | none | tiny (dozens, not millions) | "resolve this source's id" |
| Acquisition Plan | Yes (per version)/mutable (as a named entity) | `plan_id` (operator-chosen, not content-hash) | `plan_id` | none intrinsic | `source_id` | tiny (operator-configured) | "get plan X"; "list all plans" |
| Checkpoint | Mutable | `plan_id` | `plan_id` | `updated_at`, opaque `position` | `source_id` | tiny (1 per plan) | "get current position for plan X" |

No new ontology term was introduced to build this table — every row
names an object that already exists in `evidence.types` or
`daf.catalog`/`daf.orchestration`. This matches the task's own
instruction ("Do not create new ontology terms unless required") and
this phase's own finding: nothing about three real, structurally
different sources required a new identity concept, only better
*indexing* of the identities that already exist.

---

## 4 (deliverable item 6). Raw bytes vs. metadata

**Today these are not separated**, and that is the single most
concrete, code-confirmed inefficiency this phase found:
`evidence.types.Document.raw_content` (vendored, cannot be changed) and
`evidence.types.Record.raw_content` (also vendored) both store the
**complete raw acquired bytes inline**, as a JSON string field, inside
their respective per-object files. `scout.pipeline.run_scout` — the
one, unmodified, one-door admission path every DAF adapter goes
through — literally constructs both from the identical
`raw_doc.content` string (confirmed by reading `run_scout` directly:
`make_document(..., raw_content=raw_doc.content, ...)` immediately
followed by `make_record(..., raw_content=raw_doc.content)`). For every
source built so far (EDGAR, USGS, NOAA all produce exactly one `Record`
per `Document`), **this means the raw bytes are physically written to
disk twice per acquisition** — once under `documents/{Document.id}.json`,
once under `records/{Record.id}.json` — because `Document.id` and
`Record.id` are different composite hashes even though they wrap
identical content.

This is a vendored-code constraint, not a DAF design choice, and Phase J
does not propose touching `evidence.types`/`scout.pipeline` to fix it
(that would violate the standing "never modify vendored SCOUT" rule).
What a **storage-layer** fix can do instead: separate raw bytes from
metadata at the persistence layer. A metadata record (`Document`,
`Record`) would store a *reference* — `content_hash(raw_content)` — and
a single content-addressed blob store would hold the bytes exactly
once, regardless of how many metadata objects point to that hash. This
is evaluated concretely in section 5.

**Recommendation**: separate raw bytes from metadata at the storage
layer (not the evidence-type layer). This is justified by measured
evidence (real 2x duplication on every single acquisition observed in
Phases G–I), not speculation.

---

## 5 (deliverable item 6, continued). Content-addressed object storage

The existing model — `content_hash → bytes`, filesystem path =
`{category}/{id}.json` — already **is** a content-addressed object
store, just not yet factored as one with a stable interface, and not
yet separated from metadata (section 4). It already has every property
object storage needs: content identity (the filename *is* the hash),
deterministic retrieval (same hash always resolves to the same bytes),
immutability (writes are idempotent-or-reject, never overwrite), and
replayability (Phase B/G/H/I's restart demonstrations all rely on
exactly this).

**The required abstract interface, if this evolves**, is small and
already implicit in `FilesystemEvidenceStore`'s existing per-category
`put`/`get`/`has`/`all` shape:

```
put(content_hash, bytes) -> None      # idempotent; a matching existing hash is a no-op
get(content_hash) -> bytes            # raises if absent
has(content_hash) -> bool
```

A filesystem implementation of this (keyed purely by
`content_hash(raw_content)`, one file per unique content — not per
`Document`/`Record`) would, as a direct side effect, fix section 4's 2x
duplication: `Document` and `Record` would each store a reference to
the same blob instead of a second copy of the bytes. An S3/MinIO
implementation of the identical three-method interface would be a
drop-in swap requiring zero changes above the interface boundary — the
same "adapter/binding is the seam, core stays domain/backend-
independent" discipline every acquisition phase (C through I) already
established for source adapters, applied here to storage backends
instead. **This phase proposes the interface as a documented target,
consistent with the task's explicit instruction not to implement it
yet — no code was written this phase.**

---

## 6 (deliverable item 7). Metadata index

Actual retrieval patterns this project has needed, drawn from real code
(`ArtifactStore`, `daf.catalog.history`, `daf.scheduling.runner`,
every adapter binding's `advance_position`, and every CLI command),
not a speculative field list:

| Pattern | Used by | Currently | Needed index |
|---|---|---|---|
| id → object | `get_document`, `has_document`, admission dedup check | O(1), already fine | none needed |
| `artifact_id` → all `version_id`s | `ArtifactStore.list_versions`, `daf.catalog.history.known_versions` | O(n) full scan of `documents/` + `records/` | index on `(source_id, locator)` |
| `source_id` → all documents from that source | operator inspection (not yet built, but implied by every source-scoped question an operator would ask) | not implemented (would require a full scan) | index on `source_id` |
| `retrieved_at` range → documents | operator inspection, "what did we acquire yesterday" | not implemented | index on `retrieved_at` |
| `content_hash` → documents sharing it | dedup auditing, "has this exact content ever appeared under a different locator" | not implemented (would require a full scan) | index on `content_hash` |
| entire corpus → in-memory pool | `DurablePool.restore`/`load_pool`, every checkpoint-aware CLI invocation | full eager load, every call | should become a lazy/indexed load, not a full materialize |
| `plan_id` → checkpoint | `daf.scheduling.runner.execute_plan` | O(1), already fine (one file per plan) | none needed |

Per the task's own instruction, this list is **not** "index every
field automatically" — it is the specific set of lookups the existing,
working code either already performs by brute-force scan or would
need to perform to answer a question this project's own phases have
already asked (operator inspection was named explicitly in Phase D's
CLI design intent). `retrieved_at`, `source_id`, `(source_id, locator)`,
and `content_hash` are the four fields with a demonstrated real need;
nothing else is proposed for indexing at this time.

---

## 7 (deliverable items 8–9, 16–20). Relational vs. columnar vs. object storage

Evaluated against this project's actual retrieval patterns (section 6),
not general popularity.

### PostgreSQL

- Identity/metadata lookup: excellent (proper indexes, real query
  planner).
- Time-range queries: excellent.
- Analytical scans: adequate for moderate scale, not its strength at
  very large scale.
- Append behavior: excellent; row-level updates: excellent (not needed
  here — evidence is append-only by design).
- Concurrency: excellent, multi-writer, real transactions.
- Local development: **requires a running server process** — this is
  the disqualifying property for this phase's "local-first" requirement
  (section 16) as the *default* development story, though it remains
  the right choice for a future *shared, multi-process* deployment.
- Restart/recovery: excellent (WAL, proven).
- Scaling: excellent, well past this project's currently-observed
  workload.
- Operational complexity: real (a server to run, back up, upgrade) —
  disproportionate to today's actual data volume (section 15).
- **Verdict: not recommended for local/default use now; recommended as
  the metadata index's natural upgrade path if/when a shared, multi-
  writer, single-node-production deployment is actually needed** (see
  section 21's explicit trigger condition).

### SQLite

- Identity/metadata lookup: excellent (real indexes), embedded, zero
  server.
- Time-range queries: excellent for this project's realistic per-source
  volumes (thousands to low millions of rows).
- Analytical scans: adequate for moderate scale; not its strength at
  large multi-source aggregate scale.
- Append behavior: excellent for a single writer (matches the DAF's
  actual concurrency model today — one `execute_plan` call at a time
  per plan, per every phase G–I test and live demo).
- Concurrency: single-writer, multi-reader (WAL mode) — matches this
  project's actual usage pattern; would become a real constraint only
  under genuine concurrent multi-process writers, which nothing in
  Phases A–I has needed or demonstrated.
- Local development: **zero setup, ships with Python, one file** —
  exactly the local-first requirement (section 16).
- Restart/recovery: excellent, transactional, battle-tested.
- Scaling: fine up to real single-node data volumes (see section 15);
  not a distributed solution, deliberately.
- Operational complexity: effectively none.
- **Verdict: recommended as the metadata index (L1) starting point.**

### DuckDB

- Identity/metadata lookup: not its purpose (OLAP, not point-lookup/
  OLTP optimized) — would be the wrong tool for admission-time
  dedup checks or checkpoint reads.
- Analytical scans: excellent — its actual strength, and directly
  relevant to a future "how many EDGAR filings by form type per
  month across a year of acquisition" kind of question this project has
  not yet needed to answer but plausibly will.
- Reads Parquet natively and efficiently; embedded, zero server, local-
  first.
- Concurrency: single-process-oriented, fine for a derived/rebuildable
  analytical projection that is not the system of record.
- **Verdict: recommended for the analytical projection layer (L4)
  only** — never for identity-critical lookups, never as the metadata
  system of record.

### Parquet

- Not a database — a columnar file format. Excellent for large
  analytical scans over historical extracted-record content (e.g. a
  year of NOAA readings across all stations), poor for point lookups
  or admission-time identity checks.
- **Verdict: recommended as the format for L4 analytical exports**,
  generated periodically from the canonical evidence store — a derived,
  rebuildable projection, never primary storage, exactly per the task's
  section 8 warning that storage layers must not become competing
  semantic authorities.

### Iceberg

- Solves problems this project does not have yet: multi-engine
  transactional access to huge, partitioned, schema-evolving tables
  over object storage at multi-node scale.
- At this project's actual current and near-term projected scale
  (section 15), Iceberg's operational overhead (catalog service,
  compaction, multi-engine coordination) has no workload to justify it.
- **Verdict: explicitly not recommended now.** Revisit only if/when
  L4 analytical projections genuinely outgrow a single DuckDB/Parquet
  node AND require multi-engine concurrent access — neither condition
  holds today.

### Object storage (S3/MinIO)

- The natural evolution target for L0 raw blobs (section 5) once local
  disk stops being the right place for them (multi-machine acquisition,
  durability beyond one disk, sharing raw artifacts across machines).
- Not needed today: Phases G–I's entire real, live-acquired corpus
  across three sources totals a few megabytes; local disk is not a
  constraint yet (see section 15).
- **Verdict: not implemented now; the recommended `BlobStore` interface
  (section 5) is designed so this becomes a drop-in swap when actually
  needed, never a prerequisite.**

### Distinguishing canonical / analytical / search-index storage

Per the task's explicit instruction not to collapse these: **canonical**
storage (L0 blobs + L1 metadata) is the only system of record and the
only thing `evidence.admission`/`DurablePool` ever write through.
**Analytical projection** (L4, DuckDB/Parquet) is derived, rebuildable
from canonical storage at any time, and never accepts a write that
didn't already go through the one-door SCOUT admission path. **Search/
index projections** (not built this phase — see section 14) would be a
third, equally derived category. Conflating any of these would let a
downstream projection silently become a second source of truth for
questions the evidence layer is supposed to answer authoritatively —
exactly the risk section 8 of the task warns against.

---

## 8. Storage layers

```
L0  raw immutable artifacts        content-addressed bytes (today: inlined in Document/Record JSON;
                                    recommended: a real blob store, keyed by content_hash alone)
L1  artifact/version metadata      Document/Record metadata + (source_id, locator) grouping index
                                    (today: filesystem, unindexed; recommended: SQLite alongside the
                                    filesystem, or eventually replacing per-object JSON files for metadata)
L2  extracted records              Record (today folded into L1 -- Record IS metadata-shaped, and its
                                    raw_content duplication is exactly section 4's finding)
L3  observations/evidence          Observation and the rest of evidence.types -- AUTHORITATIVE, owned by
                                    EvidencePool/evidence.admission, never touched by any storage-layer change
L4  analytical projections         DuckDB/Parquet, derived and rebuildable, never authoritative
```

L3 remains exactly what Phase A established it as: the authoritative
home of scientific/semantic evidence, owned by the vendored,
unmodified `EvidencePool`/`evidence.admission`. Nothing in this phase's
recommendation touches L3 or proposes a competing semantic authority —
L0/L1/L4 are storage/indexing/projection concerns *underneath and
alongside* L3, never replacing what SCOUT's admission gate already
decides.

---

## 9. Replay

| Replay target | Current mechanism | Sufficient? |
|---|---|---|
| One artifact version | `ArtifactStore.get(artifact_id, version_id)` | Yes — O(1), correct today |
| All versions of one artifact | `ArtifactStore.list_versions` | Correct, but O(n) full scan — the metadata index (L1) fixes the *performance*, not the *correctness*, of this |
| Replay a whole source | Would require scanning `all_documents()` filtered by `source_id` | Not implemented; needs the L1 `source_id` index from section 6 |
| Replay an acquisition plan | `daf.scheduling.due`/`daf.scheduling.runner` re-executing from a checkpoint | Correct and already deterministic (Phases E, G, H, I all prove this live) |
| Replay a time range | Would require scanning `all_documents()` filtered by `retrieved_at` | Not implemented; needs the L1 `retrieved_at` index |

Determinism is already structurally guaranteed by the existing content-
addressed model (same bytes always produce the same `Document.id`); the
gap is purely *retrieval efficiency* for the "all versions"/"whole
source"/"time range" cases, not correctness. Per the task's explicit
instruction, this is **not** an execution ledger — nothing here
proposes recording *how* an acquisition ran, only indexing *what* was
acquired, exactly the same boundary Phase D/E already drew between
"acquisition progress" (`AcquisitionCheckpoint`) and "scientific
provenance" (out of scope, owned by State-Space).

---

## 10. Version discovery (USGS as evidence)

Using Phase H's real revision proof
(`test_incremental_second_run_acquires_only_the_revised_event`) as the
concrete case: "what versions exist for event `us6000ti8i`" is
currently answered by `ArtifactStore.list_versions`, which scans **all**
persisted documents and records to find the ones whose
`(source_id, locator)` hashes to the given `artifact_id`. At USGS's real
per-event cardinality (section 2), this becomes the single most
scale-sensitive query in the current architecture, because — unlike
EDGAR/NOAA — USGS's object count grows with real-world event count, not
just acquisition-batch count.

"What is the latest version" and "which content hashes have been
observed" are correctly kept conceptually distinct today (Phase H's own
design, reaffirmed here): `list_versions` returns version ids ordered by
`(retrieved_at, id)` — **acquisition order, not necessarily any
scientific notion of "latest correct value"** (Phase H's own docstring
already warns of exactly this: latest ≠ newest). This phase's
recommendation preserves that distinction exactly — the L1 metadata
index adds a `(source_id, locator) → [version_ids ordered by
retrieved_at]` lookup, it does not add a "canonical latest value"
concept, which would overstep into scientific-semantics territory L3
already owns.

---

## 11. Temporal indexing (NOAA as evidence)

NOAA's real data already demonstrates that these are genuinely
different timestamps, never safe to collapse (confirmed live, Phase I):

- **source (event) time**: each reading's own `t` field inside
  `Observation.content["readings"]` — the moment the sensor measured
  something. Not indexed at the Document/Record level today (it lives
  inside extracted content, one window holding hundreds of these).
- **window begin/end**: encoded in the `Record.locator` itself
  (`"{station}:{product}:{begin}:{end}"`) — this IS what the current
  incremental checkpoint indexes by, informally, via string comparison
  inside the adapter binding.
- **acquisition time**: `Document.retrieved_at` — when the DAF actually
  fetched it, caller-supplied, never wall-clock.
- **revision time**: not directly exposed by NOAA as a timestamp (only
  the coarser `q` preliminary/verified flag) — documented in Phase I as
  an honest limitation, not invented.

**What should be indexed, and why**: `retrieved_at` (acquisition time)
and the window's begin/end (derivable from `locator`) are the two with
demonstrated real query value — "what did we acquire and when" and
"what source-time range does this artifact cover" are both real
operator/replay questions. Per-reading `event_time` should **not** be
indexed at the metadata layer — it lives inside `Observation.content`,
which is L3 (evidence), not L1 (metadata); promoting it to an indexed
metadata field would blur exactly the boundary section 8 warns against.

---

## 12. Deduplication

Current behavior, verified across Phases G–I's actual tests and live
demonstrations:

- **Identical content, same locator, re-acquired**: `Document.id`
  matches an existing id → `FilesystemEvidenceStore._write` re-verifies
  the existing file and no-ops → orchestrator reports `is_new=False` →
  `AcquisitionOutcome.DUPLICATE` if that's true of every artifact in the
  run. Zero duplication, verified live for all three sources.
- **Changed content, same locator**: new `Document.id` (content hash
  differs) → new `Document`/`Record`/`Observation` triple persisted,
  same `artifact_id` (Phase H's and Phase I's marquee proofs). Correct,
  and exactly the "new version, same artifact" behavior the task
  expects.
- **Overlapping acquisition windows** (NOAA's trailing-safety-window
  idiom): two *different* locators (different begin/end pairs) that
  happen to cover some of the same underlying days → two independent,
  both-legitimate artifacts, not deduplicated against each other,
  because they are genuinely different acquisition units (Phase I,
  confirmed both synthetically and live).

**No second deduplication mechanism is proposed.** The one gap this
phase's evidence supports fixing is *performance*, not *correctness*: at
larger scale, the existing "check if this id already exists" dedup path
remains O(1) (direct filesystem path check), so **content-addressed
deduplication itself remains sufficient and correctly designed at any
projected scale** — only the *secondary* queries (list all versions,
find by content hash across the whole corpus) need the L1 index from
section 6.

---

## 13. Partitioning

Only relevant to the analytical projection layer (L4), which is not
built this phase — evaluated here for the future Phase K/L decision,
per the task's instruction to determine the smallest useful strategy
from real workload patterns, not partition speculatively.

From the real Phase G–I workload shapes: `source_id` is the most useful
partition key (EDGAR/USGS/NOAA are already naturally disjoint,
independently-queried collections; "how many EDGAR filings this month"
never needs to scan NOAA's partition). A secondary partition by
acquisition date (`retrieved_at`, truncated to day or month) matches
every adapter's own natural batching (EDGAR: daily; NOAA: multi-day
windows; USGS: revision-driven, less date-aligned but still
acquisition-time-partitionable). **Domain and artifact-type
partitioning are not separately justified by current evidence** — with
only three sources, `source_id` already fully captures the domain/type
distinction; adding a second, redundant partition dimension this early
would be partitioning "merely because it's possible," which the task
explicitly warns against.

---

## 14. Search / graph / vector boundary

Explicitly out of scope for implementation this phase (and for the DAF
generally, per every prior phase's own repeated boundary statement).
Storage (L0/L1), retrieval (the `BlobStore`/metadata-index interfaces
from sections 5–6), and any future search/graph/vector projection are
three different concerns:

- **Storage**: canonical, content-addressed, immutable — this phase's
  actual subject.
- **Retrieval**: indexed lookup over storage's metadata — this phase's
  L1 recommendation.
- **Search/graph/vector**: hypothetical future consumers that would
  **read from** L1/L4 to build their own derived index (a GraphRAG
  layer, a vector index over `Observation.content`, a full-text search
  engine over raw artifacts) — none of which this phase builds, and
  none of which may ever become the raw-artifact authority. This is the
  same non-goal every phase since Phase F has named explicitly (GraphRAG,
  vector search, search clusters), reaffirmed here at the storage-
  architecture level specifically: the moment a search/graph/vector
  projection starts being queried as ground truth instead of the L0/L1
  canonical store, the one-door invariant (Phase A onward) has
  effectively been bypassed one layer up, and that must not happen.

---

## 15. Industrial scale question

Order-of-magnitude estimates, grounded in Phases G–I's real per-artifact
sizes (sections 2–4) times each source's own real, documented
publication cadence — not a hypothetical workload:

| Source class | Real basis | Artifacts/day | Bytes/day (raw) | Versions/day | Records/day (rows inside artifacts) |
|---|---|---|---|---|---|
| EDGAR-shaped (publication index) | 967 KB/day, ~6,600 filings/day, 1 file/business day | ~1 | ~1 MB | ~1 (never revised) | ~thousands |
| USGS-shaped (identified mutable records, M4.5+ scope like the live demo) | a few KB/event, ~10–50 significant events/day worldwide | ~10–50 | tens of KB to low hundreds of KB | + occasional revisions of older events | 1:1 with artifacts (no packing) |
| NOAA-shaped (bounded sensor windows) | 54 KB/3-day window/station, ~200 real active water-level stations | ~200 (if polled ~daily) | ~10 MB | + trailing-window re-verification (deliberate ~1.5x overlap by design) | ~hundreds of thousands (readings, packed into hundreds of Observations) |

**Combined, a DAF instance running all three of these source *classes*
continuously would plausibly acquire on the order of 10–20 MB/day and a
few hundred new evidence-object triples/day** — i.e., a few gigabytes
and roughly a hundred thousand small JSON files **per year**, before
even considering the 2x raw-content duplication from section 4 (which
would roughly double the bytes figure, not the file count).

**This is not yet a scale where filesystem storage "stops being
appropriate."** A few GB/year and low hundreds of thousands of files/year
is comfortably within what a local filesystem and an embedded SQLite
index handle well — the actual pain measured in this phase (sections 1,
6, 9, 10) is **algorithmic** (full scans, full eager reloads), not
**volumetric**. Fixing the algorithmic problem (add an index) buys
significant headroom before volume itself becomes the limiting factor.
The clearest future trigger for reconsidering local disk specifically:
adding a USGS-shaped source at "all magnitudes, not just significant"
scope (potentially thousands of events/day per such source) sustained
across many such sources simultaneously — at that point, file-count
growth (not byte volume) would be the first real constraint, favoring
the L1 index (and eventually consolidating small files into batched
blob storage) over adding more raw disk.

---

## 16. Local-first requirement

Every recommendation in this document runs on a laptop with no server
process, no cloud account, and no cluster: the filesystem (already
true), SQLite (embedded, ships with Python), and DuckDB (embedded, zero
server) all satisfy this directly. PostgreSQL, object storage, and
Iceberg are explicitly deferred, not because they are bad technology,
but because none of them are required by evidence gathered so far, and
introducing any of them now would violate this exact requirement for
every contributor who just wants to `git clone` and run the existing
test suite (as this and every prior phase's validation step has done,
zero external services, every time). Any future distributed backend
must implement the same `BlobStore`/metadata-index **contracts**
proposed in sections 5–6 — never become a prerequisite for running the
DAF locally, exactly per the task's own instruction.

---

## 17. Storage contract

**Compared against the existing `ArtifactStore` first**, per the task's
explicit instruction not to blindly create a new interface:
`ArtifactStore` already provides `put`, `get`, `exists`, `list_versions`,
plus the static `artifact_id`/`content_hash_of` derivations —
essentially every operation the task's own candidate list names
(`put_artifact`, `get_artifact`, `has_artifact` ≈ `exists`,
`list_versions`, `get_version` ≈ `get`, `find_by_content_hash` ≈
`content_hash_of` plus a lookup that does not exist yet). **The
interface shape is already sufficient.** What is missing is not a new
method signature but a faster *implementation* of the methods that
currently full-scan (`list_versions`, and the not-yet-built
`find_by_content_hash`/`list_source_artifacts`) — i.e., the L1 index
from section 6, sitting *behind* the existing `ArtifactStore` interface,
not replacing it.

**Smallest proposed extension** (for Phase K to evaluate, not
implemented here): two additional read methods on `ArtifactStore` —
`find_by_content_hash(content_hash) -> Tuple[str, ...]` (version ids)
and `list_source_artifacts(source_id) -> Tuple[str, ...]` (artifact
ids) — both currently impossible to answer without a full scan, both
with a demonstrated real use (dedup auditing; operator inspection,
respectively), both implementable behind the existing interface without
changing any of `ArtifactStore`'s current call sites in
`daf.catalog.history` or the CLI.

`replay` is deliberately **not** proposed as a new interface method:
every phase's own replay demonstrations (restart-resume in G, H, I) are
already expressed correctly as "reconstruct via `DurablePool.restore`
plus re-running `execute_plan` from a checkpoint" — adding a distinct
`replay()` primitive would risk exactly the "execution ledger" the task
explicitly says this is not.

---

## 18. Object storage / database decision — explicit recommendation

| Deployment target | Recommendation |
|---|---|
| **Development / local** | Filesystem for raw bytes (as today, evolving toward the `BlobStore` interface from section 5 to fix section 4's 2x duplication) + SQLite for the L1 metadata index (section 6) — zero new services, zero new operational surface, fixes every measured pain point (sections 1, 9, 10) at this project's actual real scale (section 15). |
| **Single-node production** | The same architecture — SQLite's single-writer/multi-reader model matches the DAF's actual concurrency pattern (one `execute_plan` per plan at a time) observed in every phase to date. Upgrade the metadata index to PostgreSQL only if/when genuine concurrent multi-process writers are actually needed (a real, nameable trigger, not a default). |
| **Future distributed deployment** | Swap the `BlobStore` filesystem implementation for an S3/MinIO-compatible one behind the same three-method interface (section 5); swap the metadata index for PostgreSQL behind the same `ArtifactStore`-shaped interface (section 17) if multi-node write concurrency is real. Add DuckDB/Parquet L4 analytical projections, rebuilt from L0/L1, independently of either swap. Iceberg only if L4 itself outgrows a single DuckDB node under genuine multi-engine concurrent access — not before. |

This is presented as a recommendation, not a foregone hypothesis: it
was derived from section 15's real scale estimate (still comfortably
single-node), section 6's real query-pattern list (fully answerable by
an indexed embedded database), and section 4's real, measured
duplication (fixable by a blob-store abstraction, not a database
migration).

---

## 19. Explicit non-recommendations

Per the task's own non-goals list, none of the following are
recommended for implementation at this time, and none were touched this
phase: Kafka, Iceberg, MinIO, S3 integration, PostgreSQL migration,
DuckDB migration, a Parquet pipeline, GraphRAG, a vector database, a
search cluster, a distributed scheduler, a distributed crawler,
State-Space integration, FEP, information gain, active learning,
Morpho, CUDA, zkVM, execution provenance. Each has a named, concrete
future trigger condition in the sections above (never "eventually, for
scale" as a vague justification) — the point of naming them is so a
future phase does not reach for one prematurely, exactly as Phases F–I
have already repeatedly declined to do for acquisition-side
infrastructure.

---

## 20. Proposed Phase K

Implement the smallest storage evolution this report actually justifies,
in this order (per the task's own framing: "Phase K will implement the
smallest storage evolution justified by this report"):

1. **`BlobStore` interface + filesystem implementation** (section 5):
   a real content-addressed blob store keyed purely by
   `content_hash(raw_content)`, fixing section 4's measured 2x
   duplication — `Document`/`Record` metadata would reference the blob
   by hash rather than each inlining a copy. This is the highest-value,
   lowest-risk change (pure storage-layer refactor, zero change to
   `evidence.types`/`scout.pipeline`, zero change to any adapter).
2. **SQLite-backed L1 metadata index** (section 6) sitting behind the
   existing `ArtifactStore` interface, populated incrementally on every
   `put` rather than requiring a full corpus reload — directly fixing
   the `DurablePool.restore`/`list_versions` full-scan pain points
   (sections 1, 9, 10) with no interface change visible to
   `daf.orchestration`/`daf.scheduling`/`daf.catalog`.
3. **The two smallest `ArtifactStore` extensions** named in section 17
   (`find_by_content_hash`, `list_source_artifacts`), now cheap given
   (2).

Explicitly **not** part of the proposed Phase K, per this report's own
findings: any change to `evidence.types`, `scout.pipeline`, or the
one-door admission path (none of the above requires it); any of the
non-recommendations in section 19; any change to acquisition-side code
(`daf.adapters`/`daf.extractors`/`daf.orchestration.bindings`) — this
is purely a storage-layer evolution underneath an acquisition contract
this phase reaffirms as correctly frozen.
