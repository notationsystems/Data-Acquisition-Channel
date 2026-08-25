"""The two identities an execution needs that nothing else in this
repository already provides.

    operation_id   WHICH acquisition operation   stable across runs
    execution_id   WHICH RUN of it               distinct per run

Both are content-addressed with `evidence.identity.content_hash`, the
same function every other id in this repository uses. Neither redefines
`artifact_id`, `version_id`, `Observation.id` or `Source.id`, and neither
participates in them.

WHY THE HASH SEMANTICS DIFFER, deliberately. `artifact_id` is a function
of WHAT was acquired, so it must be stable across equivalent execution
environments -- two runs of the same acquisition on two machines produce
one artifact. `execution_id` is a function of WHEN and WHERE a run
happened, so it must NOT be stable across them -- two runs are two
events, and collapsing them would erase the audit trail this phase
exists to create. The same primitive, two different payloads, opposite
stability requirements. `tests/test_execution_record.py` measures both.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from evidence.identity import content_hash


@dataclass(frozen=True)
class RuntimeIdentity:
    """WHERE an execution ran.

    Caller-supplied, exactly like `RawDocument.retrieved_at` and
    `AcquisitionRequest.requested_at` are caller-supplied -- this module
    never reads the clock or the environment behind a caller's back.
    `detect()` exists for production callers who want the real values;
    tests construct one explicitly so a run is reproducible.

    Hostname and process id ARE included, and that is the point: they
    are real facts about an execution and they belong to execution
    identity. What matters is that they never reach artifact identity,
    which is a separate hash over a separate payload."""

    python_version: str
    platform: str
    hostname: str
    process_id: int

    @classmethod
    def detect(cls) -> "RuntimeIdentity":
        return cls(
            python_version=sys.version.split()[0],
            platform=platform.platform(),
            hostname=platform.node(),
            process_id=os.getpid(),
        )

    @property
    def id(self) -> str:
        return content_hash(
            {
                "python_version": self.python_version,
                "platform": self.platform,
                "hostname": self.hostname,
                "process_id": self.process_id,
            }
        )


def compute_operation_id(
    plan_id: str, source_id: str, parameters: Mapping[str, Any], mode: str
) -> str:
    """The acquisition identity: WHICH operation, independent of when it
    ran, whether it succeeded, and what it produced.

    Distinct from `artifact_id` (`{source_id, locator}`) because an
    operation may acquire many artifacts or none at all -- a failed
    acquisition has an operation identity and no artifact identity, and
    that asymmetry is exactly what makes a failed execution auditable."""
    return content_hash(
        {
            "plan_id": plan_id,
            "source_id": source_id,
            "parameters": {str(k): parameters[k] for k in sorted(parameters)},
            "mode": mode,
        }
    )


def compute_execution_id(operation_id: str, runtime_id: str, started_at: str) -> str:
    """The execution identity: WHICH RUN.

    Deliberately NOT a function of the outputs. An execution id must
    exist before anything has been acquired, so that a run which fails
    at its first step still has one -- and so that the id cannot change
    depending on how the run turned out."""
    return content_hash(
        {"operation_id": operation_id, "runtime_id": runtime_id, "started_at": started_at}
    )


def fingerprint(payload: Optional[Mapping[str, Any]]) -> Optional[str]:
    """`None` in, `None` out -- explicit absence, never a hash of `{}`.

    §10's rule: do not manufacture an output fingerprint when there is
    no output. A run that produced nothing and a run whose output
    happened to be empty are different facts, and a hash of the empty
    mapping would make them look identical."""
    if payload is None:
        return None
    return content_hash({str(k): payload[k] for k in sorted(payload)})
