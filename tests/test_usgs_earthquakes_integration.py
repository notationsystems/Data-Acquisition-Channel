"""End-to-end tests for the USGS Earthquake Catalog source: SCOUT
admission, durable persistence, identity, checkpoint/incremental
behavior driven by a content-derived cursor (not the locator), revision/
version semantics, restart, failure handling, the one-door invariant,
and the existing operator CLI. Synthetic fixtures only -- see
tests/test_usgs_earthquakes_adapter.py's module docstring."""

from __future__ import annotations

import ast
import json
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

_PARAMS = {"starttime": "2026-01-01", "endtime": "2026-01-02", "minmagnitude": 3.0}


def _standard_routes() -> Dict[str, bytes]:
    return {
        "&limit=500": (FIXTURES / "usgs_listing_synthetic.json").read_bytes(),
        "eventid=synth00000001&format=geojson": (FIXTURES / "usgs_event_detail_synth00000001.json").read_bytes(),
        "eventid=synth00000002&format=geojson": (FIXTURES / "usgs_event_detail_synth00000002.json").read_bytes(),
        "eventid=synth00000003&format=geojson": (FIXTURES / "usgs_event_detail_synth00000003.json").read_bytes(),
    }


def _fixture_router(routes: Dict[str, bytes]):
    def _fetch(url: str) -> bytes:
        for suffix, content in routes.items():
            if url.endswith(suffix):
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return _fetch


def _usgs_binding_with_routes(routes: Dict[str, bytes]):
    from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
    from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor
    from daf.orchestration.adapter_registry import AdapterBinding
    from daf.orchestration.bindings import _advance_usgs_position

    def build_adapter(source, request):
        since = request.parameters.get("since")
        return UsgsEarthquakeSourceAdapter(
            start_time=str(request.parameters["starttime"]),
            end_time=str(request.parameters["endtime"]),
            min_magnitude=float(request.parameters["minmagnitude"]),
            retrieved_at=request.requested_at,
            updated_after=str(since) if since is not None else None,
            fetch_bytes=_fixture_router(routes),
        )

    return AdapterBinding(
        adapter_id="usgs-earthquakes",
        build_adapter=build_adapter,
        build_extractor=UsgsEarthquakeExtractor,
        advance_position=_advance_usgs_position,
    )


def _setup(tmp_path: Path, routes: Dict[str, bytes] | None = None):
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_usgs_binding_with_routes(routes if routes is not None else _standard_routes()))
    sources.register(
        SourceDefinition(
            source_id="usgs-earthquakes", name="USGS Earthquake Catalog", domain="scientific-dataset",
            adapter_id="usgs-earthquakes", required_parameters=("starttime", "endtime", "minmagnitude"),
            capabilities=("incremental",),
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    return sources, adapters, pool, checkpoints


def test_plan_validates_against_the_registered_source(tmp_path):
    sources, adapters, _, _ = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS), mode="incremental"
    )
    assert validate_plan(plan, sources, adapters) == ()


def test_full_pipeline_admits_evidence_through_existing_gate(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS), mode="incremental"
    )

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ACQUIRED
    assert len(result.artifacts) == 3  # three synthetic events available
    assert len(pool.all_observations()) == 3


def test_raw_artifact_and_identity_preserved(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    first_artifact = result.artifacts[0]
    document = pool.get_document(first_artifact.version_id)
    assert document.raw_content == (FIXTURES / "usgs_event_detail_synth00000001.json").read_text()
    assert document.retrieval_method == "http:usgs_earthquake_v1"

    record = next(r for r in FilesystemEvidenceStore(tmp_path / "evidence").all_records() if r.document_id == document.id)
    assert record.locator == "synth00000001"  # USGS's own event id, preserved verbatim as the locator


def test_checkpoint_advances_to_the_max_revision_time_not_the_locator(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS))

    execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    # 1700000303000 ms == 2023-11-14T22:18:23.000Z -- the LATEST `updated`
    # among the three synthetic events, not any event's locator (which
    # are opaque strings like "synth00000003" that do not sort
    # meaningfully as a cursor at all).
    assert checkpoints.get("usgs-plan").position == "2023-11-14T22:18:23.000Z"


def test_incremental_second_run_acquires_only_the_revised_event(tmp_path):
    """The central Phase H proof: the SAME event id (synth00000001)
    reappears with genuinely revised content (a corrected magnitude) on
    the second run. Because the checkpoint is a content-derived
    revision-time cursor, NOT the locator, the second run correctly
    fetches only that one revised event -- and because artifact identity
    is (source_id, locator)-based, the revision produces a NEW version
    under the SAME artifact_id, not a new artifact."""
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS), mode="incremental"
    )

    first = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")
    assert [a.locator for a in first.artifacts] == ["synth00000001", "synth00000002", "synth00000003"]
    first_artifact_id = first.artifacts[0].artifact_id
    first_version_id = first.artifacts[0].version_id

    # Upstream revises synth00000001's magnitude (a real USGS behavior --
    # see docs/DAF_USGS_EARTHQUAKE_ADAPTER.md).
    revised_listing = json.loads((FIXTURES / "usgs_listing_synthetic.json").read_text())
    revised_listing["features"] = [
        f for f in revised_listing["features"] if f["id"] == "synth00000001"
    ]
    revised_listing["features"][0]["properties"]["updated"] = 1700000901000
    routes = {
        "&limit=500&updatedafter=2023-11-14T22:18:23.000Z": json.dumps(revised_listing).encode(),
        "eventid=synth00000001&format=geojson": (FIXTURES / "usgs_event_detail_synth00000001_revised.json").read_bytes(),
    }
    adapters.register(_usgs_binding_with_routes(routes))

    second = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-26T00:00:00Z")

    assert [a.locator for a in second.artifacts] == ["synth00000001"]  # only the revised event
    second_artifact_id = second.artifacts[0].artifact_id
    second_version_id = second.artifacts[0].version_id

    assert second_artifact_id == first_artifact_id  # SAME artifact -- same (source_id, locator)
    assert second_version_id != first_version_id  # DIFFERENT version -- content genuinely changed
    assert second.artifacts[0].is_new is True  # a genuinely new version, correctly reported as new

    assert checkpoints.get("usgs-plan").position == "2023-11-14T22:28:21.000Z"
    assert len(pool.all_observations()) == 4  # 3 original + 1 revision -- no data lost, nothing overwritten

    document = pool.get_document(second_version_id)
    assert document.raw_content == (FIXTURES / "usgs_event_detail_synth00000001_revised.json").read_text()


def test_repeated_acquisition_is_reported_as_duplicate(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS))

    execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")
    from daf.catalog.checkpoint import AcquisitionCheckpoint

    checkpoints.advance(
        AcquisitionCheckpoint(plan_id="usgs-plan", source_id="usgs-earthquakes", position=None, updated_at="2026-08-26T00:00:00Z")
    )
    second = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-26T00:00:01Z")

    assert second.outcome == AcquisitionOutcome.DUPLICATE
    assert len(pool.all_observations()) == 3  # no duplication in the pool


def test_transient_http_failure_is_reported_as_source_unavailable(tmp_path):
    import urllib.error

    def _flaky(url: str) -> bytes:
        raise urllib.error.URLError("simulated connection reset")

    from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
    from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor
    from daf.orchestration.adapter_registry import AdapterBinding
    from daf.orchestration.bindings import _advance_usgs_position

    def build_adapter(source, request):
        return UsgsEarthquakeSourceAdapter(
            start_time=str(request.parameters["starttime"]), end_time=str(request.parameters["endtime"]),
            min_magnitude=float(request.parameters["minmagnitude"]), retrieved_at=request.requested_at,
            fetch_bytes=_flaky,
        )

    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(
            adapter_id="usgs-earthquakes", build_adapter=build_adapter,
            build_extractor=UsgsEarthquakeExtractor, advance_position=_advance_usgs_position,
        )
    )
    sources.register(
        SourceDefinition(
            source_id="usgs-earthquakes", name="USGS Earthquake Catalog", domain="scientific-dataset",
            adapter_id="usgs-earthquakes", capabilities=("incremental",),
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    # A raw urllib.error.URLError (an OSError subclass) reaching the
    # adapter boundary directly (bypassing _fetch_with_retries'
    # UsgsFetchError wrapping, exactly as in the EDGAR equivalent test)
    # is correctly classified SOURCE_UNAVAILABLE, not ADAPTER_FAILURE.
    assert result.outcome == AcquisitionOutcome.SOURCE_UNAVAILABLE
    assert checkpoints.get("usgs-plan") is None


def test_adapter_side_failure_is_reported_as_adapter_failure(tmp_path):
    routes = {"&limit=500": b'{"type":"FeatureCollection"}'}  # no "features" array
    sources, adapters, pool, checkpoints = _setup(tmp_path, routes=routes)
    plan = AcquisitionPlan(plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ADAPTER_FAILURE
    assert checkpoints.get("usgs-plan") is None


def test_malformed_response_is_an_extraction_failure_not_silently_admitted(tmp_path):
    routes = _standard_routes()
    routes["eventid=synth00000001&format=geojson"] = (FIXTURES / "usgs_event_detail_malformed.json").read_bytes()
    sources, adapters, pool, checkpoints = _setup(tmp_path, routes=routes)
    plan = AcquisitionPlan(plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.EXTRACTION_FAILURE
    assert checkpoints.get("usgs-plan") is None
    assert len(pool.all_observations()) == 0


def test_persistence_failure_leaves_checkpoint_unadvanced(tmp_path):
    class _BrokenStore(FilesystemEvidenceStore):
        def put_observation(self, observation) -> None:
            raise OSError("simulated disk failure")

    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_usgs_binding_with_routes(_standard_routes()))
    sources.register(
        SourceDefinition(
            source_id="usgs-earthquakes", name="USGS Earthquake Catalog", domain="scientific-dataset",
            adapter_id="usgs-earthquakes", capabilities=("incremental",),
        )
    )
    pool = DurablePool(_BrokenStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS))

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.PERSISTENCE_FAILURE
    assert checkpoints.get("usgs-plan") is None


def test_restart_resumes_incremental_acquisition_correctly(tmp_path):
    evidence_root = tmp_path / "evidence"
    checkpoint_root = tmp_path / "checkpoints"

    sources_a = SourceRegistry()
    adapters_a = AdapterRegistry()
    adapters_a.register(_usgs_binding_with_routes(_standard_routes()))
    sources_a.register(
        SourceDefinition(
            source_id="usgs-earthquakes", name="USGS Earthquake Catalog", domain="scientific-dataset",
            adapter_id="usgs-earthquakes", capabilities=("incremental",),
        )
    )
    pool_a = DurablePool(FilesystemEvidenceStore(evidence_root))
    checkpoints_a = CheckpointStore(checkpoint_root)
    plan = AcquisitionPlan(
        plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS), mode="incremental"
    )

    first = execute_plan(plan, sources_a, adapters_a, pool_a, checkpoints_a, requested_at="2026-08-25T00:00:00Z")
    assert len(first.artifacts) == 3

    del sources_a, adapters_a, pool_a, checkpoints_a  # process A exits

    sources_b = SourceRegistry()
    adapters_b = AdapterRegistry()
    revised_listing = json.loads((FIXTURES / "usgs_listing_synthetic.json").read_text())
    revised_listing["features"] = [f for f in revised_listing["features"] if f["id"] == "synth00000001"]
    revised_listing["features"][0]["properties"]["updated"] = 1700000901000
    routes_b = {
        "&limit=500&updatedafter=2023-11-14T22:18:23.000Z": json.dumps(revised_listing).encode(),
        "eventid=synth00000001&format=geojson": (FIXTURES / "usgs_event_detail_synth00000001_revised.json").read_bytes(),
    }
    adapters_b.register(_usgs_binding_with_routes(routes_b))
    sources_b.register(
        SourceDefinition(
            source_id="usgs-earthquakes", name="USGS Earthquake Catalog", domain="scientific-dataset",
            adapter_id="usgs-earthquakes", capabilities=("incremental",),
        )
    )
    pool_b = DurablePool.restore(FilesystemEvidenceStore(evidence_root))
    checkpoints_b = CheckpointStore(checkpoint_root)

    second = execute_plan(plan, sources_b, adapters_b, pool_b, checkpoints_b, requested_at="2026-08-26T00:00:00Z")

    assert [a.locator for a in second.artifacts] == ["synth00000001"]
    assert len(pool_b.all_observations()) == 4


def test_one_door_invariant_for_usgs_modules():
    for path in (
        REPO_ROOT / "daf" / "adapters" / "usgs_earthquakes.py",
        REPO_ROOT / "daf" / "extractors" / "usgs_earthquakes.py",
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


def test_cli_end_to_end_with_usgs_source(tmp_path):
    """The existing operator CLI, unmodified in shape, drives a real
    incremental USGS-style plan end to end -- fixture-backed via a
    monkeypatched fetch, run as real subprocesses."""
    root = tmp_path / "daf-root"
    SourceCatalog(root / "sources").register(
        SourceDefinition(
            source_id="usgs-earthquakes", name="USGS Earthquake Catalog", domain="scientific-dataset",
            adapter_id="usgs-earthquakes", required_parameters=("starttime", "endtime", "minmagnitude"),
            capabilities=("incremental",),
        )
    )
    PlanCatalog(root / "plans").register(
        AcquisitionPlan(
            plan_id="usgs-plan", source_id="usgs-earthquakes", parameters=dict(_PARAMS), mode="incremental",
        )
    )

    def _cli(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "daf.catalog.cli", str(root), *args],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60, check=False,
        )

    list_sources = _cli("list-sources")
    assert list_sources.returncode == 0
    assert "usgs-earthquakes" in list_sources.stdout

    list_plans = _cli("list-plans")
    assert list_plans.returncode == 0
    assert "usgs-plan" in list_plans.stdout

    validate = _cli("validate-plan", "usgs-plan")
    assert validate.returncode == 0
    assert "is valid" in validate.stdout
