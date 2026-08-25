"""Tests for daf.scheduling.due.{is_due, due_plans, run_due_plans} --
the deterministic scheduler interface, and a two-different-source
demonstration."""

from __future__ import annotations

from pathlib import Path

from daf.catalog.checkpoint import AcquisitionCheckpoint, CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.catalog.plan_catalog import PlanCatalog
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import incremental_dataset_binding, local_dataset_binding
from daf.orchestration.result import AcquisitionOutcome
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.due import due_plans, is_due, run_due_plans
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"


def test_never_run_plan_with_an_interval_is_due(tmp_path):
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={}, interval_seconds=3600)
    assert is_due(plan, checkpoints, now="2026-08-24T00:00:00Z")


def test_plan_with_no_interval_is_never_automatically_due(tmp_path):
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={})  # interval_seconds=None
    assert not is_due(plan, checkpoints, now="2026-08-24T00:00:00Z")


def test_disabled_plan_is_never_due(tmp_path):
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={}, interval_seconds=1, enabled=False)
    assert not is_due(plan, checkpoints, now="2026-08-24T00:00:00Z")


def test_plan_is_not_due_before_its_interval_elapses(tmp_path):
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    checkpoints.advance(
        AcquisitionCheckpoint(plan_id="p1", source_id="s", position=None, updated_at="2026-08-24T00:00:00Z")
    )
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={}, interval_seconds=3600)

    assert not is_due(plan, checkpoints, now="2026-08-24T00:30:00Z")  # only 30 minutes elapsed
    assert is_due(plan, checkpoints, now="2026-08-24T01:00:00Z")  # exactly one hour elapsed


def test_due_plans_returns_only_the_due_ones(tmp_path):
    plans = PlanCatalog(tmp_path / "plans")
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plans.register(AcquisitionPlan(plan_id="due-now", source_id="s", parameters={}, interval_seconds=3600))
    plans.register(AcquisitionPlan(plan_id="not-scheduled", source_id="s", parameters={}))  # no interval
    checkpoints.advance(
        AcquisitionCheckpoint(plan_id="just-ran", source_id="s", position=None, updated_at="2026-08-24T00:00:00Z")
    )
    plans.register(AcquisitionPlan(plan_id="just-ran", source_id="s", parameters={}, interval_seconds=3600))

    due = due_plans(plans, checkpoints, now="2026-08-24T00:05:00Z")
    assert [p.plan_id for p in due] == ["due-now"]


def test_run_due_plans_executes_two_different_source_semantics(tmp_path):
    """Domain independence at the scheduling layer, with a genuinely
    different acquisition pattern per plan: one snapshot source, one
    incremental/cursor source, both executed through the SAME
    run_due_plans call with no source-specific branching."""
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(local_dataset_binding())
    adapters.register(incremental_dataset_binding())
    sources.register(
        SourceDefinition(source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset")
    )
    sources.register(
        SourceDefinition(
            source_id="events", name="events", domain="test-only", adapter_id="incremental-dataset", capabilities=("incremental",)
        )
    )

    plans = PlanCatalog(tmp_path / "plans")
    plans.register(
        AcquisitionPlan(
            plan_id="widget-plan",
            source_id="widget-prices",
            parameters={"path": str(FIXTURES / "local_dataset_sample.json")},
            interval_seconds=3600,
        )
    )
    plans.register(
        AcquisitionPlan(
            plan_id="events-plan",
            source_id="events",
            parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")},
            mode="incremental",
            interval_seconds=3600,
        )
    )

    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")

    results = run_due_plans(plans, sources, adapters, pool, checkpoints, now="2026-08-24T00:00:00Z")

    assert {r.source_id for r in results} == {"widget-prices", "events"}
    assert all(r.outcome == AcquisitionOutcome.ACQUIRED for r in results)
    assert len(pool.all_observations()) == 2 + 3  # widget records + event records

    # Neither plan is due again immediately afterward.
    assert due_plans(plans, checkpoints, now="2026-08-24T00:00:01Z") == ()
