"""End-to-end tests for the Phase D catalog/planning layer: register ->
persist -> plan -> validate -> execute -> existing orchestrator -> SCOUT
-> DurablePool -> ArtifactStore, plus the one-door invariant, domain
independence, and a CLI smoke test."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from daf.catalog.plan import AcquisitionPlan, validate_plan
from daf.catalog.plan_catalog import PlanCatalog
from daf.catalog.source_catalog import SourceCatalog
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.orchestrator import AcquisitionOrchestrator
from daf.orchestration.result import AcquisitionOutcome
from daf.orchestration.source_registry import SourceDefinition
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent
CATALOG_SOURCE_FILES = (
    REPO_ROOT / "daf" / "catalog" / "plan.py",
    REPO_ROOT / "daf" / "catalog" / "source_catalog.py",
    REPO_ROOT / "daf" / "catalog" / "plan_catalog.py",
)


def _arxiv_fixture_binding(fixture_name: str) -> AdapterBinding:
    from daf.adapters.arxiv import ArxivSourceAdapter
    from daf.extractors.arxiv import ArxivExtractor

    def build_adapter(source, request):
        def _fetch(url: str) -> bytes:
            return (FIXTURES / fixture_name).read_bytes()

        return ArxivSourceAdapter(
            arxiv_ids=tuple(request.parameters["arxiv_ids"]), retrieved_at=request.requested_at, fetch_bytes=_fetch
        )

    return AdapterBinding(adapter_id="arxiv", build_adapter=build_adapter, build_extractor=ArxivExtractor)


def _local_dataset_binding() -> AdapterBinding:
    from daf.adapters.local_dataset import LocalDatasetSourceAdapter
    from daf.extractors.local_dataset import LocalDatasetExtractor

    def build_adapter(source, request):
        return LocalDatasetSourceAdapter(
            path=Path(request.parameters["path"]), source_name=source.name, retrieved_at=request.requested_at
        )

    return AdapterBinding(
        adapter_id="local-dataset", build_adapter=build_adapter, build_extractor=LocalDatasetExtractor
    )


def test_register_persist_plan_validate_execute(tmp_path):
    sources = SourceCatalog(tmp_path / "sources")
    plans = PlanCatalog(tmp_path / "plans")
    adapters = AdapterRegistry()
    adapters.register(_local_dataset_binding())

    sources.register(
        SourceDefinition(
            source_id="widget-prices",
            name="widget-dataset",
            domain="public-dataset",
            adapter_id="local-dataset",
            required_parameters=("path",),
        )
    )
    plans.register(
        AcquisitionPlan(
            plan_id="widget-daily",
            source_id="widget-prices",
            parameters={"path": str(FIXTURES / "local_dataset_sample.json")},
            schedule="daily",
        )
    )

    # persistence: reload both catalogs from disk as brand new objects
    sources = SourceCatalog(tmp_path / "sources")
    plans = PlanCatalog(tmp_path / "plans")

    plan = plans.get("widget-daily")
    assert validate_plan(plan, sources, adapters) == ()

    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)
    result = orchestrator.run(plan.to_request(requested_at="2026-08-24T00:00:00Z"))

    assert result.outcome == AcquisitionOutcome.ACQUIRED
    assert len(result.artifacts) == 2
    assert len(pool.all_observations()) == 2


def test_repeat_execution_of_the_same_plan_is_duplicate(tmp_path):
    sources = SourceCatalog(tmp_path / "sources")
    plans = PlanCatalog(tmp_path / "plans")
    adapters = AdapterRegistry()
    adapters.register(_local_dataset_binding())
    sources.register(
        SourceDefinition(source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset")
    )
    plans.register(
        AcquisitionPlan(
            plan_id="widget-daily",
            source_id="widget-prices",
            parameters={"path": str(FIXTURES / "local_dataset_sample.json")},
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)
    plan = plans.get("widget-daily")

    first = orchestrator.run(plan.to_request(requested_at="2026-08-24T00:00:00Z"))
    second = orchestrator.run(plan.to_request(requested_at="2026-08-25T00:00:00Z"))  # deliberately different requested_at

    assert first.outcome == AcquisitionOutcome.ACQUIRED
    assert second.outcome == AcquisitionOutcome.DUPLICATE
    assert {a.version_id for a in first.artifacts} == {a.version_id for a in second.artifacts}


def test_domain_independent_execution_of_two_different_sources(tmp_path):
    sources = SourceCatalog(tmp_path / "sources")
    plans = PlanCatalog(tmp_path / "plans")
    adapters = AdapterRegistry()
    adapters.register(_arxiv_fixture_binding("arxiv_single_entry_v1.xml"))
    adapters.register(_local_dataset_binding())

    sources.register(
        SourceDefinition(
            source_id="arxiv-papers",
            name="arXiv",
            domain="scientific-literature",
            adapter_id="arxiv",
            required_parameters=("arxiv_ids",),
        )
    )
    sources.register(
        SourceDefinition(
            source_id="widget-prices", name="widget-dataset", domain="public-dataset", adapter_id="local-dataset"
        )
    )
    plans.register(AcquisitionPlan(plan_id="arxiv-plan", source_id="arxiv-papers", parameters={"arxiv_ids": ["9999.00001"]}))
    plans.register(
        AcquisitionPlan(
            plan_id="widget-plan",
            source_id="widget-prices",
            parameters={"path": str(FIXTURES / "local_dataset_sample.json")},
        )
    )

    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)

    for plan_id in ("arxiv-plan", "widget-plan"):
        plan = plans.get(plan_id)
        assert validate_plan(plan, sources, adapters) == ()
        result = orchestrator.run(plan.to_request(requested_at="2026-08-24T00:00:00Z"))
        assert result.outcome == AcquisitionOutcome.ACQUIRED

    assert len(pool.all_observations()) == 1 + 2  # arxiv (1) + widget records (2)


def test_one_door_invariant_for_catalog_modules():
    """The catalog/planning layer never imports evidence.admission and
    never calls a pool mutator directly -- every execution funnels
    through the existing, unmodified AcquisitionOrchestrator."""
    for path in CATALOG_SOURCE_FILES:
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


def test_catalog_and_plan_modules_never_import_domain_specific_adapters():
    """Domain independence at the catalog layer: plan.py and
    source_catalog.py never import a concrete adapter/extractor module.
    (cli.py and orchestration.bindings are the deliberate, documented
    exception -- see their own module docstrings.)"""
    for path in CATALOG_SOURCE_FILES:
        tree = ast.parse(path.read_text())
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module)
            elif isinstance(node, ast.Import):
                imported_roots.update(alias.name for alias in node.names)
        forbidden_prefixes = ("daf.adapters", "daf.extractors")
        for module in imported_roots:
            assert not module.startswith(forbidden_prefixes), f"{path.name} imports {module}"


def test_cli_smoke_end_to_end(tmp_path):
    """A CLI-driven version of the same flow, as two separate OS
    processes would see it: register via the Python API (as an operator
    setup script would), then drive list/validate/execute purely via the
    CLI subprocess."""
    root = tmp_path / "daf-root"
    SourceCatalog(root / "sources").register(
        SourceDefinition(
            source_id="widget-prices",
            name="widget-dataset",
            domain="public-dataset",
            adapter_id="local-dataset",
            required_parameters=("path",),
        )
    )
    PlanCatalog(root / "plans").register(
        AcquisitionPlan(
            plan_id="widget-daily",
            source_id="widget-prices",
            parameters={"path": str(FIXTURES / "local_dataset_sample.json")},
            schedule="daily",
        )
    )

    def _cli(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "daf.catalog.cli", str(root), *args],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=60,
        )

    list_sources = _cli("list-sources")
    assert list_sources.returncode == 0
    assert "widget-prices" in list_sources.stdout

    list_plans = _cli("list-plans")
    assert list_plans.returncode == 0
    assert "widget-daily" in list_plans.stdout

    validate = _cli("validate-plan", "widget-daily")
    assert validate.returncode == 0
    assert "is valid" in validate.stdout

    execute = _cli("execute-plan", "widget-daily", "2026-08-24T00:00:00Z")
    assert execute.returncode == 0
    assert "outcome=acquired" in execute.stdout

    repeat = _cli("execute-plan", "widget-daily", "2026-08-25T00:00:00Z")
    assert repeat.returncode == 0
    assert "outcome=duplicate" in repeat.stdout
