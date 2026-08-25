# Phase C — DAF Source Registry and Acquisition Orchestration

**Status:** implemented and passing. Third DAF phase: orchestration
*above* the existing, unmodified SCOUT/evidence/DurablePool contract
proven in Phase A/B — source registration, adapter lookup, one
domain-agnostic orchestrator, and a genuine two-source vertical slice.

---

## Pre-implementation report

1. **Existing acquisition architecture**: `daf.vertical_slice.acquire_arxiv_papers`
   — one hardcoded function wiring `ArxivSourceAdapter` + `ArxivExtractor`
   + `run_scout`. No registry, no request/result types.
2. **Existing adapter contract**: `scout.interface.SourceAdapter`/`Extractor`
   Protocols (vendored, unmodified) — reused verbatim, not extended.
3. **Existing persistence boundary**: Phase B's `DurablePool`/
   `FilesystemEvidenceStore`/`ArtifactStore` — reused directly, unmodified
   in their public contracts (one internal bug fixed — see below).
4. **Proposed source registry**: `SourceDefinition{source_id, name, domain,
   adapter_id, configuration, capabilities, enabled}` + `SourceRegistry`
   — answers only "how to acquire," never "what it means scientifically."
5. **Proposed acquisition request**: `AcquisitionRequest{source_id,
   parameters, requested_at}` — an open `parameters` mapping, resolved
   only by the adapter factory bound to that source's `adapter_id`.
6. **Proposed orchestrator**: `AcquisitionOrchestrator(sources, adapters,
   pool).run(request) -> AcquisitionResult` — selects, invokes, persists,
   classifies failure, never admits directly.
7. **Proposed result semantics**: `AcquisitionResult{source_id, outcome,
   artifacts, admission_failures, error}`, `AcquisitionOutcome` ∈
   {ACQUIRED, DUPLICATE, SOURCE_UNAVAILABLE, ADAPTER_FAILURE,
   EXTRACTION_FAILURE, PERSISTENCE_FAILURE}.
8. **Error/retry strategy**: classify by which stage raised (adapter
   fetch vs. SCOUT/persistence), report rather than raise; no retry loop
   built — nothing in the existing adapters has failure modes worth
   automatically retrying yet (a missing id, a malformed file, a
   disabled source are all deterministic, not transient).
9. **Two-source vertical slice**: existing `ArxivSourceAdapter` (live
   HTTP query API, XML) + new `LocalDatasetSourceAdapter` (static local
   file, JSON) — a genuinely different acquisition pattern, both wired
   through the same orchestrator.
10. **Why no ontology changes**: `SourceDefinition.domain` is a free-form
    label never branched on by the orchestrator (proven by an AST-level
    test); `LocalDatasetExtractor` deliberately produces zero
    entities/relations rather than inventing a generic "dataset_record"
    ontology.
11. **Why no execution ledger**: "has this been acquired, what version
    resulted" is answerable today via Phase B's `ArtifactStore.exists()`/
    `list_versions()` — no new persistent record was needed or added.
12. **Future scheduler compatibility**: `AcquisitionRequest` has zero
    dependency on `retrieval`/`InquirySeam`/`materials` — a future
    caller (e.g. an uncertainty-driven scheduler) only needs to construct
    one and call `orchestrator.run(request)`; the orchestrator has no
    reciprocal dependency on any such caller.

---

## A bug found and fixed along the way

Phase C's repeated-acquisition tests immediately exposed a real defect in
Phase B's `FilesystemEvidenceStore._write`: it compared entire persisted
JSON payloads on a duplicate write and raised `ArtifactConflictError` on
any difference. But `Document.id` deliberately excludes `retrieved_at`
from its hash (like every identity in this codebase excludes
epistemic/temporal fields) — so re-acquiring the exact same content at a
later timestamp legitimately produces an object sharing the old id but
carrying a new `retrieved_at`, which the old check wrongly treated as a
conflict. Since two objects constructed via `make_*` can never
legitimately share an id while differing in identity-relevant fields, a
"conflicting content" write-time check can never fire for a real reason
— only for corruption of the file already on disk, independent of the
current write. Fixed: `_write` now re-verifies the *existing* file's own
identity (via the category's `*_from_dict`) instead of comparing
payloads; `ArtifactConflictError` was removed in favor of
`serialization.ArtifactIdentityMismatch`, raised consistently on read
*or* write. See `docs/DAF_DURABLE_STORAGE.md`'s addendum,
`daf/storage/filesystem_store.py`'s updated module docstring, and the
two updated/added tests in `tests/test_filesystem_store.py`.

---

## Design

```
SourceRegistry.get(source_id) -> SourceDefinition
        |
AdapterRegistry.get(source.adapter_id) -> AdapterBinding{build_adapter, build_extractor}
        |
        v
AcquisitionOrchestrator.run(AcquisitionRequest)
        |
        | adapter = binding.build_adapter(source, request)
        | raw_documents = adapter.fetch()          <- classified: SOURCE_UNAVAILABLE / ADAPTER_FAILURE
        | pre_existing_ids = {...already in pool...}
        | run_scout(_PrefetchedAdapter(raw_documents), binding.build_extractor(), pool)
        |                                            <- classified: EXTRACTION_FAILURE / PERSISTENCE_FAILURE
        v
AcquisitionResult{outcome: ACQUIRED | DUPLICATE, artifacts: (artifact_id, version_id, is_new)*}
```

`daf.orchestration.orchestrator` imports nothing from `daf.adapters`/
`daf.extractors` and nothing from `evidence.admission`, and calls no
pool mutator directly — both proven by AST-level tests. Concrete wiring
for the two Phase C sources lives in `daf.orchestration.bindings`, the
one module allowed to import them.

`LocalDatasetSourceAdapter`/`LocalDatasetExtractor` (`daf/adapters/local_dataset.py`,
`daf/extractors/local_dataset.py`) implement the same, unmodified
`SourceAdapter`/`Extractor` Protocols against a static local JSON file —
filesystem read vs. arXiv's live HTTP query, JSON vs. XML, zero
entities/relations vs. arXiv's paper+author graph — proving the
orchestrator generalizes across genuinely different acquisition shapes.

---

## Post-implementation report

### 1. Files changed

```
daf/orchestration/__init__.py
daf/orchestration/source_registry.py
daf/orchestration/adapter_registry.py
daf/orchestration/request.py
daf/orchestration/result.py
daf/orchestration/orchestrator.py
daf/orchestration/bindings.py
daf/adapters/local_dataset.py
daf/extractors/local_dataset.py
daf/storage/filesystem_store.py        (bug fix -- see above; ArtifactConflictError removed)
daf/orchestration/orchestrator.py      (uses ArtifactIdentityMismatch for persistence-failure classification)
tests/test_source_registry.py
tests/test_adapter_registry.py
tests/test_acquisition_request.py
tests/test_local_dataset_adapter.py
tests/test_local_dataset_extractor.py
tests/test_acquisition_orchestrator.py
tests/test_filesystem_store.py          (updated for the bug fix; one test renamed, one added)
tests/fixtures/local_dataset_sample.json
tests/fixtures/local_dataset_sample_revised.json
docs/DAF_DURABLE_STORAGE.md             (addendum documenting the fix)
docs/DAF_ORCHESTRATION.md               (this file)
```

### 2. New abstractions

`SourceDefinition`/`SourceRegistry`, `AdapterBinding`/`AdapterRegistry`,
`AcquisitionRequest`, `AcquisitionResult`/`AcquisitionOutcome`/
`AcquiredArtifact`, `AcquisitionOrchestrator`. One new adapter/extractor
pair (`LocalDatasetSourceAdapter`/`LocalDatasetExtractor`). No new
evidence type, no new identity scheme, no execution/operation id, no
scheduler daemon, no `AcquisitionSchedule`/history record (deliberately
— see pre-report item 11).

### 3. Existing abstractions reused

`scout.interface.SourceAdapter`/`Extractor` (unmodified), `scout.pipeline.run_scout`
(unmodified, the sole write path), `evidence.types.make_source`/`make_document`
(reused read-only, to precompute expected identity for duplicate
detection — never used to write), `daf.storage.durable_pool.DurablePool`,
`daf.storage.artifact_store.ArtifactStore.artifact_id` (unmodified).

### 4. Source registry behavior

Register/get/list by `source_id`; unknown id raises `SourceNotFoundError`
(caught by the orchestrator and turned into a `SOURCE_UNAVAILABLE`
result, never propagated as an exception to the caller); `enabled=False`
sources are likewise reported as `SOURCE_UNAVAILABLE`, not silently
skipped or raised.

### 5. Acquisition orchestration behavior

One `AcquisitionOrchestrator` instance drove both the arXiv and the
local-dataset source in `test_two_different_adapters_through_the_same_orchestrator`,
persisting both into the same `DurablePool`, with zero source-specific
branches anywhere in the orchestrator.

### 6. Two-source demonstration

Source A: `ArxivSourceAdapter` (existing, Phase A) — live HTTP query
API, XML, entity/relation graph. Source B: `LocalDatasetSourceAdapter`
(new) — static local file, JSON, zero entities/relations. Both run
through the identical `AcquisitionOrchestrator.run()` call.

### 7. Repeat acquisition behavior

Identical content re-acquired → `AcquisitionOutcome.DUPLICATE`, same
`version_id`s, `is_new=False` on every artifact, no growth in
`pool.all_observations()`. Changed content (one record's value changed)
re-acquired → `AcquisitionOutcome.ACQUIRED`, distinct `version_id`s for
the changed record, both old and new versions retained (append-only, per
Phase B).

### 8. Persistence behavior

The orchestrator never calls `pool.put_*`/`evidence.admission.admit_*`
directly (AST-verified); every persisted object flows exclusively
through the unmodified `scout.pipeline.run_scout`.

### 9. Error behavior

Four distinguishable failure outcomes, none of them raised as an
exception to the caller of `orchestrator.run()`: `SOURCE_UNAVAILABLE`
(unknown/disabled source, or a network-style error during fetch),
`ADAPTER_FAILURE` (any other fetch-time exception, e.g. a malformed
response), `EXTRACTION_FAILURE` (an exception from `Extractor.extract`),
`PERSISTENCE_FAILURE` (an `OSError` or `ArtifactIdentityMismatch` from
the storage layer). Each is covered by a dedicated test using a
deliberately broken adapter/extractor/store, never by mocking internals.

**Known partial-admission characteristic** (not a Phase C regression):
because `run_scout` admits `Document`/`Record` before `Observation` for
each item, a persistence failure at the `Observation` step can leave a
`Document`/`Record` durably persisted without a corresponding
`Observation`. This is an existing property of `run_scout`'s own
incremental admission design, unrelated to and unmodified by Phase C;
building cross-object transactional atomicity would be exactly the
"distributed consistency system" the task instructed not to build.

### 10. SCOUT regression results

Full vendored State-Space suite: **1273 passed, 0 failed, 0 files
modified.**

### 11. Full test results

`pytest tests/` (DAF, all three phases): **77 passed** — 19 (Phase A) +
26 (Phase B) + 32 new (Phase C).

### 12. ruff results

`ruff check daf/ tests/ conftest.py` → **All checks passed!**

### 13. mypy results

`mypy daf/` → **Success: no issues found in 22 source files.**

### 14. Remaining limitations

- No retry loop of any kind — every current failure mode is
  deterministic (bad config, malformed data, disabled source), so a
  retry would just fail identically; genuinely transient failures (a
  flaky network call) would need a bounded retry, deliberately not
  built this phase per the task's "keep retries simple / don't overbuild"
  instruction and the absence of a demonstrated need.
- No declarative `AcquisitionSchedule`/history record — "has this been
  acquired" is answered by `ArtifactStore` directly; a real scheduler
  would likely still want a persisted "last attempted" record eventually,
  but nothing in this phase needed one to prove the orchestration
  abstraction.
- The partial-admission characteristic noted in section 9 above.
- Only two sources exist; a third would require exactly one new
  adapter/extractor pair plus one `bindings.py` function and one
  `SourceDefinition` — no orchestrator change, which is the property
  this phase set out to prove.

### 15. Recommended Phase D

Per the task's own stop condition, this phase is complete: two sources,
one registry, one orchestrator, one SCOUT admission path, one durable
storage substrate, all tested. Any further DAF-side work (a third
adapter, a real declarative schedule, retry policy) is a straightforward
extension of what exists here. The information-gap/FEP-driven
acquisition loop and the separate Rust/zkVM/Morpho/CUDA execution plane
remain explicitly out of scope, as in Phase A/B.
