# Phase N — Experimental Result → ModelState Closed-Loop Integration

**Status:** audited, implemented, and validated — again the smallest
possible footprint: **one new test file, zero new production code.**
This phase proves the complete, executable scientific state-transition
loop `ModelState_t → predict → ActionCandidate → ExperimentalCampaign →
ExperimentalCampaignEntry → ExperimentalResult → Observation → update()
→ ModelState_(t+1)` object-by-object, extends it to a three-state
trajectory with recoverability, proves trajectory-level (not just
single-step) determinism, and — the one genuinely new piece of coverage
neither Phase M nor the vendored suite exercised directly — proves the
information-value seam (`materials.information.estimate_information_value`
+ `materials.model_state.ModelStateInformationValueModel`) correctly
reports a "before vs. after" change in predictive uncertainty across a
real state transition.

---

## Pre-implementation report

### 1. Current experiment/result lifecycle

`materials.results.make_experimental_result(campaign, entry, content,
record_id, extracted_at, extraction_method=...) -> ExperimentalResult`
(`materials/results.py:101-140`): validates `content["property"] ==
entry.property`, derives `id` via `content_hash` over
`{campaign_id, candidate_id, formulation_id, property, content,
record_id, extraction_method}`. `materials.results.admit_experimental_result(
pool, result, confidence, relationship_type="tested_during") ->
(Observation, ClaimedRelationship)` (`:143-190`): the ONLY function in
`materials/` that writes to `EvidencePool` — resolves the process
`Referent` first (so a missing one can never orphan an admitted
`Observation`), constructs and admits a new `Observation` via the
unmodified `evidence.types.make_observation`/`evidence.admission.admit_observation`,
then a `ClaimedRelationship` linking the result's formulation to the
process referent via the unmodified `admit_claimed_relationship`.

### 2. Candidate lifecycle

`materials.candidates.make_action_candidate(action_class, requirement_ids,
formulation, property, role, target_context, existing_evidence_ids=()) ->
ActionCandidate` (`materials/candidates.py:266-284`): `id` derived from
`content_hash({action_class, requirement_ids: sorted})`. In practice
built by `generate_candidates(specification) -> CandidateSet`
(`:325+`), driven by an `ExperimentSpecification` that itself comes from
`reevaluate_program`'s gap analysis — never hand-constructed in normal
use, though nothing prevents it.

### 3. Campaign lifecycle

The full assembly chain, confirmed by direct reading and reused
verbatim by this phase's tests, exactly as
`vendor/scout-retrieval-agent/tests/test_materials_model_state.py`'s own
`_setup()` already does: `reevaluate_program(pool, engine, query,
criteria) -> MaterialsIteration` → `generate_candidates(iteration.specification)
-> CandidateSet` → `evaluate_candidates(candidates) -> ...` →
`select_candidates(evaluations, policy) -> selection` →
`assemble_experiment_plan(selection) -> plan` →
`assemble_experimental_design(plan) -> design` →
`assemble_experimental_campaign(design) -> ExperimentalCampaign`, whose
`entries: Tuple[ExperimentalCampaignEntry, ...]` each carry
`candidate_id`/`formulation`/`property`/`target_context` copied verbatim
from the underlying design entry (`materials/campaign.py:97-116`).

### 4. Observation construction

Confirmed unchanged from Phase M: `evidence.types.make_observation(
record_ids, extraction_method, content, confidence, extracted_at)`,
identity over `{record_ids: sorted, extraction_method, content: sorted}`,
`confidence`/`extracted_at` excluded. `admit_experimental_result` is the
only caller in `materials/` that constructs one, from
`result.content`/`result.record_id`/`result.extraction_method`/
`result.extracted_at` — nothing new here this phase.

### 5. ModelState update contract

Confirmed unchanged from Phase M (`materials/model_state.py:420-455`):
`update(state, candidate, result, observation) -> ModelState`, reading
only `candidate.id`/`.target_context`, `result.candidate_id`/
`.formulation.id`/`.property`, `observation.content['value']`/`.id`.
Rejects a state containing a hypothetical sample; asserts
`candidate.id == result.candidate_id`.

### 6. Prediction contract

Confirmed unchanged: `predict(state, candidate) -> Prediction`
(`materials/model_state.py:359-381`), pure over `state.samples` and
`candidate.formulation.id`/`.property`/`.target_context`/`.id`.

### 7. Existing information/value integration

**Read directly this phase, not merely cited from Phase M.**
`materials.information.estimate_information_value(candidate,
current_iteration: MaterialsIteration, model: InformationValueModel) ->
InformationValueEstimate` (`materials/information.py:150-165`) is a thin,
deterministic wrapper: computes `materials.value.evaluate_information_value(
candidate, current_iteration)` (the structural, non-numeric
`CandidateInformationValue` — Phase 46), then calls `model.estimate(
information_value)`. `InformationValueModel` is a `Protocol`
(`:75-109`) requiring `name: str` (read-only property) and
`estimate(information_value) -> (Optional[float], Optional[str])`.
`materials.model_state.ModelStateInformationValueModel` (`materials/model_state.py:458-494`)
is a REAL, already-implemented conforming model: constructed with one
`ModelState` snapshot, its `estimate()` calls `predict(self._state,
information_value.evaluation.candidate)` and reports the resulting
`prediction.uncertainty` (a real sample variance once 2+ samples exist,
`None`/`NOT_DETERMINABLE` below that — never fabricated). **This is
already the complete "state → uncertainty/information gap" half of
section 13's loop, fully implemented, never previously exercised in a
test by either Phase M or this repository's own vendored suite in
combination with a real multi-step trajectory.**

### 8. Exact missing link, if any

**None found.** Every object and function this loop needs already
exists, is already correctly implemented, and composes correctly — the
audit reproduced the same conclusion Phase M reached, independently,
for this phase's broader scope (a full multi-state trajectory plus the
information-value seam). See item 10 below.

### 9. Candidate implementation options

Given no missing link was found, the only real design question was TEST
scope/shape, not production code:

- **Option 1 — one giant integration test covering everything.**
  Rejected: the task explicitly separates concerns (object-by-object
  loop, trajectory, determinism, information-value, revision-safety)
  into distinct required proofs; one monolithic test would bury
  failures and make each invariant harder to verify independently.
- **Option 2 — several small, focused tests, one per required proof,
  sharing one small fixture-construction helper.** Selected — matches
  every prior phase's own testing discipline ("focused tests only,"
  Phase M's own precedent) and keeps each failure attributable to
  exactly one invariant.

### 10. Selected smallest implementation

**Zero production code.** One new test file
(`tests/test_experimental_state_loop.py`, 5 tests) reusing the exact
campaign-assembly recipe already proven in the vendored suite and in
Phase M's own test file, run against a real
`daf.storage.durable_pool.DurablePool` throughout (not a bare
`EvidencePool`), per section 16's explicit request. No file under
`daf/` or `vendor/scout-retrieval-agent/` was touched.

---

## Post-implementation report (deliverable, per section 21)

### 1. Architecture audit

See the pre-implementation report above (items 1–8) — reached by direct
reading of `materials/model_state.py`, `materials/results.py`,
`materials/candidates.py`, `materials/campaign.py`, `materials/design.py`,
`materials/information.py`, and the vendored test
`tests/test_materials_model_state.py`, none of which were modified.
`materials/decision.py`/`materials/analysis.py`/`materials/value.py`
were re-confirmed against Phase M's own prior audit and found unchanged
and correctly understood there; not re-derived from scratch here where
Phase M's findings already stood.

### 2. Actual object lifecycle

```
MaterialProgramQuery + Criterion(s)
        │  reevaluate_program(pool, engine, query, criteria)
        ▼
MaterialsIteration (program_answer, decision, audit, gap_analysis, specification)
        │  generate_candidates(iteration.specification)
        ▼
CandidateSet → ActionCandidate (id, action_class, formulation, property, target_context, ...)
        │  evaluate_candidates → select_candidates → assemble_experiment_plan
        │  → assemble_experimental_design → assemble_experimental_campaign
        ▼
ExperimentalCampaign { entries: Tuple[ExperimentalCampaignEntry, ...] }
        │  make_experimental_result(campaign, entry, content, record_id, extracted_at)
        ▼
ExperimentalResult (candidate_id, formulation, property, content)
        │  admit_experimental_result(pool, result, confidence)
        ▼
Observation (admitted, durable) + ClaimedRelationship (tested_during)
        │  update(state, candidate, result, observation)
        ▼
ModelState_(t+1)
        │  predict(state, candidate)
        ▼
Prediction (predicted_value, uncertainty, state_id, model_state_key)
```

### 3. State-transition diagram

```
S0 (EMPTY_MODEL_STATE)
  │  predict(S0, candidate) -> Prediction(predicted_value=None, sample_count=0)
  │  update(S0, candidate, result_1, observation_1)
  ▼
S1
  │  predict(S1, candidate) -> Prediction(predicted_value=76.0, uncertainty=None, sample_count=1)
  │  estimate_information_value(candidate, iteration, ModelStateInformationValueModel(S1)) -> NOT_DETERMINABLE
  │  update(S1, candidate, result_2, observation_2)
  ▼
S2
  │  predict(S2, candidate) -> Prediction(predicted_value=80.0, uncertainty=16.0, sample_count=2)
  │  estimate_information_value(candidate, iteration, ModelStateInformationValueModel(S2)) -> ESTIMATED(16.0)
```

`S0.id != S1.id != S2.id`, all pairwise distinct; `S0`/`S1` remain
independently re-predictable after `S2` exists, with results identical
to what was computed at the time (`test_three_state_trajectory_with_recoverability`).

### 4. Experiment/result semantics

An `ExperimentalResult` is "what was actually obtained" for one campaign
entry — `content` is an open mapping the caller supplies, required to
already include `content["property"]` matching the entry's property
(enforced, never injected). No confidence/quality/probability field
exists on it; confidence is supplied separately, at admission time, to
`admit_experimental_result`.

### 5. Observation semantics

Unchanged from Phase M's audit: content-addressed identity over
`(record_ids, extraction_method, content)`, `confidence`/`extracted_at`
excluded from identity, `content` fully open. This phase's tests
directly inspect `observation.content.get("value")`,
`observation.record_ids`, and `observation.id` at the object level
(`test_full_object_by_object_state_transition_loop`), not merely
trusting that `update()` succeeded.

### 6. ModelState transition semantics

Proven directly: `update()` returns a new `ModelState` whose relevant
cell gains exactly one new `Sample(value, observation_id)`; the prior
`ModelState` object is provably unchanged (`state_t.samples == {}` still
holds after `update()` returns); `Prediction.state_id` always matches
the state it was computed against, at every point in a 3-state
trajectory.

### 7. DAF boundary

Untouched. `daf/` gained no new file, no modified file. `DurablePool` is
used in every test exactly as `daf.storage.durable_pool.DurablePool` —
DAF's own, unmodified, Phase K-built class — demonstrating (not merely
asserting) that DAF's durable evidence storage and the materials-side
experimental/state machinery compose with zero coupling of ownership:
DAF never constructs, references, or imports `ModelState`/`ActionCandidate`/
`ExperimentalResult` anywhere in its own code (confirmed unchanged since
Phase L/M's own AST-level checks — this phase adds no new DAF-side
import to check, since it adds no DAF-side code at all).

### 8. SCOUT boundary

Untouched. Every admission in this phase's tests goes through the
unmodified `evidence.admission` gates (`admit_document`/`admit_record`/
`admit_referent`/`admit_observation`/`admit_claimed_relationship`),
exactly as `scout.pipeline.run_scout` itself does for DAF's own
acquisitions. No vendored file was modified; the vendored regression
suite (1273 tests) passes unchanged.

### 9. CanonicalState decision

Not introduced. This phase's audit of the full multi-step trajectory —
including the information-value seam — found no computation anywhere in
`materials.model_state`/`materials.information`/`materials.candidates`/
`materials.campaign` that references or requires `core.canonical` in any
form. The Phase L/M finding stands, reconfirmed against this phase's
broader scope: `CanonicalState` is genuinely irrelevant to the Evidence
→ ModelState loop, not merely unused by convenience.

### 10. Information-value boundary

**Fully supported by existing machinery, now proven by test.**
`test_information_value_before_and_after_state_update` demonstrates the
complete `state → uncertainty/information gap → candidate → experiment →
result → updated state` loop section 13 asks about, using
`ModelStateInformationValueModel` + `estimate_information_value` exactly
as they already exist: before a second, independent observation exists,
the model honestly reports `NOT_DETERMINABLE` (not a fabricated number);
after it exists, it reports the real sample variance (`16.0`), matching
`predict()`'s own computation exactly. `estimate_before.information_value
== estimate_after.information_value` confirms only the MODEL's own
number changed between the two calls — the underlying structural
candidate/requirement/gap/audit chain (Phase 46) was correctly
unaffected, proving the "before vs. after" comparison is honest and not
an artifact of re-evaluating something that should have stayed fixed.
**No active-learning/selection/ranking logic exists or was added** —
this seam only ever answers "how uncertain is the model at this state,"
never "which experiment should be run next."

### 11. Implementation

Zero production code. One new test file:
`tests/test_experimental_state_loop.py` (5 tests, ~290 lines, including
one shared campaign-assembly helper and one shared result-admission
helper, both reused across all 5 tests).

### 12. Tests

1. `test_full_object_by_object_state_transition_loop` — section 15's
   required test: inspects the actual `ActionCandidate`/
   `ExperimentalCampaign`/`ExperimentalCampaignEntry`/`ExperimentalResult`/
   `Observation`/`ModelState`/`Prediction` objects at every boundary, not
   merely final success.
2. `test_three_state_trajectory_with_recoverability` — section 18: S0 →
   S1 → S2, all pairwise distinct, S0/S1 independently re-predictable
   after S2 exists with byte-identical results.
3. `test_trajectory_is_deterministic_when_repeated` — section 7,
   extended beyond Phase M's single-step determinism proof to a whole
   two-transition trajectory, built independently twice.
4. `test_information_value_before_and_after_state_update` — section 13,
   genuinely new coverage (see item 10 above).
5. `test_revised_evidence_in_the_durable_pool_does_not_mutate_existing_state`
   — sections 8/16/17 combined: new evidence admitted into the SAME
   durable pool an existing `ModelState` was built from never
   retroactively changes that state.

### 13. Determinism proof

`test_trajectory_is_deterministic_when_repeated`: two independently
constructed pools/campaigns/results (separate `tmp_path` roots, fresh
objects throughout) produce identical `candidate.id`, `s1.id`, and
`s2.id`. Combined with `test_three_state_trajectory_with_recoverability`'s
re-prediction checks, this covers both "the same trajectory reproduces
the same identities" and "a historical state's own answer never drifts
after later states are built."

### 14. Historical-state proof

Embedded in tests 1, 2, and 5 above: `state_t.samples == {}` (test 1)
and `predict(s0, candidate) == prediction_s0` /
`predict(s1, candidate) == prediction_s1` (test 2) after later states
exist; test 5 additionally proves a historical state survives NEW,
UNRELATED evidence being admitted into its own source pool afterward.

### 15. Trajectory proof

`test_three_state_trajectory_with_recoverability` (item 2 above) is the
first concrete demonstration in this repository of a 3-point State-Space
trajectory built entirely from real (if fixture-scoped) experimental
observations, with every state independently recoverable — the
literal "S0 → S1 → S2" the task's stop condition names explicitly.

### 16. Durable-pool integration

Every test in this phase uses `daf.storage.durable_pool.DurablePool`,
never a bare `EvidencePool` — extending Phase M's single-transition
proof to a full multi-state trajectory plus the information-value seam,
still with zero coupling: `DurablePool` is used exactly as DAF's own
acquisition code would use it, and the materials-side machinery never
knows or cares that the pool happens to be durable.

### 17. Remaining limitations

- Identical to Phase M's own honestly-stated limitation, unchanged: no
  current DAF source (EDGAR, USGS, NOAA, arXiv, local/incremental
  dataset) can supply a real `ExperimentalResult`/`ActionCandidate`,
  because none represent an executed materials experiment. This phase's
  trajectory, like Phase M's, is built from a controlled fixture
  scenario for that reason — an accurate reflection of what these
  sources are, not a limitation this phase's tests could or should paper
  over.
- The information-value proof (item 10) demonstrates the seam is wired
  and honest, not that its statistics are scientifically meaningful
  beyond what a sample mean/variance ever claims (per `model_state.py`'s
  own extensive "what this model is, and is not" documentation, already
  audited in Phase M and reconfirmed, not re-litigated, here).
- No new `InformationValueModel` implementation was written or
  motivated — `ModelStateInformationValueModel` already existed and
  already sufficed for everything this phase needed to prove.

### 18. Recommendation for Phase O

Per this task's own stop condition, this phase is complete: a real,
tested, three-state trajectory proves `ModelState_t → prediction →
candidate → experiment → result → observation → ModelState_(t+1)`,
DAF/SCOUT do not own `ModelState`, evidence does not silently become
predictive state, revised/new evidence does not silently mutate
scientific state, historical `ModelState` is immutable, state identity
is deterministic (at both the single-transition and whole-trajectory
level), predictions reference the correct historical state, and the
trajectory is explicitly recoverable. Per the task's own explicit
non-goals, no Gaussian process/Bayesian optimization/neural surrogate/
active learning/acquisition optimization/FEP policy/GraphRAG/vector
search/Morpho/geometric manifold/CUDA/zkVM/execution provenance/
distributed execution/scheduler infrastructure work is recommended here
either. The one honest, unresolved question — raised in both this and
Phase M's reports, not answered by either — remains whether a genuinely
experiment-shaped DAF source is worth building specifically to replace
this phase's fixture scenario with real, non-fixture scientific data;
that is a deliberate source-selection decision for a future phase, not
a default extension of this one.
