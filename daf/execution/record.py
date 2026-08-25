"""`ExecutionRecord` -- the operation, not the evidence.

TWO HASHES, ON PURPOSE. `id` answers *which execution*; `content_digest`
answers *what was recorded about it*. Splitting them is what lets an
execution id be minted before anything has run (so a run that fails at
its first step still has one) while every later-filled field stays
tamper-evident:

    id             = H({operation_id, runtime_id, started_at})
    content_digest = H(every other field)

`from_dict` recomputes BOTH and refuses either mismatch, so altering
`status`, `error`, an artifact id or the output fingerprint on disk is
caught even though none of those touch the execution's identity. This is
the same discipline `daf/storage/serialization.py` applies to evidence,
adapted to a record whose identity deliberately does not cover its own
outcome.

ABSENCE IS EXPLICIT. `output_fingerprint`, `finished_at`,
`adapter_version` and `error` are `Optional` and are `None` when the
fact does not exist -- never a hash of nothing, never an empty string.
A failed run has no output fingerprint, and saying so is different from
claiming its output was empty.

NOT EVIDENCE. Nothing here is an `evidence.types` object, nothing is
written to an `EvidencePool`, and no evidence class is ever assigned to
an execution id. `class_assigned_at_ingest` has no shortcut through this
module -- asserted in `tests/test_execution_record.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from evidence.identity import content_hash

from daf.execution.identity import compute_execution_id

SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
STATUSES: Tuple[str, ...] = (FAILED, SUCCEEDED)


class ExecutionRecordError(ValueError):
    """Base for every refusal in this module."""


class UnknownExecutionStatus(ExecutionRecordError):
    """A status outside `STATUSES` was offered."""


class ExecutionIdentityMismatch(ExecutionRecordError):
    """A persisted record's identity fields do not reproduce the id it
    was stored under."""


class ExecutionIntegrityMismatch(ExecutionRecordError):
    """A persisted record's outcome fields do not reproduce its recorded
    `content_digest` -- the identity fields are intact but something
    else was altered after the record was written."""


class OutputWithoutSuccess(ExecutionRecordError):
    """A failed execution was given an output fingerprint. §10: do not
    manufacture an output when there is none."""


@dataclass(frozen=True)
class ExecutionRecord:
    # -- identity: fixed when the run starts, before any outcome exists
    id: str
    operation_id: str
    runtime_id: str
    started_at: str
    # -- coordinates, carried for readability; never an identity
    plan_id: str
    source_id: str
    adapter_id: Optional[str]
    adapter_version: Optional[str]
    # -- outcome, filled when the run ends
    status: str
    outcome: str
    finished_at: Optional[str]
    input_fingerprint: str
    output_fingerprint: Optional[str]
    artifact_ids: Tuple[str, ...]
    version_ids: Tuple[str, ...]
    admission_failure_count: int
    error: Optional[str]
    # -- lineage: the previous execution of the SAME operation, if any
    parent_execution_id: Optional[str]
    # -- integrity over everything above except `id` itself
    content_digest: str


def _outcome_payload(
    *,
    operation_id: str,
    runtime_id: str,
    started_at: str,
    plan_id: str,
    source_id: str,
    adapter_id: Optional[str],
    adapter_version: Optional[str],
    status: str,
    outcome: str,
    finished_at: Optional[str],
    input_fingerprint: str,
    output_fingerprint: Optional[str],
    artifact_ids: Tuple[str, ...],
    version_ids: Tuple[str, ...],
    admission_failure_count: int,
    error: Optional[str],
    parent_execution_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "operation_id": operation_id,
        "runtime_id": runtime_id,
        "started_at": started_at,
        "plan_id": plan_id,
        "source_id": source_id,
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "status": status,
        "outcome": outcome,
        "finished_at": finished_at,
        "input_fingerprint": input_fingerprint,
        "output_fingerprint": output_fingerprint,
        "artifact_ids": list(artifact_ids),
        "version_ids": list(version_ids),
        "admission_failure_count": admission_failure_count,
        "error": error,
        "parent_execution_id": parent_execution_id,
    }


def make_execution_record(
    *,
    operation_id: str,
    runtime_id: str,
    started_at: str,
    plan_id: str,
    source_id: str,
    adapter_id: Optional[str],
    adapter_version: Optional[str],
    status: str,
    outcome: str,
    finished_at: Optional[str],
    input_fingerprint: str,
    output_fingerprint: Optional[str],
    artifact_ids: Tuple[str, ...] = (),
    version_ids: Tuple[str, ...] = (),
    admission_failure_count: int = 0,
    error: Optional[str] = None,
    parent_execution_id: Optional[str] = None,
) -> ExecutionRecord:
    """The only supported constructor. Both hashes are derived, never
    supplied, so a record's ids can never disagree with its content."""
    if status not in STATUSES:
        raise UnknownExecutionStatus(f"{status!r} is not one of {list(STATUSES)}")
    if status == FAILED and output_fingerprint is not None:
        raise OutputWithoutSuccess(
            "a FAILED execution was given an output fingerprint; absence is explicit"
        )

    artifact_ids = tuple(sorted(artifact_ids))
    version_ids = tuple(sorted(version_ids))
    payload = _outcome_payload(
        operation_id=operation_id,
        runtime_id=runtime_id,
        started_at=started_at,
        plan_id=plan_id,
        source_id=source_id,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        status=status,
        outcome=outcome,
        finished_at=finished_at,
        input_fingerprint=input_fingerprint,
        output_fingerprint=output_fingerprint,
        artifact_ids=artifact_ids,
        version_ids=version_ids,
        admission_failure_count=admission_failure_count,
        error=error,
        parent_execution_id=parent_execution_id,
    )
    return ExecutionRecord(
        id=compute_execution_id(operation_id, runtime_id, started_at),
        content_digest=content_hash(payload),
        **payload | {"artifact_ids": artifact_ids, "version_ids": version_ids},
    )


def execution_record_to_dict(record: ExecutionRecord) -> Dict[str, Any]:
    payload = _outcome_payload(
        operation_id=record.operation_id,
        runtime_id=record.runtime_id,
        started_at=record.started_at,
        plan_id=record.plan_id,
        source_id=record.source_id,
        adapter_id=record.adapter_id,
        adapter_version=record.adapter_version,
        status=record.status,
        outcome=record.outcome,
        finished_at=record.finished_at,
        input_fingerprint=record.input_fingerprint,
        output_fingerprint=record.output_fingerprint,
        artifact_ids=record.artifact_ids,
        version_ids=record.version_ids,
        admission_failure_count=record.admission_failure_count,
        error=record.error,
        parent_execution_id=record.parent_execution_id,
    )
    payload["id"] = record.id
    payload["content_digest"] = record.content_digest
    return payload


def execution_record_from_dict(payload: Mapping[str, Any]) -> ExecutionRecord:
    """Rebuilds through `make_execution_record` from the raw fields --
    never from the stored ids -- then checks BOTH recomputed hashes
    against the stored ones. An altered identity field fails the first
    check; an altered outcome field fails the second."""
    rebuilt = make_execution_record(
        operation_id=payload["operation_id"],
        runtime_id=payload["runtime_id"],
        started_at=payload["started_at"],
        plan_id=payload["plan_id"],
        source_id=payload["source_id"],
        adapter_id=payload["adapter_id"],
        adapter_version=payload["adapter_version"],
        status=payload["status"],
        outcome=payload["outcome"],
        finished_at=payload["finished_at"],
        input_fingerprint=payload["input_fingerprint"],
        output_fingerprint=payload["output_fingerprint"],
        artifact_ids=tuple(payload["artifact_ids"]),
        version_ids=tuple(payload["version_ids"]),
        admission_failure_count=payload["admission_failure_count"],
        error=payload["error"],
        parent_execution_id=payload["parent_execution_id"],
    )
    if payload["id"] != rebuilt.id:
        raise ExecutionIdentityMismatch(
            f"execution record persisted under id {payload['id']!r} re-hashes to "
            f"{rebuilt.id!r} -- an identity field was altered"
        )
    if payload["content_digest"] != rebuilt.content_digest:
        raise ExecutionIntegrityMismatch(
            f"execution record {payload['id']!r} carries content_digest "
            f"{payload['content_digest']!r} but its fields hash to "
            f"{rebuilt.content_digest!r} -- an outcome field was altered"
        )
    return rebuilt
