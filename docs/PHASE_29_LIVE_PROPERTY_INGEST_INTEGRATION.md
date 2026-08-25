# Phase 29 — Live Scientific Property Ingest Integration

*(Continues from `071c6a7`. Wires the property/quantity admissibility gates Phase 25
authored — but never wired — against a real DAF acquisition run.)*

```
ClassifiedPool (real, unmodified acquisition)
    |
    v  Observations whose content declares a "property"
science.admissibility.no_context_free_property   (UNCHANGED)
    |
admissible ---------------------------- inadmissible
    |                                        |
(stays real evidence)          QuarantineRecord, stage="canonical_assertion"
                                (daf.execution.quarantine, UNCHANGED types)
```

---

## 1. Reconnaissance — naming correction, and what actually exists

The brief assumes gate functions `assert_property_context`/`assert_quantity_type`.
**Neither exists.** The real functions, committed in Phase 25 and unchanged since, are
`science.admissibility.no_context_free_property` and `science.admissibility.quantity_is_typed`.
They are used here under their real names.

The brief also states *"the previous architecture work established that chemistry
identity is versioned."* **It did not.** Phase 25 measured and recorded
`identity_policy_declared: absent` and `no_point_identity_for_distributions: absent` —
no chemistry representation exists anywhere in this repository. Neither source exercised
in this phase is a chemical substance, so this is not a gap this phase needed to close;
it is confirmed still absent (`test_no_chemistry_identity_policy_is_invoked_or_invented`).

What actually exists and was inspected in full: `science/admissibility.py` (pure,
standalone, wired into nothing — its own docstring already names the gap: *"these are
ADMISSIBILITY validators the scientific layer applies to already-admitted evidence, not
an ingest gate... inadmissible evidence still exists in the pool; it is refused for
canonical assertion"*); `daf/extractors/noaa_water_level_measurements.py` in full (the
one shipped extractor whose content already carries a `property`/`value`/`unit` shape);
`daf/execution/{quarantine,store,recorded,metrics}.py` (Phase 26/27, unmodified);
`architecture/evidence_class.yaml`'s `class_admissibility` (a *different*, class-level
question, already answered, orthogonal to the property-level one this phase adds); no
`verticals/` directory, no chemistry representation anywhere.

---

## 2. The measurement that decided the design

Before writing any wiring code, the real NOAA extractor's actual output was run through
the real, unmodified gate:

```
outcome: acquired, observations: 240
sample content: {'property': 'water_level', 'value': 1.507, 'unit': 'm',
                  'datum': 'MLLW', 'station_id': '8454000',
                  'measurement_time': '2024-01-15 17:06', 'sigma': 0.006}
no_context_free_property -> admissible=False
    reasons=('MISSING_CONDITIONS', 'MISSING_METHOD', 'MISSING_UNCERTAINTY_KIND')
```

**Every one of 240 real, recorded readings fails identically, for the same three
reasons.** This is not a bug to route around — it is the honest state of the shipped
extractor, measured directly. `daf/extractors/noaa_water_level_measurements.py` has no
`method` key at all, no `conditions` mapping, and carries `sigma` as a bare float rather
than an `uncertainty`/`uncertainty_kind` pair.

**The extractor was deliberately NOT changed to fix this**, for two reasons found by
inspection, not assumed:

1. **No real `method` value exists to report.** The NOAA CO-OPS `water_level` product
   response contains no field naming an instrument, sensor, or measurement method.
   Inventing one (e.g. `"tide_gauge"`) would be exactly the fabricated method metadata
   §7 forbids — a fact *about* NOAA's collection process, true in general, but not a
   fact the source itself supplies per-reading.
2. **Reshaping `datum`/`station_id`/`measurement_time` into a nested `conditions`
   mapping would change `Observation.content`, and therefore `Observation.id`, for a
   shipped, already-tested extractor.** That is an identity-stability change to
   existing behavior, not a minimal wiring exercise, and Phase 20's established
   discipline (*"provenance legitimately participates in evidence/state identity"*)
   argues directly against silently reshaping it.

So the rejection is reported **honestly**, as real data quality, exactly matching §14's
instruction: *"if a source produces poor-quality or ambiguous scientific data, report
that result."*

For the required accepted-property demonstration (§16), the same reconnaissance found
that **no shipped, network-reachable source in this repository can produce an admissible
property today** — confirmed by inspecting every extractor's content construction, not
merely the NOAA one. This repeats Phase M's foundational, repeatedly-reaffirmed finding:
*no DAF-reachable source is a materials experiment.* Given that, the accepted case uses
the **same evidentiary standard every materials-campaign test in this repository has used
since Phase M**: a property declaration acquired through the real, unmodified
`LocalDatasetSourceAdapter → GraphDatasetExtractor → run_scout → ClassifiedPool` path,
with test-authored (not live-network) numeric values. This is **acquisition-real,
measurement-synthetic** — stated as such, not conflated with a live sensor reading.

---

## 3. Implemented

**New package `assertion/`** (`__init__.py`, `property_admissibility.py`) — the one
place acquired evidence and scientific admissibility judgment meet. No existing file was
modified inside `daf/`, `science/`, `boundary/`, `bridge/`, or `epistemics/`.

### Why a new package, not an extension of an existing one

`daf` never imports `science`; `science` never imports `daf` — both AST-verified since
before this phase. Neither module can apply the other's output to the other's input, so
the wiring this phase requires cannot live in either. This is exactly the same reasoning
that added `epistemics/` **beneath** both layers in Phase 25 to close
`class_assigned_at_ingest`; `assertion/` is added **above** both for the same reason,
verified by a new layering test (`test_assertion_is_never_imported_by_an_existing_layer`):
`daf`, `science`, `boundary`, `bridge`, `epistemics` must never import it, or the
one-directional composition becomes a cycle.

### What it does, precisely

- `property_candidates(pool, execution_id)` — a **filter**, never a transformation: every
  admitted `Observation` whose `content` contains the key `"property"`. No key is added,
  renamed, or inferred (`test_the_gate_was_not_reshaped_to_accommodate_the_source` reads
  the module source and asserts no `content[...] =`, `.setdefault`, `.update`, or
  `dict(candidate.content, ...)` pattern exists).
- `assess_property_candidate` / `assess_pool` — calls
  `science.admissibility.no_context_free_property` **exactly as committed**, on
  `candidate.content` verbatim.
- Refusals are retained through `daf.execution.quarantine.QuarantineRecord` /
  `make_quarantine_record`, **unmodified types**, with `stage="canonical_assertion"` — a
  new *string value*, not a new type, not a new admission stage in
  `architecture/admission_reachability.yaml`'s sense (that file is scoped to the
  vendored pipeline's six real stages and is untouched by this phase).

### Why a second Quarantine directory, not the existing one

`daf.execution.metrics.rejection_metrics` cross-checks the acquisition run's own
`<root>/quarantine/` count against `ExecutionRecord.admission_failure_count` — a field
fixed at acquisition time that never covers canonical-assertion refusals, because the
Observation genuinely entered the pool; it is not a `ScoutAdmissionFailure`. Writing
`canonical_assertion`-staged records into that same store would make every Phase 27/28
metrics call for this execution raise `QuarantineAccountingError`. So this phase never
opens that store: `canonical_assertion_quarantine_store(root)` points the **unmodified**
`QuarantineStore` class at `<root>/canonical_assertion_quarantine/` instead — a pure
path-composition choice, zero changes to `daf/execution/store.py`.
`test_the_canonical_assertion_quarantine_is_separate_from_scout_admission_quarantine`
measures this directly: the original store is empty, `admission_failure_count` stays 0,
and Phase 27's `rejection_metrics` returns byte-identical output before and after a
canonical-assertion pass runs.

**Canonical architecture**: `architecture/property_admissibility.yaml` records the gate
locations, the naming correction, the ownership decision, both measured reachability
results (240/0 for NOAA, 1/1 for the fixture), the quarantine separation and its reason,
and an explicit `not_claimed` block naming exactly what this phase does **not** assert
(no prediction path, no chemistry identity, no canonical-state handoff, no SCL/STE
integration). Added to `architecture/doctrine.yaml`'s source list; doctrine regenerated
with **zero diff**, word count unchanged (654/1400) — the new file is structural data,
correctly not projected into role-behavior prose per the doctrine router's own rule.

---

## 4. Real acquisition runs

**Run A — NOAA, unmodified.** `plan_id=noaa-plan`, real recorded CO-OPS bytes
(`noaa_live_8454000_20240115_mllw.json`), through `execute_plan_recorded`. 240 artifacts
acquired, 240 observations admitted (class `measured`), execution `SUCCEEDED`/`acquired`.
`assess_pool` examined 240 property candidates: **0 accepted, 240 refused**, all three
codes at count 240 each, `rejection_rate == 1.0`.

**Run B — graph-dataset, admissible fixture.** One record declaring
`property/value/unit/method/conditions/uncertainty_kind/uncertainty`, through the same
real, unmodified `LocalDatasetSourceAdapter`/`GraphDatasetExtractor`/`run_scout` path.
1 candidate examined, **1 accepted, 0 refused**.

Both runs used `execute_plan_recorded` — nothing manually constructed, no direct
`admit_observation()` call counted as reachability, matching Phase 28's discipline
exactly.

---

## 5. Accepted / rejected properties

**Accepted**: `{"property": "tensile_strength", "value": 78.0, "unit": "MPa", "method":
"ASTM_E8", "conditions": {"temperature_c": 23, "specimen": "dogbone-A",
"strain_rate_per_s": 0.001}, "uncertainty_kind": "stated", "uncertainty": 1.2}` — class
`asserted`, admissible for canonical assertion (both the Phase 25 class-level check and
this phase's property-level check pass), retained as real evidence, quarantine record
`None`.

**Rejected**: every one of 240 real NOAA `water_level` readings — class `measured`,
admissible for canonical assertion *at the class level* (Phase 25's
`class_admissibility.measured.canonical_assertion == true`), but refused at the
*property* level for `MISSING_METHOD`, `MISSING_CONDITIONS`, `MISSING_UNCERTAINTY_KIND`.
**The observation remains real, retrievable evidence** — `pool.has_observation(...)` is
`True` for every one of them after the refusal
(`test_a_refused_property_remains_real_admitted_evidence`).

---

## 6. Chemistry gates, exercised

| Gate | Exercised | Passed | Failed | Blocker |
|---|---|---|---|---|
| `no_context_free_property` | ✓ (240 real + 1 fixture) | 1/241 | 240/241 | shipped extractors supply no method/conditions |
| `quantity_is_typed` | ✓ (direct, folded into the above) | — | — | `MISSING_UNCERTAINTY_KIND` on every real reading |
| Method block | ✓ (confirmed absent) | — | 240/240 | NOAA CO-OPS reports no method field of any kind |
| Uncertainty-kind `absent` vs missing | ✓ (direct) | 1/2 | 1/2 | a bare scalar with no declared kind is refused, never silently treated as `absent` |
| Substance identity policy | not applicable | — | — | neither source is a chemical substance; none exists to invoke |

---

## 7. Evidence boundary

Confirmed four ways: `pool.fingerprint()` is byte-identical before and after a
canonical-assertion pass; an AST sweep of `assertion/` finds zero `put_*`/`admit_*`
calls; every refused NOAA observation is still retrievable by id; and class-level
admissibility (Phase 25) and property-level admissibility (this phase) are shown to be
genuinely separate questions on the same evidence — a `measured` observation can be
class-admissible and property-inadmissible simultaneously, and both facts are asserted
in the same test.

## 8. Quarantine

**`partially_enforced` — unchanged.** This phase adds a second reachable refusal surface
to the existing `QuarantineRecord`/`QuarantineStore` types; it implements no repair path
and no new quarantine semantics, so the classification is not upgraded, per §10's
explicit instruction.

## 9. Rejection metrics

| | NOAA (real) | graph-dataset (fixture) |
|---|---:|---:|
| Candidates examined | 240 | 1 |
| Accepted | 0 | 1 |
| Refused | 240 | 0 |
| Rejection rate | 1.0 | 0.0 |
| by_code | MISSING_CONDITIONS:240, MISSING_METHOD:240, MISSING_UNCERTAINTY_KIND:240 | {} |

A run with zero property candidates reports `rejection_rate = None`, never a fabricated
zero (`test_a_run_with_no_property_candidates_reports_no_rate_not_a_zero`). This metric
is a **separate unit** from Phase 27/28's acquisition-stage rejection rate — measured
over *property candidates within already-accepted observations*, not over *acquisition
attempts* — and is reported alongside, never merged into, `daf.execution.metrics`. The
Phase 27/28 terminal/partial denominator is proven byte-identical before and after a
canonical-assertion pass runs on the same execution
(`test_terminal_partial_denominator_semantics_are_untouched`).

## 10. Execution provenance

Every candidate carries the real `execution_id` from `execute_plan_recorded`
(Phase 26, unmodified). `observation_id`, `execution_id`, and `operation_id` are shown
pairwise distinct on every verdict. The `ExecutionRecord` itself is never mutated by a
canonical-assertion pass — `admission_failure_count` stays exactly what acquisition
produced (0 for both runs, since neither had a `ScoutAdmissionFailure`).

## 11. Canonical state

**No handoff exists.** Inspected: nothing in this repository feeds `evidence.pool`
output into `core.canonical.validation`. This is not built here, per §18's explicit
instruction not to invent a new bridge unless the existing architecture requires one for
this contract — it does not. Recorded as the next integration boundary, not attempted.

## 12. SCL / STE

**Not modified.** No existing contract in this repository offers accepted property
evidence to SCL or STE; none was created. The three-module layering (`DAQ → Evidence →
SCL → STE`) remains one-directional — nothing here introduces a cross-module edge.

---

## 13. Regression

| Check | Result |
|---|---|
| `tests/test_property_admission_integration.py` | **24 passed** |
| DAF full suite | **573 passed** (549 prior + 24 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/ assertion/` | Success, **75 source files** |
| `ruff` | new files carry only the repo-wide `UP006`/`UP035`/`UP045` conventions; one `I001`, one `RUF059`, one `F841`, and one genuinely new `UP007` were found and fixed |
| Doctrine | regenerated, **654 / 1400 words**, zero diff |
| `git status` | clean tree; only the three new/changed paths staged |

**One real defect was found and fixed during this phase, not left in the diff**: an
early draft of `test_no_prediction_path_exists_to_collapse_into_measurement` called
`_noaa_pool_and_execution(Path.cwd())` instead of a pytest `tmp_path`, which wrote
`evidence/`, `checkpoints/`, `executions/`, and `quarantine/` directories directly into
the repository root during a real test run. Caught by the full-suite regression (a
pre-existing Phase 25 test, `test_no_evidence_records_are_committed_to_this_repository`,
failed against the polluted tree), the stray directories were removed, and the test was
corrected to use `tmp_path`. The full suite was then rerun clean twice, and `git status`
confirms no stray paths remain.

## 14. Preserved

All Phase 25–28 invariants: the acquisition-first control graph; `class_assigned_at_ingest`;
`proposals_are_not_evidence`; the execution-record identity split; Phase 27's
terminal/partial rejection-rate semantics (proven byte-identical, not merely
unmodified-by-inspection); Phase 28's admission-reachability matrix (untouched — this
phase never touches `run_scout` or `evidence/admission.py`); Quarantine's
`partially_enforced` status; the vendored submodule, byte-identical.

## 15. Bent

**Bent: zero.** No core invariant changed. `science/admissibility.py`,
`daf/execution/{quarantine,store,recorded,metrics}.py`, and every shipped adapter/
extractor are byte-identical to Phase 28.

## 16. Qualified

- The NOAA rejection is qualified to the **shipped extractor as it exists today** — not
  a claim that NOAA CO-OPS data can never satisfy the gate, only that the current
  normalization does not carry the required fields through.
- The one accepted property is **acquisition-real, measurement-synthetic** — explicitly
  not claimed as a live sensor reading, consistent with every materials-campaign test in
  this repository since Phase M.
- Canonical-state handoff and SCL/STE consumption are reported as **not yet
  integrated**, not as failures — no existing contract required either for this phase's
  objective.

## 17. Unresolved

- **No shipped, network-reachable source can produce an accepted property today.**
  Closing this legitimately requires either a source that genuinely reports a method
  (none currently acquired does) or a deliberate, identity-aware extension of an
  existing extractor — not attempted here, since it was outside this phase's named
  target and risks changing a shipped extractor's `Observation.id`.
- Carried unchanged from Phase 27/28: `quarantine_repair`, `retraction_semantics`,
  `multi_writer.write_conflict`, `builder_check_lineage`, `attested_snapshot_identity`,
  `capabilities_5_to_9`, `unreachable_refusal_stages`.

## 18. Measured bottleneck

**Every real, network-reachable source in this repository fails the property-context
gate for the same reason: none of the seven shipped extractors emits a `method` value or
a `conditions` mapping.** This is not a per-source defect — it is a structural property
of every extractor built so far, all of which were written before Phase 25's
admissibility contract existed. The property-admissibility rate can therefore only ever
report `1.0` (rejected) for real acquisition under the current extractor set, exactly
mirroring Phase 28's finding that most admission-stage refusal codes are unreachable —
the same shape of result, one layer up.

## 19. Next executable frontier

**Extend exactly one shipped extractor to carry a real `method` value it can legitimately
report, without changing its existing content keys or its `Observation.id` for
previously-acquired records.** The clearest candidate is `daf/extractors/edgar_daily_index.py`:
an EDGAR filing's `retrieval_method` already states *how DAF acquired it*
(`"http:edgar_daily_index_v1"`), and a genuinely analogous, source-supplied fact — which
SEC form type populated the filing (already present in the raw `.idx` row, currently
discarded) — could legitimately become a `method`-shaped field without inventing
anything the source does not report. That would be the first shipped extractor capable
of producing a property observation this phase's gates could genuinely accept, closing
the bottleneck named above rather than working around it with another fixture.

---

*Halts here per the stop condition: inspected, measured, wired, adversarially checked
against a real polluted-tree regression and fixed, documented, committed and pushed. No
gate was weakened, no method was invented, no chemistry identity was chosen, and no
extractor's shipped content shape was changed.*
