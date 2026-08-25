# Phase P — Reconciliation, and Closing the Acquisition→Analysis Seam

*(Repository phases are lettered; the prompt labels this "Phase 16". Continues
from Phase O — `docs/PHASE_15_TRAJECTORY_AND_DECISION_DYNAMICS.md` — at `ce26ff9`.)*

This phase began as the reconciliation Phase O recommended, and did **not** stop
there: the reconciliation identified a concrete, code-grounded, under-composed
capability with fully established semantics, so it was built, run, measured,
fixed, and tested in this same phase.

---

## 1. The reconciliation

### What SCOUT already provides (vendored, internally at Phase ~101)

| Layer | Modules |
|---|---|
| Evidence admission | `evidence/` — `Observation`, `Record`, `Document`, `Referent`, `ClaimedRelationship` |
| Acquisition contract | `scout/interface.py` — `SourceAdapter`, `Extractor`, `ExtractionCandidate`, `ExtractedEntity`, `ExtractedRelation`; `scout/pipeline.py` — `run_scout` |
| Interpretation | `materials/analysis.py`, `materials/iteration.py`, `materials/specification.py` |
| Decision | `materials/decision.py`, `materials/candidates.py`, `materials/evaluation.py`, `materials/selection.py` |
| Experiment | `materials/plan.py`, `materials/design.py`, `materials/campaign.py`, `materials/results.py` |
| Predictive state | `materials/model_state.py`, `materials/assessment.py` |
| Trajectory & comparison | `materials/trajectory.py`, `materials/diagnostics.py` |
| Value & ranking | `materials/value.py`, `materials/utility.py`, `materials/ranking.py`, `materials/information.py`, `materials/optimization.py` |
| Other | `counterfactual.py`, `ensemble.py`, `surrogate.py`, `audit.py`, `workbench/` |

### What DAF provides

| Layer | Modules |
|---|---|
| Adapters | `arxiv`, `edgar_daily_index`, `local_dataset`, `incremental_dataset`, `noaa_water_level`, `usgs_earthquakes` |
| Extractors | one per adapter |
| Catalog & scheduling | `catalog/{plan,plan_catalog,source_catalog,checkpoint,history,cli}`, `scheduling/{due,runner}` |
| Orchestration | `orchestration/{orchestrator,bindings,adapter_registry,source_registry,request,result}` |
| Durable storage | `storage/{durable_pool,filesystem_store,artifact_store,blob_store,metadata_index,identity,serialization}` |

### The reconciliation's finding

Phase O concluded the deterministic scientific substrate was complete. It is. But
mapping the two sides against each other exposed something none of the three prior
phases had noticed, because none of them had ever *measured* it:

> **Every scientific analysis in Phases M, N and O ran on hand-built fixture
> evidence.** Not one of them ran on evidence DAF actually acquired.

Phases M and N each acquired real evidence *and* built fixture evidence, and proved
they coexist in one `DurablePool` — but the acquired half was only ever inspected
at the evidence boundary. It never reached `materials.analysis`. The reason turned
out to be structural, not incidental.

---

## 2. The frontier, established by measurement

Running the composition directly — real acquisition into a `DurablePool`, then
`reevaluate_program` over that pool — produced:

```
observations: 2 | referents: 0 | relationships: 0
REEVALUATE FAILED: KeyError "no Referent with natural_key 'process-std-190c' in pool"
```

**Every DAF extractor emits `entities=()`, `relations=()`.** That is correct for
arXiv, EDGAR, NOAA and USGS — none of those sources declares what its records are
*about* in any structural way, and inventing entities for them would be exactly the
ontology invention the DAF layer must avoid. But the consequence is that
DAF-acquired evidence has no trust-graph anchors, and `materials.analysis`
reaches observations only by traversing the graph outward from a named referent.
Acquired evidence was therefore *unreachable by the entire scientific layer*.

Meanwhile `scout.pipeline.run_scout` (`scout/pipeline.py:160-207`) has **always**
supported the missing half — it turns each `ExtractedEntity` into an admitted
`Referent` and each `ExtractedRelation` into an admitted `ClaimedRelationship`,
resolving endpoints by label. **No DAF extractor had ever used that path.**

This is a genuine under-composition with fully established semantics on both
sides: nothing needed to be designed, only connected. It is also entirely outside
Phase 15 §22's deferred list.

---

## 3. Smallest implementation

Two files touched, ~170 lines of production code, no new abstraction:

**`daf/extractors/graph_dataset.py` (new)** — `GraphDatasetExtractor`, the first
DAF extractor to populate `entities`/`relations`. It transports a subgraph the
**source record itself declares**:

```json
{
  "id": "ts-001",
  "property": "tensile_strength", "value": 78, "unit": "MPa",
  "entities":  [{"label": "formulation-f1",   "kind": "formulation"},
                {"label": "process-std-190c", "kind": "process"}],
  "relations": [{"from": "formulation-f1", "to": "process-std-190c",
                 "type": "tested_during"}]
}
```

**`daf/orchestration/bindings.py`** — `graph_dataset_binding()`, pairing the
**existing, unmodified** `LocalDatasetSourceAdapter` with the new extractor.
Acquisition mechanics are unchanged; only interpretation of the record differs.

### Design constraints honoured

- **Structural transport, not domain logic.** The extractor knows nothing about
  materials, formulations, processes, properties or measurements, and deliberately
  does **not** require a `property`/`value` pair — requiring one would encode the
  domain assumption this layer must not make. Labels, kinds and relation types are
  the source's own vocabulary. Proven behaviourally by
  `test_extractor_transports_declared_structure_without_inventing_any`, which
  extracts an astronomy record carrying no property or value at all.
- **Whether evidence is scientifically usable stays SCOUT's judgment.**
  `materials.analysis` reads `content` and decides for itself.
- **Fails loudly, never silently.** A missing/empty `entities`, a malformed entity,
  or a relation endpoint not among the record's own declared labels raises
  `GraphDatasetExtractionError`. Degrading to an empty graph would silently
  reintroduce the exact unreachable-evidence condition this phase exists to fix.
- **No new adapter, no new evidence type, no SCOUT change.** Vendored submodule
  `git status --short` is clean.

---

## 4. The defect found by running it

The first end-to-end run succeeded structurally but produced a wrong scientific
result:

```
observed_status = 'INCOMPARABLE'
observed_comparison_groups = (
  ComparisonGroup(context={'id': 'ts-001', 'unit': 'MPa'}, values=(78.0,)),
  ComparisonGroup(context={'id': 'ts-002', 'unit': 'MPa'}, values=(84.0,)),
)
```

**Root cause.** The paired adapter *requires* a per-record `id` and uses it to
build `Record.locator` (`f"{path}#{id}"`). That `id` was flowing into
`Observation.content`. `materials.analysis._comparison_context` — by deliberate
Phase 53 design — treats **every** non-value content key as part of an
observation's comparison context. Since `id` is unique per record, every acquired
measurement landed in its own single-member comparison group. The property's
status would have been `INCOMPARABLE` *permanently*, no matter how much evidence
was acquired, and the system would have proposed `measurement:context` candidates
forever while never being able to satisfy them.

This is precisely the "two kinds of context" hazard Phase M documented — an
acquisition concern silently corrupting scientific semantics.

**Where the fix belongs.** Not in `materials`: SCOUT is right not to guess which
content keys are incidental, and that restraint is load-bearing. DAF is the layer
that knows `id` is its own locator. So `id` joins `entities`/`relations` as a
structural key consumed by the extractor and never passed into content.

**Nothing is lost.** Acquisition identity is fully preserved on `Record.locator`,
which is where an acquisition identity belongs. Asserted directly in
`test_acquisition_locator_never_enters_scientific_comparison_context`, which
recovers `ts-001`/`ts-002` from the record locators.

**After the fix:**

```
content: {'property': 'tensile_strength', 'unit': 'MPa', 'value': 78}
content: {'property': 'tensile_strength', 'unit': 'MPa', 'value': 84}
ComparisonGroup(context={'unit': 'MPa'}, values=(78.0, 84.0))
observed_status = 'CONFLICTING_EVIDENCE'
candidates: [('model_validation:unspecified','PREDICTED'), ('measurement:repeat','OBSERVED')]
```

Acquired evidence now yields **the same scientific state** (`CONFLICTING_EVIDENCE`,
values 78/84, a `measurement:repeat` candidate) that Phases N and O obtained from
hand-built fixtures. That equivalence is the real proof the composition is sound.

---

## 5. Tests

`tests/test_acquired_evidence_analysis.py` — 7 tests, no fixture `Observation`
admitted anywhere in the acquisition path:

| Test | Proves |
|---|---|
| `test_acquisition_admits_the_declared_evidence_graph` | `run_scout` admits declared entities/relations as real `Referent`s/`ClaimedRelationship`s |
| `test_acquired_evidence_alone_drives_the_scientific_decision_layer` | the call that previously raised `KeyError` now yields a real gap analysis, decision and candidate set; every backing observation has `extraction_method='json:graph_dataset_v1'` |
| `test_acquisition_locator_never_enters_scientific_comparison_context` | regression lock on §4's defect, including locator recoverability |
| `test_acquired_evidence_reaches_a_model_state_transition` | continuity with Phases N/O — acquired evidence motivates a campaign, result and `ModelState` (`predicted_value == 81.0`) |
| `test_acquisition_to_decision_is_deterministic` | same source file → two independent pools → identical observation ids, referent ids, decision, candidates |
| `test_extractor_transports_declared_structure_without_inventing_any` | domain neutrality, via an astronomy record with no property/value |
| `test_extractor_rejects_malformed_declarations_loudly` | five distinct malformed inputs each raise `GraphDatasetExtractionError` |

### Two test bugs found and fixed during the run

1. `pool.all_documents()` does not exist — `DurablePool` exposes
   `all_observations`/`all_referents`/`all_claimed_relationships`/
   `all_derived_values`/`all_derived_groundings`. Reached the document via
   `pool.get_record(obs.record_ids[0]).document_id`.
2. The first determinism test compared acquisitions from **different file paths**
   and failed. That failure was correct: `Record.locator` embeds the dataset path,
   so the same records acquired from a different path are legitimately different
   evidence with different ids — **provenance is part of identity here, by
   design**. The test was corrected to acquire one shared source file into two
   independent pools, which is the meaningful determinism claim.

---

## 6. Validation

| Check | Result |
|---|---|
| DAF suite | **289 passed** (282 prior + 7 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule cleanliness | `git status --short` clean |
| `mypy daf/` | Success, **43** source files (42 + 1 new) |
| `ruff` | `UP035`/`UP006` (`typing.Tuple`/`Dict`/`List`) only — the repo-wide convention every existing DAF extractor already carries; new module matches its neighbours |

No existing test was weakened, skipped or deleted. No existing DAF behaviour
changed: `local_dataset_binding` and every other binding are untouched, and the
new `id`-stripping applies only to the new `graph-dataset` adapter id.

---

## 7. Boundaries preserved

- **SCOUT unmodified.** No vendored file changed. The new extractor uses only the
  published `scout.interface` contract.
- **No domain logic in DAF.** The extractor supplies no vocabulary; it transports
  what the source declares, and rejects what it cannot transport faithfully.
- **CanonicalState / Morpho** — not connected, unchanged from Phases L/N/O.
- **Layer separation** — acquisition still ends at admission; interpretation still
  begins at `materials.analysis`. What changed is only that acquired evidence now
  carries the graph anchors the interpretation layer requires.

---

## 8. Limitations

1. **The dataset is still local and synthetic.** This phase closed the *structural*
   seam; it did not acquire real materials measurements from a live scientific
   API. `GraphDatasetExtractor` works against any source whose records declare
   their own structure, but no such live source is wired up.
2. **Only one DAF source declares a graph.** NOAA/USGS/EDGAR/arXiv still emit
   empty entity sets, and their evidence remains unreachable by `materials`.
   Whether any of them *should* declare structure is a per-source scientific
   judgment, deliberately not made here.
3. **`id`-stripping is scoped to this extractor.** Other adapters with their own
   incidental-metadata keys could hit the same comparison-context hazard. There is
   no general mechanism preventing it, and inventing one would require guessing
   which keys are incidental — the thing SCOUT deliberately refuses to do.
4. **Experimental results are still supplied, not acquired.** Unchanged from
   Phase M: no DAF source is a materials experiment.
5. **Expected information gain remains `NOT_DETERMINABLE`.** Untouched by design.

---

## 9. Recommendation for the next phase

The acquisition→analysis seam is now closed and regression-locked. The two honest
remaining frontiers are unchanged in substance but now better positioned:

- **(a) A real declared-structure source.** Limitation 1 is now a small step
  rather than an architectural one: the transport exists, so this reduces to
  finding a real dataset whose records identify their subjects. This is the
  cheapest remaining increase in honesty.
- **(b) Expected information gain.** Still the real scientific frontier, still
  squarely inside Phase 15 §22's deferred list. It should not be started without
  an explicit decision that the deferral has ended.

Recommendation: **(a)**, then revisit (b) as a deliberate scope decision.

---

*Phase P halts here: reconciled, built, run, measured, fixed, tested, documented,
committed and pushed.*
