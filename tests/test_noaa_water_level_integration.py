"""End-to-end tests for the NOAA CO-OPS water-level source: SCOUT
admission, durable persistence, identity, checkpoint/incremental
behavior driven by a window-shaped, self-describing locator, revision
semantics generalized to a WINDOW (not an individual record, unlike
Phase H's USGS events), restart, failure handling, the one-door
invariant, and the existing operator CLI. Synthetic fixtures only -- see
tests/test_noaa_water_level_adapter.py's module docstring."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Dict

from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan, validate_plan
from daf.catalog.plan_catalog import PlanCatalog
from daf.catalog.source_catalog import SourceCatalog
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.result import AcquisitionOutcome
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent

_PARAMS = {"station": "9999999", "product": "water_level", "start_date": "20260101", "end_date": "20260201"}


def _fixture_router(routes: Dict[str, bytes]):
    def _fetch(url: str) -> bytes:
        for suffix, content in routes.items():
            if url.endswith(suffix):
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return _fetch


def _noaa_binding_with_routes(routes: Dict[str, bytes]):
    from daf.adapters.noaa_water_level import NoaaWaterLevelSourceAdapter
    from daf.extractors.noaa_water_level import NoaaWaterLevelExtractor
    from daf.orchestration.adapter_registry import AdapterBinding
    from daf.orchestration.bindings import _advance_noaa_position

    def build_adapter(source, request):
        since = request.parameters.get("since")
        return NoaaWaterLevelSourceAdapter(
            station=str(request.parameters["station"]),
            product=str(request.parameters["product"]),
            start_date=str(request.parameters["start_date"]),
            end_date=str(request.parameters["end_date"]),
            retrieved_at=request.requested_at,
            since_window_end=str(since) if since is not None else None,
            fetch_bytes=_fixture_router(routes),
        )

    return AdapterBinding(
        adapter_id="noaa-water-level",
        build_adapter=build_adapter,
        build_extractor=NoaaWaterLevelExtractor,
        advance_position=_advance_noaa_position,
    )


def _first_window_routes() -> Dict[str, bytes]:
    return {"begin_date=20260101&end_date=20260103&datum=MLLW&units=metric&time_zone=gmt&format=json":
            (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_bytes()}


def _second_window_routes() -> Dict[str, bytes]:
    return {"begin_date=20260102&end_date=20260104&datum=MLLW&units=metric&time_zone=gmt&format=json":
            (FIXTURES / "noaa_window_synthetic_20260102_20260104.json").read_bytes()}


def _setup(tmp_path: Path, routes: Dict[str, bytes] | None = None):
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_noaa_binding_with_routes(routes if routes is not None else _first_window_routes()))
    sources.register(
        SourceDefinition(
            source_id="noaa-water-level", name="NOAA CO-OPS Tides & Currents", domain="environmental-observations",
            adapter_id="noaa-water-level", required_parameters=("station", "product", "start_date", "end_date"),
            capabilities=("incremental",),
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    return sources, adapters, pool, checkpoints


def test_plan_validates_against_the_registered_source(tmp_path):
    sources, adapters, _, _ = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS), mode="incremental"
    )
    assert validate_plan(plan, sources, adapters) == ()


def test_full_pipeline_admits_evidence_through_existing_gate(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS), mode="incremental"
    )

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ACQUIRED
    assert len(result.artifacts) == 1  # ONE artifact per fetch() call -- a whole window, not per-reading
    assert len(pool.all_observations()) == 1


def test_raw_artifact_and_identity_preserved(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    artifact = result.artifacts[0]
    document = pool.get_document(artifact.version_id)
    assert document.raw_content == (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_text()
    assert document.retrieval_method == "http:noaa_water_level_v1"

    record = next(r for r in FilesystemEvidenceStore(tmp_path / "evidence").all_records() if r.document_id == document.id)
    assert record.locator == "9999999:water_level:MLLW:metric:20260101:20260103"  # the whole window, preserved verbatim


def test_checkpoint_advances_to_the_window_end_date_embedded_in_the_locator(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS))

    execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    # Unlike USGS (Phase H), the cursor value IS recoverable from the
    # locator alone here -- no raw_content parsing needed for this source.
    assert checkpoints.get("noaa-plan").position == "20260103"


def test_incremental_second_run_rewinds_by_the_trailing_safety_window(tmp_path):
    """The central Phase I proof: the SECOND run does not start
    immediately after the first window's end date -- it deliberately
    rewinds by `revision_lookback_days - 1` to re-verify the trailing
    edge of the previous window (Phase F's idiom, applied live here for
    the first time, for a different root cause: catching a window's
    preliminary readings later becoming verified, not late arrival)."""
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS), mode="incremental"
    )

    first = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")
    assert first.artifacts[0].locator == "9999999:water_level:MLLW:metric:20260101:20260103"

    adapters.register(_noaa_binding_with_routes(_second_window_routes()))
    second = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-26T00:00:00Z")

    # window_start = 20260103 - 1 day = 20260102 -- overlaps Jan2-3 with
    # the first window on purpose, extends one new day to Jan4.
    assert second.artifacts[0].locator == "9999999:water_level:MLLW:metric:20260102:20260104"
    assert checkpoints.get("noaa-plan").position == "20260104"
    assert len(pool.all_observations()) == 2  # two DIFFERENT window-artifacts, both legitimately admitted


def test_re_fetching_the_same_window_with_revised_readings_creates_a_new_version_same_artifact(tmp_path):
    """Generalizes Phase H's marquee finding (stable locator + revised
    content -> new version, same artifact) from an event-id locator to a
    WINDOW-shaped locator: re-requesting the EXACT SAME window
    (station/product/begin/end all identical) after NOAA's QC pipeline
    has flipped some readings from preliminary to verified must produce
    a NEW version under the SAME artifact_id -- proving the Phase B/H
    identity split generalizes without any further core changes."""
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS))

    first = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")
    first_artifact = first.artifacts[0]

    # Manually re-request the IDENTICAL window (same locator) -- as if an
    # operator reset the checkpoint to re-verify an already-acquired
    # window, exactly the scenario a real trailing-safety-window overlap
    # produces when it happens to land on the exact same boundaries.
    revised_routes = {
        "begin_date=20260101&end_date=20260103&datum=MLLW&units=metric&time_zone=gmt&format=json":
            (FIXTURES / "noaa_window_synthetic_20260101_20260103_revised.json").read_bytes()
    }
    from daf.orchestration.orchestrator import AcquisitionOrchestrator
    from daf.orchestration.request import AcquisitionRequest

    revised_adapters = AdapterRegistry()
    revised_adapters.register(_noaa_binding_with_routes(revised_routes))
    orchestrator = AcquisitionOrchestrator(sources, revised_adapters, pool)
    second_result = orchestrator.run(
        AcquisitionRequest(source_id="noaa-water-level", parameters=dict(_PARAMS), requested_at="2026-08-26T00:00:00Z")
    )

    assert second_result.outcome == AcquisitionOutcome.ACQUIRED
    second_artifact = second_result.artifacts[0]
    assert second_artifact.locator == first_artifact.locator == "9999999:water_level:MLLW:metric:20260101:20260103"
    assert second_artifact.artifact_id == first_artifact.artifact_id  # SAME artifact -- same (source_id, locator)
    assert second_artifact.version_id != first_artifact.version_id  # DIFFERENT version -- content genuinely changed
    assert second_artifact.is_new is True

    document = pool.get_document(second_artifact.version_id)
    assert document.raw_content == (FIXTURES / "noaa_window_synthetic_20260101_20260103_revised.json").read_text()
    assert len(pool.all_observations()) == 2  # original window-version + revised window-version, both kept


def test_repeated_acquisition_of_an_unchanged_window_is_reported_as_duplicate(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS))

    execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")
    from daf.catalog.checkpoint import AcquisitionCheckpoint

    checkpoints.advance(
        AcquisitionCheckpoint(plan_id="noaa-plan", source_id="noaa-water-level", position=None, updated_at="2026-08-26T00:00:00Z")
    )
    second = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-26T00:00:01Z")

    assert second.outcome == AcquisitionOutcome.DUPLICATE
    assert len(pool.all_observations()) == 1  # no duplication in the pool


def test_transient_http_failure_is_reported_as_source_unavailable(tmp_path):
    import urllib.error

    def _flaky(url: str) -> bytes:
        raise urllib.error.URLError("simulated connection reset")

    from daf.adapters.noaa_water_level import NoaaWaterLevelSourceAdapter
    from daf.extractors.noaa_water_level import NoaaWaterLevelExtractor
    from daf.orchestration.adapter_registry import AdapterBinding
    from daf.orchestration.bindings import _advance_noaa_position

    def build_adapter(source, request):
        return NoaaWaterLevelSourceAdapter(
            station=str(request.parameters["station"]), product=str(request.parameters["product"]),
            start_date=str(request.parameters["start_date"]), end_date=str(request.parameters["end_date"]),
            retrieved_at=request.requested_at, fetch_bytes=_flaky,
        )

    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(
            adapter_id="noaa-water-level", build_adapter=build_adapter,
            build_extractor=NoaaWaterLevelExtractor, advance_position=_advance_noaa_position,
        )
    )
    sources.register(
        SourceDefinition(
            source_id="noaa-water-level", name="NOAA CO-OPS Tides & Currents", domain="environmental-observations",
            adapter_id="noaa-water-level", capabilities=("incremental",),
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.SOURCE_UNAVAILABLE
    assert checkpoints.get("noaa-plan") is None


def test_adapter_side_failure_is_reported_as_adapter_failure(tmp_path):
    routes = {
        "begin_date=20260101&end_date=20260103&datum=MLLW&units=metric&time_zone=gmt&format=json":
            b'{"error": {"message": "The station is not a valid station or there is system error."}}'
    }
    sources, adapters, pool, checkpoints = _setup(tmp_path, routes=routes)
    plan = AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ADAPTER_FAILURE
    assert checkpoints.get("noaa-plan") is None


def test_malformed_response_is_an_extraction_failure_not_silently_admitted(tmp_path):
    routes = {
        "begin_date=20260101&end_date=20260103&datum=MLLW&units=metric&time_zone=gmt&format=json":
            (FIXTURES / "noaa_window_malformed.json").read_bytes()
    }
    sources, adapters, pool, checkpoints = _setup(tmp_path, routes=routes)
    plan = AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.EXTRACTION_FAILURE
    assert checkpoints.get("noaa-plan") is None
    assert len(pool.all_observations()) == 0


def test_persistence_failure_leaves_checkpoint_unadvanced(tmp_path):
    class _BrokenStore(FilesystemEvidenceStore):
        def put_observation(self, observation) -> None:
            raise OSError("simulated disk failure")

    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_noaa_binding_with_routes(_first_window_routes()))
    sources.register(
        SourceDefinition(
            source_id="noaa-water-level", name="NOAA CO-OPS Tides & Currents", domain="environmental-observations",
            adapter_id="noaa-water-level", capabilities=("incremental",),
        )
    )
    pool = DurablePool(_BrokenStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.PERSISTENCE_FAILURE
    assert checkpoints.get("noaa-plan") is None


def test_restart_resumes_incremental_acquisition_correctly(tmp_path):
    evidence_root = tmp_path / "evidence"
    checkpoint_root = tmp_path / "checkpoints"

    sources_a = SourceRegistry()
    adapters_a = AdapterRegistry()
    adapters_a.register(_noaa_binding_with_routes(_first_window_routes()))
    sources_a.register(
        SourceDefinition(
            source_id="noaa-water-level", name="NOAA CO-OPS Tides & Currents", domain="environmental-observations",
            adapter_id="noaa-water-level", capabilities=("incremental",),
        )
    )
    pool_a = DurablePool(FilesystemEvidenceStore(evidence_root))
    checkpoints_a = CheckpointStore(checkpoint_root)
    plan = AcquisitionPlan(
        plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS), mode="incremental"
    )

    first = execute_plan(plan, sources_a, adapters_a, pool_a, checkpoints_a, requested_at="2026-08-25T00:00:00Z")
    assert len(first.artifacts) == 1

    del sources_a, adapters_a, pool_a, checkpoints_a  # process A exits

    sources_b = SourceRegistry()
    adapters_b = AdapterRegistry()
    adapters_b.register(_noaa_binding_with_routes(_second_window_routes()))
    sources_b.register(
        SourceDefinition(
            source_id="noaa-water-level", name="NOAA CO-OPS Tides & Currents", domain="environmental-observations",
            adapter_id="noaa-water-level", capabilities=("incremental",),
        )
    )
    pool_b = DurablePool.restore(FilesystemEvidenceStore(evidence_root))
    checkpoints_b = CheckpointStore(checkpoint_root)

    second = execute_plan(plan, sources_b, adapters_b, pool_b, checkpoints_b, requested_at="2026-08-26T00:00:00Z")

    assert second.artifacts[0].locator == "9999999:water_level:MLLW:metric:20260102:20260104"
    assert len(pool_b.all_observations()) == 2


def test_one_door_invariant_for_noaa_modules():
    for path in (
        REPO_ROOT / "daf" / "adapters" / "noaa_water_level.py",
        REPO_ROOT / "daf" / "extractors" / "noaa_water_level.py",
    ):
        tree = ast.parse(path.read_text())
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        forbidden = {"materials", "experiment", "workbench", "core", "morpho", "backends", "runtime"}
        assert not (imported_roots & forbidden), f"{path.name} imports {imported_roots & forbidden}"

        source_text = path.read_text()
        assert "evidence.admission" not in source_text
        for forbidden_call in (".put_source(", ".put_document(", ".put_record(", ".put_observation("):
            assert forbidden_call not in source_text


def test_cli_end_to_end_with_noaa_source(tmp_path):
    """The existing operator CLI, unmodified in shape, drives a real
    incremental NOAA-style plan end to end -- fixture-backed via a
    monkeypatched fetch, run as real subprocesses."""
    root = tmp_path / "daf-root"
    SourceCatalog(root / "sources").register(
        SourceDefinition(
            source_id="noaa-water-level", name="NOAA CO-OPS Tides & Currents", domain="environmental-observations",
            adapter_id="noaa-water-level", required_parameters=("station", "product", "start_date", "end_date"),
            capabilities=("incremental",),
        )
    )
    PlanCatalog(root / "plans").register(
        AcquisitionPlan(
            plan_id="noaa-plan", source_id="noaa-water-level", parameters=dict(_PARAMS), mode="incremental",
        )
    )

    def _cli(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "daf.catalog.cli", str(root), *args],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60, check=False,
        )

    list_sources = _cli("list-sources")
    assert list_sources.returncode == 0
    assert "noaa-water-level" in list_sources.stdout

    list_plans = _cli("list-plans")
    assert list_plans.returncode == 0
    assert "noaa-plan" in list_plans.stdout

    validate = _cli("validate-plan", "noaa-plan")
    assert validate.returncode == 0
    assert "is valid" in validate.stdout
