# Phase 31 — USGS Method Provenance and Quantity Semantics

*(Continues from `5de8848`. Answers the question Phase 30 posed and deliberately left
open: does USGS `magnitude_type` satisfy the property-admissibility contract, and does
a logarithmic, conventionally unitless magnitude scale satisfy `quantity_is_typed`?)*

**Result: partially accepted.** Method and quantity/unit are both correctly, honestly
representable by the existing contract — implemented. Conditions and uncertainty are
not, and remain genuinely rejected. **Real USGS acquisition now examines property
candidates for the first time (0 → 3), and correctly rejects all three for exactly two
reasons — never the two Phase 30 resolved.**

---

## Reconnaissance

Read in full: `daf/extractors/usgs_earthquakes.py` (already read completely in Phase 30),
`science/admissibility.py`'s exact code (not its docstring), every real USGS fixture
byte-for-byte, and the extractor's own existing unit tests
(`tests/test_usgs_earthquakes_extractor.py`) to confirm no test hardcodes an exact
content-shape or `Observation.id` that this phase's change would silently break.

## Quantity contract

`science.admissibility.quantity_is_typed`'s entire unit check is:

```python
if not content.get("unit"):
    reasons.append(MISSING_UNIT)
```

**It performs no semantic or dimensional validation of what `unit` contains** — any
truthy value satisfies it. Measured from the function's own source, not inferred from
its name or docstring. It has no unit vocabulary, no dimension table, and does not
distinguish a physical SI unit from any other truthy string
(`test_quantity_contract_requires_no_dimensional_validation`). This settles §3
precisely: the contract *requires* value + a truthy unit; it neither explicitly permits
nor forbids a dimensionless declaration — it simply never validates deeply enough to
know the difference. That silence is not license to fabricate one, but it is evidence
that a genuine, non-fabricated dimensionless declaration is not a weakening of the gate.

## Magnitude semantics

Four concepts, kept apart rather than collapsed, per §4/§6:

| Concept | Value | Source |
|---|---|---|
| Property | `"earthquake_magnitude"` | new, descriptive, matches existing naming (`water_level`, `tensile_strength`) |
| Quantity (value) | the numeric magnitude | verbatim `properties.mag`, already `magnitude` |
| Physical dimension (unit) | `"dimensionless"` | a documented scientific fact: seismic magnitude scales are logarithmic and carry no physical dimension by international convention (SI itself recognizes the symbol `1` for dimensionless quantities) |
| Method (scale identity) | verbatim `magnitude_type` (`"mb"`, `"ml"`, ...) | USGS's own data model already separates *which number* from *how it was computed* |

**`Mw` never becomes `unit`.** Every existing extractor in this repository that supplies
a unit uses a genuine physical unit of measurement (NOAA: `m`/`ft`; the Phase 29
accepted fixture: `MPa`); nothing in this codebase has ever used `unit` to mean a scale
identifier, so writing `unit="mb"` would be inconsistent with every established
precedent, not merely internally ambiguous. Verified directly:
`test_scale_identifier_never_appears_as_the_unit_value`.

## Method provenance

The existing method-block contract is one flat, truthy `content["method"]` string with
no format requirement. `magnitude_type` satisfies it **without any new ontology**: the
implementation literally aliases the existing `magnitude_type` value into a second key,
carried verbatim, never wrapped or reinterpreted
(`test_method_is_the_verbatim_source_value_never_reinterpreted`). When a real event
genuinely supplies no `magType`, `method` is `None` too, and `MISSING_METHOD` correctly
fires — not defaulted (`test_a_missing_magtype_yields_a_genuine_missing_method_rejection`).

## Representation decision

**Split, and reported honestly as split — not rounded to a single verdict:**

- **Method: accepted by existing representation.** No invention required.
- **Quantity/unit: accepted by existing representation**, using a genuine,
  non-fabricated `"dimensionless"` declaration — a real fact about the scale, not a
  placeholder chosen to pass the gate.
- **Conditions: source insufficient.** `place`/`origin_time`/`depth_km` identify *which
  event* this is — identity, not a measurement condition a second reading of the same
  quantity could legitimately vary by. `status` (`automatic`/`reviewed`) is
  revision/QC metadata, the *same category* Phase 17 excluded from NOAA's content (`q`)
  for the same reason: a later, reviewed revision of an event must stay comparable to
  its own earlier automatic reading, not be silently split into a different
  comparison context by treating a QC flag as a condition. No genuine conditioning
  field exists in any real fixture in this repository. `MISSING_CONDITIONS` preserved.
- **Uncertainty: source insufficient.** No fixture or documented field in this
  repository's USGS acquisition carries a magnitude error or confidence value.
  `MISSING_UNCERTAINTY_KIND` preserved — and `absent` was **considered and rejected**,
  not merely omitted: assigning it would assert *"the source explicitly reported no
  error,"* a stronger and different claim than *"no error data was available to this
  acquisition at all."*

---

## Implementation

**One additive change to one shipped extractor**, `daf/extractors/usgs_earthquakes.py`:
four new content keys (`property`, `value`, `unit`, `method`) added alongside every
existing one (`event_id`, `magnitude`, `magnitude_type`, `place`, `origin_time`,
`updated`, `status`, `longitude`, `latitude`, `depth_km` — all unchanged). Two new
module constants, `PROPERTY = "earthquake_magnitude"` and
`DIMENSIONLESS_UNIT = "dimensionless"`. `daf/adapters/usgs_earthquakes.py` and every
other production module are untouched.

Canonical architecture: `architecture/method_provenance_reachability.yaml`'s
`usgs_magnitude_type` determination extended with the quantity/conditions/uncertainty
decisions, their evidence, the identity impact, and the real acquisition result.
`tests/test_edgar_method_provenance_reachability.py`'s Phase 30 test updated to record
that this candidate — named there and deliberately not built — was implemented here.
Doctrine regenerated, zero diff.

New test file `tests/test_usgs_property_admission_integration.py` (23 tests), plus two
new tests in `tests/test_usgs_earthquakes_extractor.py` locking the additive keys and
the no-`magType` honesty case.

## Real acquisition

`plan_id=usgs-plan`, real fixture GeoJSON bytes for three synthetic events, through
`execute_plan_recorded` — adapter → extractor → `run_scout` → `ClassifiedPool`, nothing
manually constructed. 3 artifacts acquired, 3 observations admitted (class `measured`),
execution `SUCCEEDED`/`acquired`, zero `ScoutAdmissionFailure`s.

## Identity

**Changed, and disclosed rather than concealed, per §11.** `Observation.content`
genuinely changed, so `Observation.id` for USGS acquisitions differs from every prior
phase. Verified directly, not merely asserted: the *same* `record_ids` a real
acquisition produced, re-hashed with the pre-Phase-31 content shape (every new key
stripped, every old key checked equal), yields a **different** observation id than the
real, current one — isolating the identity change to content alone
(`test_observation_identity_changed_and_is_disclosed`).

This is safe to disclose rather than migrate, for two independently sufficient reasons:
no `EvidencePool` records are committed anywhere in this repository
(`architecture/invariants.yaml` migration count: 0), and USGS observations have always
emitted `entities=(), relations=()`, so no existing `retrieval.engine`/
`materials.analysis` comparison-context behavior — the exact concern that stopped a
similar change to NOAA in Phase 29 — exists here to disturb
(`test_artifact_identity_is_unaffected_by_the_content_addition` confirms `artifact_id`,
which never depends on content, is untouched).

## Evidence

`pool.fingerprint()` is byte-identical before and after a canonical-assertion pass.
Every rejected USGS observation remains real, retrievable evidence, correctly
classified `measured`. An AST sweep of `assertion/` finds zero `put_*`/`admit_*` calls.
The method field and the magnitude value do not become evidence by themselves — they
remain properties on an Observation whose canonical-assertion admissibility is judged
independently, and still fails, on the two dimensions the source cannot supply.

## Quarantine

**`partially_enforced` — unchanged.** All three USGS refusals are retained in the
Phase 29 canonical-assertion quarantine store (separate from Scout admission
quarantine, unchanged), each linked to its execution, each carrying exactly
`{MISSING_CONDITIONS, MISSING_UNCERTAINTY_KIND}`. No repair path exists; none was
built.

## Metrics

| | USGS (real, this phase) | EDGAR (Phase 30) |
|---|---:|---:|
| Documents acquired | 3 | 3 |
| Property candidates | **3** (was 0) | 0 |
| Accepted | 0 | 0 |
| Refused | 3 | 0 |
| Rejection codes | `MISSING_CONDITIONS`, `MISSING_UNCERTAINTY_KIND` | *(no candidates to reject)* |
| Property-layer rejection rate | 1.0 | `None` |
| Phase 27/28 terminal refusals | 0 | 0 |
| Phase 27/28 rejection rate | 0.0 | 0.0 |
| Unclassified backlog | 0 | 0 |

Phase 27/28's acquisition-stage metrics are measured, not merely assumed, unaffected
(`test_phase_27_28_metrics_are_unaffected_by_the_usgs_extension`). Two runs of
identical bytes on different days produce identical `by_code`/`rejection_rate` and
correctly distinct execution ids
(`test_repeated_real_acquisition_produces_identical_admissibility_verdicts`).

## EDGAR comparison

The two determinations sit on opposite sides of the same test, which is the point of
running them together:

| | EDGAR `form_type` | USGS `magnitude_type` |
|---|---|---|
| Classifies | which regulatory document was filed | how a scientific quantity was computed |
| Real values | `10-K`, `8-K`, `S-1`, ... | `mb`, `ml`, `mw`, ... |
| Content has a property/value pair at all? | **No** | **Yes** (added this phase) |
| Verdict | `document_classification` | `legitimate_method_provenance` |
| Property candidates examined | 0 | 3 |
| Action taken | none | additive extractor extension |

`test_edgar_semantics_are_unchanged_by_the_usgs_extension` asserts both verdicts
directly and confirms EDGAR's extractor source is untouched — the system distinguishes
genuine method provenance from document metadata that merely resembles it, rather than
accepting any source field that looks method-shaped.

---

## Regression

| Check | Result |
|---|---|
| `tests/test_usgs_property_admission_integration.py` | **23 passed** |
| `tests/test_usgs_earthquakes_extractor.py` | **7 passed** (5 prior + 2 new) |
| `tests/test_edgar_method_provenance_reachability.py` | **14 passed** — one Phase 30 test updated to reflect this phase's implementation |
| DAF full suite | **611 passed** (587 prior + 23 new + 1 updated) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/ assertion/` | Success, **75 source files** |
| `ruff` | new/changed files carry only the repo-wide `UP006`/`UP035`/`UP045` conventions; one `I001` and one `RUF059` were found and fixed |
| Doctrine | regenerated, **654 / 1400 words**, zero diff |
| `git status` | clean; only the new test file plus the extractor, canonical YAML, doc, and doctrine changes staged |

## Bent

**Bent: zero.** `science/admissibility.py`, `daf/execution/{quarantine,store,recorded,metrics}.py`,
`assertion/`, `daf/adapters/usgs_earthquakes.py`, and every other extractor/adapter are
byte-identical to Phase 30. The one production change is additive to one extractor's
content dict, adding new keys and modifying none.

## Qualified

- The `"dimensionless"` unit declaration is a genuine scientific fact about magnitude
  scales, not a universal template — it should not be read as license to declare any
  quantity dimensionless merely to satisfy `MISSING_UNIT`.
- The `method` value is the raw scale code (`"mb"`) rather than an expanded, self-
  describing string, deliberately: the surrounding content (`property`,
  `event_id`, ...) supplies context by co-location, and expanding it would be adding
  interpretation the source did not supply.
- USGS observations remain unreachable through `retrieval.engine`/`materials.analysis`
  (still `entities=(), relations=()`) — this phase changed admissibility judgment only,
  not graph reachability.

## Unresolved

- **No source in this repository can currently produce an *accepted* property
  assertion through real, unmodified acquisition** — unchanged in aggregate count from
  Phase 29/30, though the *reason* narrowed for USGS specifically from "six absences"
  to "two genuine, source-limited absences."
- Whether a genuine conditioning field exists anywhere in the real USGS FDSN schema
  that this repository's fixtures simply don't populate (e.g. a real `magSource`
  network identifier) remains unexamined — not fabricated here, not ruled out.
- Carried unchanged: `quarantine_repair`, `retraction_semantics`,
  `multi_writer.write_conflict`, `builder_check_lineage`, `attested_snapshot_identity`,
  `capabilities_5_to_9`.

## Measured bottleneck

**Uncertainty is now the single most common real refusal reason across every source
this project has acquired.** NOAA (Phase 29, 240/240), and now USGS (3/3), both fail
`MISSING_UNCERTAINTY_KIND` — two structurally different sources, two different
scientific domains, the same absence. Method and conditions vary source to source;
uncertainty data has been absent from every real acquisition this project has ever run.

## Next executable frontier

**Determine whether any DAF-reachable source in this repository ever reports a
magnitude/measurement uncertainty value at all**, before attempting to wire one.
Concretely: inspect the full USGS FDSN event-detail schema (not just this repository's
synthetic fixtures) for a genuine error field (e.g. `magError`, `magNst`), and
separately inspect whether NOAA CO-OPS's `s` (sigma) field — already extracted and
already excluded from this repository's admissibility wiring in Phase 29 for lack of an
`uncertainty_kind` companion — could close *that* source's uncertainty gap the same way
this phase closed USGS's method gap: by adding, not inventing. This is the same
reconnaissance-then-decide discipline this phase and Phase 30 both applied, aimed at
the one gate every acquired source has failed so far.

---

*Halts here per the stop condition: inspected, measured, determined per-dimension
rather than as one verdict, implemented the smallest additive extension the evidence
supported, disclosed the identity change it caused, documented, tested, committed and
pushed. Neither gate was weakened, no unit was fabricated, no scale identifier was
treated as an SI unit, and EDGAR's determination was not reopened.*
