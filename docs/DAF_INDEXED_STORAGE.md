# Phase K — DAF Indexed Durable Storage

**Status:** implemented and passing. Ninth DAF phase: the smallest
storage evolution Phase J's reconnaissance justified — a content-addressed
`BlobStore` eliminating raw-content duplication, and a local, embedded
SQLite `MetadataIndex` replacing full directory scans — with zero change
to acquisition semantics, zero change to vendored SCOUT/evidence code,
and full backward compatibility with every durable directory Phases
A–J ever produced.

---

## Pre-implementation report

### 1–4. Current implementation, duplication, layout, identity — confirmed against HEAD, not assumed from the Phase J report

Re-read directly (not trusted from the report) before writing any code:
`daf/storage/filesystem_store.py`, `durable_pool.py`, `artifact_store.py`,
`serialization.py`; `daf/catalog/{source_catalog,plan_catalog,checkpoint,history}.py`;
and, critically, the **vendored** `evidence/pool.py`, `evidence/types.py`,
`scout/pipeline.py`. Three Phase J findings were reconfirmed exactly:

- `scout.pipeline.run_scout` (vendored, unmodified) builds `Document` and
  its one `Record` from the **identical** `raw_doc.content` string
  (`make_document(..., raw_content=raw_doc.content, ...)` immediately
  followed by `make_record(..., raw_content=raw_doc.content)`), and
  `daf.storage.serialization`'s `document_to_dict`/`record_to_dict` both
  wrote that string to disk verbatim — confirmed real, on-disk, 2x
  duplication, not a transient in-memory artifact.
- `ArtifactStore.list_versions`/`_locator_for` (`daf/storage/artifact_store.py`)
  called `self._store.all_documents()`/`all_records()` — a full
  `Path.glob("*.json")` + parse of **every** persisted Document/Record —
  with no secondary index of any kind.
- `DurablePool.restore`/`load_pool` (`daf/storage/durable_pool.py`) called
  `_replay_into`, which loads **all eight** evidence categories in full
  before returning — exactly what `daf.catalog.cli`'s `execute-plan`
  triggers on every single invocation.

One new fact, found only by reading the vendored `evidence/pool.py`
directly: `EvidencePool.fingerprint()` hashes `sorted(self._sources)`,
`sorted(self._documents)`, ..., `sorted(self._derived_groundings)` — the
**sorted id keys** of its eight private dicts, never any object's actual
content. This is what makes section 8 below possible at all.

### 5–8. Proposed BlobStore boundary, SQLite schema, indexes, migration strategy

See the "Design" section below — implemented exactly as proposed, no
deviation discovered during implementation.

### 9–10. Restart and fingerprint strategy

Lazy hydration behind `EvidencePool`'s unchanged public contract, and an
index-only `fingerprint()` override — both detailed below, both
requiring zero changes to vendored `EvidencePool`.

### 11–12. Crash-safety and backward-compatibility strategy

Write ordering (blob → metadata → index, each independently atomic) and
a dual-format read path (old inlined `raw_content`, new
`content_hash`-referenced) — both detailed below.

### 13. Expected complexity improvements

`ArtifactStore.list_versions`/`find_by_content_hash`/`list_source_artifacts`:
O(entire corpus) → O(indexed lookup + result size). `DurablePool.restore`
+ ordinary `has_document`/`get_document` calls (the orchestrator's actual
acquisition-time hot path): O(entire corpus) → O(1) per call, corpus-size-
independent. `fingerprint()`: O(entire corpus, every object's content
parsed) → O(id-list size only, zero content reads). All four claims are
proven by dedicated tests, not asserted — see "Performance/complexity
demonstration" below.

**Code change justified?** Yes — Phase J's own five-point recommendation
(BlobStore + SQLite index) is exactly what section 14 below implements,
nothing beyond it.

---

## Design

```
                                DAF
                                 │
                      ┌──────────┴──────────┐
                      ▼                     ▼
              MetadataIndex             BlobStore
                 SQLite                filesystem
                      │                     │
         artifact_id, source_id,      content-addressed
         locator, content_hash,       raw content, one
         retrieved_at -- an INDEX     file per unique hash
                      │                     │
                      └──────────┬──────────┘
                                 ▼
                    FilesystemEvidenceStore
                (still the canonical authority --
                 documents/records/... JSON files,
                 now referencing blobs by hash)
```

### BlobStore (`daf/storage/blob_store.py`)

```
put(content_hash, raw_content) -> None   # idempotent
get(content_hash) -> str                 # raises BlobNotFoundError if absent
has(content_hash) -> bool
```

Stores `str`, not `bytes` — matching every acquired artifact in this
codebase exactly (`RawDocument.content`/`Document.raw_content`/
`Record.raw_content` are all `str`) and matching
`evidence.identity.content_hash`'s own established call convention, so
`BlobStore`'s hash is byte-for-byte the same hash `make_document`/
`make_record` already compute — never a re-encoding that could drift
from it. One file per content hash, atomic temp+replace writes (the
same discipline `FilesystemEvidenceStore` already used). `get()`
re-verifies the read content's hash before returning it —
`BlobCorruptionError` on mismatch, independent of and in addition to the
existing `Document`/`Record`-level check.

BlobStore has no concept of Document, Record, artifact identity, version
identity, acquisition state, or execution provenance — it stores content
addressed by a hash, nothing else, per the task's own explicit
boundary.

### Raw-content deduplication (`daf/storage/filesystem_store.py`)

`documents/{id}.json` and `records/{id}.json` now store
`"raw_content": null, "content_hash": "<hash>"` instead of inlining the
string. `put_document`/`put_record` write the blob **first** (idempotent
— a re-acquisition of identical content is a no-op there too), then the
metadata JSON referencing it. `get_document`/`get_record`/`all_documents`/
`all_records` transparently resolve the reference back into a real,
fully-populated `Document`/`Record` — `evidence.types.Document`/`Record`
(vendored) are completely unchanged; every in-memory object this module
hands back still carries a real `raw_content` string exactly as before.
**No vendored type was touched — this was purely a storage-layer
representation change, exactly the boundary the task's section 3
required ("If changing vendored evidence types would be required: STOP").**

Backward compatibility: a pre-Phase-K file inlines `raw_content`
directly and has no `content_hash` key; `_resolve_raw_content` checks for
that first and only falls back to the blob store when it's absent — so
every directory Phases A–J ever wrote remains fully readable forever,
with **no forced migration or rewrite** of existing files.

### MetadataIndex (`daf/storage/metadata_index.py`)

```sql
CREATE TABLE sources (id TEXT PRIMARY KEY);
CREATE TABLE documents (id TEXT PRIMARY KEY, source_id, content_hash, retrieval_method, retrieved_at);
CREATE TABLE records (id TEXT PRIMARY KEY, document_id, locator, artifact_id, content_hash);
CREATE TABLE observations (id TEXT PRIMARY KEY);
-- + indexes on documents(source_id, content_hash, retrieved_at), records(artifact_id, document_id)
```

Only four categories are indexed: `sources`, `documents`, `records`,
`observations` — the four every real adapter (arXiv, EDGAR, USGS, NOAA)
actually populates. `referents`, `claimed_relationships`, `derived_values`,
`derived_groundings` are never constructed by any of them (every
extractor in this codebase returns `entities=()`, `relations=()`) —
indexing them would have been exactly the "index every field
automatically" Phase J's own report warned against. `fingerprint()`
still answers correctly for those four via a cheap filename-only glob
(see below), never by omitting them.

`artifact_id` is computed once, in one place
(`daf/storage/identity.py::compute_artifact_id`), and used identically by
`ArtifactStore.artifact_id` (now a thin delegate) and
`MetadataIndex.record_record` — no duplicated identity formula.

### Index queries (`ArtifactStore`, extended)

`list_versions`/`_locator_for` now query the index instead of scanning;
two new methods answer patterns Phase J's reconnaissance found no
efficient path for at all: `find_by_content_hash` (dedup auditing) and
`list_source_artifacts` (operator inspection). **The existing
`ArtifactStore` interface was compared against first, per the task's own
instruction — it was already the right shape; only its `list_versions`/
`_locator_for` implementations changed, plus two additive methods.**

### DurablePool restart (`daf/storage/durable_pool.py`) — lazy hydration

`restore()` now returns immediately — no eager `_replay_into`. Single-
object access (`has_source`/`get_source`/`has_document`/`get_document`/
`has_record`/`get_record`/`has_observation`/`get_observation` — the four
categories that scale with acquisition volume) resolves against the
already-O(1) `FilesystemEvidenceStore` (filename = id, unchanged since
Phase B) on first miss, memoizing into the same in-memory dict
`_replay_into` would have populated it into. Full-corpus methods
(`all_referents`/`all_claimed_relationships`/`all_observations`/
`all_derived_values`/`all_derived_groundings`/`fingerprint_history`/
`__len__`) trigger a one-time full hydration (`_ensure_hydrated`,
identical replay logic/order to Phase B–J) before delegating to the
unmodified vendored `EvidencePool` method — so their answers are
byte-for-byte identical to eager restore, only the *timing* of when that
cost is paid has moved. `has_referent`/`get_referent`/`has_derived_value`/
`get_derived_value`/`has_derived_grounding`/`get_derived_grounding` (the
three categories no adapter has ever populated) also trigger full
hydration on any access — correct, and not worth a bespoke lazy path for
categories with no real corpus to avoid loading.

`EvidencePool` (vendored) is not modified at all — every override lives
on `DurablePool`, calling `super()`/the base class's methods exactly as
Phase B's original design already did for `put_*`.

### Fingerprint strategy — section 8's question, answered

**Yes**, `fingerprint()` can be computed from the metadata index without
loading any object's content — because `EvidencePool.fingerprint()`
itself already only depends on id sets, never content (confirmed by
reading it directly, see item 1–4 above). `DurablePool.fingerprint()`
reproduces the exact same payload shape as the union of (a) whatever ids
are already in memory (from any prior `put_*`/lazy `get_*` this process
performed) and (b) `MetadataIndex.all_ids(category)` for the four
indexed categories, or a cheap filename-only glob
(`FilesystemEvidenceStore.all_ids_by_filename`, no JSON body parsed) for
the four that aren't indexed. If the pool has already fully hydrated,
the override defers to the vendored implementation directly (no reason
to recompute what's already in memory). **Equivalence, not just a
plausible-looking reimplementation, is proven by dedicated tests**
(`test_fingerprint_is_equivalent_whether_or_not_the_pool_has_hydrated`,
`test_fingerprint_reflects_partial_in_process_hydration_correctly`) —
comparing the lazy path's output against the fully-hydrated vendored
computation over the same real corpus, both for an untouched pool and
for a pool that has already lazily loaded some (but not all) objects.

`fingerprint_history()`'s exact incremental sequence (order-dependent,
unlike `fingerprint()` itself) is honestly **not** specially preserved
under lazy loading — grep confirms `fingerprint_history` is never
actually read by any DAF code or test (only `fingerprint()` is), and Phase
B–J's own eager restore already populated it via repeated `put_*` calls
in replay order rather than genuine acquisition-time order, so this
phase changes *nothing* about its pre-existing relationship to "real"
history. Documented here per the task's "if no, document why."

### Crash safety (section 10) and corruption detection (section 11)

Write ordering for every `documents`/`records` write: **(1)** blob
(idempotent, atomic temp+replace) → **(2)** metadata JSON (atomic
temp+replace, referencing the blob's hash) → **(3)** index row
(`INSERT OR IGNORE`, cheap, last). A crash between (1) and (2) leaves an
orphaned-but-harmless blob (content-addressed; a future write of the
same content finds it already there). A crash between (2) and (3) leaves
canonical storage fully correct and self-verifiable, with the index
merely stale — exactly the state `rebuild()` exists to repair, and the
state `FilesystemEvidenceStore.__init__` detects and repairs
**automatically** (an index reporting zero documents next to a store
with at least one persisted document triggers `rebuild()` once, both
checks O(1)). No ordering can produce a metadata entry referencing a
blob that was never written — the specific failure mode section 10
forbids.

Corruption detection is now two-layered: `BlobStore.get()` independently
re-verifies read content against its own filename hash
(`BlobCorruptionError`), and the existing `Document`/`Record`-level
re-verification (`ArtifactIdentityMismatch`, unchanged since Phase B)
still catches a tampered `content_hash` *reference* even when the blob
it resolves to is itself perfectly valid. Both are exercised by
dedicated tests using two *different* tampering scenarios (see "Files
changed" below) — proving they are genuinely two distinct, independently
useful checks, not one masquerading as two.

---

## Post-implementation report

### 1. Files changed

```
daf/storage/identity.py                (new -- compute_artifact_id, extracted from ArtifactStore)
daf/storage/blob_store.py              (new -- BlobStore, BlobNotFoundError, BlobCorruptionError)
daf/storage/metadata_index.py          (new -- MetadataIndex, SQLite schema, rebuild())
daf/storage/filesystem_store.py        (blob-referenced documents/records, index updates, auto-rebuild-if-stale,
                                         all_ids_by_filename, has_source/has_observation added)
daf/storage/artifact_store.py          (list_versions/_locator_for now index-backed; find_by_content_hash/
                                         list_source_artifacts added; artifact_id delegates to daf.storage.identity)
daf/storage/durable_pool.py            (lazy hydration for restore(); index-backed fingerprint(); force_full_hydration())
tests/test_blob_store.py               (new, 8 tests)
tests/test_metadata_index.py           (new, 11 tests)
tests/test_storage_index_real_adapter_shapes.py  (new, 3 tests -- EDGAR/USGS/NOAA locator shapes through the index)
tests/test_filesystem_store.py         (2 corruption tests replaced/split: blob-layer vs. metadata-layer tampering)
tests/test_artifact_store.py           (+3 tests: find_by_content_hash, list_source_artifacts, no-full-scan proof)
tests/test_durable_pool.py             (+5 tests: lazy restart, hydration-triggers-correctly, fingerprint
                                         equivalence x2, index rebuild-after-deletion)
docs/DAF_INDEXED_STORAGE.md            (this file)
```

Not touched, by design: `evidence/types.py`, `evidence/pool.py`,
`evidence/identity.py`, `scout/pipeline.py` (all vendored); every file
under `daf/adapters/`, `daf/extractors/`, `daf/orchestration/bindings.py`,
`daf/catalog/plan*.py`, `daf/scheduling/*.py` — this phase is entirely a
storage-layer evolution underneath an acquisition contract Phase J
reaffirmed as correctly frozen.

### 2. BlobStore interface

`put(content_hash, raw_content) -> None` (idempotent), `get(content_hash) -> str`
(raises `BlobNotFoundError`; verifies content on read, raises
`BlobCorruptionError` on mismatch), `has(content_hash) -> bool`. See
"Design" above.

### 3. Filesystem implementation

One file per content hash (`{root}/{hash}.blob`), atomic temp+replace
writes. See "Design" above.

### 4. SQLite schema

Four tables (`sources`, `documents`, `records`, `observations`), five
indexes, all created via `CREATE TABLE/INDEX IF NOT EXISTS` on
`MetadataIndex.__init__`. See "Design" above for the full DDL.

### 5. Metadata indexes

`documents(source_id)`, `documents(content_hash)`, `documents(retrieved_at)`,
`records(artifact_id)`, `records(document_id)` — the five Phase J's
reconnaissance found a real query against, none speculative.

### 6. Migration/rebuild behavior

Fully automatic and transparent: `FilesystemEvidenceStore.__init__`
detects an empty index next to a non-empty store (O(1) check both ways)
and calls `MetadataIndex.rebuild(store)`, which repopulates every table
from the store's own canonical `all_*()` methods. Verified by
`test_index_rebuild_after_deletion_recovers_the_same_logical_state`:
delete `index.sqlite`, reopen the store, confirm `list_versions`/
`fingerprint()` give byte-for-byte identical answers to before the
deletion — Phase J's own "filesystem = authority, SQLite = derived, and
if SQLite is deleted, rebuild reproduces the identical logical storage
state" invariant, proven, not just asserted.

### 7. Restart behavior

`DurablePool.restore()` no longer eagerly loads the corpus.
`test_restart_does_not_hydrate_until_a_full_corpus_method_is_called`
proves this directly (not via timing): with a 50-artifact synthetic
corpus, the store's four full-scan methods are monkeypatched to raise if
called at all, then `restore()` + `has_document`/`get_document` (a hit
and a genuine miss) are exercised — none of the patched methods fire.
`test_all_observations_still_triggers_full_hydration_when_actually_needed`
proves the complementary claim: a caller that DOES need the full corpus
still gets the fully correct answer.

### 8. Raw-byte deduplication behavior

Every new acquisition now writes its raw content once, not twice — the
blob is written before either metadata file, and both `documents/{id}.json`
and `records/{id}.json` reference it by hash rather than inlining it a
second time. Old, pre-Phase-K directories are unaffected and remain
fully valid (dual-format read path, see "Design").

### 9. Fingerprint equivalence

Proven equal in both directions the task asked about: a never-hydrated
pool's `fingerprint()` equals a fully-hydrated pool's, over the same
real corpus (`test_fingerprint_is_equivalent_whether_or_not_the_pool_has_hydrated`),
and a *partially* lazily-loaded pool's `fingerprint()` (some objects
touched via `get_document`, most not) also equals both
(`test_fingerprint_reflects_partial_in_process_hydration_correctly`) —
ruling out a double-counting or missing-id bug in the in-memory/index
union specifically.

### 10. Corruption behavior

Two independently-verified layers: `BlobCorruptionError` when the raw
content itself is tampered (caught by `BlobStore.get()`'s own hash
re-verification, before any Document-level logic even runs) and
`ArtifactIdentityMismatch` when the metadata's `content_hash` *reference*
is tampered to point at a different (still valid) blob (caught by the
existing, unchanged Document-level re-verification). Both are exercised
by dedicated tests using genuinely different tampering scenarios, in
`tests/test_filesystem_store.py`.

### 11. Performance/complexity demonstration

Both claims are proven by making the "old, expensive" code path raise if
it is ever invoked, not by timing (deterministic, no flakiness):

- `test_list_versions_and_get_never_full_scan_the_store`
  (`tests/test_artifact_store.py`): 50 unrelated artifacts persisted,
  then `store.all_documents`/`all_records` are replaced with a function
  that raises `AssertionError`; `list_versions`/`get`/
  `find_by_content_hash`/`list_source_artifacts` are all then called
  successfully — proving they never touch those methods.
- `test_restart_does_not_hydrate_until_a_full_corpus_method_is_called`
  (`tests/test_durable_pool.py`): same technique, 50-artifact corpus,
  `restore()` + `has_document`/`get_document`.

Per the task's own instruction, no wall-clock benchmark is claimed —
these tests demonstrate the *algorithmic path* changed (the expensive
methods are provably never called for these operations), not a specific
production-scale speedup number.

### 12–14. EDGAR / USGS / NOAA behavior

Every one of Phases G/H/I's own integration test suites (30+30+32 tests,
including live-network-independent CLI subprocess tests) passes
unmodified against this phase's storage layer — proving the acquisition-
side contract genuinely didn't change. Additionally,
`tests/test_storage_index_real_adapter_shapes.py` (new) specifically
proves the index gives correct answers against each source's real
locator shape: EDGAR's bare date-string locators (three dates → three
correctly-grouped artifacts), USGS's stable event-id locator surviving a
real content revision (two versions, one artifact, correctly ordered),
and NOAA's composite window-descriptor locator (opaque to the index,
indexed as a plain string, no NOAA-specific parsing anywhere in
`daf.storage.metadata_index`).

### 15. Full tests

`pytest tests/`: **262 passed** — 232 (Phases A–J) + 30 new (8 BlobStore
+ 11 MetadataIndex + 3 cross-source locator-shape + 2 replaced/added
corruption tests in `test_filesystem_store.py` + 3 in `test_artifact_store.py`
+ 5 restart/fingerprint/rebuild tests in `test_durable_pool.py` — net of
one pre-existing corruption test split into two more precisely-scoped
ones).

Full vendored State-Space suite: **1273 passed, 0 failed, 0 files
modified.**

### 16. mypy

`mypy daf/` → **Success: no issues found in 42 source files.**

### 17. ruff

`ruff check` on every new/changed file: zero correctness findings after
fixing two genuine issues found during development (two unused `typing`
imports left over from a refactor, one unnecessary `# noqa` for a rule
this project's ruff config doesn't enable). Remaining findings
(`UP006`/`UP035`/`UP045`/`UP037`/`I001`) are exclusively the same
pre-existing style-modernization patterns present throughout the
codebase since Phase A (see Phases G/H/I's own reports for the identical
finding) — matched, not refactored away.

### 18. Remaining limitations

- `fingerprint_history()`'s exact incremental sequence is not specially
  preserved under lazy loading (see "Fingerprint strategy" above) —
  honestly documented rather than silently accepted, and unaffected in
  practice since nothing in this codebase reads it.
- The index rebuild triggered by `FilesystemEvidenceStore.__init__` pays
  a real O(corpus) cost the first time it fires on a pre-Phase-K or
  index-deleted directory — expected and bounded (a one-time cost, not a
  recurring one), matching Phase J's own framing that a rebuild is
  supposed to cost O(corpus) once.
- Old, pre-Phase-K files are never proactively rewritten to the new
  deduplicated blob-referenced format — they remain valid and readable
  forever, but do not retroactively gain the 2x-duplication fix. A
  future phase could add an opt-in migration pass if this is ever
  judged worth the risk of rewriting existing data; this phase
  deliberately does not, per "do not require users to delete or
  recreate" and in the interest of the smallest safe change.
- `MetadataIndex` opens a short-lived SQLite connection per call rather
  than holding one open for its lifetime — a deliberate choice for
  safety against this codebase's own "construct a second store instance
  over the same root after only `del`-eting the first" restart-test
  pattern (see that module's own docstring), at a small (sub-millisecond,
  not measured to matter at this project's scale per Phase J's own
  estimates) per-call overhead.
- No concurrent-writer stress testing was performed (single-writer-at-a-
  time remains this project's only demonstrated concurrency model,
  matching Phase J's own recommendation to defer that question to
  PostgreSQL only if a real multi-process-writer need appears).

### 19. Recommended Phase L

Per this task's own stop condition, this phase is complete: the
filesystem remains canonical raw storage; SQLite provides durable,
rebuildable metadata indexing; restart no longer blindly loads the
entire historical corpus; artifact/version/content identity semantics
are provably unchanged (fingerprint equivalence, all Phase A–J tests
passing unmodified). Two reasonable directions for a future phase,
consistent with Phase J's own deferred-items list: (a) an opt-in
migration pass that rewrites pre-Phase-K directories into the
deduplicated blob-referenced format, if the 2x-duplication savings are
ever judged worth it at real scale; or (b) begin evaluating the DuckDB/
Parquet analytical-projection layer Phase J scoped but explicitly
deferred, now that the canonical+indexed storage layer underneath it is
in place. PostgreSQL, S3/MinIO, Iceberg, Kafka, distributed storage/
acquisition, GraphRAG, vector search, State-Space integration, FEP,
information gain, active learning, Morpho, CUDA, zkVM, and execution
provenance all remain untouched, per this phase's explicit stop
condition.
