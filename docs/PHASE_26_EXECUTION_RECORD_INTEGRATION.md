# Phase 26 — Execution Record Integration

*(Continues from `f87aeb6`. Closes the frontier Phase 25 identified: `execution_recorded`
was the one universal invariant with no representation in this repository at all.)*

```
             ACQUISITION
                  |
                  v
          EXECUTION RECORD
                  |
        +---------+---------+
        v                   v
   Artifact identity    Execution identity
        |                   |
        +---------+---------+
                  v
          Acquisition Result
                  |
                  v
       class_assigned_at_ingest
                  |
          +-------+-------+
          v               v
       admitted        rejected
          |               |
          v               v
       Evidence       Quarantine
```

---

## 1. Reconnaissance — what already existed

The term sweep required by §4 (`ExecutionRecord`, `execution_record`, `execution_id`,
`execution_identity`, `OperationTrace`, `execution_lineage`, `input_fingerprint`,
`output_fingerprint`, `artifact_fingerprint`, `adapter_version`, `runtime_version`,
`run_record`, `acquisition_record`) returned **zero hits across the entire repository,
including the vendored substrate.**

Three things that *look* like execution provenance were found and read in full. None
of them is one:

| Found | What it actually is | Why it is not an execution record |
|---|---|---|
| `evidence/provenance.py` — `ancestry_of` | `DerivedValue.derived_from` traversal | A derived read-only view over the pool. Its own docstring: *"there is no identity to compare, because nothing here is evidence."* Describes dependency, not an event |
| `core/canonical/version.py` — `ProvenanceInfo(author, transaction_id, source, timestamp)` | Provenance of a canonical **`Version`** | Describes who accepted a state version. DAF never creates a `Version`. Lives in the never-modified submodule |
| `morpho/provenance.py` — `ProvenanceRecord(source, origin_version, compiler_version, …)` | Provenance of a **Morpho compilation** | Describes a compile, not an acquisition. Also vendored |

And the seam itself already said so out loud. `daf/orchestration/result.py`:

> *"It is explicitly NOT scientific evidence, NOT provenance, and NOT an execution
> ledger — it carries no operation id, no execution record, and is never persisted
> anywhere by this module."*

That was a deliberate prior decision, and this phase is the one that changes it.

### Ownership: **Case B**, with the Case C caveat stated

An identity/fingerprinting substrate exists and no execution-event record does.

- **Reused, not re-invented:** `evidence.identity.content_hash` — every id minted in
  this phase uses the same primitive as every other id in the repository.
- **Reused vocabulary:** `source`, `timestamp`, and the *notion* of a transaction
  coordinate come from `ProvenanceInfo`/`ProvenanceRecord` rather than being renamed
  into synonyms.
- **DAF-owned, and marked as an integration dependency:** DAF is the acquisition
  boundary, so the record lives here. `architecture/execution_record.yaml` states
  `scope: daf_acquisition_only` and records, in the file itself, that a broader
  unified substrate which later grows its own contract should **absorb** this one
  rather than sit beside it. It is not claimed to be globally canonical.

---

## 2. Two hashes, deliberately different semantics

The single most important design decision, and the one §13 explicitly warns not to
assume:

```
execution_id   = H({operation_id, runtime_id, started_at})    minted BEFORE the run
content_digest = H(every other field)                          minted when it ends
```

**Why the identity hash excludes the outcome.** §10 requires that a run which begins
and then fails stays auditable. If the execution id were a function of the outcome it
could not exist until the outcome did — so a plan that fails validation, before an
adapter is even resolved, would have no record at all. Minting first also means the
id cannot shift depending on how the run turned out.

**Why that needs a second hash.** An identity that excludes `status`, `error`,
`artifact_ids` and `output_fingerprint` leaves those fields untamper-evident.
`content_digest` covers them. `execution_record_from_dict` recomputes **both** and
raises `ExecutionIdentityMismatch` or `ExecutionIntegrityMismatch` accordingly.
Measured on real persisted records for seven separate fields.

Contrast with artifact identity, which is the *opposite* requirement:

| | must be stable across runtimes | must differ per run |
|---|---|---|
| `artifact_id`, `version_id`, `Observation.id` | **yes** | no |
| `operation_id` | yes | no |
| `execution_id`, `runtime_id` | no | **yes** |

`test_artifact_identity_is_stable_across_execution_environments` runs the same NOAA
acquisition twice — different hostname, platform, process id, and a run a year and a
half apart — and asserts different execution ids alongside **byte-identical**
`operation_id`, `artifact_ids`, `version_ids`, `input_fingerprint` and
`output_fingerprint`. That is §8, measured rather than asserted.

---

## 3. Fields — only what acquisition can truthfully provide

`adapter_version` is the field most likely to have been faked. Nothing in the
repository provided one: `AdapterBinding` carried `adapter_id`, `build_adapter`,
`build_extractor`, `advance_position` and nothing else.

Rather than invent a version string that would drift, it is **derived from the code
that actually runs**:

```python
_code_version(NoaaWaterLevelSourceAdapter, NoaaWaterLevelMeasurementExtractor)
  == content_hash({module_name: module_source, ...})
```

It changes exactly when acquisition behaviour can change, is identical on two machines
with the same checkout, and is verified in the test by recomputing it from the two
source files independently. `AdapterBinding.version` is **additive and defaulted**, so
every pre-existing construction site and any externally registered binding is
unaffected — and an undeclared version is recorded as `None`, never guessed
(`test_an_undeclared_adapter_version_is_recorded_as_absent_not_guessed`).

**Absence is explicit throughout.** `adapter_id` is `None` when no adapter ran — which
is a fact about the run, not missing data. `output_fingerprint` is `None` on failure
and `make_execution_record` raises `OutputWithoutSuccess` if a caller offers one
anyway; `fingerprint(None)` returns `None` rather than hashing `{}`, because a run
that produced nothing and a run whose output happened to be empty are different facts.

**Deliberately excluded**, and recorded as excluded in the contract: model binding,
snapshot identity, GPU/accelerator fields, domain method blocks. None of them describes
anything this repository does.

**Clock discipline preserved.** `started_at`/`finished_at` are caller-supplied, exactly
like `RawDocument.retrieved_at` and `AcquisitionRequest.requested_at`. This package
never reads the clock. `RuntimeIdentity.detect()` exists for production callers; tests
construct one explicitly.

---

## 4. Integration at the real seam

`execute_plan_recorded` wraps the **unmodified** `execute_plan`. The orchestrator is
untouched, `run_scout` remains the single evidence write path, and nothing in
`daf/execution/` calls a pool mutator — asserted at the AST level.

Recording is additive: `test_the_unrecorded_acquisition_path_still_works` runs a plain
`execute_plan` and asserts it acquires normally **and writes no execution record**.

### Event coverage — measured against the actual failure semantics

| Event | Record? | What it carries |
|---|---|---|
| Plan validation failure | ✓ | `FAILED`, `source_unavailable`, no adapter |
| Unknown source | ✓ | `adapter_id=None` — no adapter ran |
| Unknown adapter | ✓ | `adapter_id` kept, `adapter_version=None` — no code ran |
| Adapter failure / malformed source | ✓ | `adapter_version` present — the adapter *did* run |
| Extraction / persistence failure | ✓ | `FAILED`, error retained |
| Successful acquisition | ✓ | artifacts, versions, output fingerprint |
| Duplicate | ✓ | `SUCCEEDED`, `duplicate` |
| Admission rejection | ✓ | plus one quarantine record per refusal |
| Checkpoint persistence failure | ✓ | `SUCCEEDED` with the checkpoint error named, **then the original exception is re-raised** — the artifacts really were persisted, and the caller is still loudly told |

Every failed run answers §10's four questions: what operation (`plan_id`,
`operation_id`), what source (`source_id`, `input_fingerprint`), which adapter and
version, when (`started_at`), and what failed (`error`).

---

## 5. Quarantine — Phase 25's gap, closed halfway and said so

Phase 25 recorded `rejection_policy` as `represented_unenforced`:
`ScoutAdmissionFailure` already carried the stage and errors of every refused
admission and handed them to the caller, but **nothing retained them** — a rejection
vanished when the result went out of scope.

Now each refusal becomes a `QuarantineRecord(id, execution_id, stage, errors)`,
content-addressed, persisted, tamper-evident, and linked to the execution that caused
it. Quarantine is **not** the execution record: one execution produces many
quarantine records or none, and `test_quarantine_is_not_the_execution_record` asserts
the ids differ and that quarantine carries no `status` or `adapter_id`.

**The rejection path exercised is real, not a mock.** `run_scout` refuses an
extraction whose `extraction_method` names a model but supplies no confidence
(`MISSING_MODEL_CONFIDENCE`) rather than defaulting it to 1.0. That is the only
admission failure this repository's own pipeline can currently produce, and it is
driven through the unmodified pipeline with a real dataset acquisition.

Status moved to `partially_enforced`, not `enforced`. **Repair-and-re-ingest does not
exist**, and the per-invariant rejection *rate* is not aggregated. Both are recorded
as gaps. There is still no `--force` path — there was never one to remove.

---

## 6. Not evidence — four independent mechanisms

| Mechanism | Test |
|---|---|
| Stored in its own directories, never a `FilesystemEvidenceStore` category | `test_execution_records_live_outside_the_evidence_store` |
| `EvidencePool.fingerprint()` unchanged by recording a run | `test_an_execution_record_is_not_evidence` |
| No evidence class is ever assigned to an execution id | `test_an_execution_id_never_receives_an_evidence_class` |
| AST: nothing in `daf/execution/` calls `put_*` or `admit_*` | `test_the_execution_package_never_writes_evidence` |

`class_assigned_at_ingest` has no shortcut through this package. The evidence an
execution describes *is* classified (`measured` for NOAA); the execution itself is
`UNCLASSIFIED` and inadmissible for canonical assertion — and those are two different
questions, only one of which has an answer.

---

## 7. Required phase report

**Implemented.** `daf/execution/` (`identity`, `record`, `quarantine`, `store`,
`recorded`); `AdapterBinding.version` (additive, defaulted) and derived versions for
all eight bindings in `daf/orchestration/bindings.py`;
`architecture/execution_record.yaml`; four invariant rows added and two updated in
`architecture/invariants.yaml`; `tests/test_execution_record.py`; regenerated
`docs/generated/DOCTRINE.md`; this document.

**Verified** — only what was actually executed:

| Check | Result |
|---|---|
| `tests/test_execution_record.py` | **28 passed** |
| `tests/test_epistemic_boundary.py` | **27 passed**, unmodified |
| `tests/test_doctrine_generation.py` | **19 passed**, unmodified |
| DAF full suite | **512 passed** (484 prior + 28 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/` | Success, **72 source files** |
| `ruff` | new files carry only the repo-wide `UP006`/`UP035`/`UP045`/`UP037` conventions; one `I001`, one `C408` and one mypy `arg-type` found in new code were fixed |
| Doctrine | regenerated; conformance gate green |

**Preserved.** `run_scout` as the single evidence write path. `class_assigned_at_ingest`
and all of Phase 25's boundary tests, unmodified. The acquisition-first control graph.
`daf ↛ materials`, `science ↛ daf`, `epistemics` as a leaf. `expected_information_gain`
still `NOT_DETERMINABLE`. All 484 prior tests pass unchanged.

**Extended.** Execution and operation identity; a tamper-evident execution record over
every acquisition outcome; durable quarantine linked to it; derived adapter versions.

**Integrated.** `evidence.identity.content_hash` (identity substrate);
`execute_plan`/`AcquisitionOrchestrator`/`run_scout` (acquisition, unmodified);
`ClassifiedPool` (classification, unmodified); `ScoutAdmissionFailure` (rejection
reasons); `AdapterBinding`/`SourceRegistry` (coordinates); `architecture/` +
`epistemics/doctrine.py` (canonical contract and regeneration).

**Qualified.** The contract is `scope: daf_acquisition_only`. Timestamps are
caller-supplied rather than wall-clock, matching the repository's existing discipline.
`adapter_version` is a code hash, not a semantic version.

**Bent: zero.** No core invariant changed. The vendored submodule is byte-identical.

**Execution record state.** 18 fields; `execution_id = H({operation_id, runtime_id,
started_at})`; `content_digest = H(everything else)`; `operation_id = H({plan_id,
source_id, parameters, mode})`. Nullable by design: `adapter_id`, `adapter_version`,
`finished_at`, `output_fingerprint`, `error`, `parent_execution_id`.

**Identity state.** Six identities, pairwise distinct and asserted so:

```
operation_id   H({plan_id, source_id, parameters, mode})     stable per operation
execution_id   H({operation_id, runtime_id, started_at})     distinct per run
artifact_id    H({source_id, locator})                       stable per artifact
version_id     Document.id                                   per acquired version
observation_id H({record_ids, extraction_method, content})   per admitted fact
evidence class beside the object, fixed at ingest            per admitted object
```

The execution record **references** the others and redefines none.

**Acquisition state.** NOAA CO-OPS (recorded real bytes, `measured`) and graph-dataset
(`asserted`), both through the real adapter → `execute_plan` → `run_scout` →
`ClassifiedPool` path.

**Failure state.** Eleven event classes exercised (§4 table above). No manufactured
output fingerprints. No silently discarded execution events.

**Quarantine state.** `execution → result → rejection reason → quarantine record`,
persisted and tamper-evident, driven by a real `MISSING_MODEL_CONFIDENCE` refusal. A
successful run quarantines nothing.

**Persistence state.** Create → persist → restore → identity verified. Altering an
identity field raises `ExecutionIdentityMismatch`; altering any of seven outcome
fields raises `ExecutionIntegrityMismatch`; a record filed under the wrong filename is
refused; an altered quarantine record raises `QuarantineIdentityMismatch`.

**Doctrine state.** Canonical sources now six (`execution_record.yaml` added).
Regeneration deterministic; committed output matches; budget **559 / 1400 words**;
vendor lint green; CI gate unchanged. The execution-record *contract* is structural
information, so it went into the canonical YAML and was deliberately **not** projected
into doctrine prose — which is `architecture/doctrine.yaml`'s own routing rule applied
rather than quietly bypassed.

**Migration state.** Unchanged: **0** legacy records committed to this repository.
No quarantined records exist outside tests. Execution records begin at this commit;
every acquisition performed before it has none, and none is back-filled — a
back-filled execution record would be a fabricated event.

**Unresolved** — carried forward:

- `quarantine_repair` — **new.** Retention exists; repair-and-re-ingest does not.
  What a repaired record looks like, and who may resubmit it, is open.
- `rejection_rate_per_invariant` — **new.** Errors carry codes; no per-run rate is
  aggregated.
- `retraction_semantics` — no path removes an admitted `Observation` without orphaning
  scientific state. Execution records inherit this: their store also has no delete.
- `multi_writer.write_conflict`, `builder_check_lineage`,
  `attested_snapshot_identity`, `capabilities_5_to_9` — unchanged from Phase 25.

**Measured bottleneck.** The rejection path could only be exercised **one way**:
`MISSING_MODEL_CONFIDENCE` is the sole admission failure this repository's own
adapters and pipeline can currently produce. Every other `ScoutAdmissionFailure`
stage (`document`, `record`, `observation`, `referent`) exists in `run_scout` and is
unreachable from any DAF source, because the adapters cannot construct evidence that
fails those gates. So quarantine is proved to work on one refusal class and is
untested against four others — not for lack of trying, but because nothing here can
produce them.

**Next executable frontier.** **Aggregate the per-invariant rejection rate per ingest
run**, and surface the unclassified backlog alongside it, as one reported ingest
metric. It is the smallest next step that is fully grounded: both inputs already
exist (`QuarantineStore.for_execution`, `ClassRegister.unclassified`), it needs no new
identity, and §23's *"rejection rate is a metric"* is the last unimplemented clause of
the rejection policy. It also directly attacks the bottleneck above, because a
per-code rate makes visible which admission gates are never exercised.

---

*Halts here per the stop condition: inspected, built, run, observed, fixed, audited,
validated, documented, committed and pushed. Chemistry is not begun; no model binding,
canary or attestation was implemented.*
