"""Minimal operator CLI for the DAF catalog/planning layer.

    python -m daf.catalog.cli <root> list-sources
    python -m daf.catalog.cli <root> inspect-source <source_id>
    python -m daf.catalog.cli <root> list-plans
    python -m daf.catalog.cli <root> inspect-plan <plan_id>
    python -m daf.catalog.cli <root> validate-plan <plan_id>
    python -m daf.catalog.cli <root> execute-plan <plan_id> <requested_at>

Calls exactly the same Python interfaces (`SourceCatalog`, `PlanCatalog`,
`validate_plan`, `AcquisitionOrchestrator`) a programmatic caller would
-- this module adds no logic of its own beyond argument parsing and
printing. `<root>` holds three subdirectories: `sources/`, `plans/`,
`evidence/` (the durable evidence substrate, per Phase B).

Registering a source or plan is a programmatic action (construct a
`SourceCatalog`/`PlanCatalog` and call `.register(...)`), not a CLI verb
-- this mirrors `daf.orchestration.bindings` being the one place concrete
adapters are wired in, kept out of the generic catalog/orchestrator code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import daf  # noqa: F401  -- vendored repo onto sys.path

from daf.catalog.plan import validate_plan
from daf.catalog.plan_catalog import PlanCatalog
from daf.catalog.source_catalog import SourceCatalog
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import arxiv_binding, local_dataset_binding
from daf.orchestration.orchestrator import AcquisitionOrchestrator
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore


def _default_adapters() -> AdapterRegistry:
    adapters = AdapterRegistry()
    adapters.register(arxiv_binding())
    adapters.register(local_dataset_binding())
    return adapters


def _main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)

    root = Path(sys.argv[1])
    command = sys.argv[2]
    args = sys.argv[3:]

    sources = SourceCatalog(root / "sources")
    plans = PlanCatalog(root / "plans")
    adapters = _default_adapters()

    if command == "list-sources":
        for source in sources.all_sources():
            print(
                f"{source.source_id}\t{source.name}\tdomain={source.domain}\t"
                f"adapter={source.adapter_id}\tenabled={source.enabled}"
            )

    elif command == "inspect-source":
        print(sources.get(args[0]))

    elif command == "list-plans":
        for plan in plans.all_plans():
            print(f"{plan.plan_id}\tsource={plan.source_id}\tenabled={plan.enabled}\tschedule={plan.schedule}")

    elif command == "inspect-plan":
        print(plans.get(args[0]))

    elif command == "validate-plan":
        plan = plans.get(args[0])
        issues = validate_plan(plan, sources, adapters)
        if not issues:
            print(f"plan {plan.plan_id!r} is valid")
        else:
            for issue in issues:
                print(f"{issue.code}: {issue.message}")
            raise SystemExit(1)

    elif command == "execute-plan":
        plan = plans.get(args[0])
        requested_at = args[1]
        issues = validate_plan(plan, sources, adapters)
        if issues:
            for issue in issues:
                print(f"{issue.code}: {issue.message}")
            raise SystemExit(1)

        # DurablePool.restore (not the plain constructor) so this fresh
        # process's in-memory pool actually reflects what earlier CLI
        # invocations already persisted -- otherwise duplicate-detection
        # would only ever see this process's own writes. See
        # docs/DAF_ORCHESTRATION.md's Phase D report for why this matters.
        pool = DurablePool.restore(FilesystemEvidenceStore(root / "evidence"))
        orchestrator = AcquisitionOrchestrator(sources, adapters, pool)
        result = orchestrator.run(plan.to_request(requested_at))

        print(f"outcome={result.outcome.value}")
        for artifact in result.artifacts:
            print(f"  artifact_id={artifact.artifact_id} version_id={artifact.version_id} is_new={artifact.is_new}")
        if result.error:
            print(f"error: {result.error}")
        if result.outcome.value not in ("acquired", "duplicate"):
            raise SystemExit(1)

    else:
        print(__doc__)
        raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover
    _main()
