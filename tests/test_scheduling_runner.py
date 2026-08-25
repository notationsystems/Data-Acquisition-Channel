"""Tests for daf.scheduling.runner.execute_plan -- checkpoint advancement
semantics, snapshot vs incremental behavior, restart, and failure
handling."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import incremental_dataset_binding, local_dataset_binding
from daf.orchestration.result import AcquisitionOutcome
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import CheckpointPersistenceError, execute_plan
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent


def _snapshot_setup(tmp_path):
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(local_dataset_binding())
    sources.register(
        SourceDefinition(source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset")
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    return sources, adapters, pool, checkpoints


def _incremental_setup(tmp_path):
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(incremental_dataset_binding())
    sources.register(
        SourceDefinition(
            source_id="events", name="events", domain="test-only", adapter_id="incremental-dataset", capabilities=("incremental",)
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    return sources, adapters, pool, checkpoints


def test_snapshot_plan_advances_checkpoint_timestamp_but_never_a_position(tmp_path):
    sources, adapters, pool, checkpoints = _snapshot_setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="widget-daily", source_id="widget-prices", parameters={"path": str(FIXTURES / "local_dataset_sample.json")}
    )

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ACQUIRED
    checkpoint = checkpoints.get("widget-daily")
    assert checkpoint.position is None
    assert checkpoint.updated_at == "2026-08-24T00:00:00Z"


def test_incremental_plan_first_run_acquires_everything_and_advances_position(tmp_path):
    sources, adapters, pool, checkpoints = _incremental_setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="events-plan",
        source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")},
        mode="incremental",
    )

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ACQUIRED
    assert len(result.artifacts) == 3
    checkpoint = checkpoints.get("events-plan")
    assert checkpoint.position == "000000000003"  # highest sequence acquired


def test_incremental_plan_second_run_resumes_from_checkpoint(tmp_path):
    sources, adapters, pool, checkpoints = _incremental_setup(tmp_path)
    plan_initial = AcquisitionPlan(
        plan_id="events-plan",
        source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")},
        mode="incremental",
    )

    first = execute_plan(plan_initial, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")
    assert len(first.artifacts) == 3  # sequences 1-3

    # The "source" now has two new records (4, 5) beyond the checkpoint --
    # same plan_id, same logical plan, pointed at the grown file.
    plan_grown = AcquisitionPlan(
        plan_id="events-plan",
        source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample_extended.json")},
        mode="incremental",
    )
    second = execute_plan(plan_grown, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert second.outcome == AcquisitionOutcome.ACQUIRED
    assert len(second.artifacts) == 2  # only the NEW records were fetched at all
    assert all(a.is_new for a in second.artifacts)
    assert checkpoints.get("events-plan").position == "000000000005"
    assert len(pool.all_observations()) == 5  # 3 + 2, none re-fetched


def test_repeated_acquisition_from_the_same_checkpoint_is_idempotent(tmp_path):
    sources, adapters, pool, checkpoints = _incremental_setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="events-plan",
        source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")},
        mode="incremental",
    )
    execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")
    checkpoint_after_first = checkpoints.get("events-plan")

    # Re-running against the SAME (unextended) file finds nothing new past
    # the checkpoint -- must not corrupt state or regress the checkpoint.
    second = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert second.artifacts == ()
    assert second.outcome == AcquisitionOutcome.ACQUIRED  # zero fetched is a successful, empty run
    checkpoint_after_second = checkpoints.get("events-plan")
    assert checkpoint_after_second.position == checkpoint_after_first.position
    assert len(pool.all_observations()) == 3  # unchanged


def test_overlapping_results_are_deduplicated_by_existing_identity_machinery(tmp_path):
    """If a plan is (re-)configured with a `since` earlier than the real
    checkpoint -- simulating a source that returns overlapping records --
    the existing content-addressed dedup must handle it, not a new
    mechanism."""
    sources, adapters, pool, checkpoints = _incremental_setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="events-plan",
        source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")},
        mode="incremental",
    )
    execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    # Force an overlapping re-fetch by rewinding the checkpoint manually.
    from daf.catalog.checkpoint import AcquisitionCheckpoint

    checkpoints.advance(
        AcquisitionCheckpoint(plan_id="events-plan", source_id="events", position="000000000001", updated_at="2026-08-25T00:00:00Z")
    )
    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:01Z")

    assert result.outcome == AcquisitionOutcome.DUPLICATE  # sequences 2, 3 already durably persisted
    assert len(pool.all_observations()) == 3  # no duplication


def test_checkpoint_does_not_advance_on_disabled_source(tmp_path):
    sources, adapters, pool, checkpoints = _incremental_setup(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="events", name="events", domain="test-only", adapter_id="incremental-dataset",
            capabilities=("incremental",), enabled=False,
        )
    )
    plan = AcquisitionPlan(
        plan_id="events-plan", source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")}, mode="incremental",
    )

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.SOURCE_UNAVAILABLE
    assert checkpoints.get("events-plan") is None  # never advanced


def test_checkpoint_does_not_advance_on_adapter_failure(tmp_path):
    sources, adapters, pool, checkpoints = _incremental_setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="events-plan", source_id="events",
        parameters={"path": str(tmp_path / "does-not-exist.json")}, mode="incremental",
    )

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ADAPTER_FAILURE
    assert checkpoints.get("events-plan") is None


def test_checkpoint_does_not_advance_on_persistence_failure(tmp_path):
    class _BrokenStore(FilesystemEvidenceStore):
        def put_observation(self, observation) -> None:
            raise OSError("simulated disk failure")

    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(incremental_dataset_binding())
    sources.register(
        SourceDefinition(
            source_id="events", name="events", domain="test-only", adapter_id="incremental-dataset", capabilities=("incremental",)
        )
    )
    pool = DurablePool(_BrokenStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(
        plan_id="events-plan", source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")}, mode="incremental",
    )

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.PERSISTENCE_FAILURE
    assert checkpoints.get("events-plan") is None


def test_checkpoint_persistence_failure_is_reported_distinctly_after_a_successful_acquisition(tmp_path):
    class _BrokenCheckpointStore(CheckpointStore):
        def advance(self, checkpoint) -> None:
            raise OSError("simulated checkpoint disk failure")

    sources, adapters, pool, _ = _incremental_setup(tmp_path)
    checkpoints = _BrokenCheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(
        plan_id="events-plan", source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")}, mode="incremental",
    )

    with pytest.raises(CheckpointPersistenceError) as excinfo:
        execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    # The acquisition itself DID succeed -- artifacts are durably persisted
    # even though checkpoint tracking failed.
    assert excinfo.value.result.outcome == AcquisitionOutcome.ACQUIRED
    assert len(pool.all_observations()) == 3


def test_full_restart_resumes_incremental_acquisition_correctly(tmp_path):
    evidence_root = tmp_path / "evidence"
    checkpoint_root = tmp_path / "checkpoints"

    sources_a = SourceRegistry()
    adapters_a = AdapterRegistry()
    adapters_a.register(incremental_dataset_binding())
    sources_a.register(
        SourceDefinition(
            source_id="events", name="events", domain="test-only", adapter_id="incremental-dataset", capabilities=("incremental",)
        )
    )
    pool_a = DurablePool(FilesystemEvidenceStore(evidence_root))
    checkpoints_a = CheckpointStore(checkpoint_root)
    plan = AcquisitionPlan(
        plan_id="events-plan", source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample.json")}, mode="incremental",
    )

    first = execute_plan(plan, sources_a, adapters_a, pool_a, checkpoints_a, requested_at="2026-08-24T00:00:00Z")
    assert first.outcome == AcquisitionOutcome.ACQUIRED
    assert len(first.artifacts) == 3

    del sources_a, adapters_a, pool_a, checkpoints_a  # process A exits

    # process B: brand new objects, same on-disk paths, source now has more data
    sources_b = SourceRegistry()
    adapters_b = AdapterRegistry()
    adapters_b.register(incremental_dataset_binding())
    sources_b.register(
        SourceDefinition(
            source_id="events", name="events", domain="test-only", adapter_id="incremental-dataset", capabilities=("incremental",)
        )
    )
    pool_b = DurablePool.restore(FilesystemEvidenceStore(evidence_root))
    checkpoints_b = CheckpointStore(checkpoint_root)
    plan_extended = AcquisitionPlan(
        plan_id="events-plan", source_id="events",
        parameters={"path": str(FIXTURES / "incremental_dataset_sample_extended.json")}, mode="incremental",
    )

    second = execute_plan(plan_extended, sources_b, adapters_b, pool_b, checkpoints_b, requested_at="2026-08-25T00:00:00Z")

    assert second.outcome == AcquisitionOutcome.ACQUIRED
    assert len(second.artifacts) == 2  # correctly resumed -- only sequences 4, 5
    assert checkpoints_b.get("events-plan").position == "000000000005"
    assert len(pool_b.all_observations()) == 5


def test_one_door_invariant_for_scheduling_modules():
    for path in (REPO_ROOT / "daf" / "scheduling" / "runner.py", REPO_ROOT / "daf" / "scheduling" / "due.py"):
        source_text = path.read_text()
        tree = ast.parse(source_text)
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
            elif isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)

        assert "evidence.admission" not in imported_modules, path.name
        for forbidden_call in (".put_source(", ".put_document(", ".put_record(", ".put_observation("):
            assert forbidden_call not in source_text, f"{path.name} calls {forbidden_call}"
        forbidden_prefixes = ("daf.adapters", "daf.extractors")
        assert not any(module.startswith(forbidden_prefixes) for module in imported_modules), path.name
