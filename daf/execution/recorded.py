"""The acquisition seam, with the execution recorded.

    execute_plan_recorded(...)
        |
        |  1. operation_id      minted from the plan       (stable per operation)
        |  2. execution_id      minted BEFORE anything runs (distinct per run)
        |  3. execute_plan(...)  <-- the UNMODIFIED Phase-E path
        |  4. execution record persisted, success or failure
        |  5. quarantine records persisted, one per refused admission
        v
    RecordedExecution(result, execution, quarantine)

WHY THE ID IS MINTED FIRST. §10 requires that a run which begins and
then fails stays auditable. If the execution id were a function of the
outcome it could not exist until the outcome did, so a plan that fails
validation -- before an adapter is even resolved -- would have no record
at all. Minting first also means the id cannot change depending on how
the run turned out.

WHAT THIS DOES NOT DO. It does not reimplement acquisition. `execute_plan`
is called unmodified, the orchestrator is untouched, `run_scout` remains
the single evidence write path, and nothing here calls a pool mutator.
`class_assigned_at_ingest` still happens where it happened before, inside
`ClassifiedPool.put_*` -- this wrapper sits outside that and cannot
bypass it.

CLOCK DISCIPLINE. `started_at`/`finished_at` are caller-supplied, exactly
like `AcquisitionRequest.requested_at` and `RawDocument.retrieved_at`.
This module never reads the clock. A caller with a real one passes both;
a caller with a single instant gets a record whose run took no time,
which is at least not a fabrication.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from evidence.pool import EvidencePool

from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import (
    RuntimeIdentity,
    compute_execution_id,
    compute_operation_id,
    fingerprint,
)
from daf.execution.quarantine import QuarantineError, QuarantineRecord, make_quarantine_record
from daf.execution.record import FAILED, SUCCEEDED, ExecutionRecord, make_execution_record
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.orchestration.adapter_registry import AdapterNotFoundError, AdapterRegistry
from daf.orchestration.result import AcquisitionOutcome, AcquisitionResult
from daf.orchestration.source_registry import SourceNotFoundError, SourceRegistry
from daf.scheduling.runner import CheckpointPersistenceError, execute_plan

_SUCCESSFUL_OUTCOMES = (AcquisitionOutcome.ACQUIRED, AcquisitionOutcome.DUPLICATE)


@dataclass(frozen=True)
class RecordedExecution:
    """What one recorded acquisition produced. The three are deliberately
    separate objects: the result says what was acquired, the execution
    says how the run went, and the quarantine records say what was
    refused. An execution with no rejections carries an empty tuple, not
    a placeholder."""

    result: AcquisitionResult
    execution: ExecutionRecord
    quarantine: Tuple[QuarantineRecord, ...]


def _adapter_coordinates(
    plan: AcquisitionPlan, sources: SourceRegistry, adapters: AdapterRegistry
) -> Tuple[Optional[str], Optional[str]]:
    """Which adapter ran, and which version of its code.

    Both are `None` when the source or adapter could not be resolved --
    which is a real fact about the run ("no adapter ran, the source was
    unknown"), not missing data to be filled in later."""
    try:
        source = sources.get(plan.source_id)
    except SourceNotFoundError:
        return None, None
    try:
        binding = adapters.get(source.adapter_id)
    except AdapterNotFoundError:
        return source.adapter_id, None
    return binding.adapter_id, binding.version


def execute_plan_recorded(
    plan: AcquisitionPlan,
    sources: SourceRegistry,
    adapters: AdapterRegistry,
    pool: EvidencePool,
    checkpoints: CheckpointStore,
    requested_at: str,
    *,
    executions: ExecutionRecordStore,
    quarantine: QuarantineStore,
    runtime: RuntimeIdentity,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
) -> RecordedExecution:
    started_at = started_at if started_at is not None else requested_at
    finished_at = finished_at if finished_at is not None else started_at

    operation_id = compute_operation_id(
        plan_id=plan.plan_id,
        source_id=plan.source_id,
        parameters=plan.parameters,
        mode=plan.mode,
    )
    parent = executions.latest_for_operation(operation_id)
    execution_id = compute_execution_id(operation_id, runtime.id, started_at)
    adapter_id, adapter_version = _adapter_coordinates(plan, sources, adapters)

    # The input fingerprint covers WHAT WAS ASKED FOR, never what came
    # back -- so it is identical across a successful run and a failed
    # retry of the same request, which is what makes the two comparable.
    input_fingerprint = fingerprint(
        {"source_id": plan.source_id, "parameters": dict(plan.parameters), "mode": plan.mode}
    )
    assert input_fingerprint is not None  # payload is never None here

    checkpoint_error: Optional[Exception] = None
    try:
        result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at)
    except CheckpointPersistenceError as exc:
        # Acquisition succeeded and the artifacts ARE durably persisted;
        # only checkpoint tracking fell behind. The execution record is
        # written before re-raising, so the run stays auditable.
        result = exc.result
        checkpoint_error = exc

    succeeded = result.outcome in _SUCCESSFUL_OUTCOMES
    status = SUCCEEDED if succeeded else FAILED

    # §10: no manufactured output. A failed run has no output
    # fingerprint at all, which is not the same as an empty one.
    output_fingerprint = (
        fingerprint(
            {
                "artifact_ids": sorted(a.artifact_id for a in result.artifacts),
                "version_ids": sorted(a.version_id for a in result.artifacts),
            }
        )
        if succeeded
        else None
    )

    error = result.error
    if checkpoint_error is not None:
        error = f"checkpoint persistence failed after successful acquisition: {checkpoint_error}"

    record = make_execution_record(
        operation_id=operation_id,
        runtime_id=runtime.id,
        started_at=started_at,
        plan_id=plan.plan_id,
        source_id=plan.source_id,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        status=status,
        outcome=result.outcome.value,
        finished_at=finished_at,
        input_fingerprint=input_fingerprint,
        output_fingerprint=output_fingerprint,
        artifact_ids=tuple(a.artifact_id for a in result.artifacts),
        version_ids=tuple(a.version_id for a in result.artifacts),
        admission_failure_count=len(result.admission_failures),
        error=error,
        parent_execution_id=parent.id if parent is not None else None,
    )
    assert record.id == execution_id  # minted before the run, unchanged by it
    executions.put(record)

    quarantined = tuple(
        make_quarantine_record(
            execution_id=record.id,
            stage=failure.stage,
            errors=tuple(
                QuarantineError(object_type=e.object_type, code=e.code, message=e.message)
                for e in failure.errors
            ),
        )
        for failure in result.admission_failures
    )
    for quarantine_record in quarantined:
        quarantine.put(quarantine_record)

    if checkpoint_error is not None:
        raise checkpoint_error

    return RecordedExecution(result=result, execution=record, quarantine=quarantined)
