# Phase T (completion) — Information Gap → Acquisition Seam

*(Repository phases are lettered; the prompt labels this "Phase 20". Completes the
work begun at `777ff4e`, continuing from `docs/PHASE_20_ACQUISITION_TO_STATE_FRONTIER.md`.)*

## Architecture

```
              ModelState                  materials/   (vendored, unmodified)
                  |
                  v  diagnosis
            InformationGap                science/     imports materials
                  |                                    NEVER imports daf
                  v  carried verbatim
          EvidenceRequirement             materials/   (vendored, unmodified)
                  |
                  v  intent_for()         science/
          AcquisitionIntent               boundary/    NEUTRAL
                  |                                    imports only `evidence`
                  v  an operator/scheduler/DAF reads it
                 DAF                      daf/         NEVER imports materials
                  |
                  v
              Evidence
                  |
                  v
          ModelState(t+1)                 ← FUTURE closed-loop control step.
                                            NOT automatic in this phase.
```

**The final arrow is not implemented and is not automatic.** Nothing in this
repository executes an `AcquisitionIntent`. The composition tests perform that step
by hand, which is the point: the scientific layer states what it needs, and
something else decides how.

---

## 1. What was already there

| Concern | Existing type | Verdict |
|---|---|---|
| What is unresolved | `InformationGap` (`science/`, built earlier this phase) | Present |
| What evidence would bear on it | `materials.specification.EvidenceRequirement` | **Already correct — composed, not replaced** |
| gap → requirement | `InformationGap.requirements`, carried verbatim | **Already a field — no function added** |
| Expected information gain | hard-coded `NOT_DETERMINABLE` | **Untouched** |
| Operational acquisition | `daf.catalog.plan.AcquisitionPlan{plan_id, source_id, parameters, …}` | Present |
| **requirement → acquirable statement** | — | **Missing** |

### Audit corrections

Two things in the brief did not match the code, and the code won:

- **`materials/gap_analysis.py` does not exist.** Gap types live in
  `materials/experiment.py` (`EvidenceGap`, `SideGap`, `ExperimentGapAnalysis`)
  and `materials/specification.py` (`EvidenceRequirement`,
  `specify_experiment_requirements`).
- **`gap_to_requirement(gap) -> EvidenceRequirement` was not built.** It would have
  been a function whose entire body is `return gap.requirements`.
  `diagnose_information_gap` already puts the vendored requirements on the gap
  verbatim. This project has repeatedly declined thin wrappers — the vendored
  `materials/trajectory.py` declines one for the same reason — so `gap.requirements`
  *is* that mapping, and `intents_for` consumes it directly.

---

## 2. What was actually missing, and why

`EvidenceRequirement` is semantically correct and needs no replacement. But it is a
**`materials` type**, and `daf` is AST-verified never to import `materials`. So a
scientific requirement could not be *read* by an acquiring layer at all — not
because the semantics were wrong, but because **no object existed that both sides
were allowed to name**.

That is the entire gap this phase closed, and it is a dependency-direction problem
rather than a modelling one.

### `boundary/` — the neutral layer

```python
@dataclass(frozen=True)
class AcquisitionIntent:
    id: str                    # content_hash of the five fields below
    subject_natural_key: str
    subject_kind: str
    property: str
    role: str                  # OBSERVED | PREDICTED
    target_context: Mapping[str, object]
```

Imports only `evidence.identity` — the substrate `daf` and `materials` **already
both depend on** — so neither side is excluded. Verified at AST level:
`boundary` imports no `materials`, no `daf`, no `science`.

**Every field is there because an acquirer cannot choose a mechanism without it:**
which referent (`subject_*`), what quantity (`property`), whether a measurement or
a prediction is wanted (`role` — a measurement source cannot supply a prediction),
and under what conditions (`target_context`).

**Deliberately absent, each for a stated reason:**

| Excluded | Why |
|---|---|
| the criterion's `operator`/`target` (`>= 80`) | That is the **decision threshold**, not the evidence wanted. A source does not filter measurements by whether they pass; `materials.decision` applies the threshold afterwards. Carrying it would push a scientific decision into the acquisition boundary. |
| gap category (`MEASUREMENT_CONFLICT`, …) | Explains *why* the gap exists, not what to acquire. An acquirer does the same thing either way. |
| `existing_evidence_ids`, provenance sets | Pool state. Leaking it would tie the boundary to which store the requirement was computed against. |
| `source_id`, `adapter_id`, `url`, `plan_id`, `parameters`, `schedule` | Acquisition decisions. An intent that named them would not be an intent. |
| information value / expected gain / priority | Would be expected-information-gain by another name. |

### Why the translation lives in `science/`, not `boundary/`

Deciding *which parts of a requirement constitute the evidence wanted* is a
scientific judgement. If `boundary/` performed the translation it would have to
import `materials`, and `daf` could then no longer read it. So:

```
science  --imports-->  boundary  <--imports--  daf / operator
science  --imports-->  materials
daf      --NEVER-->    materials
```

No layer imports the one that would create a cycle, and `science` never imports
`daf` in either direction.

---

## 3. Why the two uncertainty axes stay separate

Established earlier this phase and unchanged: model-state uncertainty and evidence
gap are **different axes with different anchors**.

| state | n | `estimate_status` (model) | `gap_category` (evidence) |
|---|---|---|---|
| S0 | 0 | NOT_DETERMINABLE | MEASUREMENT_CONFLICT |
| S1 | 1 | NOT_DETERMINABLE | MEASUREMENT_CONFLICT |
| S2 | 2 | **ESTIMATED (16.0)** | MEASUREMENT_CONFLICT |

At S2 the model resolves while the evidence conflict persists. The seam preserves
this: `InformationGap.reasons` carries `UNCERTAIN_STATE` and `ABSENT_EVIDENCE`
independently, and the `AcquisitionIntent` carries **neither** — because an
acquirer's job is the same regardless of which axis is open.

---

## 4. Ownership

| Object | Owner | May name | May never name |
|---|---|---|---|
| `ModelState`, `EvidenceRequirement` | vendored `materials/` | — | (unmodified by this repo) |
| `InformationGap` | `science/` | `materials`, `boundary` | `daf` |
| `intent_for` / `intents_for` | `science/` | `materials`, `boundary` | `daf` |
| `AcquisitionIntent` | `boundary/` | `evidence` only | `materials`, `daf`, `science` |
| `AcquisitionPlan`, `AcquisitionRequest` | `daf/` | `evidence` | `materials`, `science`, `boundary` |

---

## 5. The seam in practice

With a real conditioning context — `materials.decision.Criterion`'s own documented
example shape, and the brief's own illustration:

```
criterion: tensile_strength >= 80  @ {"temperature": 25, "temperature_unit": "C"}
observed_status: INCOMPARABLE          (no existing evidence was gathered at 25 C)

intents produced:
  id=8d233c6c…  subject=formulation-f1/formulation  property=tensile_strength
                role=PREDICTED  ctx={'temperature': 25, 'temperature_unit': 'C'}
  id=7e4b2c1c…  subject=formulation-f1/formulation  property=tensile_strength
                role=OBSERVED   ctx={'temperature': 25, 'temperature_unit': 'C'}
```

Two intents differing only in `role` have different ids — a measurement source
cannot satisfy a request for a prediction. The `>= 80` threshold appears nowhere.

`intents_for` deduplicates by intent id rather than by requirement: two
requirements wanting the same class of evidence are **one thing to acquire**, and
reporting it twice would invite an acquirer to fetch it twice.

---

## 6. Live composition (Step 8), and its honest limit

One bounded live NOAA acquisition, real network:

```
LIVE acquisition: acquired | observations: 240
analysis: observed=240 groups=240 disagreement=None
sample content: {'property': 'water_level', 'value': 0.136, 'unit': 'm',
                 'datum': 'MLLW', 'station_id': '8454000',
                 'measurement_time': '2024-01-15 00:00', 'sigma': 0.006}

AcquisitionIntent for this real evidence class:
  id=0581a8a56b5ea581  subject=8454000/monitoring_station
  property=water_level  role=OBSERVED  ctx={'datum': 'MLLW', 'unit': 'm'}
  names a source? False
```

This is real neutrality evidence: **the same boundary object expresses a
`monitoring_station`/`water_level` evidence class as expresses
`formulation`/`tensile_strength`**, with no domain vocabulary of its own.

**What was deliberately not done:** no `InformationGap` was diagnosed for NOAA. That
would require `ActionCandidate`/`MaterialsIteration` semantics — formulations,
processes, criteria — that NOAA does not supply, and fabricating them is precisely
what Phase Q refused. The live demonstration therefore covers *evidence → analysis →
representable at the boundary*, and stops where honesty requires.

---

## 6b. Initial assumptions that turned out to be wrong

Recorded because each cost real work, and because the code overruled every one:

1. **"`materials/gap_analysis.py` holds the gap types."** It does not exist. Gap
   types live in `materials/experiment.py` (`EvidenceGap`, `SideGap`,
   `ExperimentGapAnalysis`) and `materials/specification.py`
   (`EvidenceRequirement`, `specify_experiment_requirements`).
2. **"A `gap_to_requirement()` function is needed."** It is not.
   `diagnose_information_gap` already attaches the vendored requirements to the
   gap verbatim, so the function's entire body would be `return gap.requirements`.
3. **"A new requirement object is needed for the scientific layer."** No —
   `EvidenceRequirement` already says what is needed without saying how to get it.
   The missing piece was one layer further out.
4. **"The blocker is semantic."** It was a *dependency direction*. The semantics
   were already right; no object existed that both sides were permitted to name.
5. **"Determinism failures mean the identity scheme is wrong."** They did not.
   Provenance legitimately participates in evidence and state identity, so
   determinism comparisons must share one source — the earlier fix was already
   correct and was left alone.

## 6c. Why `AcquisitionPlan` was not reused as the scientific requirement

The obvious shortcut would have been to let the scientific layer emit an
`AcquisitionPlan` directly. It was rejected on four grounds, each visible in the
type itself:

```python
AcquisitionPlan(plan_id, source_id, parameters, enabled, schedule, mode, interval_seconds)
```

1. **It has already made the decision.** `source_id` names *which source*, and
   `parameters` are adapter-shaped. A scientific layer emitting one would be
   choosing the mechanism, which is exactly the choice it must not make.
2. **It cannot express the question.** There is no field for subject, property,
   role, or conditioning context. "Tensile strength of F1 at 25 °C" is not
   representable in it at all, except by encoding it into `parameters` — i.e. into
   an adapter's private schema.
3. **It would invert the dependency.** `AcquisitionPlan` lives in `daf/`, so
   `science` would have to import `daf`. That is the one direction this phase
   exists to prevent.
4. **It carries execution policy.** `schedule`, `mode`, `interval_seconds`,
   `enabled` are operational concerns with no scientific meaning. A requirement
   that carried them would be claiming things the scientific layer has no basis
   to assert.

`AcquisitionIntent` remains justified precisely because it is the complement:
everything `AcquisitionPlan` cannot say, and nothing it can.

## 6d. The five identities stay distinct

Section 3's requirement, asserted mechanically rather than by inspection. Each
object has exactly one discriminating field that appears in **no** other:

| Object | Question it answers | Discriminator |
|---|---|---|
| `InformationGap` | what remains unresolved? | `state_id` |
| `EvidenceRequirement` | what evidence would help? | `criterion` |
| `AcquisitionIntent` | what class of evidence? | `subject_natural_key` |
| `AcquisitionPlan` | how will it be executed? | `plan_id` |
| `AcquisitionRequest` | execute it, now | `requested_at` |

The test additionally proves the separation runs both ways: no scientific object
carries an execution handle (`source_id`, `plan_id`, `parameters`, `schedule`,
`mode`, `interval_seconds`), and no operational object carries scientific
semantics (`criterion`, `reasons`, `requirements`, `estimate`, `role`,
`target_context`). `AcquisitionPlan` and `AcquisitionRequest` are also kept
apart — a plan is standing intent to execute, a request is one execution at one
instant.

## 6e. Context propagation, asserted at every hop

Section 4, with the real example carried end to end:

```
Criterion.context                    {"temperature": 25, "temperature_unit": "C"}
        |
        v
EvidenceRequirement.criterion_context {"temperature": 25, "temperature_unit": "C"}
        |
        v
AcquisitionIntent.target_context      {"temperature": 25, "temperature_unit": "C"}
```

Unchanged at each step, and carried as the source's own open mapping rather than
rewritten into a DAF parameter schema. The intent is asserted to contain none of
`endpoint`, `adapter`, `adapter_id`, `url`, `page`, `pagination`, `cursor`,
`checkpoint`, `schedule`, `interval_seconds`, `source_id`, `parameters`.

## 6f. The two directions execute independently, at runtime

Section 8, proven by observing `sys.modules` rather than by reasoning:

- **DAF without science.** `science` and `boundary` are deleted from
  `sys.modules`, a full DAF acquisition runs to completion, and neither package
  reappears. DAF is usable with no scientific layer present.
- **Science without further DAF.** Translating a requirement into an intent
  imports no `daf` module that was not already loaded, and executes nothing
  (`execute_plan` is additionally monkeypatched to raise if called).

## 7. Tests

`tests/test_information_gap_acquisition_seam.py` — 16 tests covering all ten
original items, Step 6's seven negative boundaries, and this round's §3/§4/§8:

| Requirement | Test |
|---|---|
| 1, 3 gap determinism / gap-vs-state identity | `test_gap_is_deterministic_and_separates_gap_identity_from_state_identity` |
| 2 gap immutability | `test_gap_is_immutable` |
| 4 gap → requirement semantics | `test_the_gap_already_carries_its_requirements_verbatim` |
| 5 deterministic requirement/intent identity | `test_intent_identity_is_deterministic_and_content_derived` |
| 6 science → boundary composition | `test_intent_carries_conditioning_context_and_no_decision_threshold` |
| 7, 6.1, 6.6 dependency directions | `test_dependency_directions_are_structural` (AST, all three packages) |
| 8, 9, 6.2 no pool access, no mutation | `test_diagnosis_and_translation_never_touch_the_evidence_pool` |
| 6.3, 6.5 translation performs no acquisition | `test_translating_a_requirement_performs_no_acquisition` |
| 10 complete path | `test_complete_path_from_acquired_evidence_to_acquisition_intent` |
| 6.7 many mechanisms, one intent | `test_one_intent_can_be_satisfied_by_structurally_different_mechanisms` |
| Step 7 information value stays honest | `test_the_seam_connects_to_information_value_without_estimating_gain` |
| neutrality in practice | `test_intent_json_shape_is_readable_without_any_scientific_import` |
| §3 five identities stay distinct | `test_the_five_objects_remain_distinct_semantic_identities` |
| §4 context survives every hop | `test_conditioning_context_survives_criterion_to_requirement_to_intent` |
| §8 DAF runs without the scientific layers | `test_daf_acquires_without_importing_the_scientific_layers` |
| §8 science translates without reaching into DAF | `test_science_builds_an_intent_without_reaching_further_into_daf` |

**On Step 6.7** — the invariant the brief calls most important. The same intent is
satisfied twice by genuinely different mechanisms: a **real DAF acquisition**, and
**direct manual admission** by an operator with no DAF involvement at all (two
distinct `extraction_method`s in one pool). The intent is byte-identical in both
cases because it names no mechanism. Only two mechanisms are exercised — the claim
proven is that the abstraction does not *prevent* others, not that they all exist.

### Deduplication

A third copy of the acquisition→trajectory fixture would have guaranteed drift, so
it was extracted to `tests/helpers_state_gap.py` and
`tests/test_state_gap_frontier.py` now imports it (400 → 320 lines). No assertion
was changed or weakened.

---

## 8. Defects found during implementation

1. **`science/acquisition_seam.py` needed a type annotation** — `mypy` caught an
   unannotated dict. Fixed rather than ignored.
2. **`pytest.raises(Exception)`** for the immutability test was a blind assertion
   (`B017`); narrowed to `FrozenInstanceError`, which is what frozen dataclasses
   actually raise.
3. **Two dead imports** left by the deduplication (`json`, `campaign_for`), removed.
4. **A referenced helper module did not exist** — the first draft imported
   `tests.helpers_state_gap` as a package, which fails because `tests/` has no
   `__init__.py`. Corrected to the flat import pytest actually supports.

5. **A stray file was written into the vendored submodule.** A shell working
   directory persisted from an earlier `cd vendor/scout-retrieval-agent`, so an
   append intended for `tests/test_information_gap_acquisition_seam.py` created a
   *new* file of that name inside the submodule instead. Caught immediately
   because the appended tests failed with `NameError` at an impossibly low line
   number, and `git show HEAD:<path>` then reported the file absent from HEAD —
   which only makes sense if `git` was running in a different repository. Fixed by
   moving the content into the real file and deleting the stray one; the submodule
   is verified clean again. The real file was never damaged. Subsequent shell
   commands use `git -C` and subshell `( cd … )` so the working directory cannot
   leak between calls.

No defect was found in the previously committed `science/information_gap.py`; the
earlier determinism fix (shared source path) was already correct, exactly as Step 1
prescribed — provenance legitimately participates in evidence and state identity.

---

## 9. Validation

| Check | Result |
|---|---|
| DAF suite | **348 passed** (332 prior + 16 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git status --short` clean |
| `mypy daf/ science/ boundary/` | Success, 51 source files |
| `ruff` (changed/new files) | 12 findings, all `UP006`/`UP035`/`UP045`/`I001` repo-wide conventions — no genuine finding. `B017`, `PLR0402` and two `F401` were found and fixed |
| Live | one bounded real NOAA acquisition (§6) |
| Test isolation | seam + frontier suites re-run together to confirm the `sys.modules` manipulation in the §8 test leaks nothing |

---

## 10. Invariants preserved

Unchanged and re-asserted: immutable `ModelState` with deterministic `id`;
historical state immutability; deterministic evidence identity; artifact/version
distinction; DAF durable persistence; checkpoint semantics; SCOUT one-door
admission; `EvidencePool` semantics; provenance preservation; scientific
comparison-context semantics; CanonicalState/Morpho separation; **DAF independence
from `materials`**; **`science` independence from `daf`** — now joined by
**`boundary` independence from all three domain layers**.

The vendored submodule remains unmodified. No ontology was expanded.

---

## 11. Deliberately deferred

- **Expected information gain** — still `NOT_DETERMINABLE`, carried explicitly so
  the refusal stays visible. At S2 a gap holds a real observed value (16.0) *and*
  that refusal simultaneously.
- **Executing an intent.** Nothing turns an `AcquisitionIntent` into an
  `AcquisitionPlan` automatically. That mapping requires source knowledge — which
  source can supply property P about subject S under context C — and is the next
  control-loop phase's subject.
- **Ranking or prioritising intents.** Two intents are incomparable by design;
  ordering them is expected-information-gain by another name.
- **Automatic re-acquisition**, active learning, optimisers, schedulers,
  GraphRAG, geometry/manifolds, transformers, Gaussian processes, neural
  surrogates, FEP loops, execution ledgers, zkVM — none introduced.

**Remaining limitations:** only two acquisition mechanisms are exercised; the
scientific measurement values remain synthetic (no DAF-reachable source is a
materials experiment); and `target_context` is only as rich as the criterion that
produced it.

---

*Halts here per the stop condition: audited, built, run, observed, fixed, audited,
validated, committed and pushed. Expected-information-gain optimisation and
autonomous acquisition are not begun.*
