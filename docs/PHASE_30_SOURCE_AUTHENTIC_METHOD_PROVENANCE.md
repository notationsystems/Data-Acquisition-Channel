# Phase 30 — Source-Authentic Method Provenance

*(Continues from `a25ee46`. Answers the question Phase 29's next-frontier section posed,
and corrects a factual error in how that section posed it.)*

**Result: EDGAR's form-type field is real, preserved, and not scientific method. No
production code was changed.** An acceptance rate of zero is the correct outcome here,
per the brief's own governing principle.

---

## Reconnaissance

Read in full: `daf/extractors/edgar_daily_index.py`, its adapter, every EDGAR fixture,
and — because the determination method generalizes — `daf/extractors/usgs_earthquakes.py`
and its fixture, for comparison.

**The first finding corrects Phase 29 itself.** Its closing section claimed EDGAR's
form-type field is *"already present in the raw `.idx` row, currently discarded."*
That is factually wrong, measured directly against a real acquisition:

```python
filings.append({..., "form_type": form_type, ...})
form_type_counts[form_type] = form_type_counts.get(form_type, 0) + 1
...
content = {"date_filed": ..., "filing_count": ..., "form_type_counts": form_type_counts,
           "filings": filings}
```

`form_type` is parsed per filing and aggregated into `form_type_counts` — **both are
present in every acquired Observation's content today**, and have been since this
extractor was written. Nothing here was ever discarded. This is corrected in place in
`docs/PHASE_29_LIVE_PROPERTY_INGEST_INTEGRATION.md` §19.

**The second finding is the one that actually answers this phase's question.** A real
acquisition of the standard three-day EDGAR fixture window produced these form types,
verbatim:

```
10-K, 8-K, 8-K/A, S-1, 424B3, D
```

---

## Candidate field

`filings[].form_type` / `form_type_counts` in `daf/extractors/edgar_daily_index.py`.

## Decision

**Contextual/document classification only.** Every observed value is a documented SEC
regulatory filing-type code (17 CFR 240/249): `10-K` is an annual report, `8-K` a
current report of a material event, `8-K/A` an amendment to one, `S-1` an IPO
registration statement, `424B3` a prospectus filed under Rule 424(b)(3), `D` a
Regulation D exempt-offering notice. Each classifies **which regulatory disclosure form
a company filed** — none describes how a measurement, computation, or simulation was
performed. Promoting a filing-type code to a measurement method would be a category
error, not a normalization.

**A second, independent finding makes the question moot even before the semantic one is
reached.** `daf.extractors.edgar_daily_index`'s `Observation.content` is
`{date_filed, filing_count, form_type_counts, filings}` — **it has no `property` key at
all.** Measured directly: `assertion.property_admissibility.property_candidates()` over
a real EDGAR acquisition examines **zero** candidates, and
`science.admissibility.no_context_free_property` on the raw content returns
`MISSING_PROPERTY`, `MISSING_VALUE`, and `MISSING_UNIT` **alongside**
`MISSING_METHOD`/`MISSING_CONDITIONS`/`MISSING_UNCERTAINTY_KIND` — six simultaneous
absences, not one gap a method fix would close. EDGAR's daily-index observation is a
filing-index summary, not a scientific property assertion, and no reshaping of
`form_type` changes that.

**Conditions and uncertainty were checked independently, per §7/§8, rather than assumed
solved together with method.** EDGAR reports no measurement conditions of any kind
(no temperature, instrument, sample, or protocol) and no uncertainty semantics of any
kind (a regulatory filing has no error bar). Both `MISSING_CONDITIONS` and
`MISSING_UNCERTAINTY_KIND` are preserved on their own evidence, not by inheritance from
the method finding. No value from `stated`/`estimated`/`propagated`/`absent` was
assigned — `absent` specifically was considered and rejected: choosing it would assert
*"the source reported no error,"* which is a different and stronger claim than *"the
source is not a measurement and has no error to report."*

---

## Implemented

**No production code.** `daf/extractors/edgar_daily_index.py`,
`daf/adapters/edgar_daily_index.py`, `science/admissibility.py`, `assertion/`, and every
other module under `daf/`, `science/`, `boundary/`, `bridge/`, `epistemics/` are
byte-identical to `a25ee46` — confirmed by `git diff --stat` returning empty for every
one of those paths.

What was added: `architecture/method_provenance_reachability.yaml` (the determination,
evidenced, plus the USGS candidate below); `tests/test_edgar_method_provenance_reachability.py`
(14 tests); a correction to `docs/PHASE_29_LIVE_PROPERTY_INGEST_INTEGRATION.md`'s wrong
claim; regenerated `docs/generated/DOCTRINE.md` (new source added, zero diff on
conformance); this document.

## Identity impact

**None.** No extractor, adapter, or gate was touched, so no artifact identity, version
identity, observation identity, or execution identity could have changed —
confirmed, not merely assumed: two runs of the identical EDGAR acquisition on different
days reproduce byte-identical `artifact_ids` and document ids, while their execution ids
correctly differ (two runs are two events, per Phase 26's established discipline). No
historical record exists to back-fill; none was touched.

## Real acquisition

`plan_id=edgar-plan`, real fixture `.idx` bytes for three days, through
`execute_plan_recorded` — the same real, unmodified adapter → extractor → `run_scout` →
`ClassifiedPool` path used throughout this project. 3 artifacts acquired, 3 observations
admitted (class `asserted`), execution `SUCCEEDED`/`acquired`, zero `ScoutAdmissionFailure`s.

## Admission

**Accepted properties: 0. Rejected properties: 0. Candidates examined: 0.** Not because
the gate rejected anything — because no EDGAR observation is a property candidate in the
first place. This is the correct, honest result for a source that has no scientific
property assertion to admit or reject.

## Rejection reasons

None produced by the property-admissibility layer, because no candidate was examined.
Direct application of `no_context_free_property` to real EDGAR content (not counted as
acquisition evidence, matching Phase 28's established discipline) returns all six:
`MISSING_PROPERTY`, `MISSING_VALUE`, `MISSING_UNIT`, `MISSING_METHOD`,
`MISSING_CONDITIONS`, `MISSING_UNCERTAINTY_KIND`.

## Metrics

| | EDGAR (real) |
|---|---:|
| Documents acquired | 3 |
| Property candidates | 0 |
| Accepted | 0 |
| Refused | 0 |
| Rejection rate (property layer) | `None` — absence, not a fabricated zero |
| Phase 27/28 terminal refusals | 0 |
| Phase 27/28 terminal denominator | 3 (accepted) |
| Phase 27/28 rejection rate | 0.0 |
| Unclassified backlog | 0 across all populated categories |

Phase 27/28's acquisition-stage metrics are untouched by this phase's determination —
measured directly on the same execution, not merely argued.

## Quarantine

**`partially_enforced` — unchanged.** No new refusal was produced (there was nothing to
refuse), so nothing was added to either quarantine store. The canonical-assertion
quarantine directory introduced in Phase 29 is untouched by this phase.

## Evidence boundary

`pool.fingerprint()` is byte-identical before and after running
`property_candidates()`/`assess_pool()` over the real EDGAR pool. Every acquired
observation remains real, retrievable evidence, correctly classified `asserted`. No
`put_*`/`admit_*` call exists anywhere in this phase's new code (there is none outside
one test file and one architecture YAML).

---

## Regression

| Check | Result |
|---|---|
| `tests/test_edgar_method_provenance_reachability.py` | **14 passed** |
| DAF full suite | **587 passed** (573 prior + 14 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/ assertion/` | Success, **75 source files**, unchanged |
| `ruff` | one `I001` in the new test file, fixed |
| Doctrine | regenerated, **654 / 1400 words**, zero diff |
| `git status` | clean; only two new paths (`architecture/method_provenance_reachability.yaml`, the new test file) plus the Phase 29 doc correction and regenerated doctrine |

## Bent

**Bent: zero.** No core invariant, gate, extractor, or adapter changed.

## Unresolved

- **No source in this repository can currently produce an accepted property assertion**
  — unchanged from Phase 29, and this phase confirms EDGAR does not close that gap. It
  remains genuinely open.
- Whether USGS's `magnitude_type` (see below) can be wired without inventing a `unit`
  for a logarithmic, conventionally unitless magnitude scale — identified, not answered.
- Carried unchanged: `quarantine_repair`, `retraction_semantics`,
  `multi_writer.write_conflict`, `builder_check_lineage`, `attested_snapshot_identity`,
  `capabilities_5_to_9`, `unreachable_refusal_stages`.

## Next executable frontier

**Determine whether USGS's `magnitude_type` field can supply genuine method provenance,
and what `quantity_is_typed` should require of a logarithmic magnitude scale before
attempting to wire it.** Unlike EDGAR's form type, this is a real candidate, evidenced
here rather than assumed: `daf/extractors/usgs_earthquakes.py` already carries
`magnitude` (the quantity) and `magnitude_type` (e.g. `"mb"`, `"ml"`, `"mw"`) straight
through from the source, and USGS magnitude-type codes name the *specific algorithm*
used to compute magnitude from seismographic data — categorically a measurement method,
not a document classification. It is recorded as `legitimate_method_provenance` in
`architecture/method_provenance_reachability.yaml` and **deliberately not implemented
here**: USGS content, like EDGAR's, has no `property`/`unit`/`conditions`/
`uncertainty_kind` shape today, and reshaping it raises its own open question this phase
does not answer — whether a Richter-style magnitude has a meaningful `unit` in the sense
`quantity_is_typed` expects. That reconnaissance, not an implementation, is the next
concrete step.

---

*Halts here per the stop condition: inspected, measured, determined honestly, corrected
a real error in the prior phase's report, documented, tested, committed and pushed. No
gate was weakened, no method was fabricated, and no production code was touched.*
