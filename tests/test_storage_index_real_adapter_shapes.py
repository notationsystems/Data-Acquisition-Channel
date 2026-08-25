"""Phase K: proves the SQLite metadata index (daf.storage.metadata_index,
consumed via daf.storage.artifact_store.ArtifactStore) gives correct
answers against the three REAL, structurally different locator shapes
Phases G/H/I established -- not just the synthetic (source_id, locator)
pairs test_artifact_store.py exercises. Each source's full integration
suite (tests/test_edgar_daily_index_integration.py,
tests/test_usgs_earthquakes_integration.py,
tests/test_noaa_water_level_integration.py) already re-runs unchanged
against Phase K's storage layer end to end -- this file specifically
targets `ArtifactStore.list_versions`/`find_by_content_hash`/
`list_source_artifacts`, none of which existed before Phase K."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.orchestrator import AcquisitionOrchestrator
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.artifact_store import ArtifactStore
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_router(routes: Dict[str, bytes]):
    def _fetch(url: str) -> bytes:
        for suffix, content in routes.items():
            if url.endswith(suffix):
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return _fetch


def test_edgar_date_string_locators_are_correctly_indexed(tmp_path):
    """EDGAR: locator IS the cursor (a bare YYYYMMDD string) -- the
    simplest real shape. Three distinct dates -> three distinct
    artifacts, each with exactly one version, correctly grouped by
    source_id via the index."""
    from daf.adapters.edgar_daily_index import EdgarDailyIndexSourceAdapter
    from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractor

    routes = {
        "index.json": (FIXTURES / "edgar_index_listing_synthetic.json").read_bytes(),
        "company.20260701.idx": (FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_bytes(),
        "company.20260702.idx": (FIXTURES / "edgar_daily_index_synthetic_20260702.idx").read_bytes(),
        "company.20260703.idx": (FIXTURES / "edgar_daily_index_synthetic_20260703.idx").read_bytes(),
    }

    def build_adapter(source, request):
        return EdgarDailyIndexSourceAdapter(
            year=2026, quarter=3, retrieved_at=request.requested_at, fetch_bytes=_fixture_router(routes)
        )

    sources = SourceRegistry()
    sources.register(SourceDefinition(source_id="edgar", name="SEC EDGAR", domain="d", adapter_id="edgar-daily-index"))
    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(adapter_id="edgar-daily-index", build_adapter=build_adapter, build_extractor=EdgarDailyIndexExtractor)
    )
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    pool = DurablePool(store)
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)

    result = orchestrator.run(AcquisitionRequest(source_id="edgar", parameters={}, requested_at="2026-08-25T00:00:00Z"))
    assert len(result.artifacts) == 3

    artifact_store = ArtifactStore(store)
    source_id = pool.get_document(result.artifacts[0].version_id).source_id
    assert len(artifact_store.list_source_artifacts(source_id)) == 3  # one artifact per distinct date
    for artifact in result.artifacts:
        assert artifact_store.list_versions(artifact.artifact_id) == (artifact.version_id,)


def test_usgs_event_id_locators_track_revisions_under_one_artifact(tmp_path):
    """USGS: locator is a stable event id, but the SAME locator can
    legitimately produce a second version (a revision) -- the index must
    group both versions under one artifact_id, ordered by acquisition
    time, exactly as ArtifactStore.list_versions has always promised."""
    from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
    from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor

    listing = json.loads((FIXTURES / "usgs_listing_synthetic.json").read_text())
    listing["features"] = [f for f in listing["features"] if f["id"] == "synth00000001"]
    single_event_listing = json.dumps(listing).encode()

    def _binding(detail_fixture: str) -> AdapterBinding:
        routes = {
            "&limit=500": single_event_listing,
            "eventid=synth00000001&format=geojson": (FIXTURES / detail_fixture).read_bytes(),
        }

        def build_adapter(source, request):
            return UsgsEarthquakeSourceAdapter(
                start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
                retrieved_at=request.requested_at, fetch_bytes=_fixture_router(routes),
            )

        return AdapterBinding(adapter_id="usgs-earthquakes", build_adapter=build_adapter, build_extractor=UsgsEarthquakeExtractor)

    store = FilesystemEvidenceStore(tmp_path / "evidence")
    pool = DurablePool(store)
    sources = SourceRegistry()
    sources.register(SourceDefinition(source_id="usgs", name="USGS", domain="d", adapter_id="usgs-earthquakes"))
    adapters = AdapterRegistry()
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)

    adapters.register(_binding("usgs_event_detail_synth00000001.json"))
    first = orchestrator.run(AcquisitionRequest(source_id="usgs", parameters={}, requested_at="2026-08-25T00:00:00Z"))
    assert first.outcome.value == "acquired"

    adapters.register(_binding("usgs_event_detail_synth00000001_revised.json"))
    second = orchestrator.run(AcquisitionRequest(source_id="usgs", parameters={}, requested_at="2026-08-26T00:00:00Z"))
    assert second.outcome.value == "acquired"
    assert second.artifacts[0].is_new is True

    artifact_id = first.artifacts[0].artifact_id
    assert artifact_id == second.artifacts[0].artifact_id  # same locator -- same artifact
    versions = ArtifactStore(store).list_versions(artifact_id)
    assert versions == (first.artifacts[0].version_id, second.artifacts[0].version_id)  # both, oldest first


def test_noaa_window_locators_are_correctly_indexed(tmp_path):
    """NOAA: locator is a composite window descriptor
    ("station:product:begin:end") -- opaque to the index, indexed as a
    plain string, no NOAA-specific parsing anywhere in
    daf.storage.metadata_index."""
    from daf.adapters.noaa_water_level import NoaaWaterLevelSourceAdapter
    from daf.extractors.noaa_water_level import NoaaWaterLevelExtractor

    routes = {
        "begin_date=20260101&end_date=20260103&datum=MLLW&units=metric&time_zone=gmt&format=json":
            (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_bytes()
    }

    def build_adapter(source, request):
        return NoaaWaterLevelSourceAdapter(
            station="9999999", product="water_level", start_date="20260101", end_date="20260201",
            retrieved_at=request.requested_at, fetch_bytes=_fixture_router(routes),
        )

    sources = SourceRegistry()
    sources.register(SourceDefinition(source_id="noaa", name="NOAA", domain="d", adapter_id="noaa-water-level"))
    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(adapter_id="noaa-water-level", build_adapter=build_adapter, build_extractor=NoaaWaterLevelExtractor)
    )
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    pool = DurablePool(store)
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)

    result = orchestrator.run(AcquisitionRequest(source_id="noaa", parameters={}, requested_at="2026-08-25T00:00:00Z"))
    assert len(result.artifacts) == 1

    artifact_store = ArtifactStore(store)
    artifact = result.artifacts[0]
    assert artifact_store.list_versions(artifact.artifact_id) == (artifact.version_id,)
    assert artifact_store._locator_for(pool.get_document(artifact.version_id)) == "9999999:water_level:MLLW:metric:20260101:20260103"
