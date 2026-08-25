# Phase T — Acquisition-to-Scientific-State Frontier

*(Repository phases are lettered; the prompt labels this "Phase 20". Continues
from Phase S — `docs/PHASE_19_ACQUISITION_IDENTITY_GENERALIZATION.md` — at
`1e43cbf`.)*

## The frontier, found by measurement

Walking a real trajectory and reading **both** existing machineries at each state:

| state | n | `estimate_status` (state) | `gap_category` (evidence) | `expected_information_gain` |
|---|---|---|---|---|
| S0 | 0 | NOT_DETERMINABLE | MEASUREMENT_CONFLICT | NOT_DETERMINABLE |
| S1 | 1 | NOT_DETERMINABLE | MEASUREMENT_CONFLICT | NOT_DETERMINABLE |
| S2 | 2 | **ESTIMATED (16.0)** | MEASUREMENT_CONFLICT | NOT_DETERMINABLE |

Two axes with **different anchors**:

- `estimate_information_value` + `ModelStateInformationValueModel` answer whether
  *the model* can resolve a cell. This **moves with the state**.
- `CandidateInformationValue.gap_category` answers what *the evidence* fails to
  establish against the criteria. It is computed from a `MaterialsIteration` at
  one evidence version, so it **does not move with the state** — still
  `MEASUREMENT_CONFLICT` at S2, where the model is already determinate.

Nothing joined them. And `InformationValueEstimate` carried the state only inside
`model_name` as the string `"model_state:<id>"`, so *"which state does this gap
belong to?"* was answerable only by splitting a string. Those two facts — an
unjoined pair of independent axes, and a state identity that was not structural —
are the entire justification for what this phase built.

---

## 1. What already existed (§2, §4)

Read at HEAD, not inferred from phase reports:

| Concern | Existing representation | Verdict |
|---|---|---|
| Evidence absence | `EvidenceGap`/`ExperimentGapAnalysis` (`materials/experiment.py`), `EvidenceRequirement` (`materials/specification.py`) | **Sufficient — composed, not replaced** |
| What evidence is needed | `EvidenceRequirement` — "describes what is needed, never a procedure" | **Sufficient — this *is* the scientific requirement §8 asks for** |
| Candidate information value | `CandidateInformationValue` (`materials/value.py`) | Sufficient |
| State uncertainty | `InformationValueEstimate.estimate_status` + `.basis` | Sufficient |
| Expected information gain | hard-coded `NOT_DETERMINABLE` | **Left exactly as-is** |
| **Gap anchored to a ModelState** | — | **Missing** |
| **Join between the two axes** | — | **Missing** |

`EvidenceRequirement` already being the right object is the most important audit
result: §8's "smallest explicit object describing the evidence needed" did not
need to be written. It is carried through verbatim.

---

## 2. What was built

`science/information_gap.py` — one frozen dataclass and one pure function.

```python
@dataclass(frozen=True)
class InformationGap:
    state_id: str                 # structural, not a substring of model_name
    candidate_id: str
    reasons: Tuple[str, ...]      # UNCERTAIN_STATE and/or ABSENT_EVIDENCE
    estimate: InformationValueEstimate      # embedded whole
    estimate_status: str
    gap_category: str
    current_status: str
    requirements: Tuple[EvidenceRequirement, ...]   # vendored, verbatim
    expected_information_gain: str                  # always NOT_DETERMINABLE

def diagnose_information_gap(state, candidate, iteration) -> Optional[InformationGap]
```

No new mathematics, no new classification vocabulary — `ESTIMATED`/
`NOT_DETERMINABLE` and the gap categories are reused verbatim. Returns `None`
when nothing is unresolved, so "nothing unresolved" can never be mistaken for
"unresolved with no reasons".

Measured behaviour across the real trajectory:

```
S0: reasons=('ABSENT_EVIDENCE','UNCERTAIN_STATE')  est=NOT_DETERMINABLE
S1: reasons=('ABSENT_EVIDENCE','UNCERTAIN_STATE')  est=NOT_DETERMINABLE
S2: reasons=('ABSENT_EVIDENCE',)                   est=ESTIMATED(16.0)
```

The gap **narrows without closing** — the state resolves, the evidence does not.
That discrimination is only expressible because the two axes are kept apart.

### A new package, and why

`science/` is a new top-level package, sibling to `daf/`. Neither existing home
could hold this:

- The vendored submodule is modified by nobody — `daf/_vendor.py` states it is
  used "without copying or modifying a single line", and every phase validates
  `git status --short` clean inside it.
- `daf/` is acquisition-only and AST-verified never to import `materials`.

So: `daf/` = acquisition (never imports `materials`), `vendor/` = evidence +
science (never modified), `science/` = composition over the vendored scientific
layer (imports `materials`, **never** imports `daf`). The last clause is enforced
at the AST level over every module in the package.

That enforcement forced a real correction mid-phase: `science/__init__.py`
initially did `import daf` for the `sys.path` bootstrap, which would have made the
independence claim false. `science/_vendor.py` is a deliberate seven-line copy of
that bootstrap rather than an import — the honest fix, instead of weakening the
assertion.

---

## 3. Alternatives rejected

| Alternative | Why rejected |
|---|---|
| **Pure composition, no object** | The information is all reachable, but `state_id` would remain `model_name.split(":")[1]`. A gap must belong to a state; string-parsing is not an interface. |
| **Add `state_id` to the vendored `InformationValueEstimate`** | Would modify the submodule, breaking this project's oldest invariant. |
| **Put it in `daf/`** | Violates the AST-verified rule that `daf` never imports `materials`, and inverts the layer boundary. |
| **A new `AcquisitionRequirement` type** | `EvidenceRequirement` already says what is needed without naming a procedure. A second object would restate it and invite source knowledge into the scientific layer. |
| **Include an `EvidenceGap`/`ExperimentGapAnalysis` reference** | Reachable through `estimate.information_value.evaluation`; adding a field for reachability alone is the "semantic completeness" §9 forbids. |
| **A `priority`/`severity` score** | Nothing in the evidence supports ordering gaps, and it would be expected-information-gain by another name. |

---

## 4. §17's explicit questions

**What is an information gap?**
What one `ModelState` fails to resolve about one `ActionCandidate`, together with
the already-specified evidence that would bear on it. It is anchored to a state
(`state_id`), a candidate, and the iteration the candidate came from.

**How is it different from missing evidence?**
Missing evidence is one of its two possible reasons. `ABSENT_EVIDENCE` is a
property of the *evidence* against a criterion and does not move with the model;
`UNCERTAIN_STATE` is a property of the *model* and does. The measured table above
shows a state where they disagree — S2 is `ESTIMATED` yet still
`MEASUREMENT_CONFLICT`. Collapsing them would lose exactly that case.

**How is it different from an acquisition request?**
A gap says *what is unresolved and what evidence would bear on it*. An
acquisition request says *which source and mechanism to use*. The gap carries
`EvidenceRequirement`s, which are asserted to name no `source_id`, `adapter_id`,
`plan_id`, `url`, or `parameters`. Choosing a source is DAF's decision, and
`science/` structurally cannot make it.

**What state does the gap belong to?**
The one named by `state_id` — now a real field. This is the concrete thing that
did not exist before.

**What can consume the gap?**
Today: a person, reading it and choosing an acquisition (demonstrated). Later:
expected-information-gain machinery, which is exactly what §12 asked this phase to
prepare an object for.

**What does the gap deliberately NOT claim?**
That it knows what an experiment would teach. `expected_information_gain` is
carried through verbatim and is always `NOT_DETERMINABLE` — carried rather than
omitted, so the refusal stays visible. At S2 the gap holds a real number (16.0)
*and* that refusal simultaneously: the number is the model's **current predictive
uncertainty**, never the **gain** an experiment would produce. It also does not
rank gaps, does not name a source, and does not act.

---

## 5. The closed partial loop (§10) and controlled re-entry (§11)

```
real DAF acquisition (graph-dataset, unmodified pipeline)
  -> Observation -> trust graph -> materials.analysis  (CONFLICTING_EVIDENCE)
  -> ModelState S0 -> S1 -> S2                          (76.0 -> 80.0)
  -> trajectory + diagnose_transitions                  (delta 4.0)
  -> InformationGap                                     (reasons narrow at S2)
  -> EvidenceRequirement            <-- STOPS HERE
```

**Re-entry produced the phase's best result.** A person reads the requirement
("observed `tensile_strength` evidence bearing on `>= 80`"), chooses a source, and
runs a second real acquisition (91, 88). The outcome, measured:

```
before:  observed_status=CONFLICTING_EVIDENCE   candidates=[measurement:repeat, model_validation]
after:   observed_status=PASS                   candidates=[model_validation]
```

The acquisition **settled the criterion**, and the candidate that targeted the
conflict stopped being generated at all. The unresolved condition *moved* rather
than merely shrinking — `gap_after.gap_category != gap_before.gap_category`. No
part of that was automatic: the composition happens in test code, not in
`science/` and not in `daf/`.

### A real constraint found by running it

Diagnosing the *old* candidate against the *new* iteration raises `KeyError`. An
`ActionCandidate` carries `requirement_ids` issued by the `MaterialsIteration`
that generated it, so a gap must be diagnosed against that same iteration.
Re-entry means regenerating candidates from the new iteration. This is pinned with
`pytest.raises(KeyError)` rather than routed around — it is a genuine invariant of
the vendored evaluation layer, not an inconvenience.

---

## 6. Tests

`tests/test_state_gap_frontier.py` — 10 tests covering all 14 required items:
acquisition reaching analysis (1–3); deterministic identity and immutable history
(4–5); trajectory and transition diagnosis (6–7); the unresolved condition and
gap determinism (8–9); no mutation and no `EvidencePool` access, with every pool
method made to raise (10–11); no `daf` import, at the AST level over every module
in the package (12); observed value never reported as expected gain (13); and
manual re-entry without runtime coupling (14).

**Fixture provenance, kept explicit (§15):**

- *Real DAF acquisition* — the unmodified adapter/extractor/orchestrator/
  `DurablePool` path over a graph-declaring dataset. The acquisition boundary is
  real, both for the initial evidence and the follow-up.
- *Synthetic scientific fixture* — the measurement values. No DAF-reachable
  source is a materials experiment (Phase M's finding, unchanged), so
  `ExperimentalResult`/`ActionCandidate` semantics use controlled values. Nothing
  here pretends tide gauges are tensile tests; Phase Q's live NOAA path is proven
  in its own suite.

### A second test error worth recording

My first determinism test compared trajectories from two different `tmp_path`s and
failed. That failure was correct, and it is the same lesson as Phase P/S:
`Sample.observation_id` traces back through Record → locator → **dataset path**,
so acquiring identical records from a different path is legitimately different
evidence with different state ids. Corrected to acquire one shared source into two
independent pools.

---

## 7. Validation

| Check | Result |
|---|---|
| DAF suite | **332 passed** (322 prior + 10 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git status --short` clean |
| `mypy daf/ science/` | Success, 47 source files |
| `ruff` | `UP006`/`UP035`/`UP045`/`I001` only — repo-wide conventions. `RUF100` and `RUF059` were found and fixed |
| Changed files | `science/` (new, 3 files), `tests/test_state_gap_frontier.py` (new), this document. **No existing file modified** |

---

## 8. Limitations

1. **One gap per (state, candidate).** No aggregation across a candidate set or a
   trajectory. Nothing in the evidence yet requires one.
2. **`ABSENT_EVIDENCE` is derived from `current_status`**, so it inherits
   `materials.value`'s classification wholesale. If that vocabulary grows, the
   `_UNSETTLED_STATUSES` tuple must grow with it — a deliberate coupling to the
   vendored vocabulary rather than a re-derivation of it.
3. **The gap does not rank or order.** Two gaps are incomparable, by design. That
   is precisely the hole expected-information-gain would fill, and it stays open.
4. **Re-entry is manual and must stay manual.** Automating it is active learning.
5. **The scientific values are still synthetic** (limitation 1 of Phase P/Q,
   unchanged): no DAF-reachable source is a materials experiment.
6. **`science/` duplicates seven lines of `daf/_vendor.py`.** A deliberate cost,
   paid to keep the independence assertion true.

---

## 9. Relationship to future expected-information-gain machinery

This phase built the object such machinery will consume, and nothing more. A
future estimator would take an `InformationGap` — which already carries the state
it belongs to, the candidate, the model's current uncertainty, and the evidence
requirements — and produce the one field deliberately left `NOT_DETERMINABLE`.

Everything needed to *pose* the question is now present and anchored. Nothing that
would *answer* it has been added, and §19 explicitly forbids proceeding into that
merely because this phase succeeded.

---

*Phase T halts here: audited, frontier measured before building, minimal
representation implemented, run, two genuine test errors observed and fixed, a
real vendored-layer constraint discovered and pinned, invariants audited,
validated, documented, committed and pushed.*
