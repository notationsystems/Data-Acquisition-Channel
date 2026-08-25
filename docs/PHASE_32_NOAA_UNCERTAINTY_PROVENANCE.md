# Phase 32 — Source-Authentic Uncertainty Provenance

*(Continues from `0271eac`. Answers the question Phase 31 posed: does NOAA's `sigma`
provide source-authentic uncertainty that can legitimately satisfy the existing
uncertainty contract?)*

**Result: accepted — but only for uncertainty.** `sigma` is a real, well-defined,
source-stated standard deviation and now resolves `MISSING_UNCERTAINTY_KIND` for every
real reading that carries it. Conditions and method were deliberately left untouched
and remain independently rejected, exactly as this phase's scope required.

---

## Reconnaissance

Read in full: `daf/extractors/noaa_water_level_measurements.py`'s existing docstring
(written after Phase 17's own real-response investigation, not re-derived here),
`science/admissibility.py`'s exact `quantity_is_typed` code, every real recorded NOAA
fixture byte, and `materials/analysis.py`'s `_comparison_context` implementation — the
last of these specifically to verify, not assume, that adding fields would not disturb
Phase 17's established `INCOMPARABLE` finding for NOAA tide-series data.

## Sigma determination

**Not inferred from the name.** The extractor's own Phase 17 docstring already states,
from real CO-OPS response investigation: *"`s` -> `sigma`, the standard deviation of the
1-second samples behind the reading."* CO-OPS 6-minute water-level products are computed
by averaging underlying high-frequency samples collected within that interval, and `s`
is the dispersion statistic of exactly those samples — reported by the source directly,
alongside the value it describes.

**Measured on the real fixture, not assumed present:** all 240 real recorded readings in
`tests/fixtures/noaa_live_8454000_20240115_mllw.json` carry `s`
(`test_sigma_is_present_on_every_real_recorded_reading`). The extractor already guards
its presence per-reading (`if sigma is not None`), so a reading genuinely lacking `s`
would carry neither `sigma` nor the new keys.

## Uncertainty classification

**Supported uncertainty.** The source establishes a specific, well-defined statistical
meaning, and the existing four-value vocabulary (`stated`, `estimated`, `propagated`,
`absent`) already has an honest home for it:

- **Not `estimated`** — the source states the number directly; DAF infers nothing.
- **Not `propagated`** — nothing here combines two other uncertainties.
- **Not `absent`** — `absent` would assert *the source explicitly reported no error*,
  the opposite of what a reported `s` value says.
- **`stated`** — the source directly supplies the figure.

`test_no_fabricated_uncertainty_kind_appears_anywhere_in_the_extractor` locks that none
of the three rejected alternatives were ever written into the extractor, even as dead
code.

## Existing contract

`quantity_is_typed` requires `uncertainty_kind` in the closed four-value set and, unless
it is `absent`, a non-null `uncertainty`. It imposes **no separate unit requirement on
`uncertainty`** — the existing contract has no such field. A standard deviation is
expressed in its quantity's own unit by statistical definition, not by a convention this
phase invented, so no new field was needed or added
(`test_uncertainty_unit_matches_the_value_unit_by_statistical_definition`).

---

## Implementation

**One additive change to one shipped extractor**,
`daf/extractors/noaa_water_level_measurements.py`: two new content keys
(`uncertainty`, `uncertainty_kind`), added **only when `sigma` is present**, alongside
every existing key (`property`, `value`, `unit`, `datum`, `station_id`,
`measurement_time`, `sigma` — all unchanged). One new module constant,
`SIGMA_UNCERTAINTY_KIND = "stated"`. `method` and `conditions` are untouched — no new
key was added for either, matching this phase's explicit scope.

`daf/adapters/noaa_water_level.py` and every other production module are untouched.

Canonical architecture: new `architecture/uncertainty_provenance_reachability.yaml`,
mirroring `architecture/method_provenance_reachability.yaml`'s structure — determination,
evidence, identity impact, real acquisition result, plus a cross-source summary
distinguishing what Phase 31 resolved for USGS from what this phase resolved for NOAA.
`architecture/property_admissibility.yaml`'s Phase 29 measured-reachability record is
corrected in place (3 reasons → 2, with the change dated and explained, not silently
overwritten). Doctrine regenerated, zero diff.

Three pre-existing tests that hardcoded the *old* content shape or rejection set were
updated, not weakened: `tests/test_live_scientific_observation.py`'s
`test_observation_content_carries_only_scientific_fields`,
`tests/test_acquisition_identity_invariants.py`'s
`test_scientific_identity_is_independent_of_acquisition_identity`, and
`tests/test_property_admission_integration.py`'s
`test_the_context_gate_rejects_every_real_noaa_reading` — each caught by the full-suite
regression, each fixed to assert the new, correct, real content shape rather than loosened.

New test file `tests/test_noaa_uncertainty_provenance.py` (24 tests).

## Real acquisition

`plan_id=noaa-plan`, real recorded CO-OPS bytes, through `execute_plan_recorded` —
adapter → extractor → `run_scout` → `ClassifiedPool`, nothing manually constructed.
240 artifacts acquired, 240 observations admitted (class `measured`), execution
`SUCCEEDED`/`acquired`, zero `ScoutAdmissionFailure`s.

## Conditions

**Independently, deliberately untouched.** `datum`/`station_id`/`measurement_time`
remain top-level context keys, not reshaped into a `conditions` mapping — the same
Phase 29 decision, unrevisited. `MISSING_CONDITIONS` fires on every one of the 240 real
readings, exactly as before this phase (`test_conditions_remain_independently_rejected`).

## Identity

**Changed, and disclosed, per §10.** `Observation.content` genuinely changed for every
reading carrying `sigma` (all 240 in the real fixture), so `Observation.id` for NOAA
acquisitions differs from every prior phase. Verified directly: the *same* `record_ids`
a real acquisition produced, re-hashed with the pre-Phase-32 content shape (`uncertainty`/
`uncertainty_kind` stripped, every other key checked equal), yields a **different**
observation id — isolating the change to content alone
(`test_observation_identity_changed_and_is_disclosed`).

This is a materially different risk profile than Phase 29's decision *not* to touch this
same extractor, and was checked accordingly rather than assumed safe by analogy to
Phase 31's USGS case: unlike USGS, NOAA observations from this extractor **are**
graph-reachable (they declare entities/relations) and **do** feed
`materials.analysis`'s `_comparison_context`. Read directly:
`_comparison_context` is every content key except `property` and the value key — a
per-reading-varying `sigma` was **already** part of that context before this phase, and
`measurement_time` alone was already unique per reading, so every reading was already its
own singleton comparison group. Adding two more keys to an already-maximally-fragmented
context cannot fragment it further. **Verified, not merely reasoned about**: this
phase's own test spawns the real, pre-existing Phase 17 regression
(`test_real_measurements_are_correctly_reported_as_not_repeated_measurements`) as a
subprocess and asserts it still passes against the changed extractor
(`test_the_incomparable_finding_is_unaffected_by_the_content_addition`), and the full
suite run for this phase confirms it directly.

## Evidence

`pool.fingerprint()` is byte-identical before and after a canonical-assertion pass.
Every rejected NOAA observation remains real, retrievable evidence, correctly classified
`measured`. An AST sweep of `assertion/` finds zero `put_*`/`admit_*` calls. `sigma`
passing a type check does not, by itself, admit anything — the complete property
assertion still fails `MISSING_CONDITIONS`/`MISSING_METHOD`.

## Quarantine

**`partially_enforced` — unchanged.** All 240 NOAA refusals are retained in the Phase 29
canonical-assertion quarantine store (separate from Scout admission quarantine,
unchanged), each linked to its execution, each now carrying exactly
`{MISSING_CONDITIONS, MISSING_METHOD}` — one fewer code than before this phase, never
zero. No repair path exists; none was built.

## Metrics

| | NOAA (this phase) | NOAA (Phase 29) | USGS (Phase 31) |
|---|---:|---:|---:|
| Documents acquired | 240 | 240 | 3 |
| Property candidates | 240 | 240 | 3 |
| Accepted | 0 | 0 | 0 |
| Rejection codes | `MISSING_CONDITIONS`, `MISSING_METHOD` | `MISSING_CONDITIONS`, `MISSING_METHOD`, `MISSING_UNCERTAINTY_KIND` | `MISSING_CONDITIONS`, `MISSING_UNCERTAINTY_KIND` |
| Property-layer rejection rate | 1.0 | 1.0 | 1.0 |
| Phase 27/28 terminal refusals | 0 | 0 | 0 |
| Phase 27/28 rejection rate | 0.0 | 0.0 | 0.0 |

Phase 27/28's acquisition-stage metrics measured unaffected
(`test_phase_27_28_metrics_are_unaffected_by_the_uncertainty_extension`). Two runs of
identical bytes on different days produce identical `by_code`/`rejection_rate` and
correctly distinct execution ids.

## Cross-source comparison

The two phases resolved **different, non-overlapping dimensions** for two structurally
different sources — neither domain's semantics leaked into the other:

| | USGS `magnitude_type` (Phase 31) | NOAA `sigma` (this phase) |
|---|---|---|
| Resolved | method, quantity/unit | uncertainty |
| Untouched, still rejected | conditions, uncertainty | conditions, method |
| Real candidates examined | 3 | 240 |
| Extractor touched | `usgs_earthquakes.py` | `noaa_water_level_measurements.py` |

`test_usgs_phase_31_behavior_is_unchanged_by_the_noaa_extension` re-runs the real Phase
31 USGS acquisition end to end and confirms its exact rejection set is untouched by this
phase's NOAA-only change.

---

## Regression

| Check | Result |
|---|---|
| `tests/test_noaa_uncertainty_provenance.py` | **24 passed** |
| `tests/test_live_scientific_observation.py`, `test_acquisition_identity_invariants.py`, `test_property_admission_integration.py` | all passing after three deliberate, disclosed updates to content-shape/rejection-set locks |
| DAF full suite | **635 passed** (611 prior + 24 new; three pre-existing tests corrected, none weakened) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/ assertion/` | Success, **75 source files** |
| `ruff` | new/changed files carry only repo-wide `UP006`/`UP035`/`UP045`/`PLW1510` conventions; one `I001` found and fixed |
| Doctrine | regenerated, **654 / 1400 words**, zero diff |
| `git status` | clean; only the new test file and new architecture YAML untracked, everything else staged |

## Bent

**Bent: zero.** `science/admissibility.py`, `daf/execution/{quarantine,store,recorded,metrics}.py`,
`assertion/`, `daf/extractors/usgs_earthquakes.py`, and every other extractor/adapter are
byte-identical to Phase 31. The one production change is additive to one extractor's
content dict, conditional on real source data, adding new keys and modifying none.

## Qualified

- `uncertainty_kind = "stated"` is grounded in this specific source's documented
  semantics (a directly-reported standard deviation) — it is not a template implying
  every numeric field a source reports should become `stated` uncertainty.
- The identity-safety argument here is source-specific: it holds because
  `_comparison_context` was already maximally fragmenting NOAA readings via
  `measurement_time` *before* this phase. It would not automatically transfer to a
  source whose comparison groups are not already singleton.
- `method`/`conditions` remain genuinely absent for NOAA; nothing here should be read as
  a step toward inventing them.

## Unresolved

- **No source in this repository can currently produce an *accepted* property assertion
  through real, unmodified acquisition** — unchanged in aggregate, though NOAA now fails
  for two reasons instead of three.
- Whether NOAA's real CO-OPS API exposes any genuine per-reading method/instrument field
  beyond what this repository's fixtures capture remains unexamined.
- Whether any genuine conditioning field exists for either NOAA or USGS beyond what has
  already been ruled out (identity fields, revision/QC flags) remains open.
- Carried unchanged: `quarantine_repair`, `retraction_semantics`,
  `multi_writer.write_conflict`, `builder_check_lineage`, `attested_snapshot_identity`,
  `capabilities_5_to_9`.

## Measured bottleneck

**`MISSING_CONDITIONS` is now the only refusal reason every DAF-reachable property
source shares.** After two phases of source-specific, per-dimension resolution, USGS
fails on `{conditions, uncertainty}` and NOAA fails on `{conditions, method}` — the one
code common to both is `MISSING_CONDITIONS`, and no source examined so far has ever
supplied a field this project judged to be a genuine measurement condition rather than
event identity or revision/QC metadata.

## Next executable frontier

**Determine whether any DAF-reachable source provides a field that is genuinely a
measurement condition** — as opposed to identity (which event/station/time this is) or
revision/QC metadata (automatic-vs-reviewed, preliminary-vs-verified) — using the same
reconnaissance-then-decide discipline this phase and Phase 30/31 applied. This is now
the single gate standing between every examined source and canonical assertion, and,
based on the pattern established across all three sources so far, it may turn out that
none of this repository's current acquisition sources reports one — a negative result
that would itself be a significant, honestly-earned finding.

---

*Halts here per the stop condition: inspected, measured, resolved the one dimension in
scope, verified independence from the two left untouched, disclosed the identity change
and confirmed its safety empirically rather than by analogy, updated three pre-existing
tests to the new reality rather than weakening them, documented, tested, committed and
pushed. Neither gate was weakened, no uncertainty kind was fabricated, and USGS's Phase
31 determination was not reopened.*
