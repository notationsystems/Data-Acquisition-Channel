"""execute_plan: checkpoint-aware plan execution wrapping the existing,
unmodified AcquisitionOrchestrator.

Ordering invariant (the whole point of this module): artifacts are
DURABLY persisted (via the unmodified `scout.pipeline.run_scout`, inside
`AcquisitionOrchestrator.run`) BEFORE the checkpoint is advanced, and the
checkpoint is advanced ONLY when that run reports `ACQUIRED` or
`DUPLICATE`. Any other outcome (source unavailable, adapter/extraction/
persistence failure, or a validation issue) leaves the checkpoint
untouched -- it must never claim progress past data the DAF did not
successfully persist.

FAILURE SEMANTICS if checkpoint persistence itself fails AFTER a
successful acquisition (e.g. the checkpoint store's disk is full): the
artifacts are already durably persisted at that point -- that fact is
real and unaffected. This module does not attempt a distributed
transaction across the evidence store and the checkpoint store (no
transaction spans a filesystem-only architecture safely); instead it
raises `CheckpointPersistenceError`, carrying the underlying
(successful) `AcquisitionResult`, so the caller is loudly told
checkpoint tracking fell behind rather than having that silently
swallowed. The next `execute_plan` call for this plan will resume from
the OLD position and re-fetch/re-process the same range -- safe and
idempotent because of the existing content-addressed deduplication
(Phase A/B): this is an at-least-once guarantee, not exactly-once.
"""

from __future__ import annotations

from daf.catalog.checkpoint import AcquisitionCheckpoint, CheckpointStore
from daf.catalog.plan import AcquisitionPlan, validate_plan
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.orchestrator import AcquisitionOrchestrator
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.result import AcquisitionOutcome, AcquisitionResult
from daf.orchestration.source_registry import SourceRegistry
from evidence.pool import EvidencePool

_SUCCESSFUL_OUTCOMES = (AcquisitionOutcome.ACQUIRED, AcquisitionOutcome.DUPLICATE)


class CheckpointPersistenceError(RuntimeError):
    """Raised when acquisition succeeded (artifacts ARE durably
    persisted -- see `result`) but persisting the checkpoint itself
    failed. Carries the underlying successful AcquisitionResult so the
    caller can inspect what was actually acquired."""

    def __init__(self, result: AcquisitionResult, cause: Exception) -> None:
        super().__init__(
            f"acquisition for source {result.source_id!r} succeeded but checkpoint persistence failed: {cause}"
        )
        self.result = result
        self.cause = cause


def execute_plan(
    plan: AcquisitionPlan,
    sources: SourceRegistry,
    adapters: AdapterRegistry,
    pool: EvidencePool,
    checkpoints: CheckpointStore,
    requested_at: str,
) -> AcquisitionResult:
    issues = validate_plan(plan, sources, adapters)
    if issues:
        return AcquisitionResult(
            source_id=plan.source_id,
            outcome=AcquisitionOutcome.SOURCE_UNAVAILABLE,
            error="; ".join(f"{issue.code}: {issue.message}" for issue in issues),
        )

    checkpoint = checkpoints.get(plan.plan_id)
    previous_position = checkpoint.position if checkpoint is not None else None

    parameters = dict(plan.parameters)
    if plan.mode == "incremental" and previous_position is not None:
        parameters["since"] = previous_position

    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)
    request = AcquisitionRequest(source_id=plan.source_id, parameters=parameters, requested_at=requested_at)
    result = orchestrator.run(request)

    if result.outcome in _SUCCESSFUL_OUTCOMES:
        source = sources.get(plan.source_id)
        binding = adapters.get(source.adapter_id)
        new_position = (
            binding.advance_position(result.artifacts, previous_position)
            if binding.advance_position is not None
            else previous_position
        )
        new_checkpoint = AcquisitionCheckpoint(
            plan_id=plan.plan_id, source_id=plan.source_id, position=new_position, updated_at=requested_at
        )
        try:
            checkpoints.advance(new_checkpoint)
        except OSError as exc:
            raise CheckpointPersistenceError(result, exc) from exc

    return result
