# Phase O — State-Space Trajectory and Decision Dynamics

*(This repository's phases are lettered A, B, C, … The task prompt labels this
"Phase 15"; it is Phase O in the repository's own sequence, continuing from
Phase N — `docs/PHASE_14_EXPERIMENTAL_STATE_LOOP.md` — at commit `5fe450a`.)*

---

## 0. Headline finding

**Every mechanism this phase asks to be designed already exists in the vendored
State-Space system, built by its own Phases 56 and 57.** The audit did not find a
missing capability; it found that the DAF-side phases had been reasoning about a
system substantially more complete than assumed.

Specifically, section 7's hypothetical

```
analyze_transition(S_t, S_(t+1)) -> TransitionAnalysis
```

is, essentially exactly, the already-implemented

```
materials.diagnostics.diagnose_transitions(trajectory, candidate, assessments)
    -> StateTransitionDiagnosticSet
```

and section 3's hypothetical trajectory representation is the already-implemented
`materials.trajectory.ModelStateTrajectory`.

Per sections 3, 7 and 10 ("if the existing architecture already represents
trajectory sufficiently: **preserve it**"; "do not add merely for descriptive
completeness"), **no production code was written in this phase** — in DAF or in
the vendored packages. What did not exist anywhere, and what this phase
contributes, is the **composition** of these layers into the single closed
decision cycle the stop condition names, exercised over DAF's own durable pool
and proven deterministic across independent runs.

This is the third consecutive phase to reach an "existing representation is
sufficient" outcome. That is worth stating plainly rather than presenting as a
fresh discovery each time: the vendored system is internally at Phase ~101
(`tests/test_phase101_fiber_architecture.py`), and the DAF-side phase sequence
has been rediscovering, one layer at a time, machinery SCOUT already shipped.

---

## 1. Audit findings

Modules read in full for this phase: `materials/trajectory.py`,
`materials/diagnostics.py`, `materials/utility.py`, `materials/ranking.py`,
`materials/value.py`, `materials/assessment.py`, plus re-reads of
`materials/model_state.py`, `materials/information.py`, `materials/iteration.py`,
`materials/candidates.py`, `materials/campaign.py`, `materials/results.py`,
`materials/decision.py`, `materials/evaluation.py`.

Two modules central to this phase were **not** in the prompt's audit list and were
found only by enumerating the package:

| Module | Built by | What it provides |
|---|---|---|
| `materials/trajectory.py` (311 lines) | SCOUT Phase 56 | `ModelStateTrajectory`, `TrajectoryEntry`, `make_model_state_trajectory`, `prediction_evolution`, `compare_predictions`, `PredictionDelta` |
| `materials/diagnostics.py` (178 lines) | SCOUT Phase 57 | `StateTransitionDiagnostic`, `StateTransitionDiagnosticSet`, `diagnose_transitions` |

Also relevant and pre-existing: `materials/utility.py` (Phase 47),
`materials/ranking.py` (Phase 48), `materials/optimization.py`,
`materials/counterfactual.py`, `materials/ensemble.py`, `materials/surrogate.py`.

### Historical relationships: explicit or reconstructible?

Section 2 asks this directly. The answer is **deliberately neither, and the
vendored design documents why**:

- `ModelState` has **no** `parent_id`/`parent_state_id` field. SCOUT Phase 56
  investigated adding one and **rejected** it, for two stated reasons: it would
  have to be excluded from `ModelState.id`'s content hash to keep identity purely
  content-derived, raising an ambiguity about what participates in equality; and
  `ModelState` would carry a field never read by `predict`/`update`.
- Lineage instead lives where it genuinely exists — **at the `update()` call
  site**, where the caller holds both parent and child — and is captured as a
  **computed view**: `TrajectoryEntry.predecessor_state_id`.

So trajectory is **explicitly represented, but as a caller-constructed view over
a caller-supplied order**, not as a field on the state and not inferred from
timestamps.

`make_model_state_trajectory` does not trust that order blindly. It **verifies**
it: for every cell present in a predecessor, the successor's sample set must be a
superset — mirroring the one thing `update()` can ever do (append a `Sample`,
never remove one). A misordered or unrelated sequence raises `ValueError`.
Proven in `test_trajectory_rejects_a_sequence_no_update_chain_could_produce`.

---

## 2. Trajectory representation

```
ModelStateTrajectory
  └── entries: Tuple[TrajectoryEntry, ...]
        ├── position: int                        # local index, 0,1,2…
        ├── state: ModelState                    # embedded whole, unmodified
        ├── state_id: str                        # == state.id
        └── predecessor_state_id: Optional[str]  # None exactly at position 0
```

Four concepts kept distinct by the vendored design, and preserved here:

| Concept | Where it lives | Note |
|---|---|---|
| **Identity** | `ModelState.id` | content-derived hash; equal content ⇒ equal id |
| **Lineage** | `TrajectoryEntry.predecessor_state_id` | computed view, not a state field |
| **Ordering** | `TrajectoryEntry.position` | caller-supplied, *verified*, never inferred |
| **Chronology** | *not modeled* | wall-clock deliberately excluded |

Chronology is excluded on purpose: using `Observation.extracted_at` to order a
trajectory would conflate "when a value was admitted to `EvidencePool`" with
"which sequence of `update()` calls a caller walked" — which can legitimately
differ (replay, synthetic trajectories, out-of-order admission).

Measured trajectory from the test suite:

```
position 0   state 44136fa355…   predecessor None
position 1   state a978ea56a4…   predecessor 44136fa355…
position 2   state 910e970d6d…   predecessor a978ea56a4…
```

---

## 3. State-difference semantics

Section 4 asks that three kinds of difference be distinguished and not collapsed.
The architecture already separates them:

| Kind of difference | Represented by | Status |
|---|---|---|
| **Numerical model difference** | `PredictionDelta` (`compare_predictions`), and `StateTransitionDiagnostic.delta_predicted_value` / `.delta_uncertainty` | **Exists** |
| **Epistemic difference** | `estimate_information_value(...)` with `ModelStateInformationValueModel` bound to each state | **Exists, composable** |
| **Structural state difference** (whole-state cell-by-cell diff) | — | **Deliberately absent** |

On the third: a generic whole-state diff was considered and **not** built, for the
reasons `materials/diagnostics.py` already documents. `update()` only ever appends
one `Sample` to the **one** cell its `result`/`candidate` name, copying every
other cell through unchanged — so every other cell is *provably* identical between
predecessor and successor. A whole-state scan would also be unenumerable in a
meaningful way: `ModelState.samples` is keyed by an opaque `resolve_model_state_key`
hash, and no registry exists mapping cells back to candidates. Adding it would be
exactly the "descriptive completeness" section 10 forbids.

**No delta is ever guessed as zero.** Where either side is `None`, the delta is
`None`. Measured, from the real trajectory:

- `S0 → S1`: `delta_predicted_value = None` (S0 had no predicted value at n=0)
- `S1 → S2`: `delta_predicted_value = 4.0` (76.0 → 80.0), but
  `delta_uncertainty = None` — because S1 had **no** uncertainty at n=1, and
  `None → 16.0` is not a subtraction the architecture will fabricate.

That second row is the clearest evidence the "never guess" discipline is real and
not merely documented.

---

## 4. Information dynamics

Existing vocabulary, all pre-existing:

- `materials.utility`: `KNOWN` / `SUPPLIED` / `NOT_DETERMINABLE`
- `materials.value`: `CONFLICTING_EVIDENCE`, `INSUFFICIENT_EVIDENCE`,
  `INCOMPARABLE`; value kinds `TESTS_CONFLICT`, `RESOLVES_MISSING_EVIDENCE`,
  `ADDRESSES_MODEL_DISAGREEMENT`, `REDUCES_INCOMPARABILITY`
- `materials.information`: `ESTIMATED` / `NOT_DETERMINABLE`

Measured across the real trajectory (`test_information_gap_closes_across_the_trajectory`):

| State | `estimate_status` | `estimate` | model name |
|---|---|---|---|
| S0 (n=0) | `NOT_DETERMINABLE` | `None` | `model_state:44136fa355…` |
| S1 (n=1) | `NOT_DETERMINABLE` | `None` | `model_state:a978ea56a4…` |
| S2 (n=2) | `ESTIMATED` | `16.0` | `model_state:910e970d6d…` |

This is section 17's required information-gap case: information is insufficient at
S0, experiments resolve it, and the status genuinely differs by S2 — expressed
entirely through existing semantics, with **no** expected-information-gain
prediction anywhere.

The test additionally asserts the two halves are not conflated: the **structural**
`CandidateInformationValue` is *identical* at S0 and S2 (`estimates[0].information_value
== estimates[2].information_value`) while the **model-derived** number changed.
Structural information value is a property of the candidate against the evidence
gap; the estimate is a property of the model state. They move independently.

---

## 5. Decision semantics

Section 6 requires these not be collapsed into one "agent action" object. They are
not — each is a distinct type with a distinct producer:

| Concept | Type | Produced by |
|---|---|---|
| Observation | `evidence.types.Observation` | `admit_observation` / `admit_experimental_result` |
| Analysis | `MaterialsIteration` | `reevaluate_program` |
| Criterion | `Criterion` | `make_criterion` |
| Candidate | `ActionCandidate` | `generate_candidates` |
| Evaluation | `CandidateEvaluation` | `evaluate_candidates` |
| Decision | `ProgramDecision`, `CandidateSelection` | `evaluate_program`, `select_candidates` |
| Action/plan | `ExperimentPlan`, `ExperimentalDesign` | `assemble_experiment_plan`, `assemble_experimental_design` |
| Campaign | `ExperimentalCampaign` | `assemble_experimental_campaign` |
| Result | `ExperimentalResult` | `make_experimental_result` |

The pipeline is a chain of narrowing commitments, and the vendored design is
explicit that ranking is *not* selection: `rank_candidates` preserves every
candidate in its output and drops none.

---

## 6. Candidate semantics and comparison findings

Section 18 asks for at least two valid candidates against the same state, and what
can legitimately be compared. The real pipeline generates exactly two:

| Candidate | role | `value_kind` | `current_status` | `expected_information_gain` |
|---|---|---|---|---|
| `measurement:repeat` | OBSERVED | `TESTS_CONFLICT` | `CONFLICTING_EVIDENCE` | `NOT_DETERMINABLE` |
| `model_validation:unspecified` | PREDICTED | `RESOLVES_MISSING_EVIDENCE` | `INSUFFICIENT_EVIDENCE` | `NOT_DETERMINABLE` |

**What can legitimately be compared:**

1. **Structural information value** — the two differ meaningfully above, and that
   difference is derived, not supplied.
2. **Caller-supplied utility** — `evaluate_utility_set` + `rank_candidates`.
   Ranking *is* already supported, so per section 18 it is tested rather than
   built. With `benefit=10.0, cost=2.0` supplied for the repeat candidate and
   nothing supplied for the other:

   ```
   measurement:repeat            utility = 8.0    rank 1     RANKED
   model_validation:unspecified  utility = None   rank None  NOT_DETERMINABLE
   ```

   The unsupplied candidate is **listed but never ranked** under
   `UNRANKED` policy — never silently placed last as though judged and found
   worse. `ranking_status` is deliberately independent of whether a rank integer
   was assigned.

**What cannot be compared — the exact seam (section 9):**

`CandidateInformationValue.expected_information_gain` is **hard-coded to
`NOT_DETERMINABLE`** in vendored `materials/value.py`. There is no estimator, and
this phase does not invent one. Consequently:

> Ranking operates **only** on caller-supplied benefit/cost. The architecture can
> say *what a candidate structurally addresses*, and *what a human judged it
> worth*. It cannot say *how much a candidate would teach*.

The distinction section 9 requires be preserved is preserved **structurally**, not
merely by convention:

- **Observed information value** — `ModelStateInformationValueModel.estimate`,
  reading `predict(state, candidate).uncertainty` off a state that already exists.
  A real number (16.0 at S2).
- **Expected information gain** — what a candidate *would* teach. Permanently
  `NOT_DETERMINABLE`.

These are different types, in different modules, with different lifecycles. They
are not interchangeable and the code cannot accidentally treat them as such.
Asserted directly in `test_candidate_comparison_at_a_single_state`.

---

## 7. Implementation

**Production code written: none.** Zero files added or modified in `daf/`; zero in
the vendored submodule (`git status --short` clean inside
`vendor/scout-retrieval-agent`).

One new test file: `tests/test_trajectory_and_decision_dynamics.py` (~330 lines,
7 tests). Its fixture helpers (`_build_campaign`, `_run_result`) are kept
self-contained, following this repository's existing one-module-one-fixture test
convention rather than introducing a cross-test-module import (there is no
`conftest.py` or `tests/__init__.py`, and no precedent for such imports).

---

## 8. Invariants proven

| Invariant | Test |
|---|---|
| `prediction.state_id` names the state it was read from | `test_stop_condition_trajectory_walk` |
| Observation is explicit and durably admitted | same |
| Historical states remain immutable across the whole walk | same |
| New state identity is deterministic | `test_trajectory_and_diagnostics_are_deterministic_across_independent_runs` |
| Transition analysis identifies the actual change | `test_stop_condition_trajectory_walk` |
| Information-value state is comparable across states | `test_information_gap_closes_across_the_trajectory` |
| Candidate/decision semantics stay explicit | `test_candidate_comparison_at_a_single_state` |
| Trajectory rejects sequences no `update()` chain could produce | `test_trajectory_rejects_a_sequence_no_update_chain_could_produce` |
| Transition analysis never reaches `EvidencePool` | `test_transition_analysis_never_reaches_the_evidence_pool` |
| New evidence alone never advances the trajectory | `test_new_evidence_alone_does_not_advance_the_trajectory` |

---

## 9. Multi-step trajectory proof

`test_stop_condition_trajectory_walk` walks the complete stop-condition cycle,
asserting on each intermediate object rather than only on final success:

```
S0 (empty)
  -> predict            p0: predicted_value=None, uncertainty=None, n=0, state_id=S0.id
  -> candidate comparison   2 candidates; ranked; measurement:repeat ranks 1
  -> experiment         result_1 (76 MPa) -> Observation admitted to DurablePool
  -> assess             observed=76.0, residual=None (no prediction at S0)
  -> S1                 predict: 76.0, uncertainty=None, n=1
  -> transition analysis  S0->S1: delta_value=None, observation_value=76.0
  -> information update   S0: NOT_DETERMINABLE -> S1: NOT_DETERMINABLE
  -> next legitimate decision   reevaluate_program: new evidence_version_id,
                                measurement:repeat still proposed
  -> experiment         result_2 (84 MPa)
  -> assess             observed=84.0, predicted=76.0, residual=8.0
  -> S2                 predict: 80.0, uncertainty=16.0, n=2
  -> transition analysis  S1->S2: delta_value=4.0, delta_uncertainty=None,
                                  residual=8.0, observation_value=84.0
```

Three distinct state identities; `S0.samples` still `{}` at the end;
`predict(S1)` still 76.0 and `predict(S2)` still 80.0 after the full walk.

The "next legitimate decision" step is real, not decorative: `reevaluate_program`
run against the pool the experiment enlarged returns a **different**
`evidence_version_id`, confirming the new experimental evidence is visible to the
next decision — the loop genuinely closes.

---

## 10. Determinism proof

`test_trajectory_and_diagnostics_are_deterministic_across_independent_runs` runs
the entire cycle twice, from independent initial objects into two independent
on-disk `DurablePool`s, and asserts equality of:

- all three state identities (S0, S1, S2), and that they are three *distinct* ids
- the candidate id
- the full transition analysis tuple (predecessor/successor ids, both deltas,
  observation value, residual) for both transitions
- the full candidate evaluation tuple (value kind, current status, expected
  information gain) for every candidate

No randomness anywhere in the path.

---

## 11. Revision-safety proof

`test_new_evidence_alone_does_not_advance_the_trajectory` preserves the Phase M/N
finding at the trajectory level. A further **real, admitted** experimental result
(value 999) is written into the very pool the trajectory was built over, and then
deliberately never applied. Afterwards:

- every state id is unchanged
- `diagnose_transitions(...)` returns a result **equal** to the one from before
- `predict(S2, candidate).predicted_value` is still `80.0` — the 999 never
  entered any state

A state transition requires an explicit `update()` call, and nothing — including
durable admission of genuine new evidence — substitutes for one.

---

## 12. Boundaries

**DAF boundary (section 13).** Untouched. No DAF production file was added or
modified. DAF supplies only `DurablePool`/`FilesystemEvidenceStore` as an
`EvidencePool` implementation. An acquisition checkpoint is *not* a scientific
state transition and the two are never equated: the trajectory begins only after
scientific interpretation has produced a `ModelState`.
`test_transition_analysis_never_reaches_the_evidence_pool` makes every
`EvidencePool` method raise and shows the entire trajectory/diagnostics analysis
still runs — the analysis layer operates purely on objects the caller already
holds.

**CanonicalState / Morpho boundary (section 12).** Not connected, as instructed.
Re-verified for this phase's scope: `materials/trajectory.py` and
`materials/diagnostics.py` import only from `materials.*` — no `core.canonical`,
no `core.projection`, no `morpho`. The two object-model chains established in
Phase L remain structurally disjoint.

**Layer separation (section 11).** Preserved; nothing merged. Acquisition (DAF) /
evidence admission (SCOUT) / interpretation (materials analysis) / predictive
state (`ModelState`) / comparison (`trajectory`, `diagnostics`) / decision
(`selection`, `ranking`) / candidate / campaign each remain distinct types
produced by distinct functions.

---

## 13. Validation

| Check | Result |
|---|---|
| DAF suite (`pytest tests/`) | **282 passed** (275 prior + 7 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule cleanliness | `git status --short` clean |
| `mypy daf/` | Success, 42 source files |
| `ruff` | 1 finding: `I001` import-block style only — the identical pre-existing convention already carried by `tests/test_experimental_state_loop.py` and `tests/test_model_state_integration.py`; left consistent with repository precedent |

No existing test was weakened, skipped, or deleted.

---

## 14. Limitations

1. **No DAF source is a real materials experiment.** Unchanged since Phase M.
   EDGAR/USGS/NOAA are passively acquired external data, not experimental campaign
   results; the trajectory here necessarily uses controlled scientific fixtures for
   the model transitions, exactly as Phase M's fallback provision allows.
2. **The predictive model is sample mean/variance.** `predicted_value` is the mean
   and `uncertainty` the population variance of a cell's samples. The trajectory
   and decision machinery is genuinely general, but the *model* it carries is
   deliberately minimal. Nothing here demonstrates scientific predictive power.
3. **Expected information gain remains unavailable.** By design, and this phase
   deliberately did not fill that seam. Candidate ranking therefore depends
   entirely on human-supplied benefit/cost — the architecture cannot yet propose
   *which experiment would teach the most*.
4. **Trajectory is a caller-constructed view.** A bare `ModelState` retrieved in
   isolation carries no lineage. Recovering history requires the caller to have
   retained the sequence. SCOUT Phase 56 named this as the exact condition under
   which the `parent_state_id` decision should be revisited — it has not yet been
   met.
5. **Single-cell scope.** `diagnose_transitions` reports one candidate's cell per
   call. Justified (all other cells are provably unchanged), but it means there is
   no single "what changed across the whole state" object.

---

## 15. Recommendation for Phase 16

The honest reading of three consecutive "existing representation is sufficient"
outcomes is that **the deterministic substrate this phase sequence set out to
establish is now demonstrably complete**. The stop condition's full cycle runs,
deterministically, over DAF's durable pool, with every epistemic boundary intact.

That makes the next decision a genuine fork, and it should be taken deliberately
rather than by default:

- **(a) Fill the expected-information-gain seam.** This is the single named
  capability the architecture structurally lacks, and it is the precondition for
  everything in section 22's deferred list (Bayesian experimental design, active
  learning, acquisition optimization). It is also the largest commitment: it
  requires a genuine model of what an experiment would teach, which is where the
  deferred mechanisms actually begin.
- **(b) Build a genuinely experiment-shaped DAF source.** Carried forward
  unresolved from Phases M and N. Until one exists, every scientific trajectory in
  this repository runs on fixtures, and limitation 1 above cannot be retired.
- **(c) Stop extending and consolidate.** The vendored system is internally at
  Phase ~101 and the DAF-side sequence has spent three phases rediscovering its
  existing layers. A deliberate reconciliation — mapping what SCOUT already
  provides against what DAF phases still assume is missing — would likely prevent
  a fourth.

Recommendation: **(c) first, then (a).** (c) is cheap and would have saved most of
this phase's audit cost had it been done earlier; (a) is the real scientific
frontier, and is better entered with an accurate map of what already exists.

Note that (a) crosses directly into section 22's deferred list. It should not be
started without an explicit decision that the deferral has ended.

---

*Phase O halts here per its stop condition: implemented, tested, documented,
committed, and pushed. It does not proceed into Phase 16.*
