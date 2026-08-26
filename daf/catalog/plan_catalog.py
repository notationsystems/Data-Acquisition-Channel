"""PlanCatalog: persistent storage for AcquisitionPlans.

Same "operator-declared, last-write-wins" persistence model as
SourceCatalog -- plans are declarative intent, not content-addressed
evidence, so there is no equivalent of `daf.storage.filesystem_store`'s
identity re-verification here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from daf.catalog.plan import AcquisitionPlan
from daf.storage.serialization import strict_json_loads


class PlanNotFoundError(KeyError):
    """Raised when no AcquisitionPlan is registered under a given id."""


def _plan_to_dict(plan: AcquisitionPlan) -> Dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "source_id": plan.source_id,
        "parameters": dict(plan.parameters),
        "enabled": plan.enabled,
        "schedule": plan.schedule,
    }


def _plan_from_dict(payload: Dict[str, Any]) -> AcquisitionPlan:
    return AcquisitionPlan(
        plan_id=payload["plan_id"],
        source_id=payload["source_id"],
        parameters=payload.get("parameters", {}),
        enabled=payload.get("enabled", True),
        schedule=payload.get("schedule"),
    )


class PlanCatalog:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._plans: Dict[str, AcquisitionPlan] = {}
        for path in sorted(self.root.glob("*.json")):
            plan = _plan_from_dict(strict_json_loads(path.read_text()))
            self._plans[plan.plan_id] = plan

    def register(self, plan: AcquisitionPlan) -> None:
        path = self.root / f"{plan.plan_id}.json"
        tmp_path = self.root / f"{plan.plan_id}.json.tmp"
        tmp_path.write_text(json.dumps(_plan_to_dict(plan), sort_keys=True, indent=2, allow_nan=False))
        tmp_path.replace(path)  # atomic on POSIX
        self._plans[plan.plan_id] = plan

    def get(self, plan_id: str) -> AcquisitionPlan:
        try:
            return self._plans[plan_id]
        except KeyError:
            raise PlanNotFoundError(f"no plan registered under id {plan_id!r}") from None

    def all_plans(self) -> Tuple[AcquisitionPlan, ...]:
        return tuple(self._plans[key] for key in sorted(self._plans))
