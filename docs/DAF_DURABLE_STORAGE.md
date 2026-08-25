# Phase B — DAF Durable Artifact Substrate

**Status:** implemented and passing. This is the second DAF phase, per
`docs/ARCHITECTURE_RECONNAISSANCE.md` section 19's phased sequence:
durable persistence underneath `EvidencePool`, without touching the SCOUT
Protocols, Evidence types, or admission gate proven in Phase A.

**Addendum (found during Phase C):** the original `_write` implementation
compared entire persisted JSON payloads on a duplicate write and raised
`ArtifactConflictError` on any difference. This was a bug: `Document.id`
(like every other identity in this codebase) deliberately excludes
epistemic/temporal fields such as `retrieved_at`, so re-acquiring
identical content at a later timestamp legitimately produces an object
with the same id but a different `retrieved_at` — a real scenario Phase
C's repeated-acquisition orchestration surfaced immediately. Since two
objects constructed via `make_*` can never legitimately share an id while
differing in identity-relevant fields, a write-time "conflicting content"
check can never fire for a legitimate reason — only for on-disk
corruption of the file already present, which is exactly what read-time
verification already existed to catch. `_write` was corrected to
re-verify the EXISTING file's own identity (via the category's
`*_from_dict`) rather than compare payloads; `ArtifactConflictError` was
removed, and corruption is now reported as `ArtifactIdentityMismatch`
consistently whether detected via a read or a write. See
`docs/DAF_ORCHESTRATION.md` and `daf/storage/filesystem_store.py`'s
module docstring for the full reasoning.

**Architectural boundary this phase locks in:** three deliberately
separate planes — DAF (durable acquisition), Evidence/Canonical State
(scientific-state), and a future Rust/zkVM/Morpho/CUDA execution plane.
This phase touches only the first. Nothing here introduces execution
identity, execution receipts, or a second provenance abstraction — see
sections 4 and 5 below for exactly why none was needed.

---

## Pre-implementation report

### 1. Existing artifact representation

`evidence.types.Document` — its own docstring literally calls it "a
retrieved artifact." `{id, source_id, raw_content, retrieval_method,
retrieved_at}`. `evidence.types.Record` carries the locator
(`{id, document_id, locator, raw_content}`) — `Document` itself has no
locator field.

### 2. Existing identity semantics

Every `evidence.types` object's `id` is `evidence.identity.content_hash`
(SHA-256 over canonical sorted-key JSON) of exactly its identity-defining
fields, always excluding epistemic/temporal annotations. Computed only by
the type's `make_*` factory — never caller-supplied.

### 3. Existing version semantics

`Document.id = content_hash({source_id, content_hash(raw_content),
retrieval_method})`. This already **is** version identity: a content
change produces a new `Document`, never an in-place mutation (confirmed
directly in Phase A's `test_changed_content_is_distinguishable_as_a_new_version`).

### 4. Existing content-hash semantics

`content_hash(raw_content)` is computed *internally* by `make_document`
as one ingredient of `Document.id`, but was not, before this phase,
exposed as an independently inspectable value distinct from `Document.id`
itself. **Identified gap #1** (per the task's instruction to name
deficiencies rather than silently patch around them): content identity
and version identity were both real, both already computed, but never
surfaced as two separate, independently queryable values. Fixed by
`ArtifactStore.content_hash_of(document)`, which recomputes
`content_hash(document.raw_content)` on demand — the exact same call
`make_document` already makes internally — never a new hash scheme.

**Identified gap #2:** there is no formal, stable "artifact identity"
(naming "the same logical source artifact" across content revisions)
anywhere in `evidence.types`. `Record.locator` is the closest existing
proxy (e.g., an arXiv entry's URL, which the `daf.adapters.arxiv` adapter
already keeps stable across revisions by design), but it is a loosely-
typed string field, not a formal identity. Filled, per the task's
"reuse existing structures rather than inventing new semantic objects"
instruction, by `ArtifactStore.artifact_id(source_id, locator)` — a
**derived**, non-authoritative hash of two already-existing fields, using
the same `content_hash` primitive everywhere else, computed on demand
and never stored as a new field on `Document` or `Record`. This mirrors
`EvidencePool.fingerprint()`'s own precedent of a derived, non-
authoritative view over already-existing ids.

### 5. Existing acquisition metadata

`retrieval_method`, `retrieved_at` (Document); `extracted_at`,
`confidence` (Observation) — real fields, excluded from identity,
preserved verbatim by this phase's serialization.

### 6. Existing storage limitations

`EvidencePool` (`evidence/pool.py`) is pure in-memory `Dict[str, T]`,
per-category, single process. Confirmed unchanged against the current
submodule pin.

### 7. Proposed minimal persistence boundary

One JSON file per object, named by its own real, existing content-hash
id, in a per-category subdirectory mirroring `EvidencePool`'s own
internal structure — all 8 categories (`Source`, `Document`, `Record`,
`Observation`, `Referent`, `ClaimedRelationship`, `DerivedValue`,
`DerivedGrounding`), since `EvidencePool` itself supports all 8 uniformly
and a persistence layer that silently dropped two of them would be a
hidden gap, not a "smallest boundary."

### 8. Storage implementation choice

Local filesystem, content-addressed, atomic writes (temp file +
`os.replace`, atomic on POSIX). No database, no message broker, no
object store — exactly matching the task's "persistence, not
infrastructure maximalism" instruction. The storage boundary
(`FilesystemEvidenceStore`'s public surface: `put_*`/`get_*`/`has_*`/
`all_*` per category) is the seam a future durable object-store backend
would implement instead, without touching `DurablePool` or
`ArtifactStore` above it.

### 9. Why this does not alter SCOUT

`scout.pipeline.run_scout` calls only the documented `EvidencePool`
surface. `DurablePool` is an `EvidencePool` **subclass** — every read
method (`get_*`, `all_*`, `has_*`, `fingerprint`, `fingerprint_history`,
`__len__`) is inherited completely unchanged; only the 8 `put_*` methods
are overridden, each adding exactly one persistence call before
delegating to `super().put_*()` (the real, original `EvidencePool`
behavior). Verified directly:
`test_durable_pool_is_indistinguishable_from_evidencepool_to_run_scout`
runs `run_scout` against a plain `EvidencePool` and a `DurablePool` side
by side and asserts identical findings, failures, ids, and fingerprint.
Zero lines of `scout/` or `evidence/` were touched.

### 10. Why no execution/provenance abstraction is required

Nothing in this phase answers "how was this transformed" or "prove this
computation happened" — every object persisted is already-admitted
evidence, and persistence never re-runs `evidence.admission` (see
`daf/storage/durable_pool.py::_replay_into`'s docstring: replay
reconstructs already-validated state, it does not re-validate it). No
operation id, execution id, or receipt of any kind exists anywhere in
this phase's code.

---

## Design

```
run_scout(adapter, extractor, DurablePool(store))
        |
        | (DurablePool.put_* : store first, then super().put_* -- unchanged EvidencePool behavior)
        v
FilesystemEvidenceStore   (root/{category}/{content-hash-id}.json, atomic writes)
        |
        | DurablePool.restore(store) / load_pool(store)  -- "process restart"
        v
a BRAND NEW EvidencePool/DurablePool, containing byte-identical objects,
each independently re-verified against its own content-hash identity
(daf.storage.serialization: every *_from_dict calls the real make_*
factory and checks the recomputed id matches the persisted one)
```

`ArtifactStore` sits alongside `FilesystemEvidenceStore` (same
underlying files, no duplicated storage) as a `Document`-centric facade
naming all three identities explicitly: `artifact_id` (derived, stable
across revisions), `version_id` (= `Document.id`, the real existing
identity), `content_hash` (the bytes alone, recomputed on demand).

---

## Post-implementation report

### 1. Files changed

All new; nothing pre-existing modified.

```
daf/storage/__init__.py
daf/storage/serialization.py
daf/storage/filesystem_store.py
daf/storage/artifact_store.py
daf/storage/durable_pool.py
daf/storage/demo.py
tests/test_storage_serialization.py
tests/test_filesystem_store.py
tests/test_artifact_store.py
tests/test_durable_pool.py
docs/DAF_DURABLE_STORAGE.md   (this file)
```

### 2. Storage abstraction

Three layers, each with a single clear responsibility:
`FilesystemEvidenceStore` (durable substrate, all 8 evidence categories),
`DurablePool` (`EvidencePool` subclass wiring `run_scout` straight into
that substrate), `ArtifactStore` (Document-centric artifact/version/
content-identity facade over the same substrate).

### 3. Storage backend

Local filesystem, JSON, content-addressed filenames, atomic writes.

### 4. Artifact persistence semantics

- Duplicate persistence of identical content under the same id, OR of
  the same identity-relevant content with different non-identity
  metadata (e.g. a later `retrieved_at`): silent no-op (content-addressing
  makes this always correct — see the Phase C addendum above).
- The file already on disk for a given id found to be self-inconsistent
  (corrupted/tampered with, independent of the current write): raises
  `serialization.ArtifactIdentityMismatch` — never reachable via
  legitimate use of this store's own API.
- Missing artifact/version: raises `KeyError`
  (`FilesystemEvidenceStore`) / `ArtifactNotFoundError`
  (`ArtifactStore`, also raised when a version_id exists but under a
  *different* artifact_id).
- Corrupted artifact (persisted content no longer matches its own
  filename/id): raises `serialization.ArtifactIdentityMismatch` on read
  — every read re-verifies identity, never trusts the filename alone.
- Partially written artifact: structurally impossible to observe —
  atomic temp-file + `os.replace` means a reader only ever sees a
  complete file or no file.

### 5. Version semantics

`version_id` = the real, pre-existing `Document.id` (no new identity
scheme). `artifact_id` = a derived `content_hash({source_id, locator})`,
stable across revisions because it never includes `raw_content`. Proven:
`test_artifact_id_stable_across_versions_while_version_id_changes` (same
artifact_id, two distinct version_ids, when only content changes).

### 6. Restart test

`test_restart_across_two_real_separate_os_processes` — two genuinely
separate `python -m daf.storage.demo` subprocess invocations (`acquire`
then `retrieve`), sharing nothing but a filesystem path, asserting
identical `version_id`, `artifact_id`, `content_hash`, `raw_bytes_len`,
and `pool.fingerprint()` across the restart. Also covered at the
in-process level (two independent `DurablePool`/`FilesystemEvidenceStore`
object graphs, old ones explicitly `del`eted) by
`test_acquire_persist_restart_retrieve_identical_identity` and
`test_version_distinguishability_survives_restart`.

### 7. Exact raw-byte verification

`restored_document.raw_content == original_raw_content` asserted directly
in the restart test; `daf/storage/serialization.py` never parses,
normalizes, or transforms `raw_content`/`content` before persisting —
every `*_to_dict` copies the field verbatim, and every `*_from_dict`
recomputes identity from that same verbatim value.

### 8. SCOUT regression results

`test_durable_pool_is_indistinguishable_from_evidencepool_to_run_scout`:
pass. Full vendored State-Space suite: **1273 passed, 0 failed, 0 files
modified.**

### 9. ruff results

`ruff check daf/ tests/ conftest.py` → **All checks passed!**

### 10. mypy results

`mypy daf/` → **Success: no issues found in 13 source files.**

### 11. Full-suite results

`pytest tests/` (DAF, all phases) → **45 passed** (19 from Phase A + 26
new in Phase B, including one live-network test and one real
two-subprocess restart test).

### 12. Known limitations

- Single-writer, single-machine filesystem store — no concurrent-writer
  safety beyond atomic single-file writes (matches `EvidencePool`'s own
  documented v1 scope: "single-writer, in-process").
- `ArtifactStore._locator_for`/`list_versions` scan all persisted Records
  linearly (O(n)) — fine at this phase's scale, not indexed; a future
  phase could add a locator→document_id index file without changing any
  public method signature.
- No sharding of the flat per-category directories — acceptable at
  vertical-slice scale, a real scaling concern for millions of objects
  (noted, not solved, here).
- `artifact_id` is defined only for `Document`/`Record` pairs (the
  `ArtifactStore` facade); the other 6 evidence categories are durable
  via `FilesystemEvidenceStore`/`DurablePool` but have no equivalent
  "logical identity across revisions" facade, because none of them
  currently has an analogous revision concept in the existing
  architecture.

### 13. Recommended next phase

Per the user's own stated direction: Phase B's job — a durable
acquisition plane — is now real. The next DAF-side step (still not
requested yet) would be additional domain adapters proving the substrate
stays domain-agnostic under real persistence, not just in memory. The
Rust/zkVM/Morpho/CUDA execution plane and any execution-provenance work
are explicitly a separate, later phase in a different project, per the
architectural invariant this phase was scoped to respect.
