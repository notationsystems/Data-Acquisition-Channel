"""Which admission gates a REAL acquisition can actually reach.

    code exists  !=  acquisition can reach it  !=  real acquisition has exercised it

Phase 28's named target was `record -> EMPTY_CONTENT`. It turned out to be
STRUCTURALLY UNREACHABLE, and the proof is here rather than asserted:
`run_scout` builds the Document and the Record from the SAME string, so an
empty body is always caught one gate earlier. That is not a missing fixture.

Two other terminal gates turned out to be reachable and had never been
exercised, both through shipped bindings on real source conditions:

    document    -> EMPTY_CONTENT   a listed file served as a zero-length body
    observation -> EMPTY_CONTENT   a dataset record declaring only structure

And two gates previously REPORTED as reachable are not, from any shipped
binding -- they were only ever reached by extractors written for the tests.
Those corrections are locked below so they cannot quietly regress.

Every acquisition here runs the full path: plan -> execute_plan_recorded ->
orchestrator -> real adapter -> run_scout -> ClassifiedPool, with execution
records, quarantine and metrics all produced by the real machinery.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

import pytest
from evidence.admission import admit_record
from evidence.types import make_record

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from daf.adapters.edgar_daily_index import EdgarDailyIndexSourceAdapter
from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.metrics import (
    PARTIAL_STAGES,
    TERMINAL_STAGES,
    ingest_report,
    rejection_metrics,
    unclassified_backlog,
)
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractor
from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.bindings import (
    _advance_edgar_position,
    _advance_usgs_position,
    _code_version,
    graph_dataset_binding,
)
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics._yaml import loads
from epistemics.evidence_class import ASSERTED, MEASURED

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MATRIX = loads((REPO_ROOT / "architecture" / "admission_reachability.yaml").read_text())

POLICY = SourceClassPolicy(
    id="source_policy:phase28",
    by_source_kind={"daily-index": ASSERTED, "dataset": ASSERTED, "event-detail": MEASURED},
)
RUNTIME = RuntimeIdentity(
    python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1
)

# The real source condition under test: the listing names the file, and the
# server returns HTTP 200 with a zero-length body. The fixture is a genuinely
# empty file, not a placeholder.
EMPTY_IDX = FIXTURES / "edgar_daily_index_synthetic_20260701_empty.idx"
EMPTY_EVENT = FIXTURES / "usgs_event_detail_synth00000001_empty.json"
STRUCTURE_ONLY = FIXTURES / "graph_dataset_structure_only.json"


def _router(routes: Dict[str, bytes]):
    """Matches on a distinguishing substring rather than a suffix: USGS
    appends `&format=geojson` after the event id, so a suffix match would
    route every detail request to the listing."""

    def fetch(url: str) -> bytes:
        for marker, content in routes.items():
            if marker in url:
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return fetch


# ------------------------------------------------------------- harness


def _edgar(routes: Dict[str, bytes]):
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="edgar-filings",
            name="SEC EDGAR",
            domain="filings",
            adapter_id="edgar-daily-index",
            required_parameters=("year", "quarter"),
            capabilities=("incremental",),
        )
    )

    def build_adapter(source, request):
        return EdgarDailyIndexSourceAdapter(
            year=int(request.parameters["year"]),
            quarter=int(request.parameters["quarter"]),
            retrieved_at=request.requested_at,
            fetch_bytes=_router(routes),
        )

    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(
            adapter_id="edgar-daily-index",
            build_adapter=build_adapter,
            build_extractor=EdgarDailyIndexExtractor,
            advance_position=_advance_edgar_position,
            version=_code_version(EdgarDailyIndexSourceAdapter, EdgarDailyIndexExtractor),
        )
    )
    plan = AcquisitionPlan(
        plan_id="edgar-plan", source_id="edgar-filings", parameters={"year": 2026, "quarter": 3}
    )
    return plan, sources, adapters


def _usgs(routes: Dict[str, bytes]):
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="usgs-quakes",
            name="USGS Earthquakes",
            domain="environmental-observations",
            adapter_id="usgs-earthquakes",
            required_parameters=("start_time", "end_time", "min_magnitude"),
            capabilities=("incremental",),
        )
    )

    def build_adapter(source, request):
        return UsgsEarthquakeSourceAdapter(
            start_time=str(request.parameters["start_time"]),
            end_time=str(request.parameters["end_time"]),
            min_magnitude=float(request.parameters["min_magnitude"]),
            retrieved_at=request.requested_at,
            fetch_bytes=_router(routes),
        )

    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(
            adapter_id="usgs-earthquakes",
            build_adapter=build_adapter,
            build_extractor=UsgsEarthquakeExtractor,
            advance_position=_advance_usgs_position,
            version=_code_version(UsgsEarthquakeSourceAdapter, UsgsEarthquakeExtractor),
        )
    )
    plan = AcquisitionPlan(
        plan_id="usgs-plan",
        source_id="usgs-quakes",
        parameters={"start_time": "2026-01-01", "end_time": "2026-01-02", "min_magnitude": 1.0},
    )
    return plan, sources, adapters


def _graph(path: Path):
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="qc-panel",
            name="QC panel",
            domain="materials",
            adapter_id="graph-dataset",
            required_parameters=("path",),
            capabilities=(),
        )
    )
    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())
    plan = AcquisitionPlan(
        plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(path)}
    )
    return plan, sources, adapters


def _acquire(root, wiring, *, started_at="2026-08-25T00:00:00Z", pool=None):
    """The complete recorded acquisition path. Nothing is stubbed."""
    plan, sources, adapters = wiring
    pool = pool if pool is not None else ClassifiedPool(FilesystemEvidenceStore(root / "evidence"), POLICY)
    recorded = execute_plan_recorded(
        plan,
        sources,
        adapters,
        pool,
        CheckpointStore(root / "checkpoints"),
        requested_at=started_at,
        executions=ExecutionRecordStore(root),
        quarantine=QuarantineStore(root),
        runtime=RUNTIME,
        started_at=started_at,
        finished_at=started_at,
    )
    return recorded, pool


def _edgar_routes(first: bytes):
    return {
        "index.json": (FIXTURES / "edgar_index_listing_synthetic.json").read_bytes(),
        "company.20260701.idx": first,
        "company.20260702.idx": (FIXTURES / "edgar_daily_index_synthetic_20260702.idx").read_bytes(),
        "company.20260703.idx": (FIXTURES / "edgar_daily_index_synthetic_20260703.idx").read_bytes(),
    }


# ------------------------------------- 1/2. document -> EMPTY_CONTENT


def test_the_empty_fixture_really_is_empty():
    """The whole document-gate result rests on this. A fixture that
    quietly gained a byte would make the test pass for the wrong reason."""
    assert EMPTY_IDX.read_bytes() == b""
    assert EMPTY_EVENT.read_bytes() == b""


def test_an_empty_edgar_daily_index_file_is_refused_at_the_document_gate(tmp_path):
    """Full acquisition. The SEC directory listing names company.20260701.idx;
    the server returns it as a zero-length body. The adapter decodes and
    wraps it without an emptiness check -- correctly, that is the gate's
    job -- and admit_document refuses it."""
    recorded, _ = _acquire(tmp_path, _edgar(_edgar_routes(EMPTY_IDX.read_bytes())))

    failures = recorded.result.admission_failures
    assert len(failures) == 1
    assert failures[0].stage == "document"
    assert [e.code for e in failures[0].errors] == ["EMPTY_CONTENT"]
    assert [e.object_type for e in failures[0].errors] == ["Document"]

    # The two non-empty days were acquired normally.
    assert len(recorded.result.artifacts) == 2
    assert recorded.execution.status == "SUCCEEDED"
    assert {a.locator for a in recorded.result.artifacts} == {"20260702", "20260703"}


def test_the_same_condition_is_reachable_through_a_second_shipped_binding(tmp_path):
    """Not an EDGAR quirk. USGS decodes and wraps a per-event detail body
    the same way, so a zero-length detail response reaches the same gate."""
    routes = {
        "eventid=synth00000001": EMPTY_EVENT.read_bytes(),
        "eventid=synth00000002": (FIXTURES / "usgs_event_detail_synth00000002.json").read_bytes(),
        "eventid=synth00000003": (FIXTURES / "usgs_event_detail_synth00000003.json").read_bytes(),
        "starttime=": (FIXTURES / "usgs_listing_synthetic.json").read_bytes(),
    }
    recorded, _ = _acquire(tmp_path, _usgs(routes))

    failures = recorded.result.admission_failures
    assert len(failures) == 1
    assert failures[0].stage == "document"
    assert [e.code for e in failures[0].errors] == ["EMPTY_CONTENT"]
    assert len(recorded.result.artifacts) == 2


# ------------------------------------ 3. observation -> EMPTY_CONTENT


def test_a_structure_only_dataset_record_is_refused_at_the_observation_gate(tmp_path):
    """A record that declares entities and relations but carries no
    measured values. `GraphDatasetExtractor` consumes id/entities/relations
    as structure, so `Observation.content` comes out empty -- while the raw
    JSON string is non-empty, so the document and record gates both pass.

    The refusal is at the observation gate and nowhere earlier: that is
    what makes it a distinct, previously unexercised terminal stage."""
    recorded, pool = _acquire(tmp_path, _graph(STRUCTURE_ONLY))

    failures = recorded.result.admission_failures
    assert len(failures) == 1
    assert failures[0].stage == "observation"
    assert [e.code for e in failures[0].errors] == ["EMPTY_CONTENT"]
    assert [e.object_type for e in failures[0].errors] == ["Observation"]

    # Both documents and both records WERE admitted -- only the observation
    # was refused. The earlier gates genuinely passed.
    assert len(pool.store.all_documents()) == 2
    assert len(pool.store.all_records()) == 2
    assert len(pool.all_observations()) == 1
    assert len(recorded.result.artifacts) == 1


# ------------------- 4/5. the named target, and why it cannot be reached


def test_record_empty_content_is_structurally_unreachable(tmp_path):
    """Phase 28's named target, disproved rather than worked around.

    `run_scout` builds the Document and the Record from the SAME
    expression -- `raw_content=raw_doc.content` -- so an empty body is
    always consumed by `admit_document` first, which then `continue`s.
    Shown two ways: in the pipeline source, and by the fact that the
    empty EDGAR file produced a `document` refusal and never a `record`
    one."""
    pipeline = (REPO_ROOT / "vendor/scout-retrieval-agent/scout/pipeline.py").read_text()
    assert pipeline.count("raw_content=raw_doc.content") == 2, (
        "the document and the record are no longer built from the same string; "
        "re-derive this verdict"
    )

    recorded, _ = _acquire(tmp_path, _edgar(_edgar_routes(EMPTY_IDX.read_bytes())))
    stages = {f.stage for f in recorded.result.admission_failures}
    assert stages == {"document"}
    assert "record" not in stages

    entry = _matrix_entry("record", "EMPTY_CONTENT")
    assert entry["verdict"] == "STRUCTURALLY_UNREACHABLE"


def test_admit_record_still_refuses_empty_content_which_is_semantics_not_reachability():
    """Explicitly allowed by the phase brief, and explicitly NOT counted
    as acquisition reachability. The gate's meaning is intact; nothing
    about this call proves an acquisition can reach it."""
    errors = admit_record(_EmptyPool(), make_record(document_id="d", locator="l", raw_content=""))
    assert [e.code for e in errors] == ["EMPTY_CONTENT", "UNKNOWN_DOCUMENT"]

    entry = _matrix_entry("record", "EMPTY_CONTENT")
    assert entry.get("exercised") is None, (
        "a direct admit_record() call must never be recorded as acquisition reachability"
    )


class _EmptyPool:
    def has_document(self, document_id):
        return False


# --------------------------------- 6/7/8/9. execution, quarantine, metrics


def test_the_refusal_is_linked_to_its_execution_and_quarantined(tmp_path):
    recorded, _ = _acquire(tmp_path, _edgar(_edgar_routes(EMPTY_IDX.read_bytes())))

    assert recorded.execution.admission_failure_count == 1
    assert len(recorded.quarantine) == 1
    quarantined = recorded.quarantine[0]
    assert quarantined.execution_id == recorded.execution.id
    assert quarantined.stage == "document"
    assert [e.code for e in quarantined.errors] == ["EMPTY_CONTENT"]

    # Durable, and still linked after a restart.
    assert QuarantineStore(tmp_path).for_execution(recorded.execution.id) == recorded.quarantine
    assert recorded.execution.adapter_id == "edgar-daily-index"
    assert recorded.execution.adapter_version is not None


def test_the_new_refusal_lands_in_the_terminal_denominator(tmp_path):
    """document is a terminal stage, so the refusal both counts and
    enters the denominator."""
    recorded, _ = _acquire(tmp_path, _edgar(_edgar_routes(EMPTY_IDX.read_bytes())))
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    assert "document" in TERMINAL_STAGES
    assert metrics.accepted == 2
    assert metrics.terminal_refusals == 1
    assert metrics.partial_refusals == 0
    assert metrics.attempts == 3, "accepted + terminal must equal the files offered"
    assert metrics.rejection_rate == pytest.approx(1 / 3)

    by_code = {(c.stage, c.code): c for c in metrics.by_code}
    assert set(by_code) == {("document", "EMPTY_CONTENT")}
    assert by_code[("document", "EMPTY_CONTENT")].count == 1
    assert by_code[("document", "EMPTY_CONTENT")].rate == pytest.approx(1 / 3)


def test_the_observation_refusal_lands_in_the_terminal_denominator(tmp_path):
    recorded, _ = _acquire(tmp_path, _graph(STRUCTURE_ONLY))
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    assert "observation" in TERMINAL_STAGES
    assert metrics.accepted == 1
    assert metrics.terminal_refusals == 1
    assert metrics.attempts == 2
    assert metrics.rejection_rate == 0.5
    assert {(c.stage, c.code) for c in metrics.by_code} == {("observation", "EMPTY_CONTENT")}


def test_the_phase_27_terminal_versus_naive_distinction_still_holds(tmp_path):
    """Regression on the 25%-versus-40% result. A newly reachable terminal
    stage must not change how partial stages are treated."""
    assert set(TERMINAL_STAGES) == {"document", "extraction", "observation", "record"}
    assert set(PARTIAL_STAGES) == {"referent", "relationship"}

    recorded, _ = _acquire(tmp_path, _graph(STRUCTURE_ONLY))
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    # One refusal, one acceptance: terminal rate 0.5. The naive rate over
    # ALL refusals happens to agree here because there is no partial
    # refusal -- which is exactly the point: they diverge only when a
    # partial one exists, and the mechanism that keeps them apart is the
    # stage split asserted above.
    naive = len(recorded.result.admission_failures) / (
        metrics.accepted + len(recorded.result.admission_failures)
    )
    assert metrics.rejection_rate == naive == 0.5
    assert metrics.partial_refusals == 0


def test_the_backlog_is_unaffected_by_a_refusal(tmp_path):
    """A refused record never entered the pool, so it cannot appear in the
    backlog either -- as unclassified or otherwise."""
    _, pool = _acquire(tmp_path, _graph(STRUCTURE_ONLY))
    backlog = unclassified_backlog(pool.store, pool.register)

    by_category = {c.category: c for c in backlog.categories}
    assert by_category["observations"].total == 1, "the refused observation is not in the store"
    assert by_category["observations"].unclassified == 0
    assert by_category["documents"].total == 2
    assert by_category["documents"].unclassified == 0


# ------------------------------------------------------ 10. determinism


def test_the_refusal_and_its_metrics_are_deterministic_across_runs(tmp_path):
    """Two runs of the same input. Execution identities differ -- they are
    different events -- while the refusal, its classification and the
    computed rate do not."""
    first, pool = _acquire(
        tmp_path, _graph(STRUCTURE_ONLY), started_at="2026-08-25T00:00:00Z"
    )
    second, _ = _acquire(
        tmp_path, _graph(STRUCTURE_ONLY), started_at="2026-08-26T00:00:00Z", pool=pool
    )

    assert first.execution.id != second.execution.id, "two runs are two executions"
    assert first.execution.operation_id == second.execution.operation_id

    quarantine = QuarantineStore(tmp_path)
    a = rejection_metrics(first.execution, quarantine)
    b = rejection_metrics(second.execution, quarantine)

    assert [(c.stage, c.code, c.count, c.rate) for c in a.by_code] == [
        (c.stage, c.code, c.count, c.rate) for c in b.by_code
    ]
    assert a.terminal_refusals == b.terminal_refusals == 1
    assert a.partial_refusals == b.partial_refusals == 0
    # The second run re-acquired identical bytes, so nothing new was
    # admitted -- but the refusal fired again and is attributed to its own
    # execution.
    assert second.result.outcome.value == "duplicate"
    assert len(quarantine.for_execution(second.execution.id)) == 1

    report = ingest_report(ExecutionRecordStore(tmp_path), quarantine, pool.store, pool.register)
    assert len(report.runs) == 2
    assert report == ingest_report(
        ExecutionRecordStore(tmp_path), quarantine, pool.store, pool.register
    )


# ------------------------------------------- 11. the evidence boundary


def test_a_refused_record_never_becomes_evidence(tmp_path):
    """The empty EDGAR document is refused, and nothing about exercising
    that path lets it into the pool."""
    recorded, pool = _acquire(tmp_path, _edgar(_edgar_routes(EMPTY_IDX.read_bytes())))

    assert len(pool.store.all_documents()) == 2, "the refused document entered the pool"
    for document in pool.store.all_documents():
        assert document.raw_content != ""
    for record in pool.store.all_records():
        assert record.raw_content != ""

    # Nor does the refusal, the quarantine record or the execution.
    assert pool.register.class_of(recorded.execution.id) == "unclassified"
    assert pool.register.class_of(recorded.quarantine[0].id) == "unclassified"
    assert not (tmp_path / "evidence" / "quarantine").exists()
    assert not (tmp_path / "evidence" / "executions").exists()


def test_the_refused_document_is_absent_by_identity_not_merely_by_count(tmp_path):
    """Stronger than a count: the id an empty document WOULD have carries
    no artifact, no record and no class assignment."""
    from evidence.types import make_document, make_source

    recorded, pool = _acquire(tmp_path, _edgar(_edgar_routes(EMPTY_IDX.read_bytes())))
    source = make_source(kind="daily-index", name="SEC EDGAR")
    refused = make_document(
        source_id=source.id,
        raw_content="",
        retrieval_method="http:edgar_daily_index_v1",
        retrieved_at="2026-08-25T00:00:00Z",
    )

    assert not pool.has_document(refused.id)
    assert refused.id not in set(recorded.execution.version_ids)
    assert pool.register.class_of(refused.id) == "unclassified"


# ----------------------------------- 12. the matrix cannot drift silently


def _matrix_entry(stage: str, code: str):
    for entry in MATRIX["stages"][stage]["codes"]:
        if entry["code"] == code:
            return entry
    raise AssertionError(f"{stage}/{code} is not in architecture/admission_reachability.yaml")


def test_the_matrix_covers_exactly_the_codes_the_pipeline_can_emit():
    """A refusal code added upstream must not go silently unclassified --
    it would appear in the metric with no way to tell a real zero from a
    structural one."""
    admission = (REPO_ROOT / "vendor/scout-retrieval-agent/evidence/admission.py").read_text()
    pipeline = (REPO_ROOT / "vendor/scout-retrieval-agent/scout/pipeline.py").read_text()

    def codes_in(source: str, function: str) -> set:
        body = source.split(f"def {function}(", 1)[1].split("\ndef ", 1)[0]
        # AdmissionError("<object_type>", "<CODE>", ...) -- the calls span
        # several lines, so match across them rather than splitting.
        return set(re.findall(r'AdmissionError\(\s*"[^"]+",\s*"([A-Z_]+)"', body, flags=re.DOTALL))

    emitted = {
        "document": codes_in(admission, "admit_document"),
        "record": codes_in(admission, "admit_record"),
        "observation": codes_in(admission, "admit_observation"),
        "referent": codes_in(admission, "admit_referent"),
        "relationship": codes_in(admission, "admit_claimed_relationship") | {"UNKNOWN_LABEL"},
        "extraction": {"MISSING_MODEL_CONFIDENCE"},
    }
    assert "MISSING_MODEL_CONFIDENCE" in pipeline
    assert "UNKNOWN_LABEL" in pipeline

    for stage, expected in emitted.items():
        declared = {c["code"] for c in MATRIX["stages"][stage]["codes"]}
        assert declared == expected, f"{stage}: matrix declares {declared}, pipeline emits {expected}"


def test_every_reachable_entry_names_a_fixture_and_is_actually_exercised():
    reachable = [
        (stage, entry)
        for stage, spec in MATRIX["stages"].items()
        for entry in spec["codes"]
        if entry["verdict"] == "REACHABLE"
    ]
    assert {stage for stage, _ in reachable} == {"document", "observation"}

    for stage, entry in reachable:
        assert entry["exercised"] is True, f"{stage}/{entry['code']} claims REACHABLE but is not exercised"
        assert entry["exercised_by"] == "tests/test_admission_reachability.py"
        assert (REPO_ROOT / entry["fixture"]).exists(), f"{stage}: fixture {entry['fixture']} is missing"
        assert entry["binding"]


def test_every_unreachable_entry_names_what_blocks_it():
    for stage, spec in MATRIX["stages"].items():
        for entry in spec["codes"]:
            if entry["verdict"] == "REACHABLE":
                continue
            assert entry.get("blocked_by"), f"{stage}/{entry['code']} is unreachable but names no blocker"


def test_the_matrix_records_the_two_corrections_to_earlier_phases():
    """Phase 26 and 27 reported gates as reachable that no shipped binding
    can reach. The corrections are canonical data, not just prose, so the
    claim cannot quietly revert."""
    for stage, code in (("extraction", "MISSING_MODEL_CONFIDENCE"), ("relationship", "UNKNOWN_LABEL")):
        entry = _matrix_entry(stage, code)
        assert entry["verdict"] == "ADAPTER_UNREACHABLE"
        assert entry["exercised"] is False
        assert "bespoke extractor" in entry["exercised_only_by"]
        assert entry["correction"]

    assert len(MATRIX["corrections"]) == 2


def test_no_shipped_extractor_can_produce_a_model_attributed_candidate():
    """The evidence behind the `extraction` correction, measured over the
    real extractor sources rather than asserted."""
    for path in sorted((REPO_ROOT / "daf" / "extractors").glob("*.py")):
        source = path.read_text()
        assert 'extraction_method="model:' not in source
        assert "confidence=None" not in source


def test_the_summary_counts_match_the_matrix_itself():
    verdicts = [c["verdict"] for s in MATRIX["stages"].values() for c in s["codes"]]
    summary = MATRIX["summary"]
    assert summary["codes_total"] == len(verdicts)
    assert summary["reachable"] == verdicts.count("REACHABLE")
    assert summary["structurally_unreachable"] == verdicts.count("STRUCTURALLY_UNREACHABLE")
    assert summary["adapter_unreachable"] == verdicts.count("ADAPTER_UNREACHABLE")
    assert summary["extractor_defect_only"] == verdicts.count("EXTRACTOR_DEFECT_ONLY")
    assert summary["exercised_by_real_acquisition"] == sum(
        1 for s in MATRIX["stages"].values() for c in s["codes"] if c.get("exercised") is True
    )
