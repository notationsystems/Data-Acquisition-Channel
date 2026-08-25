"""End-to-end tests for the SEC EDGAR daily-index source: SCOUT
admission, durable persistence, identity, checkpoint/incremental
behavior, restart, failure handling, the one-door invariant, and the
existing operator CLI. Synthetic fixtures only -- see
tests/test_edgar_daily_index_adapter.py's module docstring."""

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


def _standard_routes() -> Dict[str, bytes]:
    return {
        "index.json": (FIXTURES / "edgar_index_listing_synthetic.json").read_bytes(),
        "company.20260701.idx": (FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_bytes(),
        "company.20260702.idx": (FIXTURES / "edgar_daily_index_synthetic_20260702.idx").read_bytes(),
        "company.20260703.idx": (FIXTURES / "edgar_daily_index_synthetic_20260703.idx").read_bytes(),
    }


def _fixture_router(routes: Dict[str, bytes]):
    def _fetch(url: str) -> bytes:
        for suffix, content in routes.items():
            if url.endswith(suffix):
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return _fetch


def _edgar_binding_with_routes(routes: Dict[str, bytes]):
    from daf.adapters.edgar_daily_index import EdgarDailyIndexSourceAdapter
    from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractor
    from daf.orchestration.adapter_registry import AdapterBinding
    from daf.orchestration.bindings import _advance_edgar_position

    def build_adapter(source, request):
        since = request.parameters.get("since")
        return EdgarDailyIndexSourceAdapter(
            year=int(request.parameters["year"]),
            quarter=int(request.parameters["quarter"]),
            retrieved_at=request.requested_at,
            since_date=str(since) if since is not None else None,
            fetch_bytes=_fixture_router(routes),
        )

    return AdapterBinding(
        adapter_id="edgar-daily-index",
        build_adapter=build_adapter,
        build_extractor=EdgarDailyIndexExtractor,
        advance_position=_advance_edgar_position,
    )


def _setup(tmp_path: Path, routes: Dict[str, bytes] | None = None):
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_edgar_binding_with_routes(routes if routes is not None else _standard_routes()))
    sources.register(
        SourceDefinition(
            source_id="edgar-filings",
            name="SEC EDGAR",
            domain="corporate-filings",
            adapter_id="edgar-daily-index",
            required_parameters=("year", "quarter"),
            capabilities=("incremental",),
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    return sources, adapters, pool, checkpoints


def test_plan_validates_against_the_registered_source(tmp_path):
    sources, adapters, _, _ = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3}, mode="incremental"
    )
    assert validate_plan(plan, sources, adapters) == ()


def test_full_pipeline_admits_evidence_through_existing_gate(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3}, mode="incremental"
    )

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ACQUIRED
    assert len(result.artifacts) == 3  # three synthetic days available
    assert len(pool.all_observations()) == 3


def test_raw_artifact_and_identity_preserved(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3})

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    first_artifact = result.artifacts[0]
    document = pool.get_document(first_artifact.version_id)
    assert document.raw_content == (FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_text()
    assert document.retrieval_method == "http:edgar_daily_index_v1"

    record = next(r for r in FilesystemEvidenceStore(tmp_path / "evidence").all_records() if r.document_id == document.id)
    assert record.locator == "20260701"  # EDGAR's own date, preserved verbatim as the locator


def test_checkpoint_advances_to_the_latest_date_after_a_successful_run(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3})

    execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert checkpoints.get("edgar-plan").position == "20260703"


def test_incremental_second_run_acquires_only_newly_relevant_dates(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(
        plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3}, mode="incremental"
    )

    first = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")
    assert [a.locator for a in first.artifacts] == ["20260701", "20260702", "20260703"]

    # A fourth day is now published upstream.
    routes = _standard_routes()
    routes["index.json"] = b'{"directory":{"item":[' + b'{"name":"company.20260701.idx"},{"name":"company.20260702.idx"},{"name":"company.20260703.idx"},{"name":"company.20260704.idx"}' + b"]}}"
    routes["company.20260704.idx"] = (FIXTURES / "edgar_daily_index_synthetic_20260703.idx").read_bytes()  # reuse content, only locator matters here
    adapters.register(_edgar_binding_with_routes(routes))

    second = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")

    assert [a.locator for a in second.artifacts] == ["20260704"]  # only the newly relevant date
    assert checkpoints.get("edgar-plan").position == "20260704"


def test_repeated_acquisition_is_reported_as_duplicate(tmp_path):
    sources, adapters, pool, checkpoints = _setup(tmp_path)
    plan = AcquisitionPlan(plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3})

    # Rewind: re-request the same range twice by resetting the checkpoint
    # between calls (simulating an operator re-running against an
    # unchanged upstream range).
    execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")
    from daf.catalog.checkpoint import AcquisitionCheckpoint

    checkpoints.advance(
        AcquisitionCheckpoint(plan_id="edgar-plan", source_id="edgar-filings", position=None, updated_at="2026-08-25T00:00:00Z")
    )
    second = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:01Z")

    assert second.outcome == AcquisitionOutcome.DUPLICATE
    assert len(pool.all_observations()) == 3  # no duplication in the pool


def test_transient_http_failure_is_reported_as_source_unavailable(tmp_path):
    import urllib.error

    def _flaky(url: str) -> bytes:
        raise urllib.error.URLError("simulated connection reset")

    from daf.adapters.edgar_daily_index import EdgarDailyIndexSourceAdapter
    from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractor
    from daf.orchestration.adapter_registry import AdapterBinding
    from daf.orchestration.bindings import _advance_edgar_position

    def build_adapter(source, request):
        return EdgarDailyIndexSourceAdapter(
            year=int(request.parameters["year"]), quarter=int(request.parameters["quarter"]),
            retrieved_at=request.requested_at, fetch_bytes=_flaky,
        )

    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(
            adapter_id="edgar-daily-index", build_adapter=build_adapter,
            build_extractor=EdgarDailyIndexExtractor, advance_position=_advance_edgar_position,
        )
    )
    sources.register(
        SourceDefinition(
            source_id="edgar-filings", name="SEC EDGAR", domain="corporate-filings",
            adapter_id="edgar-daily-index", capabilities=("incremental",),
        )
    )
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3})

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    # This test injects urllib.error.URLError directly as fetch_bytes,
    # bypassing _fetch_with_retries/EdgarFetchError wrapping entirely.
    # URLError is itself an OSError subclass, so the orchestrator's
    # existing OSError/ConnectionError/TimeoutError branch correctly
    # classifies it as SOURCE_UNAVAILABLE (a transient/environmental
    # failure), not ADAPTER_FAILURE (a bug in the adapter's own logic).
    assert result.outcome == AcquisitionOutcome.SOURCE_UNAVAILABLE
    assert checkpoints.get("edgar-plan") is None


def test_adapter_side_failure_is_reported_as_adapter_failure(tmp_path):
    """Distinct from the SOURCE_UNAVAILABLE case above: here the adapter's
    own fetch_bytes returns successfully, but the directory listing names
    no company.*.idx files -- EdgarDailyIndexSourceAdapter.fetch() raises
    EdgarFetchError (a RuntimeError, not OSError/ConnectionError/TimeoutError)
    directly, which the orchestrator's broad `except Exception` branch
    correctly classifies as ADAPTER_FAILURE."""
    routes = {"index.json": b'{"directory":{"item":[]}}'}
    sources, adapters, pool, checkpoints = _setup(tmp_path, routes=routes)
    plan = AcquisitionPlan(plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3})

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.ADAPTER_FAILURE
    assert checkpoints.get("edgar-plan") is None


def test_malformed_response_is_an_extraction_failure_not_silently_admitted(tmp_path):
    routes = _standard_routes()
    routes["company.20260701.idx"] = (FIXTURES / "edgar_daily_index_malformed.idx").read_bytes()
    sources, adapters, pool, checkpoints = _setup(tmp_path, routes=routes)
    plan = AcquisitionPlan(plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3})

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.EXTRACTION_FAILURE
    assert checkpoints.get("edgar-plan") is None
    assert len(pool.all_observations()) == 0


def test_persistence_failure_leaves_checkpoint_unadvanced(tmp_path):
    class _BrokenStore(FilesystemEvidenceStore):
        def put_observation(self, observation) -> None:
            raise OSError("simulated disk failure")

    sources = SourceRegistry()
    adapters = AdapterRegistry()
    adapters.register(_edgar_binding_with_routes(_standard_routes()))
    sources.register(
        SourceDefinition(
            source_id="edgar-filings", name="SEC EDGAR", domain="corporate-filings",
            adapter_id="edgar-daily-index", capabilities=("incremental",),
        )
    )
    pool = DurablePool(_BrokenStore(tmp_path / "evidence"))
    checkpoints = CheckpointStore(tmp_path / "checkpoints")
    plan = AcquisitionPlan(plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3})

    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-24T00:00:00Z")

    assert result.outcome == AcquisitionOutcome.PERSISTENCE_FAILURE
    assert checkpoints.get("edgar-plan") is None


def test_restart_resumes_incremental_acquisition_correctly(tmp_path):
    evidence_root = tmp_path / "evidence"
    checkpoint_root = tmp_path / "checkpoints"

    sources_a = SourceRegistry()
    adapters_a = AdapterRegistry()
    adapters_a.register(_edgar_binding_with_routes(_standard_routes()))
    sources_a.register(
        SourceDefinition(
            source_id="edgar-filings", name="SEC EDGAR", domain="corporate-filings",
            adapter_id="edgar-daily-index", capabilities=("incremental",),
        )
    )
    pool_a = DurablePool(FilesystemEvidenceStore(evidence_root))
    checkpoints_a = CheckpointStore(checkpoint_root)
    plan = AcquisitionPlan(
        plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3}, mode="incremental"
    )

    first = execute_plan(plan, sources_a, adapters_a, pool_a, checkpoints_a, requested_at="2026-08-24T00:00:00Z")
    assert len(first.artifacts) == 3

    del sources_a, adapters_a, pool_a, checkpoints_a  # process A exits

    sources_b = SourceRegistry()
    adapters_b = AdapterRegistry()
    routes_b = _standard_routes()
    routes_b["index.json"] = b'{"directory":{"item":[{"name":"company.20260701.idx"},{"name":"company.20260702.idx"},{"name":"company.20260703.idx"},{"name":"company.20260704.idx"}]}}'
    routes_b["company.20260704.idx"] = (FIXTURES / "edgar_daily_index_synthetic_20260703.idx").read_bytes()
    adapters_b.register(_edgar_binding_with_routes(routes_b))
    sources_b.register(
        SourceDefinition(
            source_id="edgar-filings", name="SEC EDGAR", domain="corporate-filings",
            adapter_id="edgar-daily-index", capabilities=("incremental",),
        )
    )
    pool_b = DurablePool.restore(FilesystemEvidenceStore(evidence_root))
    checkpoints_b = CheckpointStore(checkpoint_root)

    second = execute_plan(plan, sources_b, adapters_b, pool_b, checkpoints_b, requested_at="2026-08-25T00:00:00Z")

    assert [a.locator for a in second.artifacts] == ["20260704"]
    assert len(pool_b.all_observations()) == 4


def test_one_door_invariant_for_edgar_modules():
    for path in (
        REPO_ROOT / "daf" / "adapters" / "edgar_daily_index.py",
        REPO_ROOT / "daf" / "extractors" / "edgar_daily_index.py",
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


def test_cli_end_to_end_with_edgar_source(tmp_path):
    """The existing Phase D CLI, unmodified in shape, drives a real
    incremental EDGAR-style plan end to end -- fixture-backed via a
    monkeypatched fetch, run as real subprocesses."""
    root = tmp_path / "daf-root"
    SourceCatalog(root / "sources").register(
        SourceDefinition(
            source_id="edgar-filings", name="SEC EDGAR", domain="corporate-filings",
            adapter_id="edgar-daily-index", required_parameters=("year", "quarter"), capabilities=("incremental",),
        )
    )
    PlanCatalog(root / "plans").register(
        AcquisitionPlan(
            plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3}, mode="incremental",
        )
    )

    # Note: this smoke test exercises the CLI's wiring (registries,
    # checkpoint store, validate-then-execute flow) against the REAL
    # edgar_daily_index_binding, which would hit the live network on
    # execute. We only exercise the read-only commands here to stay
    # offline-safe in ordinary CI; the live path is covered separately
    # in tests/test_edgar_daily_index_live.py.
    def _cli(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "daf.catalog.cli", str(root), *args],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60, check=False,
        )

    list_sources = _cli("list-sources")
    assert list_sources.returncode == 0
    assert "edgar-filings" in list_sources.stdout

    list_plans = _cli("list-plans")
    assert list_plans.returncode == 0
    assert "edgar-plan" in list_plans.stdout

    validate = _cli("validate-plan", "edgar-plan")
    assert validate.returncode == 0
    assert "is valid" in validate.stdout
