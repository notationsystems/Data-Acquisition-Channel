# Phase M — Evidence / Model-State Integration Audit and Minimal Bridge

**Status:** audited, validated, and implemented — the smallest possible
footprint: **one new test file, zero new production code, zero changes
to DAF, zero changes to vendored `evidence`/`materials`.** This phase
proves the exact path Phase L's reconciliation identified — admitted
`Observation` → `materials.model_state.update()` → `ModelState` →
`predict()` — already works correctly using existing, unmodified public
interfaces on both sides, while honestly documenting the one real
DAF-source limitation the audit found: none of EDGAR, USGS, or NOAA can
honestly participate in the full chain without fabricating materials-
science semantics they do not have.

---

## Pre-implementation report

### 1. Exact ModelState contract

`materials/model_state.py:255-271`. `ModelState(id: str, samples:
Mapping[str, Tuple[Sample, ...]])`, frozen, `__post_init__` sorts and
freezes every cell. `Sample(value: float, observation_id: str)`
(`:244-252`). `id` is `evidence.identity.content_hash` over
`{key: [(value, observation_id), ...] for key in sorted(samples)}`
(`make_model_state`, `:303-314`) — deterministic, order-independent by
construction. `EMPTY_MODEL_STATE = make_model_state({})` (`:317`) is the
canonical starting state.

### 2. Exact Observation contract

`evidence/types.py`. `Observation(id, record_ids: Tuple[str,...],
extraction_method: str, content: Mapping[str, object], confidence: float,
extracted_at: str)`. Identity (`make_observation`) hashes `{record_ids:
sorted, extraction_method, content: sorted items}` — **excludes**
`confidence`/`extracted_at`. `content` is a completely open mapping;
nothing in `evidence.types`/`evidence.admission` constrains its keys or
requires a `"value"` field — `admit_observation` only checks
non-emptiness (`evidence/admission.py:55-77`).

### 3. Exact `update()` contract

`materials/model_state.py:420-455`. `update(state: ModelState, candidate:
ActionCandidate, result: ExperimentalResult, observation: Observation) ->
ModelState`. Reads exactly: `state.samples`, `candidate.id`,
`candidate.target_context`, `result.candidate_id`, `result.formulation.id`,
`result.property`, `observation.content.get("value")`, `observation.id`.
Asserts `candidate.id == result.candidate_id` and that `state` contains
no hypothetical sample (Phase 61's counterfactual guard). Resolves the
cell via `resolve_model_state_key(result.formulation.id, result.property,
candidate.target_context)` and appends one `Sample` via the shared
`_transition` function. Never mutates `state`; always returns a new
object. Confirmed by the module's own "Update sufficiency" (Phase 55)
docstring section and reproduced independently here (see tests below).

### 4. Exact `predict()` contract

`materials/model_state.py:359-381`. `predict(state: ModelState, candidate:
ActionCandidate) -> Prediction`. Reads only `state.samples`,
`candidate.formulation.id`, `candidate.property`, `candidate.target_context`,
`candidate.id`. Pure, side-effect-free — no `EvidencePool`, no
`RetrievalEngine`, no wall-clock. `Prediction` carries `predicted_value`/
`uncertainty` (both `None` below the sample count that defines them —
never defaulted to zero), `state_id`, `candidate_id`, `model_state_key`,
and no id of its own (a pure function of `(state.id, candidate.id)`).

### 5. Why the "value" requirement exists

`observation.content.get("value")` is read at exactly one place —
`update()`'s line 452 — and is asserted numeric (`isinstance(value, (int,
float))`, `:453`) before being appended as a `Sample.value`. This is not
an arbitrary convention: it is the ONE piece of information `update()`
actually needs from an `Observation` beyond its `id` — the measured
outcome itself. It is scalar (a single `float`), has no explicit unit
field (units, if relevant, are `materials.analysis`'s "evidence
comparison context" concern — see item 7 below — never part of the
scalar `update()` reads), does not itself participate in confidence
(confidence gates admission via `evidence.admission`, entirely upstream
of and separate from `update()`), and categorical observations are
**not supported** — `update()` hard-asserts numeric, with no fallback.
Missing values are not supported either: `observation.content.get("value")`
returning `None` fails the `isinstance` assertion immediately, by
design (a `None`/missing value must never silently become 0.0 or be
skipped — an `AssertionError` is the correct, honest failure mode).

### 6. ModelState resolution semantics

Already Phase 53's own, already-correct conclusion, reconfirmed by
direct reading rather than trusted from prior docs: `resolve_model_state_key(
formulation_id, property, target_context)` (`materials/model_state.py:274-300`)
keys each cell by `(formulation, property, target_context)`, where
`target_context` is always `ActionCandidate.target_context` — **not**
`(formulation, property)` alone. The module's own extensive docstring
(`:1-219`) already documents exactly why this phase does not need to
re-derive: Phase 52 conflated two different "context" concepts (evidence-
comparison context vs. model-conditioning context) and Phase 53 fixed it
by sourcing `target_context` identically on both `predict`'s and
`update`'s side. This audit found no reason to revisit that resolution —
it is correct, and this phase changes nothing about it.

### 7. Evidence-context vs. model-context distinction

Restated precisely because it is the crux of why no new "universal
context" abstraction is introduced: **evidence comparison context**
(`materials.analysis._comparison_context`) is every `Observation.content`
key except `property` and the measured value — mechanically derived,
necessarily including incidental metadata (`unit`, instrument, etc.)
alongside genuine experimental conditions, because it cannot tell them
apart. **Model conditioning context** (`ActionCandidate.target_context`)
is a caller-curated declaration of which conditions a specific
`Criterion` actually cares about. These overlap in vocabulary
(`temperature` might appear in both) but are structurally different
objects from different sources. `update()` correctly uses only the
second. This audit confirms — by reading the code, not by assumption —
that inventing a scheme to reclassify `Observation.content` keys into
"real" conditioning variables versus incidental metadata would be
exactly the invented ontology this phase's task forbids, and the
existing code already avoids it correctly.

### 8. CanonicalState relevance

**Not relevant, confirmed by re-derivation, not merely cited from Phase
L.** `update`/`predict`/`resolve_model_state_key`/`ModelState`'s own
module (`materials/model_state.py`) contains zero references to
`core.canonical` (grep-confirmed). Neither function needs a canonical
relationship graph, a schema-typed field, or an edge structure —
`ModelState`'s only inputs are a formulation `Referent`, a property
string, a context mapping, and a numeric value. `CanonicalState` provides
none of the transformations `update`/`predict` actually perform (mean/
variance over a sample list). **Decision: kept out of the integration
path, unchanged from Phase L's finding.**

### 9. Morpho relevance

**Not relevant to this bridge.** Per Phase L's own investigation
(reaffirmed, not re-derived, since nothing in this phase's audit of
`materials/model_state.py` touches Morpho at all): `morpho.compiler.compile_morpho`
consumes `core.projection.ProjectedState`, itself derived purely from
`core.canonical.Version` — a chain with no `ModelState`/`Observation`
involvement whatsoever. This phase's bridge does not touch Morpho, and
no future relationship is proposed here beyond what Phase L already
determined (`CanonicalState → Morpho`, never `ModelState → Morpho`,
unless a future phase deliberately builds a NEW `ModelState →
CanonicalState` bridge first — not attempted or motivated here).

### 10. Identity mapping

| Identity | Computed by | Scope |
|---|---|---|
| `Observation.id` | `evidence.identity.content_hash({record_ids, extraction_method, content})` | one extracted fact |
| `ExperimentalResult.id` | `content_hash({campaign_id, candidate_id, formulation_id, property, content, record_id, extraction_method})` | one application-level "what was obtained" record |
| `ActionCandidate.id` | `content_hash({action_class, requirement_ids: sorted})` | one proposed information-acquisition action |
| `ModelState.id` | `content_hash({cell: sorted[(value, observation_id)]})` | one point-in-time set of per-cell samples |

No identity collision or conflation found; each is a genuinely distinct
content-addressed space, exactly as Phase L's own identity table already
established for the evidence side.

### 11. Temporal mapping

`update`/`predict`/`ModelState`/`Prediction` carry **no timestamp field
at all** — confirmed directly (neither dataclass has a time-shaped
field). The closest thing is `Sample.observation_id`, traceable back to
`Observation.extracted_at` if a caller needs it. No time field was added
by this phase — the honest finding, stated plainly per the task's own
instruction, is that ModelState has no temporal semantics of its own,
and none is introduced here merely because DAF has timestamps.

### 12. Information-loss analysis

For an `Observation` flowing (via `ExperimentalResult`) into `update()`:

| Preserved | Transformed | Ignored by `update()` (but not discarded — still in the pool) | Unavailable to ModelState entirely |
|---|---|---|---|
| `observation.content["value"]` (as `Sample.value`) | none — read verbatim | `observation.content`'s every OTHER key (`unit`, etc.) | `observation.extracted_at`, `observation.confidence`, `record_ids` |
| `observation.id` (as `Sample.observation_id`) | none | `result.campaign_id`, `result.record_id`, `result.extraction_method` | any `ClaimedRelationship`/`Referent` beyond `result.formulation` |
| `result.formulation.id` + `result.property` + `candidate.target_context` (as the resolved cell key) | combined via `resolve_model_state_key`, itself a content-hash, not a lossy transform | — | — |

Nothing is silently discarded from the DURABLE record — every ignored
field remains fully present and queryable in the `EvidencePool`/DAF
storage; only `ModelState`'s own in-memory representation narrows to
exactly what its statistics need. This is the correct, minimally-lossy
shape: passing `unit`/`record_ids`/`confidence` into `ModelState` would
be passing irrelevant metadata into predictive state, which the task
explicitly forbids.

### 13. Candidate bridge designs considered

- **Design 1 — a new `resolve_model_observation(observation) -> ModelObservation`
  function**, per the task's own "Outcome B" template. **Rejected**:
  `resolve_model_state_key` already deliberately declines to accept an
  `Observation` polymorphically (its own docstring, quoted in item 6/7
  above, explains exactly why — an `Observation` has no `target_context`
  of its own, and accepting one would invite the wrong input back in).
  Building a NEW function that DOES accept a bare `Observation` would
  either (a) require inventing where `target_context` comes from for a
  bare `Observation` (impossible without guessing), or (b) just
  re-expose `update()`'s existing four-argument shape under a new name,
  adding indirection with no semantic gain.
- **Design 2 — a new evidence-content convention forcing every DAF
  extractor to emit `content["value"]`**. **Rejected**: this would
  require every DAF adapter (EDGAR, USGS, NOAA) to fabricate a
  materials-science "value" for content that has no such meaning
  (a daily filing count, an earthquake magnitude, a sensor window) —
  exactly the "arbitrary context fields"/fabrication the task's stop
  condition names explicitly.
- **Design 3 — do nothing beyond a test.** Use the EXISTING, unmodified
  `update`/`predict`/`resolve_model_state_key` API directly, with the
  ALREADY-EXISTING campaign-assembly pipeline (`materials.iteration`/
  `materials.candidates`/`materials.evaluation`/`materials.selection`/
  `materials.plan`/`materials.design`/`materials.campaign`) supplying
  `ActionCandidate`/`ExperimentalResult` exactly as
  `vendor/scout-retrieval-agent/tests/test_materials_model_state.py`
  already proves works. **Selected.**

### 14. Selected design, and why it is the smallest correct one

**No new abstraction anywhere.** The existing `materials.model_state`
API, together with the existing `materials.results.admit_experimental_result`
write boundary and the existing campaign-assembly pipeline, is already
the complete, correct, sufficient bridge — Outcome A, in the task's own
terms, for the *mechanism*. What was actually missing was not code but
**proof**: no test anywhere (DAF's or the vendored repository's) had
ever demonstrated that a `daf.storage.durable_pool.DurablePool`
(DAF-owned, persistent) works correctly as the `EvidencePool` this whole
chain expects, or that DAF-acquired evidence and materials-admitted
experimental evidence can coexist in one durable pool. This phase
implements exactly that proof, and nothing else — one new test file
(`tests/test_model_state_integration.py`), zero new production code.

For the three real DAF sources built so far, the audit's honest,
non-hidden finding (Outcome C's spirit, scoped correctly): EDGAR, USGS,
and NOAA are all passively-acquired external data, not the record of an
executed materials experiment testing a candidate formulation. None can
supply a semantically valid `ActionCandidate`/`ExperimentalCampaign`
without fabricating a materials-science narrative that does not exist
for "SEC filed a document today" or "an earthquake occurred" or "a tide
gauge recorded a reading." This is documented, not hidden, and no
bridge was built to paper over it.

---

## Post-implementation report

### 1. Audit findings

Summarized in the pre-implementation report above (items 1–9); all
findings were reached by direct reading of `materials/model_state.py`,
`materials/results.py`, `materials/candidates.py`, `materials/campaign.py`,
`materials/decision.py`, `materials/analysis.py`, `evidence/types.py`,
`evidence/admission.py`, and the vendored test
`tests/test_materials_model_state.py`, none of which were modified.

### 2. Actual ModelState semantics

See item 1 above. `ModelState` is a deterministic empirical estimator —
sample mean/variance per `(formulation, property, target_context)` cell,
recomputed on demand, nothing incrementally accumulated, nothing
physically or causally modeled. Confirmed unchanged by this phase.

### 3. Actual Observation semantics

An `Observation` guarantees: content-addressed identity over
`(record_ids, extraction_method, content)`; an open, extractor-defined
`content` mapping with no required keys beyond non-emptiness; a
required, range-checked `confidence`; and `extracted_at` excluded from
identity. It guarantees NOTHING about `content`'s internal shape — the
"value" convention is a `materials`-side expectation of ONE particular
consumer (`update()`), never an `evidence`-layer contract.

### 4. "value" semantics

See item 5 above: scalar, numeric (`int`/`float`), required (no missing-
value support), no unit, no categorical support, read at exactly one
line of `materials/model_state.py`.

### 5. State-resolution decision

Preserved exactly as Phase 53 left it: `(formulation, property,
target_context)`, never `(formulation, property)` alone. This audit
re-derived and confirmed the reasoning independently rather than citing
it — no change made.

### 6. CanonicalState decision

Kept out of the Evidence → ModelState path — confirmed by direct
re-reading, not merely re-cited. See item 8 above.

### 7. Morpho decision

Not touched, not integrated. Its future attachment point remains
`CanonicalState → core.projection → Morpho`, per Phase L, reaffirmed
here. See item 9 above.

### 8. Bridge design

No new bridge abstraction. See items 13–14 above for the full
reasoning and the three designs considered.

### 9. Files changed

```
tests/test_model_state_integration.py   (new, 8 tests)
docs/PHASE_13_MODEL_STATE_INTEGRATION.md   (this file)
```

Nothing else. No file under `daf/` (production code), no file under
`vendor/scout-retrieval-agent/` (vendored `evidence`/`scout`/`materials`/
`core`/`morpho`) was touched.

### 10. Invariants preserved

All of Phase 52/53's invariants hold, unmodified, verified by this
phase's own tests (not merely re-asserted from the vendored suite):
immutable `ModelState` (`test_historical_model_state_is_unchanged_after_update`);
deterministic `ModelState.id`
(`test_deterministic_state_transition_same_inputs_same_state_id`);
`Prediction.state_id` correctness across sequential transitions
(`test_sequential_updates_and_predictions_reference_the_correct_state`);
`update(state, ...)` returning a new state, never mutating the old one
(same test); `predict`/`update` never touching `EvidencePool`
(`test_update_and_predict_never_access_evidencepool`, proven by
monkeypatching every `EvidencePool` method to raise and confirming
neither function trips it); no DAF dependency anywhere in
`materials.model_state` (`test_model_state_module_has_no_daf_dependency`,
AST-verified against the vendored source directly).

### 11. Information-loss analysis

See item 12 above — a table of preserved/transformed/ignored/unavailable
fields, concluding the transformation is minimally lossy at the durable-
storage level (nothing is discarded from the pool) and appropriately
lossy at the `ModelState` level (irrelevant metadata correctly excluded
from predictive state).

### 12. Revision semantics

`test_revised_artifact_version_does_not_automatically_mutate_model_state`
uses REAL USGS revision data (Phase H's own synthetic fixtures, real
adapter/extractor/orchestrator code) to prove directly: acquiring a
revised artifact version (same `artifact_id`, new `version_id`, `is_new
=True`) leaves an already-built `ModelState` byte-for-byte unchanged.
The sequence is, and must remain: revised evidence (an acquisition-layer
fact) → an explicit, separate `update()` call (a scientific-domain
decision, never automatic) → a new `ModelState`. DAF's acquisition layer
never silently mutates scientific state, confirmed by test, not merely
asserted by design intent.

### 13. Temporal semantics

`ModelState`/`Prediction`/`update`/`predict` have no temporal field —
confirmed and documented (item 11 above), not augmented. No time field
was added anywhere by this phase.

### 14. Real-data integration

`test_real_noaa_observation_reaches_the_evidence_boundary_in_a_durable_pool`
acquires a real (Phase I synthetic-fixture-backed, real-code) NOAA
water-level window through DAF's actual `daf.orchestration`/
`scout.pipeline.run_scout` path into a real `DurablePool`, confirms it
is genuinely durable and admitted, and confirms — empirically, not by
assertion — that its `content` has the numeric information `update()`
eventually wants (`content["readings"][i]["value"]`) one level deeper
than `update()` reads (`content["value"]` directly), and stops there
deliberately. `test_model_state_transition_from_a_fixture_result_shares_the_real_acquisition_pool`
then reuses the SAME `DurablePool` (already containing that real NOAA
evidence) for a controlled fixture experimental-campaign scenario,
proving the two coexist and that the full `update`/`predict` chain
works correctly against a `DurablePool`, not just a bare vendored
`EvidencePool`.

### 15. Tests

8 new tests in `tests/test_model_state_integration.py`, all deterministic,
none a large matrix or benchmark: real-evidence-boundary proof, fixture-
chain state transition, historical-state immutability, cross-fixture-
instance determinism, sequential update/predict consistency, USGS
revision-does-not-mutate-state, no-EvidencePool-access proof, no-DAF-
dependency proof.

### 16. Ruff

`ruff check tests/test_model_state_integration.py`: zero correctness
findings after removing four genuinely unused imports found during
development. The one remaining finding (`I001`, blank-line-separated
vendored/DAF import grouping) matches the same established, deliberate
style convention every EDGAR/USGS/NOAA integration test file in this
project already uses — matched, not refactored away, per every prior
phase's identical precedent.

### 17. Mypy

`mypy daf/` → **Success: no issues found in 42 source files** (unchanged
— this phase added no file under `daf/`, so DAF's own type-checked
surface is identical to Phase K's).

### 18. Full validation

`pytest tests/` (DAF, all ten phases): **270 passed** — 262 (Phases
A–L) + 8 new. Full vendored State-Space suite: **1273 passed, 0 failed,
0 files modified** — confirming this phase, like Phase L, never touched
a single vendored file, only read it and called its existing public
API from a new DAF-side test.

### 19. Remaining limitations

- No current DAF extractor (arXiv, EDGAR, USGS, NOAA, local_dataset,
  incremental_dataset) can honestly supply `ExperimentalResult`/
  `ActionCandidate` scaffolding, because none of their sources are
  materials-experiment results. This is not a defect to fix — it is an
  accurate reflection of what those sources actually are. A future
  source that genuinely IS an executed-experiment result (e.g. a lab
  instrument's data export) could connect meaningfully; none built so
  far is that shape, and none should be forced to pretend otherwise.
- The controlled fixture scenario in this phase's tests mirrors the
  vendored test suite's own `_setup()` pattern closely, by design (a
  proven, already-tested recipe, not a new invention) — but this means
  it is not independently novel science, only a faithful reuse of an
  existing, working example, exactly as intended.
- `materials.model_state.update()`'s reliance on a full
  `ExperimentalCampaign`/`ActionCandidate` assembly (itself requiring
  `materials.iteration`/`materials.candidates`/`materials.evaluation`/
  `materials.selection`/`materials.plan`/`materials.design`/
  `materials.campaign` — the Phase 27–44 pipeline) means connecting ANY
  new evidence to `ModelState`, from any source, always requires a
  deliberate, upstream act of experimental design (a `Criterion`, a
  `MaterialProgramQuery`) by a human or a future planning system — never
  something an acquisition layer alone can supply. This is accurately
  reflected, not worked around, by this phase's tests.

### 20. Recommended Phase N

Per this task's own stop condition, this phase is complete: a
demonstrated, semantically justified path from an admitted `Observation`
through explicit model-domain resolution (the existing, unmodified
`resolve_model_state_key`/`update`/`predict`) to `ModelState` and the
existing state dynamics — proven against a real `DurablePool` containing
real DAF-acquired evidence, without contaminating DAF, SCOUT, Evidence,
CanonicalState, or Morpho with responsibilities belonging elsewhere. No
further Evidence/ModelState bridge work is justified by current
evidence. Per the task's own explicit non-goals (Gaussian processes,
Bayesian models, neural surrogates, active learning, information-gain
optimization, acquisition-policy optimization, GraphRAG, vector search,
Morpho integration, CUDA, zkVM, execution provenance), none of those are
recommended here either. If a future phase is warranted, the most
honest next question — raised but explicitly not answered by this phase
— is whether a genuinely experiment-shaped DAF source (as opposed to a
passively-acquired public dataset) is worth building specifically to
exercise this now-proven bridge end-to-end with real, non-fixture
scientific data; that is a source-selection decision for a future phase
to make deliberately, not a default extension of this one.
