# Phase E — DAF Incremental Acquisition and Scheduling Semantics

**Status:** implemented and passing. Fifth DAF phase: an opaque,
DAF-owned acquisition checkpoint, an explicit snapshot/incremental
distinction on `AcquisitionPlan`, and a deterministic due-plan
scheduler interface — all layered strictly above the unmodified Phase
A/B/C/D acquisition/persistence/orchestration/catalog contract.

---

## Pre-implementation report

1. **Existing acquisition semantics**: `AcquisitionRequest.parameters` is
   an opaque, adapter-defined mapping; no source currently accepts a
   "resume from here" parameter.
2. **Existing adapter capabilities**: `ArxivSourceAdapter` fetches an
   explicit id list (snapshot-by-identifier); `LocalDatasetSourceAdapter`
   reads an entire file every run (whole-file snapshot). **Neither has
   any cursor/pagination concept.**
3. **Snapshot/incremental distinction**: confirmed genuinely absent from
   the existing adapters — not merely undocumented. Per the task's own
   allowance, one new, clearly-labeled deterministic local adapter
   (`daf.adapters.incremental_dataset`) was added specifically to
   demonstrate real cursor semantics, rather than inventing incremental
   behavior against a real external API.
4. **Proposed checkpoint abstraction**: `AcquisitionCheckpoint{plan_id,
   source_id, position: Optional[str], updated_at}` — `position` is
   deliberately **opaque**; the checkpoint machinery itself never parses
   or compares it. Only an `AdapterBinding.advance_position` callable
   (adapter-specific, Phase E addition, default `None`) interprets it,
   by inspecting `AcquiredArtifact.locator` (a new field on the existing
   Phase C `AcquiredArtifact`).
5. **Checkpoint ownership**: DAF acquisition infrastructure
   (`daf.catalog.checkpoint`), not evidence, not `EvidencePool`, not any
   future State-Space concept — a checkpoint means "the apparatus
   progressed to here," nothing about scientific meaning.
6. **Persistence ordering**: artifacts are durably persisted (via the
   unmodified `run_scout`, inside `AcquisitionOrchestrator.run`) BEFORE
   the checkpoint is advanced, and only when the outcome is `ACQUIRED`
   or `DUPLICATE`.
7. **Proposed scheduler**: `daf.scheduling.due.{is_due, due_plans,
   run_due_plans}` — pure functions of `(plan, checkpoint, now)`, no
   daemon, no loop, `now` always caller-supplied.
8. **Failure semantics**: source/adapter/extraction/persistence failures
   never advance the checkpoint (verified by dedicated tests per
   category); a checkpoint-persistence failure AFTER a successful
   acquisition is reported distinctly via `CheckpointPersistenceError`
   rather than silently swallowed or misreported as an acquisition
   failure.
9. **Restart semantics**: reuses Phase B's exact pattern
   (`DurablePool.restore`) for evidence, plus the equally simple
   `CheckpointStore` (a plain per-`plan_id` JSON file, last-write-wins,
   atomic) for checkpoint state — no second persistence stack.
10. **Why no distributed scheduler**: `run_due_plans` is a pure,
    deterministic function; nothing in this phase needs concurrent
    workers, a message queue, or cross-process coordination to prove the
    required semantics.

---

## Design

```
AcquisitionPlan.mode ("snapshot" | "incremental", default "snapshot")
AcquisitionPlan.interval_seconds (Optional[int], default None)
                    |
                    v
         daf.scheduling.runner.execute_plan
                    |
        validate_plan(...)  [unmodified logic, Phase D, extended with
                              INVALID_MODE / INCREMENTAL_NOT_SUPPORTED]
                    |
        checkpoint = checkpoints.get(plan.plan_id)
        if mode == "incremental" and checkpoint.position is not None:
            parameters["since"] = checkpoint.position
                    |
                    v
        AcquisitionOrchestrator.run(...)        [unmodified, Phase C]
                    |
                    v
        scout.pipeline.run_scout -> DurablePool -> ArtifactStore  [unmodified, Phase A/B]
                    |
                    v  only on ACQUIRED / DUPLICATE
        binding.advance_position(result.artifacts, previous_position) -> new position
        checkpoints.advance(AcquisitionCheckpoint(..., position=new_position, updated_at=requested_at))


daf.scheduling.due.run_due_plans(plans, ..., now)
                    |
        is_due(plan, checkpoints, now):
            enabled and interval_seconds is not None and
            (no checkpoint yet, or now - checkpoint.updated_at >= interval_seconds)
                    |
                    v
        execute_plan(...) for each due plan   [same function as above]
```

`daf.scheduling.runner`/`daf.scheduling.due` never import
`daf.adapters`/`daf.extractors`/`evidence.admission` and never call a
pool mutator directly (AST-verified) — every write still funnels through
the unchanged `AcquisitionOrchestrator`/`run_scout`.

### The new incremental adapter

`daf.adapters.incremental_dataset.IncrementalDatasetSourceAdapter` reads
a local JSON array where each record carries an explicit integer
`sequence`; `fetch()` returns only records with `sequence >
since_sequence`. Each record's `locator` IS its zero-padded sequence
number — this is what lets
`daf.orchestration.bindings.incremental_dataset_binding`'s
`advance_position` compute "the highest sequence acquired this run"
generically from `AcquiredArtifact.locator`, without the checkpoint
machinery or orchestrator ever knowing what a locator means for any
given source. Reuses the existing `LocalDatasetExtractor` unchanged
(the record shape is identical to `local_dataset`'s).

### Why `position` stays opaque

`daf.catalog.checkpoint`, `daf.scheduling.runner`, and
`daf.scheduling.due` never parse, compare, or interpret `position` as
anything other than an opaque string. Only the specific
`AdapterBinding.advance_position` that produced a position ever reads it
back (via its own `build_adapter`, e.g. `incremental_dataset_binding`
converting `parameters["since"]` into `since_sequence`). This is the
direct, tested consequence of the central question this phase posed:
"last timestamp," "last sequence," and "last token" are not
interchangeable, so nothing above the adapter binding may assume a
shared representation.

### Atomicity — exact failure semantics

There is no cross-object transaction spanning the evidence store and the
checkpoint store (both are plain filesystem JSON stores; a real
distributed transaction was explicitly out of scope). The actual
guarantee: **artifacts are always durable before the checkpoint would
even attempt to advance.** If checkpoint persistence itself then fails,
`execute_plan` raises `CheckpointPersistenceError` (carrying the
already-successful `AcquisitionResult`) rather than reporting false
success or silently losing the acquisition outcome. The next call for
that plan resumes from the OLD checkpoint position and safely re-fetches
the same range — idempotent, at-least-once, by the existing
content-addressed deduplication machinery (Phase A/B), never a new
dedup mechanism.

---

## Post-implementation report

### 1. Files changed

```
daf/catalog/checkpoint.py                      (new)
daf/catalog/plan.py                            (extended: mode, interval_seconds, 2 new validation checks)
daf/orchestration/adapter_registry.py          (extended: AdapterBinding.advance_position, additive)
daf/orchestration/result.py                    (extended: AcquiredArtifact.locator, additive)
daf/orchestration/orchestrator.py              (one line: pass locator= when constructing AcquiredArtifact)
daf/orchestration/bindings.py                  (new: incremental_dataset_binding)
daf/adapters/incremental_dataset.py            (new)
daf/scheduling/__init__.py                     (new)
daf/scheduling/runner.py                       (new)
daf/scheduling/due.py                          (new)
tests/fixtures/incremental_dataset_sample.json           (new)
tests/fixtures/incremental_dataset_sample_extended.json  (new)
tests/test_checkpoint.py                       (new)
tests/test_incremental_dataset_adapter.py      (new)
tests/test_plan.py                             (extended: mode/interval_seconds tests)
tests/test_scheduling_runner.py                (new)
tests/test_due_plans.py                        (new)
docs/DAF_INCREMENTAL_ACQUISITION.md            (this file)
```

### 2. Checkpoint abstraction

`AcquisitionCheckpoint{plan_id, source_id, position: Optional[str],
updated_at}`, persisted by `CheckpointStore` (one JSON file per
`plan_id`, atomic writes, last-write-wins — DAF/apparatus-owned progress,
not evidence). `position` is opaque everywhere except inside the
specific `AdapterBinding` that produced it.

### 3. Snapshot/incremental semantics

`AcquisitionPlan.mode` defaults to `"snapshot"` — a Phase D plan
constructed without the new fields behaves identically
(`test_plan_defaults_are_backward_compatible_with_phase_d`). Snapshot
plans still fully re-acquire every run (relying on existing dedup), and
their checkpoint's `position` stays `None` forever while `updated_at`
still advances (used for due-scheduling). Incremental plans inject
`parameters["since"]` from the checkpoint and only fetch what's new
(`test_incremental_plan_second_run_resumes_from_checkpoint`: 3 records
first run, 2 new records second run against a grown source, zero
re-fetched).

### 4. Scheduler behavior

`is_due`/`due_plans`/`run_due_plans` are pure functions of
`(plan/plans, checkpoints, now)` — no daemon, no wall-clock read. A plan
with `interval_seconds=None` is never automatically due (explicit
execution only, Phase D's behavior preserved). A never-run plan with an
interval is immediately due. `test_run_due_plans_executes_two_different_source_semantics`
proves one `run_due_plans` call correctly drives one snapshot plan and
one incremental plan with zero source-specific branching anywhere in
`daf.scheduling`.

### 5. Persistence ordering

Proven directly: `test_checkpoint_does_not_advance_on_disabled_source`,
`..._on_adapter_failure`, `..._on_persistence_failure` all assert
`checkpoints.get(plan_id) is None` after a failed run.
`test_checkpoint_persistence_failure_is_reported_distinctly_after_a_successful_acquisition`
proves the inverse ordering claim: artifacts ARE durable
(`pool.all_observations()` has 3 entries) even when the checkpoint write
itself is the thing that fails.

### 6. Restart demonstration

`test_full_restart_resumes_incremental_acquisition_correctly`: process A
acquires 3 records and exits; process B — brand-new `SourceRegistry`/
`AdapterRegistry`/`DurablePool.restore`/`CheckpointStore` objects, same
on-disk paths only — resumes and correctly fetches only the 2 new
records from a grown source.

### 7. Failure behavior

Four failure categories tested (disabled source, adapter failure,
persistence failure, checkpoint-persistence failure), each leaving the
checkpoint untouched except the last, which is reported via a distinct
exception carrying the real (successful) result.

### 8. Duplicate behavior

`test_repeated_acquisition_from_the_same_checkpoint_is_idempotent` and
`test_overlapping_results_are_deduplicated_by_existing_identity_machinery`
(a checkpoint deliberately rewound to force an overlapping re-fetch) both
confirm zero corruption and zero duplication — entirely via Phase A/B's
existing content-addressed identity, no new dedup mechanism.

### 9. Two-source demonstration

`test_run_due_plans_executes_two_different_source_semantics`: one
snapshot plan (`local-dataset`) and one incremental plan
(`incremental-dataset`) executed through the same `run_due_plans` call,
same pool, same checkpoint store.

### 10. One-door proof

`test_one_door_invariant_for_scheduling_modules` (AST-level, both
`daf/scheduling/runner.py` and `daf/scheduling/due.py`): no
`evidence.admission` import, no direct `put_*` call, no
`daf.adapters`/`daf.extractors` import anywhere in the scheduling layer.

### 11. Full test results

`pytest tests/` (DAF, all five phases): **137 passed** — 19 (A) + 26 (B)
+ 32 (C) + 25 (D) + 35 new (E). Full vendored State-Space suite: **1273
passed, 0 failed, 0 files modified.**

### 12. ruff

`ruff check daf/ tests/ conftest.py` → **All checks passed!**

### 13. mypy

`mypy daf/` → **Success: no issues found in 33 source files.**

### 14. Limitations

- `advance_position` is trusted, adapter-supplied code — a badly written
  one could compute a nonsensical position; this is the same trust
  boundary `build_adapter`/`build_extractor` already carry, not a new
  risk category.
- `IncrementalDatasetSourceAdapter` requires every record to declare an
  explicit integer `sequence`; it does not generalize to timestamp- or
  token-based incremental sources without a new binding (by design —
  see "why position stays opaque" above; a timestamp-cursor source would
  need its own adapter and its own `advance_position`, not a shared one).
- No bounded-retry policy was added: every failure mode demonstrated this
  phase is deterministic (bad path, disabled source, broken store), so a
  retry would fail identically — consistent with Phase C's same finding
  and the task's own "do not build an elaborate retry scheduler"
  instruction.
- `run_due_plans` executes due plans sequentially, not concurrently — no
  concurrency was required to prove the semantics, and this phase
  explicitly excludes distributed workers.

### 15. Recommended Phase F

Per the task's own stop condition, this phase is complete: source → plan
→ checkpoint → acquire → SCOUT → persist → advance checkpoint → wait →
resume, across two genuinely different acquisition semantics, all
tested. A real Phase F scheduler daemon would call `run_due_plans` on a
timer (still no new abstraction needed here — the interface is already
daemon-ready). The FEP/information-gap-driven `AcquisitionRequest`
remains the next real architectural frontier and remains untouched, as
does the separate Rust/zkVM/Morpho/CUDA execution plane.
