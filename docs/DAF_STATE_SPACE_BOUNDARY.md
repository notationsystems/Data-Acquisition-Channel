# Phase L — DAF / SCOUT / State-Space Boundary Reconciliation

**Status:** documentation/reconnaissance only. No code was changed this
phase. Every claim below is grounded in direct inspection of the actual
current code — `daf/` and the vendored `evidence/`, `scout/`,
`materials/`, `core/canonical/`, `core/projection/`, `retrieval/`,
`experiment/`, `workbench/`, `morpho/` — not the older architecture
prose the task itself warned may be stale. Where code and prior
documentation disagree, this report says so explicitly and follows the
code.

**Headline correction:** the task's assumed pipeline —
`Evidence → Canonical State → Typed Coordinates/Cells → ModelState → State-Space Transformer`
— **does not exist as a single chain in the current code.** The
repository contains **two structurally separate, non-interacting object
models**, each internally coherent, that the task's assumed diagram
conflates into one:

1. **The Evidence/ModelState chain** (`evidence/` → `materials/` →
   `experiment/`): `Observation` feeds `materials.model_state.update`
   directly. There is no `CanonicalState`/`Version` anywhere in this
   chain.
2. **The Canonical/Morpho chain** (`core/canonical/` → `core/projection/`
   → `morpho/`): `CanonicalState`/`Version` feeds `ProjectedState` feeds
   `compile_morpho`. There is no `Observation`/`EvidencePool` anywhere
   in this chain.

Confirmed both directions, by grep and by the vendored code's own
docstrings: `evidence/`/`scout/` never import `core.canonical`;
`core/canonical/`/`core/projection/` never import `evidence`/`scout`.
`materials/` imports `evidence.*` extensively; it never imports
`core.canonical`. `morpho/compiler.py` imports `core.canonical.schema`
and `core.projection.project`; it never imports `evidence`. DAF imports
neither `materials/` nor `core.canonical/` — grep across all of
`daf/` for `materials\.|from materials|core\.canonical|from core\b`
returns **zero matches**.

Also: no class named `Transformer`/`StateSpaceTransformer` exists
anywhere in the repository. The task's "State-Space Transformer" names a
role, not a class — the actual implementation of that role is
`materials.model_state.predict(state, candidate) -> Prediction`, a pure
function (`Prediction = G(state, candidate)`).

---

## Pre-implementation report

**Files inspected** (direct reads plus two parallel research passes,
cited by file:line throughout this document): `daf/orchestration/*.py`,
`daf/catalog/*.py`, `daf/storage/*.py`, `daf/adapters/*.py`,
`daf/extractors/*.py`; vendored `evidence/types.py`, `evidence/identity.py`,
`evidence/admission.py`, `evidence/pool.py`; `scout/pipeline.py`,
`scout/interface.py`; `materials/model_state.py`, `materials/analysis.py`,
`materials/results.py`, `materials/candidates.py`, `materials/decision.py`,
`materials/value.py`, `materials/design.py`, `materials/information.py`;
`core/canonical/{state,version,schema,delta,validation}.py`;
`core/projection/project.py`; `morpho/compiler.py`; `experiment/session.py`,
`experiment/step.py`; `retrieval/engine.py`, `retrieval/context.py`;
`workbench/interaction.py`; relevant vendored tests
(`tests/test_materials_consumer.py`, `tests/test_observation_semantics.py`)
and vendored docs (`docs/ARCHITECTURE.md`, `docs/EXPERIMENT_ARCHITECTURE.md`,
`docs/RETRIEVAL_ARCHITECTURE.md`).

**Actual object flow**: `RawDocument` (DAF adapter) → `Source`/`Document`/
`Record`/`Observation` (`scout.pipeline.run_scout`, vendored, admitted via
`evidence.admission`) → `EvidencePool`/`DurablePool` (shared). From
there, **two independent downstream consumers already exist in this
codebase**, neither reachable through DAF: `materials.analysis.analyze`
(read-only interpretation) and `materials.results.admit_experimental_result`
+ `materials.model_state.update` (a second, DAF-independent evidence
producer feeding `ModelState`). See sections 6–8 for exact traces.

**Identity findings**: eight distinct content-addressed identities exist
across the two chains (`Document.id`, `Record.id`, `Observation.id`,
`ModelState.id`, `core.canonical.Version.id`, plus DAF's own derived
`artifact_id`/`content_hash`/`MetadataIndex` rows) — no accidental
conflation found; see section 9's full table.

**Temporal findings**: at least six distinct timestamp/temporal
concepts exist, deliberately kept separate; see section 10.

**Provenance findings**: acquisition provenance (DAF checkpoints/
artifact history), evidence provenance (`evidence.provenance.ancestry_of`,
consumed by `materials.analysis`), and scientific derivation
(`DerivedValue.derived_from`) are three distinct, already-separated
mechanisms. No execution ledger exists anywhere in this codebase, and
none is proposed here.

**Coupling findings**: DAF is coupled to `scout`/`evidence` only (by
design, since Phase A). `materials`/`experiment`/`retrieval`/`workbench`
are coupled to `evidence`/`scout` but not to DAF or `core.canonical`.
`morpho` is coupled to `core.canonical`/`core.projection` but not to
`evidence`/`materials`. No accidental coupling was found in either
direction.

**Boundary findings**: see sections 13–16.

**Is implementation necessary this phase?** **No.** Every invariant this
report can state is already true of the current code without any
change. No concrete code defect was found that prevents an established
invariant from being represented (see section 18's per-invariant
verdicts). Per the task's own section 19 gate, no implementation is
justified, and none is proposed.

---

## 1. Current DAF architecture

DAF owns exactly: acquisition (`daf/adapters/`, `daf/extractors/`,
`daf/orchestration/`), catalog/scheduling (`daf/catalog/`,
`daf/scheduling/`), and durable persistence/indexing of whatever `scout.
pipeline.run_scout` admits (`daf/storage/`: `FilesystemEvidenceStore`,
`BlobStore`, `MetadataIndex`, `ArtifactStore`, `DurablePool`). DAF never
imports `evidence.admission` directly (AST-verified by every adapter's
own `test_one_door_invariant_for_*_modules` test, forbidding
`materials`/`experiment`/`workbench`/`core`/`morpho`/`backends`/`runtime`)
and never constructs an `Observation`/`Document`/`Record` itself — only
`scout.pipeline.run_scout` (vendored, unmodified since Phase A) does
that, from the `RawDocument`/`ExtractionCandidate` pairs a DAF adapter/
extractor produces.

Ownership table:

| Object | Owner | Identity | Lifecycle | Persisted by | Downstream consumer |
|---|---|---|---|---|---|
| `SourceDefinition` | DAF (`daf.orchestration.source_registry`) | `source_id` (operator-chosen) | mutable, operator-declared | `daf.catalog.source_catalog.SourceCatalog` | `AcquisitionOrchestrator` |
| `AcquisitionPlan` | DAF (`daf.catalog.plan`) | `plan_id` (operator-chosen) | mutable, operator-declared | `daf.catalog.plan_catalog.PlanCatalog` | `daf.scheduling.runner.execute_plan` |
| `AcquisitionRequest` | DAF (`daf.orchestration.request`) | none (transient) | one call, never persisted | never | `AcquisitionOrchestrator.run` |
| `AcquisitionCheckpoint` | DAF (`daf.catalog.checkpoint`) | `plan_id` | mutable, last-write-wins | `daf.catalog.checkpoint.CheckpointStore` | `execute_plan`'s next call |
| `RawDocument` | DAF adapter | none (transient) | one `fetch()` call | never (converted immediately) | `scout.pipeline.run_scout` |
| `Source`/`Document`/`Record`/`Observation` | **SCOUT** (vendored) | content-hash (`evidence.identity.content_hash`) | immutable once admitted | `daf.storage.filesystem_store.FilesystemEvidenceStore` (DAF-owned persistence of a SCOUT-owned object) | `EvidencePool`; `materials.*`; `retrieval.*` |
| `AcquiredArtifact`/`AcquisitionResult` | DAF (`daf.orchestration.result`) | derived `artifact_id`/`version_id` (echoes `Document`/`Record` identity) | transient, never persisted | never | caller of `orchestrator.run`/`execute_plan` |
| `BlobStore` entries | DAF (`daf.storage.blob_store`) | `content_hash(raw_content)` | immutable | filesystem | `FilesystemEvidenceStore` |
| `MetadataIndex` rows | DAF (`daf.storage.metadata_index`) | mirrors Document/Record ids | derived, rebuildable | SQLite | `ArtifactStore` |

DAF is explicitly, and correctly, **not** the owner of `Document`/
`Record`/`Observation` identity or semantics — it only durably persists
and indexes objects SCOUT constructs and validates. `daf/storage/artifact_store.py`'s
own docstring states this precisely: `artifact_id` is "a DERIVED,
non-authoritative hash," never a new identity SCOUT doesn't already
imply.

## 2. Current SCOUT architecture

SCOUT (`evidence/` + `scout/`, vendored, never modified by any DAF
phase) owns: the eight evidence categories (`Source`, `Document`,
`Record`, `Observation`, `Referent`, `ClaimedRelationship`, `DerivedValue`,
`DerivedGrounding` — `evidence/types.py`), their content-addressed
identity (`evidence/identity.py::content_hash`, a SHA-256 of canonical
JSON, deliberately excluding epistemic/temporal fields —
`confidence`/`retrieved_at`/`extracted_at`/`derived_at`), structural
admission (`evidence/admission.py`'s eight `admit_*` functions — pure
validation, never construction; e.g. `admit_document` rejects empty
content or an unknown `source_id`; `admit_observation` rejects empty
`record_ids`/unknown record/empty `extraction_method`/empty `content`),
and the in-memory `EvidencePool` (`evidence/pool.py`) that everything
above operates on.

`scout.pipeline.run_scout(adapter, extractor, pool)` is the **one-door**
entry point DAF's `AcquisitionOrchestrator` calls: it builds `Source`→
`Document`→`Record` from one `RawDocument`, admits each, runs the
extractor to get `ExtractionCandidate`s, builds and admits an
`Observation` per candidate, and returns a tuple of `ScoutFinding`
(bundling the admitted objects plus retrieval-metric fields —
`novelty`/`connectivity`/`redundancy`/`source_diversity`/
`evidence_density`/`bridge_potential`/`fep_signal` — computed by
`evidence.metrics`/`evidence.fep_interface`, still inside `scout/`, never
persisted by DAF) plus `ScoutAdmissionFailure`s. **SCOUT never reaches
`core.canonical` at all** (its own module docstring says so explicitly).

## 3. Current State-Space architecture

This is the section where the task's assumed structure most needs
correcting. There is no single "State-Space" package — there are two
separate subsystems, both real and implemented, that never interact:

**(a) The Evidence/ModelState chain**, under `materials/`/`experiment/`/
`retrieval/`/`workbench/`:

- `materials.analysis.analyze(pool, engine, question) -> MaterialPropertyAnswer`
  (`materials/analysis.py`) — **read-only** interpretation: resolves a
  `Referent`, retrieves `Observation`s and `DerivedValue`s from the pool,
  groups them by "comparison context," and computes disagreement
  statistics (min/max/spread — explicitly "never an average, a ranking,
  or a chosen 'winner'," per its own module docstring). This is the
  closest thing to "scientific/domain interpretation" the task asks
  about, and it is purely a *reader* of the pool — `pool.put_*` never
  appears in this module.
- `materials.results.admit_experimental_result(pool, result, confidence, ...)`
  (`materials/results.py`) — the **one place** in the `materials/` layer
  that *writes*: constructs a new `Observation` via the same,
  unmodified `evidence.types.make_observation`/`evidence.admission.admit_observation`
  DAF's own acquisition path uses, from an `ExperimentalResult`
  (a `materials`-owned dataclass, not evidence). This is a **second,
  independent producer of evidence**, structurally parallel to DAF's own
  acquisition path but never touching DAF at all.
- `materials.model_state.ModelState` (`materials/model_state.py:255-271`)
  — a frozen dataclass with exactly two fields: `id: str` and
  `samples: Mapping[str, Tuple[Sample, ...]]`, where `Sample(value: float,
  observation_id: str)`. `id` is `content_hash({key: [(s.value,
  s.observation_id) for s in samples[key]] for key in sorted(samples)})`
  — the same `evidence.identity.content_hash` primitive, reused, **not**
  `core.canonical.version.compute_version_id` (confirmed: no reference to
  `core.canonical`/`compute_version_id` anywhere in `model_state.py`).
  `update(state, candidate, result, observation: Observation) -> ModelState`
  is the actual evidence→ModelState transition: it reads only
  `observation.content.get("value")` and `observation.id`, nothing else.
  `predict(state, candidate) -> Prediction` is the read side — a pure
  function of `(state.id, candidate.id)`, deliberately carrying no
  confidence/probability/calibration field beyond a sample mean and
  (2+ samples) population variance, "none is fabricated here" (module
  docstring).
- `experiment/session.py`/`experiment/step.py` — the actual, implemented
  (not merely specified) orchestration loop: `run_experiment_step`
  calls `admit_experimental_result` then `materials.model_state.update`,
  closing the `S_t → prediction → experiment → observation → S_{t+1}`
  loop `docs/EXPERIMENT_ARCHITECTURE.md` describes. A vendored-repo
  audit note in that same doc (Phase 62) once found this loop
  "mathematically closed but structurally disconnected: nothing
  sequences it end to end" — that finding is **stale**: `experiment/`
  now implements exactly that sequencing.

**(b) The Canonical/Morpho chain**, under `core/canonical/`/
`core/projection/`/`morpho/`:

- `core.canonical.state.CanonicalState(schema_version, fields: Mapping[str,
  Field], edges: Tuple[EdgeRecord, ...])` and `core.canonical.version.Version
  (id, parent, state, schema_version, provenance, timestamp)`, with
  `id = compute_version_id(state)` (SHA-256 over `{schema_version, fields,
  edges}` only — `core/canonical/version.py:77-78`).
- `core.projection.project.project_state(version) -> ProjectedState` — a
  pure, deterministic projection, explicitly "not estimation... no
  inference, no I/O" (module docstring).
- `morpho.compiler.compile_morpho(projected, config) -> MorphoDocument` —
  consumes `ProjectedState`, produces a geometric/executable
  representation (`morpho/ir.py`'s `Entity`/`Transform`/`Vec3`/
  `CoordinateFrame` types).

**Neither chain references the other.** `CanonicalState`/`Version` never
appear in `materials/`; `Observation`/`EvidencePool` never appear in
`core/canonical/`/`core/projection/`/`morpho/`. This is confirmed by the
vendored codebase's own architecture doc, `docs/ARCHITECTURE.md`: "`core/`
does not import `evidence/`; `evidence/` does not import
`core.canonical.validation`" — a deliberate, documented, and (by grep)
actually-enforced separation, not an accidental gap.

## 4–5 (embedded in 6–8). EDGAR / USGS / NOAA traces, and where each chain currently terminates

## 6. Trace: one real EDGAR object

```
SourceDefinition(source_id="edgar-filings", adapter_id="edgar-daily-index")   [DAF, daf.orchestration.source_registry]
        │
        ▼  AcquisitionRequest(source_id=..., parameters={year, quarter, since}, requested_at=...)
        │  [DAF, daf.orchestration.request — transient]
        ▼
EdgarDailyIndexSourceAdapter.fetch() -> Tuple[RawDocument, ...]   [DAF, daf.adapters.edgar_daily_index]
        │  RawDocument(source_name="SEC EDGAR", content=<raw .idx text>, locator="20260701", ...)
        ▼
scout.pipeline.run_scout(adapter, EdgarDailyIndexExtractor(), pool)   [SCOUT, vendored, unmodified]
        │  make_source -> Source; make_document -> Document (raw artifact = version, id = content-hash)
        │  make_record -> Record (locator="20260701" preserved verbatim)
        │  EdgarDailyIndexExtractor.extract(record) -> ExtractionCandidate(
        │      content={"date_filed": "20260701", "filing_count": 6593,
        │               "form_type_counts": {...}, "filings": [...]},
        │      extraction_method="text:edgar_daily_index_v1", confidence=1.0)
        │  make_observation -> Observation (admitted via evidence.admission.admit_observation)
        ▼
EvidencePool / DurablePool   [SCOUT type, DAF-persisted via daf.storage.filesystem_store.FilesystemEvidenceStore]
        │
        ▼
AcquiredArtifact(artifact_id=..., version_id=Document.id, locator="20260701", raw_content=...)
   [DAF, daf.orchestration.result — reports back to the caller, never persisted]
        │
        ▼  ??? — the chain STOPS here.
```

**The chain terminates before `materials`/`ModelState` — explicitly, not
by omission.** No code anywhere calls `materials.analysis.analyze` or
`materials.model_state.update` with an EDGAR-derived `Observation`.
Moreover, even if a caller wired the SAME `DurablePool` instance into
`materials.analysis.analyze`, the EDGAR `Observation.content` dict
(`date_filed`/`filing_count`/`form_type_counts`/`filings`) has **no
`"value"` key** — the one thing `materials.model_state.update` actually
reads off `observation.content`. This is a genuine, code-grounded
content-shape gap, not a wiring gap: nothing prevents connecting an
EDGAR-acquired pool into `materials/`, but nothing in the current
content shape would make that connection *meaningful* to
`ModelState.update` without new extraction-content-shape work — out of
this phase's scope, and not proposed here.

## 7. Trace: one real USGS object

```
UsgsEarthquakeSourceAdapter.fetch()   [DAF]
        │  RawDocument(locator="us6000ti8i", content=<event-detail JSON>, ...)
        ▼
scout.pipeline.run_scout(...)   [SCOUT, unmodified]
        │  Document.id = content_hash({source_id, content_hash(raw_content), retrieval_method})
        │  Record.locator = "us6000ti8i"  (STABLE across revisions)
        │  UsgsEarthquakeExtractor -> Observation.content = {"event_id": "us6000ti8i",
        │      "magnitude": 4.2, "updated": 1787371813040, "status": "reviewed", ...}
        ▼
EvidencePool  (Phase H: a REVISION re-fetch produces a NEW Document/Record/Observation
               triple, SAME artifact_id = content_hash({source_id, "us6000ti8i"}),
               DIFFERENT version_id/Document.id/Observation.id)
```

A revised acquired version does **not** automatically imply a
particular scientific-state transition, and the current code keeps
these genuinely separate: `ArtifactStore`/`MetadataIndex` (DAF) track
"two `Document`s share this `artifact_id`" as a pure acquisition-identity
fact — nothing about it constructs, updates, or even references a
`ModelState`. If a caller DID feed both the original and the revised
`Observation` into `materials.model_state.update` (via two separate
calls), each would append a distinct `Sample(value=magnitude,
observation_id=Observation.id)` to whatever `ModelState` cell
`resolve_model_state_key` computes for that `(formulation, property,
target_context)` — i.e. **evidence revision and model-state transition
are two separate operations even in the chain that DOES connect them**:
revision produces a new `Observation`; only an explicit `update(...)`
call (which nothing in DAF or the current pipeline issues automatically)
would turn that into a new `ModelState`. USGS's `Observation.content`
DOES have a numeric field (`"magnitude"`) but not one named `"value"` —
same content-shape gap as EDGAR, for the same reason (no DAF extractor
was designed against `materials.model_state`'s expected content shape,
because DAF's whole mandate through Phase K was acquisition/persistence,
never scientific interpretation).

## 8. Trace: one real NOAA window

```
NoaaWaterLevelSourceAdapter.fetch()   [DAF]
        │  RawDocument(locator="9999999:water_level:20260101:20260103",
        │              content=<JSON with 720 readings>, ...)
        ▼
scout.pipeline.run_scout(...)   [SCOUT, unmodified]
        │  ONE Document, ONE Record (the whole window) -- NOT one per reading
        │  NoaaWaterLevelExtractor -> ONE Observation.content = {
        │      "station_id": "9999999", "reading_count": 720,
        │      "quality_counts": {"p": N, "v": M},
        │      "readings": [{"time": ..., "value": ..., "quality": ...}, ...]}
        ▼
EvidencePool
```

Individual readings are **none of** "artifact," "record," or (standalone)
"observation" at the evidence-admission layer — they are plain data
*inside* one `Observation.content["readings"]` list, exactly the
"raw artifact vs. event" distinction Phase I deliberately chose (one
artifact per window, not per reading, to avoid a per-reading artifact
explosion — see `docs/DAF_NOAA_WATER_LEVEL_ADAPTER.md`). Interestingly,
each individual reading DOES have a field literally named `"value"` (the
water-level measurement) — but it is nested inside
`Observation.content["readings"][i]["value"]`, not at
`Observation.content["value"]` directly, so `materials.model_state.update`'s
`observation.content.get("value")` would currently read `None` for a
NOAA-window `Observation` even though the numeric information it wants
is present one level deeper. This is the clearest evidence in this
report that "evidence" (an admitted `Observation`) and "a `ModelState`-
ready sample" are related but **not identical** representations, and
that connecting them meaningfully is a real, nontrivial, deliberately-
out-of-scope design question — not a missing import.

## 9. Identity reconciliation table

| Identity | What it identifies | Determined by | Immutable? | Content-addressed? | Multiple can exist? | Owner |
|---|---|---|---|---|---|---|
| DAF `source_id` | one acquisition source configuration | operator choice (string) | no (mutable config) | no | one per source | DAF (`SourceDefinition`) |
| `evidence.types.Source.id` | one (kind, name) pair | `content_hash({kind, name})` | yes | yes | one per distinct (kind, name) | SCOUT |
| DAF `artifact_id` | "the same logical acquired thing across revisions" | `content_hash({source_id, locator})`, derived, never stored | yes (as a formula; not a stored field) | yes | one per (source, locator) | DAF (`ArtifactStore`/`daf.storage.identity`), **non-authoritative** |
| `version_id` (= `Document.id`) | one specific acquired revision | `content_hash({source_id, content_hash(raw_content), retrieval_method})` | yes | yes | many per artifact_id (Phase H/I proved this live) | SCOUT |
| `content_hash` (bare) | raw bytes alone | `content_hash(raw_content)` | yes | yes | many Documents can share one (Phase K's dedup proof) | SCOUT identity primitive, used by DAF's BlobStore too |
| `Record.id` | one raw structural unit within a Document | `content_hash({document_id, locator, raw_content})` | yes | yes | 1:1 with Document in every DAF adapter so far | SCOUT |
| `Observation.id` | one extracted fact | `content_hash({record_ids: sorted, extraction_method, content: sorted})` — **excludes** `confidence`/`extracted_at` | yes | yes | many per Record if re-extracted differently | SCOUT |
| `ModelState.id` | one point-in-time set of per-cell samples | `content_hash({key: [(value, observation_id), ...] for key in sorted(samples)})` | yes | yes | one per distinct sample-set (a new sample = a new id) | `materials` |
| `core.canonical.Version.id` (`VersionId`) | one frozen CanonicalState | `compute_version_id(state)` = SHA-256 over `{schema_version, fields, edges}` | yes | yes | one per distinct CanonicalState content | `core.canonical` — **entirely separate identity space, never intersects with any evidence id** |

**No accidental conflation found.** Every identity above is genuinely
distinct in what it names and how it's computed; `artifact_id` is
explicitly documented as derived/non-authoritative (never a competing
"real" identity); `ModelState.id` and `Version.id` both reuse
`content_hash`-style hashing as a *pattern*, never the same *function
call* or the same *input shape* — they are independent identity spaces
that happen to follow the same discipline, not one identity leaking into
the other.

## 10. Temporal reconciliation table

| Timestamp | Meaning | Layer | Excluded from identity? |
|---|---|---|---|
| `AcquisitionRequest.requested_at` | when a DAF acquisition run was requested | acquisition metadata | n/a (not part of any evidence identity) |
| `Document.retrieved_at` | when DAF/SCOUT fetched this content | acquisition metadata (SCOUT-typed, DAF-supplied) | yes — excluded from `Document.id` |
| source event time (e.g. USGS `properties.time`, NOAA reading `t`) | when the real-world event/reading occurred | source semantics, lives INSIDE `Observation.content`, never promoted to a metadata field | n/a — it's data, not identity |
| source revision time (USGS `properties.updated`; NOAA `q` preliminary/verified flag) | when the SOURCE last changed its own record | source semantics, also inside `Observation.content` (or, for NOAA, only a coarse flag — no NOAA revision timestamp is exposed by the source at all, honestly documented as a limitation in Phase I) | n/a |
| `AcquisitionCheckpoint.updated_at` | when a plan last successfully ran | acquisition-progress metadata | n/a — not evidence at all |
| `Observation.extracted_at` | when extraction ran | evidence metadata (SCOUT-typed) | yes — excluded from `Observation.id`, deliberately, so identical re-extraction produces the same id regardless of when it happened |
| `core.canonical.Version.timestamp` | when a CanonicalState version was created | Canonical-chain metadata | yes — excluded from `Version.id` |
| (no "model-state time" field exists) | — | `ModelState` carries no timestamp at all — only `id` and `samples`; the closest thing is each `Sample`'s `observation_id`, traceable back to `Observation.extracted_at` if needed | n/a |

No universal timestamp field was introduced or is recommended — six
genuinely distinct temporal concepts already exist, each scoped to
exactly the layer that needs it, matching the task's own instruction not
to collapse them.

## 11. Provenance boundary

Three distinct, already-separated provenance mechanisms exist:

1. **Acquisition provenance** (DAF): `AcquiredArtifact`/`AcquisitionResult`
   (transient, never persisted as a ledger), `ArtifactStore.list_versions`/
   `MetadataIndex` (durable, but purely "which version_ids exist for this
   artifact_id," never "why" or "by what computation"). `daf/orchestration/result.py`'s
   own docstring states this explicitly: "explicitly NOT scientific
   evidence, NOT provenance, and NOT an execution ledger."
2. **Evidence provenance** (`evidence.provenance.ancestry_of`, consumed
   by `materials.analysis`): traces which `DerivedValue`s/`Observation`s
   a claim ultimately derives from, via `DerivedValue.derived_from` and
   `ClaimedRelationship.observation_id` — a real, implemented mechanism,
   entirely within the evidence/materials layer, never touching DAF.
3. **Scientific derivation** (`DerivedValue`/`DerivedGrounding`): a
   `DerivedValue` names its own `derived_from` (other Observations or
   DerivedValues) and `method` — this is SCOUT/evidence-typed, admitted
   through the same `evidence.admission` gate, and is the mechanism
   `materials.analysis`'s disagreement statistics would flow through if
   ever promoted to a stored derived claim (not currently exercised by
   any DAF-adjacent code).

**No execution ledger exists anywhere in this codebase**, and none is
introduced by this report. DAF persistence (`FilesystemEvidenceStore`/
`BlobStore`/`MetadataIndex`) answers "what was acquired and when," never
"what computation produced this value and how it can be re-verified" —
that would be zkVM/verifiable-execution provenance, explicitly out of
scope for this phase and every phase before it.

## 12. Representation/dynamics analysis

For each major boundary object, grounded in what the current code
actually does with it (not what it could theoretically support):

- **`RawDocument`**: preserves exactly the bytes a source returned.
  Enables: byte-exact replay, corruption detection, re-extraction with a
  different extractor later. Must not claim: any interpretation —
  it has no `content` semantics beyond "this is what the source said."
- **`Document`/`Record`**: preserve raw content plus a stable grouping
  key (`locator`) and provenance (`source_id`, `retrieval_method`,
  `retrieved_at`). Enable: `ArtifactStore`'s artifact/version distinction,
  restart-safe replay (Phases B/G/H/I/K all proved this live). Must not
  claim: scientific meaning — `Document.content` is text/JSON, not a
  validated fact.
- **`Observation`**: preserves one extractor's structured reading of a
  Record, with an extraction method and (optional, range-checked)
  confidence. Enables: `materials.analysis`'s disagreement statistics
  (multiple Observations about the same thing are kept, never
  collapsed), `materials.model_state.update` (when content shape
  matches). Must not claim: a single "correct" value — the whole
  Referent/`ClaimedRelationship`/multi-Observation design exists
  specifically so contradictory evidence coexists rather than getting
  silently averaged away (`ClaimedRelationship`'s identity deliberately
  includes `observation_id` for exactly this reason).
- **`ModelState`**: preserves a per-cell sample history sufficient to
  compute a mean and (2+ samples) variance. Enables: `predict()`'s
  reproducible, side-effect-free `Prediction`. Must not claim:
  confidence/calibration/likelihood beyond what a sample mean/variance
  actually supports — `Prediction`'s own docstring is explicit that this
  is deliberate, not an oversight.
- **`CanonicalState`/`Version`**: preserves a frozen, schema-typed field/
  edge graph. Enables: pure, deterministic projection
  (`project_state`) and Morpho compilation. Must not claim: any relation
  to acquired evidence or predictive state — by design, it has none.
- **DAF's `MetadataIndex`**: preserves fast lookup over already-canonical
  identity fields. Enables: `list_versions`/`find_by_content_hash`/
  `list_source_artifacts` without a full scan (Phase K). Must not claim:
  to be a second raw-content or identity authority — it is rebuildable
  from the filesystem specifically so it never becomes one.

## 13. State-Space boundary — does the code support Evidence → Observation → ModelState update without DAF owning ModelState construction?

**Yes, and it already does, structurally — DAF never constructs
`ModelState` anywhere, and nothing about the existing `materials.model_state.update`
signature requires it to.** The actual separation realized in code:

```
DAF        = acquisition + durable acquisition state   [confirmed: zero ModelState/CanonicalState reference anywhere in daf/]
SCOUT      = evidence discovery/admission               [confirmed: evidence.admission never touches materials/core.canonical]
materials  = scientific interpretation + ModelState      [confirmed: analyze()/update() operate only on EvidencePool + materials-owned types]
```

The one place this differs from the task's clean four-layer picture:
there is no evidence of a distinct "State-Space" package consuming
`materials.model_state` from outside — `experiment/` (which DOES call
`update()`/`predict()`) is itself part of the same vendored repository
`materials/` lives in, not a separate system DAF or an external caller
reaches through some documented interface. If "State-Space" in the
task's vocabulary means `materials.model_state` + `experiment`, that
already exists and is already correctly separated from DAF. If it means
something else not yet present in this codebase, that thing does not
exist yet and this report makes no claim about it.

## 14. Future Morpho attachment point

**Already wired, but to the OTHER chain.** `morpho.compiler.compile_morpho(
projected: ProjectedState, config) -> MorphoDocument` already consumes
`core.projection.project.project_state`'s output, which itself is a pure
projection of `core.canonical.Version`. Morpho's real attachment point —
already implemented — is downstream of `CanonicalState`/`Version`, not
downstream of `ModelState`/`Observation`. If a future phase wanted
Morpho to visualize/compile something derived from acquired evidence or
model state, that would require a NEW bridge from
`materials.ModelState`/`Observation` into a `CanonicalState`-shaped
representation first (since `core.canonical` has no evidence-awareness
at all today) — a nontrivial design question this phase does not
attempt to answer, consistent with "Do NOT implement Morpho integration"
and "Only determine where Morpho would conceptually attach."

## 15. Future GraphRAG/vector attachment point

No graph/vector projection exists in this codebase today (confirmed:
`evidence.trust_graph.build_trust_graph` exists and is used by
`scout.pipeline`/`retrieval.engine` for retrieval-quality metrics —
connectivity, bridge potential — but this is NOT a general-purpose graph
database or GraphRAG layer; it's a small, purpose-built trust-scoring
structure over `Referent`/`ClaimedRelationship`). Per Phase J's own
storage-architecture conclusion (reaffirmed here): any future graph/
vector/search projection must be built by READING from
`EvidencePool`/`FilesystemEvidenceStore`/`MetadataIndex` (canonical) and
producing a derived, rebuildable index — never a second authority. The
correct seam is exactly where `materials.analysis`/`retrieval.engine`
already sit today: read-only consumers of the pool, one layer above
DAF's own storage, with no write path back into canonical evidence
except through the existing `evidence.admission` gate.

## 16. Future State-Space Transformer interface

No class named `Transformer`/`StateSpaceTransformer` exists in this
codebase (confirmed by direct grep). The role that name implies is
already implemented as `materials.model_state.predict(state, candidate)
-> Prediction` — a pure function needing only a `ModelState` and an
`ActionCandidate`, with **zero dependency on DAF, `EvidencePool`, or how
the underlying evidence was acquired** (confirmed: `predict`'s signature
takes no pool, no Document, no Record — only `state: ModelState`). This
already satisfies invariant I2 below. The minimal future interface, IF
DAF-acquired evidence is ever meant to feed this: a function of shape
`Observation -> Optional[Sample-ready value]` (i.e., something that knows
how to read `observation.content` for a GIVEN extraction method and
produce the `value`/context `materials.model_state.update` expects) —
this is a content-shape adapter, not a DAF change and not a
`materials`/vendored change; it would live wherever the caller wiring
DAF's pool into `materials.model_state.update` lives, outside both
codebases. Not proposed or built here.

## 17. Dependency matrix

| | may depend on | may read | may write | may construct | must not depend on |
|---|---|---|---|---|---|
| **DAF** | `scout`, `evidence` (via `scout.pipeline`/`evidence.pool` only) | `EvidencePool` (via `DurablePool`) | `Document`/`Record`/`Observation` (only via `run_scout`, never directly) | `RawDocument`, `AcquiredArtifact`, DAF catalog/checkpoint types | `materials`, `core.canonical`, `experiment`, `retrieval`, `workbench`, `morpho` (confirmed: zero imports) |
| **SCOUT** (`scout`+`evidence`) | nothing outside itself | its own pool | its own 8 categories | `Source`/`Document`/`Record`/`Observation`/etc. via `make_*` | `daf`, `materials`, `core.canonical`, `morpho` (confirmed) |
| **Evidence** (`evidence.types`/`pool`/`admission`/`identity`) | nothing | itself | itself | 8 categories | everything above it |
| **Scientific domain** (`materials`) | `evidence` | `EvidencePool` | new `Observation`s (via `admit_experimental_result`, same gate as DAF) | `ModelState`, `Prediction`, `ExperimentalResult`, `ActionCandidate` | `daf`, `core.canonical`, `morpho` (confirmed: zero imports) |
| **Canonical State** (`core.canonical`) | nothing outside itself | itself | itself | `CanonicalState`, `Version` | `evidence`, `materials`, `daf` (confirmed) |
| **ModelState** (`materials.model_state`) | `evidence.types`/`evidence.identity` (for `Observation`/`content_hash`) | `Observation.content`/`.id` only | nothing (pure) | `ModelState`, `Sample`, `Prediction` | `core.canonical`, `daf` |
| **State-Space / experiment** (`experiment`) | `materials`, `evidence` | `EvidencePool`, `ModelState` | `Observation` (only via `materials.results.admit_experimental_result`, per `docs/EXPERIMENT_ARCHITECTURE.md`'s own explicit rule) | `ExperimentSession`, `ExperimentStepResult` | `daf`, `core.canonical` |
| **Morpho** | `core.canonical`, `core.projection` | `Version`/`ProjectedState` | nothing (pure compiler) | `MorphoDocument` | `evidence`, `materials`, `daf` (confirmed) |
| **GraphRAG (future)** | would read `EvidencePool`/DAF storage | canonical evidence | nothing back into canonical storage | a derived graph index | must never become raw-artifact authority |
| **Vector/Search (future)** | same as above | same | nothing back | a derived index | same |

## 18. Architectural invariants — verdicts

| Invariant | Verdict | Evidence |
|---|---|---|
| **I1.** DAF never constructs ModelState. | **HOLDS** | Zero `ModelState`/`materials` reference anywhere in `daf/` (grep-confirmed). |
| **I2.** State-Space never needs to know how a raw artifact was acquired. | **HOLDS** | `materials.model_state.update`/`predict` take `Observation`/`ModelState`/`ActionCandidate` only — no `RawDocument`, no adapter, no DAF type anywhere in their signatures. |
| **I3.** Raw artifact bytes remain recoverable independently of scientific interpretation. | **HOLDS** | `Document.raw_content` (via DAF's `BlobStore`, Phase K) is retrievable with zero dependency on `materials`/`experiment` ever having run. |
| **I4.** Evidence identity is not ModelState identity. | **HOLDS** | Section 9's table: `Observation.id` and `ModelState.id` are different hash inputs over different fields, computed by different functions in different modules. |
| **I5.** Acquisition checkpoints are not scientific state. | **HOLDS** | `AcquisitionCheckpoint` (`daf.catalog.checkpoint`) has no relationship to `ModelState` in code or in concept — confirmed by its own docstring ("acquisition PROGRESS, never scientific state"). |
| **I6.** Model-state transitions are not acquisition events. | **HOLDS** | `materials.model_state.update` is called only from `experiment/step.py`, never from any DAF module; DAF's `AcquisitionResult`/checkpoint advancement never references `ModelState`. |
| **I7.** Search/graph/vector representations are projections, not authorities. | **HOLDS (for what exists)** | The one graph-shaped structure that exists (`evidence.trust_graph`) is a derived retrieval-quality metric, recomputed from the pool, never a second store of record. No vector/search projection exists yet to violate this. |
| **I8.** A revised artifact version does not automatically imply a particular scientific-state transition. | **HOLDS** | Confirmed directly by the USGS trace (section 7): a new `Document`/`Observation` from a revision does not, by itself, call `materials.model_state.update` — that requires a separate, explicit call nothing in the current pipeline issues automatically. |

**All eight invariants hold, without modification, in the current code.**
None required a fix to become true — they were each already true, and
this phase's job was to verify and document that precisely, not repair
anything.

## 19. Unresolved questions

- **Content-shape mismatch**: no current DAF extractor (arXiv, EDGAR,
  USGS, NOAA, local_dataset, incremental_dataset) produces
  `Observation.content` with a top-level `"value"` key —
  `materials.model_state.update`'s one required input field. Connecting
  real DAF-acquired evidence to `ModelState` meaningfully would require
  either a new extraction convention or an adapter function between
  `Observation.content` and `Sample` — not attempted here, flagged for a
  future phase to decide deliberately rather than accidentally.
- **No demonstrated end-to-end run**: no test in this repository (DAF's
  or vendored) constructs a `DurablePool`, runs a real DAF adapter
  through it, and THEN passes that same pool into
  `materials.analysis.analyze`/`materials.model_state.update`. The
  connection is structurally possible (both expect the same
  `EvidencePool` interface) but has never actually been exercised
  together — an empirical gap between "provably possible" and "proven
  to work," worth closing with a real (not merely hypothetical) test in
  a future phase if this connection is ever intended to be used.
  Nothing about it is incorrect; it is simply unexercised.
  The other three "unresolved" items the task's framing might expect —
  a dedicated evidence→ModelState "resolver" component, a documented
  external interface for a "State-Space" system distinct from
  `materials`, and any relationship between the Canonical/Morpho chain
  and acquired evidence — do not currently exist as gaps to close,
  because (per sections 3, 13, 14) the code shows they are either
  already implemented in a different shape than assumed
  (`materials.model_state.update` IS the resolver) or genuinely absent
  by design (no code connects the two chains, and none should be added
  without a real, motivating case).

## 20. Recommendation for the next phase

This phase's stop condition is met: the architecture can now answer,
precisely and from code, what DAF owns, what SCOUT owns, what
constitutes scientific evidence, what constitutes Canonical State, what
constitutes ModelState, what crosses each boundary, which identities and
timestamps belong to which layer, and which representations are
authoritative versus projections (sections 1–17 above). No code defect
was found that prevents any established invariant from being
represented, so per the task's own gate, nothing was implemented.

A reasonable next phase, if this reconciliation is acted on, would
address the one concrete, code-grounded gap section 19 identifies: a
small, deliberate empirical proof that a DAF-populated `DurablePool` can
be handed directly to `materials.analysis.analyze` and (for a source
whose extractor is adjusted to emit a `"value"`-shaped `Observation.content`)
`materials.model_state.update`, without any change to either DAF's or
`materials`'s existing public interfaces. That is a validation exercise,
not a new abstraction — consistent with every "reconciliation before
industrialization" phase this project has followed since Phase F. Per
this phase's own explicit stop condition, no such work is begun here.
