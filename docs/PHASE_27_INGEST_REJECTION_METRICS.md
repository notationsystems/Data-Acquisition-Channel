# Phase 27 — Ingest Rejection Metrics and Unclassified Backlog

*(Continues from `da0f504`. Closes the last unimplemented clause of the rejection
policy: `rejection_rate_per_invariant`.)*

---

## 1. Inspection — where the quantities already were

| Quantity | Where it lives today |
|---|---|
| ingest run | `ExecutionRecord.id` / `.operation_id` — Phase 26 |
| accepted | `ExecutionRecord.artifact_ids` (one per admitted observation) |
| rejected | `QuarantineRecord`, one per refused admission — Phase 26 |
| rejection invariant/reason | `AdmissionError.code`, retained in `QuarantineRecord.errors` |
| unclassified records | `ClassRegister.unclassified(ids)` — Phase 25 |
| execution identity | `ExecutionRecord.id` |
| **total attempted** | **nowhere — and it is not simply accepted + rejected** |

Existing metrics machinery was checked before writing any: `evidence/metrics.py`
(connectivity, novelty, redundancy) is a pure function of a `TrustGraph`, and its own
docstring records the same discipline this phase follows — *"not to implement a metric
simply because it sounds useful."* It measures a graph, not an ingest run, so there was
nothing to extend there.

Six refusal stages exist in `run_scout`: `document`, `record`, `extraction`,
`observation`, `referent`, `relationship`.

---

## 2. The measurement that decided the design

Before writing the metric, four dataset records were run through the **real, unmodified
pipeline** with an extractor that produces three different real outcomes:

```
outcome             : acquired
artifacts (accepted): 3
admission_failures  : 2
by stage            : {'extraction': 1, 'relationship': 1}
by code             : {'MISSING_MODEL_CONFIDENCE': 1, 'UNKNOWN_LABEL': 1}
observations in pool: 3          <-- not 2
```

**Three observations were admitted, not two.** The two refusals are not the same kind
of event:

| Stage | What happened | Effect on the pool |
|---|---|---|
| `extraction` | model named, no confidence supplied | the observation **never entered** |
| `relationship` | relation names a label not extracted as an entity | the observation **entered anyway**; only the edge was refused |

So the obvious formula is wrong:

```
naive:   refusals / (refusals + accepted)  =  2 / 5  =  0.40
actual:  terminal  / (terminal + accepted) =  1 / 4  =  0.25
```

`accepted (3) + terminal (1) = 4` = exactly the records offered. The arithmetic closes
only when the two refusal kinds are kept apart.

### The rule that follows

```
TERMINAL   document, extraction, observation, record
           the candidate did not enter. accepted + terminal = attempts,
           and a rate may be taken over that.

PARTIAL    referent, relationship
           the observation entered anyway. Counted and reported beside
           the rate, never folded into it -- doing so would claim a
           rejection that did not happen.
```

`RejectionCount.rate` is therefore `None` for a partial stage: a refused edge divided
by admissions is a number with no meaning, and reporting one would be worse than
reporting nothing.

`test_a_partial_refusal_does_not_count_against_the_rejection_rate` asserts both the
correct value **and** that it differs from the naive one, so the distinction cannot
quietly regress. `test_the_admitted_observation_behind_the_partial_refusal_really_is_in_the_pool`
independently confirms the premise by reading the pool rather than trusting the metric.

---

## 3. Absence stays explicit

A run that attempted nothing has **no** rejection rate — not a rate of `0.0`. The same
discipline `output_fingerprint` follows on a failed execution: a convenient zero is a
fabricated measurement.

Distinguished by test:

| Case | `attempts` | `rejection_rate` |
|---|---|---|
| Clean NOAA run | 40 | `0.0` — zero refusals over real attempts genuinely is zero |
| Unknown source, nothing attempted | 0 | `None` |

---

## 4. Nothing new was created

The prompt's four prohibitions — no execution-record redesign, no quarantine redesign,
no back-filled history, **no new identities** — are structural here, not just observed.
Every type in `daf/execution/metrics.py` is a **derived view**: no `id` field, never
persisted, recomputed on demand from records that already exist. The same discipline
`evidence/trust_graph.py` and `evidence/provenance.py` established for computed views.

- `test_metrics_introduce_no_identity_and_are_never_persisted` asserts no view carries
  an `id`, and that computing a report writes **no file** — the set of `*.json` on disk
  is byte-identical before and after.
- `test_the_report_is_recomputable_from_disk_alone` rebuilds the whole report in a
  fresh store and register and asserts equality.
- `ExecutionRecord`, `QuarantineRecord`, `ClassifiedPool` and the acquisition path are
  **unmodified**.

The one non-metric change is a single additive `FilesystemEvidenceStore.categories()`
classmethod — because the backlog must enumerate every category the store actually has,
and keeping a second copy of that list is exactly how the two would drift when a ninth
category appears.

---

## 5. Cross-checked rather than averaged over

A rate computed over refusals that were silently lost would understate itself. The
execution record already says how many refusals there were, so the two are reconciled:

```python
if len(refusals) != execution.admission_failure_count:
    raise QuarantineAccountingError(...)
```

Deleting one quarantine file raises rather than reporting a lower rate
(`test_missing_quarantine_records_are_detected_not_averaged_over`). An unrecognised
stage raises rather than being silently counted as terminal — and that test **swaps** a
record rather than adding one, so the count still matches and it exercises the stage
check instead of passing on the accounting check that precedes it.

---

## 6. The unclassified backlog

Counted per category from the **durable store**, not an in-memory pool, so it survives
a restart and so a corpus persisted before `class_assigned_at_ingest` existed is
reported as what it is: wholly unclassified (`test_an_unclassified_corpus_is_reported_as_wholly_unclassified`
measures exactly that — `unclassified_fraction == 1.0`).

One honest result worth naming: `referents` shows as unclassified, and that is correct
rather than a bug. `ClassifiedPool` deliberately never classifies a `Referent` — an
identity anchor asserts nothing about the world, so it has no class. The backlog
reports what is unclassified; a Referent genuinely is.

`unclassified_fraction` is `None` for an empty store — absence again, not zero.

The report deliberately carries both together: a rejection rate read alone invites
treating refusal as the only way evidence fails to become assertable, when
admitted-but-unclassified is the other way.

---

## 7. Report

**Implemented.** `daf/execution/metrics.py` (`rejection_metrics`,
`unclassified_backlog`, `ingest_report`, and their five view types);
`FilesystemEvidenceStore.categories()`; two invariants added and
`rejection_policy` updated in `architecture/invariants.yaml`; a `metrics` pointer in
`architecture/execution_record.yaml`; `tests/test_ingest_metrics.py`; regenerated
`docs/generated/DOCTRINE.md`; this document.

**Verified** — only what was actually executed:

| Check | Result |
|---|---|
| `tests/test_ingest_metrics.py` | **17 passed** |
| `tests/test_execution_record.py` | **28 passed**, unmodified |
| `tests/test_doctrine_generation.py` | **19 passed**, unmodified |
| DAF full suite | **529 passed** (512 prior + 17 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/` | Success, **73 source files** |
| `ruff` | new files carry only the repo-wide `UP006`/`UP035`/`UP045`/`UP037` conventions; one `RUF059` in new code was fixed |
| Doctrine | regenerated, **615 / 1400 words**, conformance gate green |

**Preserved.** Execution records, quarantine, `ClassifiedPool`, the acquisition path
and `run_scout` as the single evidence write path — all unmodified. Every Phase 25/26
boundary test passes unchanged. No historical execution record was invented.

**Extended.** Per-(stage, code) rejection counts and rates per run; the terminal/partial
distinction; the per-category unclassified backlog; a combined ingest report, scopable
to one operation.

**Bent: zero.** No core invariant changed. The submodule is byte-identical.

**Unresolved** — carried forward:

- `quarantine_repair` — refusals are now retained *and counted*; repair-and-re-ingest
  still does not exist.
- `unreachable_refusal_stages` — **newly recorded.** See below.
- `retraction_semantics`, `multi_writer.write_conflict`, `builder_check_lineage`,
  `attested_snapshot_identity`, `capabilities_5_to_9` — unchanged.

**Measured bottleneck.** Phase 26 reported that only `MISSING_MODEL_CONFIDENCE` was
reachable. This phase found a second — `UNKNOWN_LABEL` at the `relationship` stage — so
**two of six stages** can now be exercised. The other four (`document`, `record`,
`observation`, `referent`) remain unreachable from any DAF source, because no adapter
can construct evidence that fails those gates. Their rates are therefore *structurally*
zero rather than measured, and the report cannot currently tell the difference between
"this gate never fires" and "this gate is never reached". That is recorded in
`architecture/invariants.yaml` as `unreachable_refusal_stages` rather than left to look
like clean data.

> **Corrected by Phase 28.** Two claims in the paragraph above are wrong, and were
> disproved by tracing the adapters and then executing them:
>
> * **`document` is reachable**, not unreachable — the EDGAR and USGS adapters decode a
>   fetched body straight into `RawDocument.content` with no emptiness check, so a
>   zero-length HTTP 200 body reaches `admit_document`. `observation` is reachable too,
>   through a graph-dataset record that declares only structural keys.
> * **The two stages called "reachable" here are not**, from any shipped binding. Both
>   were reached only by extractors written for these tests. Every shipped extractor
>   hardcodes a non-`model:` method with `confidence=1.0`, and every relation-emitting
>   extractor validates its endpoints before emitting.
>
> The count of gates exercised by *real* acquisition was therefore **zero** at the end of
> Phase 27, not two. See `architecture/admission_reachability.yaml` and
> `docs/PHASE_28_ADMISSION_GATE_REACHABILITY.md`.

**Next executable frontier.** **Make the four unreachable admission gates reachable, by
building the one adapter path that can fail them.** The most concrete is `record`:
`admit_record` refuses `EMPTY_CONTENT` and `UNKNOWN_DOCUMENT`, and no current adapter
can produce either, because every one of them derives a record's content directly from
the bytes it fetched. An adapter over a source with genuinely empty rows — an EDGAR
index with a blank line, a NOAA window with a gap — would exercise it with real data.
Until then, four of the six rates this phase computes are unfalsifiable, and a metric
nobody can falsify is the weakest part of the rejection policy.

---

*Halts here per the stop condition: inspected, measured, built, run, observed, fixed,
audited, validated, documented, committed and pushed. Execution records and quarantine
were not redesigned; no identity was created; no history was back-filled.*
