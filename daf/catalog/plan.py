"""AcquisitionPlan: declarative, repeatable acquisition intent.

    AcquisitionPlan -> (to_request) -> AcquisitionRequest -> AcquisitionOrchestrator

A plan never replaces `AcquisitionRequest` -- it is a named, persistable
declaration of "what request to construct." Repeatability means exactly
this: the same plan, converted at any time, produces an
`AcquisitionRequest` with the same `source_id`/`parameters`; only
`requested_at` varies, and it is always supplied by whoever executes the
plan -- a plan never generates a wall-clock timestamp itself, matching
every other caller-supplied timestamp in this codebase.

`validate_plan` follows the vendored State-Space repository's own
`evidence.admission` discipline: a structural, non-raising check that
returns a tuple of typed issues (empty = valid) rather than raising for
expected problems.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple

from daf.orchestration.adapter_registry import AdapterNotFoundError, AdapterRegistry
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.source_registry import SourceNotFoundError, SourceRegistry


@dataclass(frozen=True)
class AcquisitionPlan:
    plan_id: str
    source_id: str
    parameters: Mapping[str, Any]
    enabled: bool = True
    # Free-form, declarative only (e.g. "daily", "every_6_hours") -- never
    # interpreted or executed by anything in this phase. A future
    # scheduler is the only thing that would ever read this field.
    schedule: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))

    def to_request(self, requested_at: str) -> AcquisitionRequest:
        return AcquisitionRequest(source_id=self.source_id, parameters=self.parameters, requested_at=requested_at)


@dataclass(frozen=True)
class PlanValidationIssue:
    code: str
    message: str


def validate_plan(
    plan: AcquisitionPlan, sources: SourceRegistry, adapters: AdapterRegistry
) -> Tuple[PlanValidationIssue, ...]:
    try:
        source = sources.get(plan.source_id)
    except SourceNotFoundError:
        # Nothing else below is checkable without a resolved source.
        return (PlanValidationIssue("UNKNOWN_SOURCE", f"no source registered under id {plan.source_id!r}"),)

    issues = []

    if not source.enabled:
        issues.append(PlanValidationIssue("SOURCE_DISABLED", f"source {plan.source_id!r} is disabled"))

    try:
        adapters.get(source.adapter_id)
    except AdapterNotFoundError:
        issues.append(
            PlanValidationIssue(
                "UNKNOWN_ADAPTER",
                f"source {plan.source_id!r}'s adapter {source.adapter_id!r} is not registered",
            )
        )

    if not plan.enabled:
        issues.append(PlanValidationIssue("PLAN_DISABLED", f"plan {plan.plan_id!r} is disabled"))

    missing = tuple(key for key in source.required_parameters if key not in plan.parameters)
    if missing:
        issues.append(
            PlanValidationIssue(
                "MISSING_PARAMETERS",
                f"plan {plan.plan_id!r} is missing required parameter(s) {missing} for source {plan.source_id!r}",
            )
        )

    return tuple(issues)
