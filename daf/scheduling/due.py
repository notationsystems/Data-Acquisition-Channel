"""due_plans / run_due_plans: a deterministic scheduler INTERFACE, not a
daemon.

    AcquisitionPlan.interval_seconds  (explicit, typed -- see daf.catalog.plan)
              |
              v
    is_due(plan, checkpoints, now)   -- pure function of (plan, checkpoint, now)
              |
              v
    due_plans(...) -> Tuple[AcquisitionPlan, ...]
              |
              v
    run_due_plans(...) -> Tuple[AcquisitionResult, ...]   (calls daf.scheduling.runner.execute_plan)

No loop, no sleep, no background thread, no reading of the wall clock:
`now` is always supplied by the caller (a cron entry, an operator, a
future real scheduler), matching every other timestamp in this codebase.
A plan with `interval_seconds is None` is never automatically due --
explicit execution only, exactly Phase D's behavior.
"""

from __future__ import annotations

from datetime import datetime
from typing import Tuple

from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.catalog.plan_catalog import PlanCatalog
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.result import AcquisitionResult
from daf.orchestration.source_registry import SourceRegistry
from daf.scheduling.runner import execute_plan
from evidence.pool import EvidencePool


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_due(plan: AcquisitionPlan, checkpoints: CheckpointStore, now: str) -> bool:
    if not plan.enabled or plan.interval_seconds is None:
        return False
    checkpoint = checkpoints.get(plan.plan_id)
    if checkpoint is None:
        return True  # never successfully run -- always due
    elapsed_seconds = (_parse_iso(now) - _parse_iso(checkpoint.updated_at)).total_seconds()
    return elapsed_seconds >= plan.interval_seconds


def due_plans(plans: PlanCatalog, checkpoints: CheckpointStore, now: str) -> Tuple[AcquisitionPlan, ...]:
    return tuple(plan for plan in plans.all_plans() if is_due(plan, checkpoints, now))


def run_due_plans(
    plans: PlanCatalog,
    sources: SourceRegistry,
    adapters: AdapterRegistry,
    pool: EvidencePool,
    checkpoints: CheckpointStore,
    now: str,
) -> Tuple[AcquisitionResult, ...]:
    return tuple(
        execute_plan(plan, sources, adapters, pool, checkpoints, requested_at=now)
        for plan in due_plans(plans, checkpoints, now)
    )
