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

Phase E additions, both backward compatible (a Phase D plan constructed
without them behaves exactly as before):

- `mode: "snapshot" | "incremental"` (default `"snapshot"`) -- whether
  `daf.scheduling.runner.execute_plan` should inject the plan's current
  checkpoint position into the request and advance it afterward.
  "snapshot" means exactly what it meant before this phase existed: full
  re-acquisition every run, relying on existing content-addressed
  deduplication (Phase A/B) rather than any cursor.
- `interval_seconds: Optional[int]` (default `None`) -- an explicit,
  typed due-scheduling interval, deliberately SEPARATE from the existing
  free-form `schedule` label (never parsed/interpreted here) rather than
  trying to infer machine-actionable semantics from a string like
  "daily". `None` means "never automatically due" -- explicit execution
  only, exactly Phase D's behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple

from daf.orchestration.adapter_registry import AdapterNotFoundError, AdapterRegistry
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.source_registry import SourceNotFoundError, SourceRegistry

_VALID_MODES = ("snapshot", "incremental")


@dataclass(frozen=True)
class AcquisitionPlan:
    plan_id: str
    source_id: str
    parameters: Mapping[str, Any]
    enabled: bool = True
    # Free-form, declarative only (e.g. "daily", "every_6_hours") -- never
    # interpreted or executed by anything in this codebase. Purely a
    # human-readable annotation; see `interval_seconds` for the typed,
    # machine-actionable equivalent.
    schedule: Optional[str] = None
    mode: str = "snapshot"
    interval_seconds: Optional[int] = None

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

    binding = None
    try:
        binding = adapters.get(source.adapter_id)
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

    if plan.mode not in _VALID_MODES:
        issues.append(PlanValidationIssue("INVALID_MODE", f"plan {plan.plan_id!r} has unknown mode {plan.mode!r}"))
    elif plan.mode == "incremental":
        supports_incremental = (
            "incremental" in source.capabilities and binding is not None and binding.advance_position is not None
        )
        if not supports_incremental:
            issues.append(
                PlanValidationIssue(
                    "INCREMENTAL_NOT_SUPPORTED",
                    f"source {plan.source_id!r} does not support incremental acquisition "
                    f"(requires 'incremental' in capabilities and an adapter binding with advance_position)",
                )
            )

    return tuple(issues)
