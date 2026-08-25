"""End-to-end tests for daf.orchestration.orchestrator.AcquisitionOrchestrator
-- the Phase C two-source vertical slice, failure classification, the
one-door SCOUT admission invariant, domain independence, and restart
retrieval of orchestrator-produced artifacts."""

from __future__ import annotations

import ast
from pathlib import Path

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.adapters.local_dataset import LocalDatasetSourceAdapter
from daf.extractors.arxiv import ArxivExtractor
from daf.extractors.local_dataset import LocalDatasetExtractor
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.orchestrator import AcquisitionOrchestrator
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.result import AcquisitionOutcome
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"
ORCHESTRATOR_SOURCE = (Path(__file__).parent.parent / "daf" / "orchestration" / "orchestrator.py").read_text()


def _arxiv_fixture_binding(fixture_name: str) -> AdapterBinding:
    def build_adapter(source, request):
        def _fetch(url: str) -> bytes:
            return (FIXTURES / fixture_name).read_bytes()

        return ArxivSourceAdapter(
            arxiv_ids=tuple(request.parameters.get("arxiv_ids", ("9999.00001",))),
            retrieved_at=request.requested_at,
            fetch_bytes=_fetch,
        )

    return AdapterBinding(adapter_id="arxiv", build_adapter=build_adapter, build_extractor=ArxivExtractor)


def _local_dataset_binding() -> AdapterBinding:
    def build_adapter(source, request):
        return LocalDatasetSourceAdapter(
            path=Path(request.parameters["path"]), source_name=source.name, retrieved_at=request.requested_at
        )

    return AdapterBinding(
        adapter_id="local-dataset", build_adapter=build_adapter, build_extractor=LocalDatasetExtractor
    )


def _fresh(tmp_path):
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_arxiv_fixture_binding("arxiv_single_entry_v1.xml"))
    adapters.register(_local_dataset_binding())
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "store"))
    return sources, adapters, AcquisitionOrchestrator(sources, adapters, pool), pool


def _dataset_request(path_name: str, requested_at: str = "2026-08-24T00:00:00Z") -> AcquisitionRequest:
    return AcquisitionRequest(
        source_id="widget-prices", parameters={"path": str(FIXTURES / path_name)}, requested_at=requested_at
    )


def test_successful_orchestration_for_arxiv_source(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(source_id="arxiv-papers", name="arXiv", domain="scientific-literature", adapter_id="arxiv")
    )

    result = orchestrator.run(
        AcquisitionRequest(
            source_id="arxiv-papers", parameters={"arxiv_ids": ["9999.00001"]}, requested_at="2026-08-24T00:00:00Z"
        )
    )

    assert result.outcome == AcquisitionOutcome.ACQUIRED
    assert len(result.artifacts) == 1
    assert result.artifacts[0].is_new
    assert len(pool.all_observations()) == 1


def test_successful_orchestration_for_local_dataset_source(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset"
        )
    )

    result = orchestrator.run(_dataset_request("local_dataset_sample.json"))

    assert result.outcome == AcquisitionOutcome.ACQUIRED
    assert len(result.artifacts) == 2  # two records in the fixture
    assert all(a.is_new for a in result.artifacts)
    assert len(pool.all_observations()) == 2


def test_acquired_artifact_exposes_raw_content_generically(tmp_path):
    """Phase H: AcquiredArtifact.raw_content is populated for EVERY
    adapter, not just the one (USGS) that motivated adding it -- proving
    the orchestrator plumbs it through generically rather than as a
    source-specific special case."""
    import json

    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset"
        )
    )

    result = orchestrator.run(_dataset_request("local_dataset_sample.json"))

    raw_contents = {a.raw_content for a in result.artifacts}
    assert raw_contents == {
        json.dumps({"id": "widget-1", "value": 42.5, "unit": "USD"}, sort_keys=True),
        json.dumps({"id": "widget-2", "value": 17.0, "unit": "USD"}, sort_keys=True),
    }


def test_two_different_adapters_through_the_same_orchestrator(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(source_id="arxiv-papers", name="arXiv", domain="scientific-literature", adapter_id="arxiv")
    )
    sources.register(
        SourceDefinition(
            source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset"
        )
    )

    arxiv_result = orchestrator.run(
        AcquisitionRequest(
            source_id="arxiv-papers", parameters={"arxiv_ids": ["9999.00001"]}, requested_at="2026-08-24T00:00:00Z"
        )
    )
    dataset_result = orchestrator.run(_dataset_request("local_dataset_sample.json"))

    assert arxiv_result.outcome == AcquisitionOutcome.ACQUIRED
    assert dataset_result.outcome == AcquisitionOutcome.ACQUIRED
    # SAME orchestrator, SAME pool -- both sources' evidence coexists
    assert len(pool.all_observations()) == 1 + 2


def test_repeated_acquisition_is_reported_as_duplicate(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset"
        )
    )
    request = _dataset_request("local_dataset_sample.json")

    first = orchestrator.run(request)
    second = orchestrator.run(request)

    assert first.outcome == AcquisitionOutcome.ACQUIRED
    assert second.outcome == AcquisitionOutcome.DUPLICATE
    assert {a.version_id for a in first.artifacts} == {a.version_id for a in second.artifacts}
    assert all(not a.is_new for a in second.artifacts)
    assert len(pool.all_observations()) == 2  # no duplication in the pool


def test_changed_content_is_reported_as_newly_acquired_with_distinct_version(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset"
        )
    )

    first = orchestrator.run(_dataset_request("local_dataset_sample.json"))
    second = orchestrator.run(_dataset_request("local_dataset_sample_revised.json", "2026-08-25T00:00:00Z"))

    assert first.outcome == AcquisitionOutcome.ACQUIRED
    assert second.outcome == AcquisitionOutcome.ACQUIRED  # widget-1's value changed -> a new version
    assert {a.version_id for a in first.artifacts} != {a.version_id for a in second.artifacts}
    assert len(pool.all_observations()) == 4  # 2 + 2 distinct versions, both retained


def test_unknown_source_is_reported_not_raised(tmp_path):
    _, _, orchestrator, _ = _fresh(tmp_path)
    result = orchestrator.run(
        AcquisitionRequest(source_id="does-not-exist", parameters={}, requested_at="2026-08-24T00:00:00Z")
    )
    assert result.outcome == AcquisitionOutcome.SOURCE_UNAVAILABLE
    assert result.error is not None


def test_disabled_source_is_reported_not_raised(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="widget-prices",
            name="widget-dataset",
            domain="public-dataset",
            adapter_id="local-dataset",
            enabled=False,
        )
    )
    result = orchestrator.run(_dataset_request("local_dataset_sample.json"))
    assert result.outcome == AcquisitionOutcome.SOURCE_UNAVAILABLE


def test_adapter_failure_is_reported_not_raised(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="arxiv-broken", name="arXiv (broken)", domain="scientific-literature", adapter_id="arxiv-broken"
        )
    )
    adapters.register(
        AdapterBinding(
            adapter_id="arxiv-broken",
            build_adapter=lambda source, request: ArxivSourceAdapter(
                arxiv_ids=("9999.00003",),
                retrieved_at=request.requested_at,
                fetch_bytes=lambda url: (FIXTURES / "arxiv_entry_missing_id.xml").read_bytes(),
            ),
            build_extractor=ArxivExtractor,
        )
    )

    result = orchestrator.run(
        AcquisitionRequest(source_id="arxiv-broken", parameters={}, requested_at="2026-08-24T00:00:00Z")
    )

    assert result.outcome == AcquisitionOutcome.ADAPTER_FAILURE
    assert result.error is not None
    assert len(pool.all_observations()) == 0


def test_source_unavailable_on_network_style_error_is_reported_not_raised(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="arxiv-unreachable",
            name="arXiv (unreachable)",
            domain="scientific-literature",
            adapter_id="arxiv-unreachable",
        )
    )

    def _always_fails(url: str) -> bytes:
        raise ConnectionError("simulated network outage")

    adapters.register(
        AdapterBinding(
            adapter_id="arxiv-unreachable",
            build_adapter=lambda source, request: ArxivSourceAdapter(
                arxiv_ids=("9999.00001",), retrieved_at=request.requested_at, fetch_bytes=_always_fails
            ),
            build_extractor=ArxivExtractor,
        )
    )

    result = orchestrator.run(
        AcquisitionRequest(source_id="arxiv-unreachable", parameters={}, requested_at="2026-08-24T00:00:00Z")
    )
    assert result.outcome == AcquisitionOutcome.SOURCE_UNAVAILABLE


def test_extraction_failure_is_reported_not_raised(tmp_path):
    sources, adapters, orchestrator, pool = _fresh(tmp_path)
    sources.register(
        SourceDefinition(
            source_id="broken-extractor-source", name="broken", domain="test-only", adapter_id="broken-extractor"
        )
    )

    class _AlwaysBreaksExtractor:
        def extract(self, record):
            raise ValueError("simulated extraction failure")

    adapters.register(
        AdapterBinding(
            adapter_id="broken-extractor",
            build_adapter=lambda source, request: LocalDatasetSourceAdapter(
                path=FIXTURES / "local_dataset_sample.json", source_name="test", retrieved_at=request.requested_at
            ),
            build_extractor=_AlwaysBreaksExtractor,
        )
    )

    result = orchestrator.run(
        AcquisitionRequest(source_id="broken-extractor-source", parameters={}, requested_at="2026-08-24T00:00:00Z")
    )
    assert result.outcome == AcquisitionOutcome.EXTRACTION_FAILURE
    assert len(pool.all_observations()) == 0


def test_persistence_failure_is_reported_not_raised(tmp_path):
    class _BrokenStore(FilesystemEvidenceStore):
        def put_observation(self, observation) -> None:
            raise OSError("simulated disk failure")

    pool = DurablePool(_BrokenStore(tmp_path / "store"))
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_local_dataset_binding())
    sources.register(
        SourceDefinition(
            source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset"
        )
    )
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)

    result = orchestrator.run(_dataset_request("local_dataset_sample.json"))
    assert result.outcome == AcquisitionOutcome.PERSISTENCE_FAILURE


def test_one_door_admission_invariant():
    """The orchestrator never imports evidence.admission and never calls
    a pool mutator directly -- the only write path is the unmodified
    scout.pipeline.run_scout call."""
    tree = ast.parse(ORCHESTRATOR_SOURCE)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

    assert "evidence.admission" not in imported_modules
    for forbidden_call in (
        ".put_source(",
        ".put_document(",
        ".put_record(",
        ".put_observation(",
        ".put_referent(",
        ".put_claimed_relationship(",
    ):
        assert forbidden_call not in ORCHESTRATOR_SOURCE


def test_orchestrator_never_imports_domain_specific_adapter_modules():
    """Domain independence: the orchestration core operates purely via
    the registries' callables, never importing a concrete adapter or
    extractor module."""
    tree = ast.parse(ORCHESTRATOR_SOURCE)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module)
        elif isinstance(node, ast.Import):
            imported_roots.update(alias.name for alias in node.names)

    forbidden_prefixes = ("daf.adapters", "daf.extractors")
    for module in imported_roots:
        assert not module.startswith(forbidden_prefixes), (
            f"orchestrator imports {module}, breaking domain independence"
        )


def test_restart_retrieval_of_orchestrator_produced_artifacts(tmp_path):
    store_path = tmp_path / "store"
    pool_a = DurablePool(FilesystemEvidenceStore(store_path))
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_local_dataset_binding())
    sources.register(
        SourceDefinition(
            source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset"
        )
    )
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool_a)

    result = orchestrator.run(_dataset_request("local_dataset_sample.json"))
    assert result.outcome == AcquisitionOutcome.ACQUIRED
    original_version_ids = {a.version_id for a in result.artifacts}

    del pool_a, orchestrator  # simulate process restart

    pool_b = DurablePool.restore(FilesystemEvidenceStore(store_path))
    for version_id in original_version_ids:
        assert pool_b.has_document(version_id)
        assert pool_b.get_document(version_id).id == version_id
