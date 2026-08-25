# Phase 28 — Admission Gate Reachability

*(Continues from `809e77c`. Answers the question Phase 27 left open: which admission
gates can a real DAF acquisition actually reach.)*

```
code exists   !=   acquisition can reach it   !=   real acquisition has exercised it
```

---

## 1. Implemented

`architecture/admission_reachability.yaml` (canonical: the verdict for all 15 refusal
codes, method, and two corrections to earlier phases); `tests/test_admission_reachability.py`
(20 tests); three fixtures representing real source conditions
(`edgar_daily_index_synthetic_20260701_empty.idx`, `usgs_event_detail_synth00000001_empty.json`
— both genuinely zero-length — and `graph_dataset_structure_only.json`); one corrected
paragraph in `docs/PHASE_27_INGEST_REJECTION_METRICS.md`; one corrected `unreachable_refusal_stages`
entry and one new invariant, `refusal_reachability_declared`, in `architecture/invariants.yaml`;
regenerated `docs/generated/DOCTRINE.md`. **No production code changed** — no adapter, no
extractor, no admission gate, no execution record, no quarantine mechanism, no metric.

---

## 2. Reconnaissance — why `record → EMPTY_CONTENT` cannot fire

Read in full before writing anything: `evidence/admission.py`, `scout/pipeline.py`, and
every one of the six adapters and seven extractors that ship with DAF.

`run_scout` builds both objects from the identical expression:

```python
document = make_document(source_id=source.id, raw_content=raw_doc.content, ...)   # line 104
if admit_document(pool, document) is a list: continue                              # line 108
record = make_record(document_id=document.id, locator=raw_doc.locator,
                     raw_content=raw_doc.content)                                  # line 114
if admit_record(pool, record) is a list: continue                                  # line 117
```

`admit_document` tests the exact same string one gate earlier and `continue`s before
`admit_record` ever runs. **This is not a missing fixture — it is a structural property
of the unmodified pipeline.** No adapter input can reach the record gate with empty
content, because the document gate consumes the condition first. Building a fixture for
it, however carefully, would prove nothing: the pipeline would never let it arrive.

That is exactly the failure mode §6 warned against — mistaking "I can call `admit_record()`
directly" for acquisition reachability — inverted: here the honest finding is that the
target genuinely cannot be reached, and the fix is to report that rather than route
around it.

---

## 3. The smallest real seam — found by tracing, not searching

Rather than stop at the disproof, the same tracing method was applied to the other five
stages, then adversarially re-checked by an independent workflow (8 tracer/refuter agents,
129 tool calls, every REACHABLE claim executed against real code before being accepted).
Two real seams were found and confirmed:

**`document → EMPTY_CONTENT`.** `EdgarDailyIndexSourceAdapter` and `UsgsEarthquakeSourceAdapter`
both decode an HTTP response body straight into `RawDocument.content`
(`edgar_daily_index.py:150-158`, `usgs_earthquakes.py:184-197`) with **no emptiness check** —
correctly so; that check is the gate's job, not the adapter's. A directory listing that
names a file, served as a zero-length 200 body, reaches `admit_document` and is refused.
Executed against **both** bindings independently; both produce exactly one
`ScoutAdmissionFailure(stage="document", errors=(AdmissionError("Document","EMPTY_CONTENT",...),))`.

**`observation → EMPTY_CONTENT`.** `GraphDatasetExtractor` is the one extractor that
*transforms* its payload rather than passing fixed keys through: it drops `entities`,
`relations` and `id` as structure (`STRUCTURAL_KEYS`) and keeps everything else as
`Observation.content`. A dataset record declaring **only** those three keys — a real,
well-formed graph declaration with no measured value — yields `content == {}` while the
raw JSON string (and therefore the document and the record) both pass their gates
normally. Executed: one `observation`-stage refusal, zero document/record refusals, the
other record in the same file accepted.

Both were run through `execute_plan_recorded` — the complete recorded acquisition path,
nothing stubbed — not through a direct `admit_*()` call.

---

## 4. A correction the adversarial pass forced

Verifying REACHABLE was not the only thing the tracing did. It also disproved two claims
this project itself made:

| Phase | Claimed | Actual |
|---|---|---|
| 26/27 | `extraction → MISSING_MODEL_CONFIDENCE` reachable | **ADAPTER_UNREACHABLE.** All seven shipped extractors hardcode a non-`model:` method with `confidence=1.0` (checked over every extractor source; `test_no_shipped_extractor_can_produce_a_model_attributed_candidate` locks it). It was only ever reached by a bespoke extractor written for `tests/test_execution_record.py`. |
| 27 | `relationship → UNKNOWN_LABEL` reachable | **ADAPTER_UNREACHABLE.** Every relation-emitting extractor validates its endpoints before emitting: `GraphDatasetExtractor` checks against its own declared labels and raises rather than emit an unknown one; `ArxivExtractor` and the NOAA measurement extractor build endpoints from the same non-empty strings they just emitted as entities. It was only ever reached by a bespoke extractor written for `tests/test_ingest_metrics.py`. |

**The count of gates exercised by real acquisition was zero at the end of Phase 27, not
two.** Both corrections are recorded as canonical data
(`architecture/admission_reachability.yaml`'s `corrections` block) with a test —
`test_the_matrix_records_the_two_corrections_to_earlier_phases` — so the claim cannot
quietly revert, and the source paragraph in `docs/PHASE_27_INGEST_REJECTION_METRICS.md`
is amended in place rather than left standing.

---

## 5. Full reachability matrix (measured)

| Stage | Kind | Code | Verdict | Real input | Exercised |
|---|---|---|---|---|---|
| document | terminal | `EMPTY_CONTENT` | **REACHABLE** | zero-length response body, EDGAR or USGS | ✓ |
| document | terminal | `UNKNOWN_SOURCE` | STRUCTURALLY_UNREACHABLE | — | — |
| record | terminal | `EMPTY_CONTENT` | STRUCTURALLY_UNREACHABLE | — (this phase's named target) | — |
| record | terminal | `UNKNOWN_DOCUMENT` | STRUCTURALLY_UNREACHABLE | — | — |
| extraction | terminal | `MISSING_MODEL_CONFIDENCE` | ADAPTER_UNREACHABLE *(corrected)* | — | — |
| observation | terminal | `EMPTY_CONTENT` | **REACHABLE** | structure-only graph-dataset record | ✓ |
| observation | terminal | `NO_RECORD_IDS` | STRUCTURALLY_UNREACHABLE | — | — |
| observation | terminal | `UNKNOWN_RECORD` | STRUCTURALLY_UNREACHABLE | — | — |
| observation | terminal | `NO_EXTRACTION_METHOD` | EXTRACTOR_DEFECT_ONLY | — | — |
| referent | partial | `EMPTY_NATURAL_KEY` | ADAPTER_UNREACHABLE | — | — |
| referent | partial | `EMPTY_KIND` | ADAPTER_UNREACHABLE | — | — |
| relationship | partial | `UNKNOWN_LABEL` | ADAPTER_UNREACHABLE *(corrected)* | — | — |
| relationship | partial | `EMPTY_TYPE` | EXTRACTOR_DEFECT_ONLY | — | — |
| relationship | partial | `UNKNOWN_REFERENT` | STRUCTURALLY_UNREACHABLE | — | — |
| relationship | partial | `UNKNOWN_OBSERVATION` | STRUCTURALLY_UNREACHABLE | — | — |

**15 codes total: 2 reachable and exercised, 7 structurally unreachable, 4 adapter-unreachable,
2 extractor-defect-only.** Every STRUCTURALLY_UNREACHABLE and ADAPTER_UNREACHABLE row names
its exact blocker in the canonical YAML — file and line, not "not currently observed."

---

## 6. Real acquisition runs

**Run A — EDGAR, empty `.idx`.** `plan_id=edgar-plan`, `source_id=edgar-filings`,
`adapter_id=edgar-daily-index`. Listing names three dates; `20260701` served empty.
Result: 2 artifacts accepted (`20260702`, `20260703`), 1 admission failure
(`stage=document, code=EMPTY_CONTENT`), execution `SUCCEEDED`/`acquired`, 1 quarantine
record linked to the execution id.

**Run B — USGS, empty event detail.** Same shape, `adapter_id=usgs-earthquakes`, one of
three event details served empty. Identical single `document`/`EMPTY_CONTENT` failure —
confirming the seam is a property of the *pattern* (decode-and-wrap with no check), not
one adapter's bug.

**Run C — graph-dataset, structure-only record.** `plan_id=qc-plan`, `adapter_id=graph-dataset`.
Two documents and two records admitted (both raw JSON strings non-empty); one observation
admitted, one refused (`stage=observation, code=EMPTY_CONTENT`).

Every run went through `execute_plan_recorded` unmodified.

---

## 7. Terminal metrics (re-measured)

| Run | Accepted | Terminal refusals | Attempts | Terminal rate |
|---|---:|---:|---:|---:|
| A (EDGAR) | 2 | 1 | 3 | **0.333** |
| B (USGS) | 2 | 1 | 3 | 0.333 |
| C (graph-dataset) | 1 | 1 | 2 | 0.500 |

Phase 27's regression is intact: `test_the_phase_27_terminal_versus_naive_distinction_still_holds`
re-derives `TERMINAL_STAGES`/`PARTIAL_STAGES` and confirms a newly reachable terminal
stage changes *which* rate is computed, never *how*. The naive and terminal rates
coincide for run C only because it contains no partial refusal — exactly the condition
under which Phase 27 said they must agree.

## 8. Partial metrics

No partial-stage refusal (`referent`, `relationship`) was produced in this phase — both
remain `ADAPTER_UNREACHABLE`/`EXTRACTOR_DEFECT_ONLY`. No rate is assigned to a code with
no meaningful denominator; that machinery is unchanged from Phase 27 and is not
re-implemented here.

## 9. Unclassified backlog

Unaffected by a refusal, as it must be: a refused object never enters the pool, so it
cannot appear in the backlog as classified or unclassified. `test_the_backlog_is_unaffected_by_a_refusal`
measures this directly — the accepted observation shows `unclassified=0`; the refused
one is absent from the store entirely, not present-and-flagged.

## 10. Execution provenance

Every run's `ExecutionRecord` carries the real `adapter_id`/`adapter_version` (derived
from actual module source, per Phase 26), `admission_failure_count` matching the actual
refusal count, and a `QuarantineRecord` whose `execution_id` round-trips through
`QuarantineStore.for_execution` after being read back from disk. **No new identity was
created** — every id used here is `operation_id`/`execution_id`/`artifact_id` from
Phase 26, unchanged.

## 11. Quarantine

**`partially_enforced` — unchanged, and correctly so.** This phase demonstrates two
*additional* reachable refusal classes flowing into the existing quarantine mechanism; it
implements no repair path and no new quarantine semantics, so the enforcement status is
left exactly where Phase 27 set it. `daf/execution/quarantine.py` was not modified.

## 12. Evidence boundary

Confirmed three ways: the refused EDGAR document's *would-be* id is checked directly
against the pool (`test_the_refused_document_is_absent_by_identity_not_merely_by_count`)
and is absent — not merely undercounted; the accepted documents/records in the same run
all carry non-empty content, proving no truncated object slipped through; and the
execution record and quarantine record themselves carry no evidence class
(`register.class_of(...) == "unclassified"`), confirming `execution record ≠ evidence`
and `rejection metric ≠ evidence` hold under a live refusal, not merely by construction.

## 13. Determinism

Two runs of the identical graph-dataset input, a day apart: different `execution_id`
(different runtime/time — correctly so), identical `operation_id`, identical `by_code`
tuples (stage, code, count, rate), identical terminal/partial counts. The second run's
outcome is `duplicate` (the bytes were already acquired), and its own refusal still fires
and is attributed to its own execution — repetition does not merge or suppress it. The
combined `ingest_report` over both runs is itself reproducible from disk alone.

## 14. Doctrine / architecture

`architecture/admission_reachability.yaml` was added because the reachability verdict is
exactly the kind of structural fact `architecture/doctrine.yaml`'s own routing rule sends
to canonical YAML rather than prose — and because Phase 27 shipped a wrong claim as
prose, which a test could not have caught. It carries a drift guard
(`test_the_matrix_covers_exactly_the_codes_the_pipeline_can_emit`) that parses the actual
vendored `admission.py`/`pipeline.py` source and fails if a new refusal code appears
without a declared verdict. Regenerated; **zero diff** on the conformance check.

---

## 15. Regression

| Check | Result |
|---|---|
| `tests/test_admission_reachability.py` | **20 passed** |
| DAF full suite | **549 passed** (529 prior + 20 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/` | Success, **73 source files** (unchanged — no production module touched) |
| `ruff` | new files carry only the repo-wide `UP006` convention; one `F401`, two `RUF059`, one `FURB167` found in the new test file were fixed |
| Doctrine | regenerated, **654 / 1400 words**, conformance gate green |

## 16. Bent

**Bent: zero.** No admission gate, no adapter, no extractor, no execution record, no
quarantine mechanism and no metric was modified. The submodule is byte-identical.

## 17. Qualified

- `record → EMPTY_CONTENT`, this phase's named target, is **structurally unreachable**
  through the unmodified pipeline — not a gap to be closed by a fixture, a limitation of
  the architecture as given.
- The reachability of `document`/`observation` is qualified to the two source conditions
  measured (a zero-length HTTP body; a structure-only dataset record) — not a claim that
  every input reaching those adapters can trigger it.
- `extraction`/`relationship` reachability, previously asserted, is now qualified to "the
  pipeline supports it" rather than "a shipped source can produce it."

## 18. Unresolved

- **`extraction`/`relationship` remain genuinely unreachable** until a model-backed
  extractor or a source with a real dangling-label condition is built. Neither is
  invented here.
- `referent → EMPTY_NATURAL_KEY`/`EMPTY_KIND` and `relationship → EMPTY_TYPE` are
  ADAPTER_UNREACHABLE / EXTRACTOR_DEFECT_ONLY respectively — closing them would require
  a new adapter or a bug, not a fixture. Not attempted.
- Carried unchanged from Phase 27: `quarantine_repair`, `rejection_rate_per_invariant`'s
  aggregation gap, `retraction_semantics`, `multi_writer.write_conflict`,
  `builder_check_lineage`, `attested_snapshot_identity`, `capabilities_5_to_9`.

## 19. Measured bottleneck

**Two of four terminal stages are exercisable; two are architecturally closed.**
`document` and `observation` now have real, repeatable evidence. `record` is
structurally unreachable and `extraction` is unreachable from any shipped extractor. Of
the two partial stages, both remain unreachable without new code. The rejection-rate
metric can therefore only ever report real, non-trivial data for **two** of six stages
under the current adapter set — the other four will report a rate of `None`/absent
forever unless a new adapter, extractor, or (for `record`) a change to the vendored
pipeline is introduced. That is now a documented, tested fact rather than an open
question.

## 20. Next executable frontier

**Build the first model-backed extractor.** It is the one remaining unreachable gate
whose closure requires no vendored-pipeline change and no speculative adapter: a real
`extraction_method="model:..."` path with a genuinely omittable confidence is exactly
the condition `MISSING_MODEL_CONFIDENCE` exists to catch, and Phase 22–24's vocabulary/
capability work already establishes the pattern for adding a new interpretive layer
without touching acquisition. It would close one of the two remaining ADAPTER_UNREACHABLE
terminal-adjacent gates with a real capability rather than a synthetic one, and is the
only remaining gate this repository could close without inventing an adapter behavior
purely to trigger a refusal.

---

*Halts here per the stop condition: inspected, traced, adversarially verified, one
target disproved honestly, two real seams found and exercised, two prior claims
corrected, measured, documented, committed and pushed. No gate was weakened, no
identity was created, no failure was fabricated.*
