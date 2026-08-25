"""`QuarantineRecord` -- a rejection, traceable back to the run that
produced it.

    execution -> acquisition result -> rejection reason -> quarantine

Quarantine is NOT the execution record and does not become one. It
references `execution_id` and stops there: one execution can produce many
quarantine records (one per refused admission), and an execution with no
rejections produces none. Collapsing them would make "the run happened"
and "something in it was refused" the same fact.

WHAT THIS CLOSES AND WHAT IT DOES NOT. Phase 25 recorded quarantine as
`represented_unenforced`: `scout.pipeline.ScoutAdmissionFailure` already
carries the stage and errors of every refused admission and hands them
back to the caller, but nothing RETAINED them, so a rejection vanished
when the result went out of scope. This retains them, queryably, keyed
by the execution that caused them.

It does NOT implement repair-and-re-ingest, and there is still no
`--force` path -- there was never one to remove. What a repaired record
would look like, and who may resubmit it, stays open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple

from evidence.identity import content_hash


class QuarantineIdentityMismatch(ValueError):
    """A persisted quarantine record's fields do not reproduce the id it
    was stored under."""


@dataclass(frozen=True)
class QuarantineError:
    object_type: str
    code: str
    message: str


@dataclass(frozen=True)
class QuarantineRecord:
    """One refused admission, retained.

    `message` participates in identity along with `code`: two refusals
    with the same code and different messages are different rejections,
    and deduplicating them would hide which record failed."""

    id: str
    execution_id: str
    stage: str
    errors: Tuple[QuarantineError, ...]


def _errors_payload(errors: Tuple[QuarantineError, ...]) -> list:
    return [
        {"object_type": e.object_type, "code": e.code, "message": e.message} for e in errors
    ]


def make_quarantine_record(
    execution_id: str, stage: str, errors: Tuple[QuarantineError, ...]
) -> QuarantineRecord:
    errors = tuple(errors)
    record_id = content_hash(
        {"execution_id": execution_id, "stage": stage, "errors": _errors_payload(errors)}
    )
    return QuarantineRecord(id=record_id, execution_id=execution_id, stage=stage, errors=errors)


def quarantine_record_to_dict(record: QuarantineRecord) -> Dict[str, Any]:
    return {
        "id": record.id,
        "execution_id": record.execution_id,
        "stage": record.stage,
        "errors": _errors_payload(record.errors),
    }


def quarantine_record_from_dict(payload: Mapping[str, Any]) -> QuarantineRecord:
    rebuilt = make_quarantine_record(
        execution_id=payload["execution_id"],
        stage=payload["stage"],
        errors=tuple(
            QuarantineError(
                object_type=e["object_type"], code=e["code"], message=e["message"]
            )
            for e in payload["errors"]
        ),
    )
    if payload["id"] != rebuilt.id:
        raise QuarantineIdentityMismatch(
            f"quarantine record persisted under id {payload['id']!r} re-hashes to "
            f"{rebuilt.id!r} -- the retained rejection was altered"
        )
    return rebuilt
