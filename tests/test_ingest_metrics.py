"""Per-invariant rejection rate per ingest run, and the unclassified backlog.

The central fact this file exists to lock down was measured, not assumed:
a run of four dataset records produced three accepted observations, one
refusal at `extraction` and one at `relationship` -- and the second did
NOT prevent an observation from entering the pool. A single "refusals
over refusals-plus-accepted" rate would report 0.40 for a run whose real
rejection rate is 0.25.

Every acquisition here is the real, unmodified DAF path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scout.interface import ExtractedEntity, ExtractedRelation, ExtractionCandidate

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.metrics import (
    PARTIAL_STAGES,
    STAGES,
    TERMINAL_STAGES,
    QuarantineAccountingError,
    ingest_report,
    rejection_metrics,
    unclassified_backlog,
)
from daf.execution.quarantine import make_quarantine_record
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding, noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.class_store import ClassAssignmentStore
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics.evidence_class import ASSERTED, MEASURED, ClassRegister

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()

POLICY = SourceClassPolicy(
    id="source_policy:phase27",
    by_source_kind={"tide-station-window": MEASURED, "dataset": ASSERTED},
)
RUNTIME = RuntimeIdentity(
    python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1
)
NOAA_PARAMETERS = {
    "station": "8454000",
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}


class _MixedExtractor:
    """Three real outcomes from one extractor, all through the unmodified
    pipeline:

      `bad`    -- names a model with no confidence. `run_scout` refuses it
                  at `extraction` (MISSING_MODEL_CONFIDENCE) and the
                  observation never enters the pool.  TERMINAL
      `orphan` -- declares a relation to a label it did not extract as an
                  entity. The OBSERVATION IS ADMITTED; only the edge is
                  refused, at `relationship` (UNKNOWN_LABEL).  PARTIAL
      anything else -- accepted.
    """

    def extract(self, record):
        payload = json.loads(record.raw_content)
        identifier = payload["id"]
        if identifier == "bad":
            return (
                ExtractionCandidate(
                    content=payload,
                    entities=(),
                    relations=(),
                    extraction_method="model:unnamed",
                    confidence=None,
                ),
            )
        if identifier == "orphan":
            return (
                ExtractionCandidate(
                    content=payload,
                    entities=(ExtractedEntity(label="f1", kind="formulation"),),
                    relations=(
                        ExtractedRelation(from_label="f1", to_label="nowhere", type="tested_during"),
                    ),
                    extraction_method="transcription",
                    confidence=1.0,
                ),
            )
        return (
            ExtractionCandidate(
                content=payload,
                entities=(ExtractedEntity(label="f1", kind="formulation"),),
                relations=(),
                extraction_method="transcription",
                confidence=1.0,
            ),
        )


def _dataset(root, identifiers):
    path = root / "panel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([{"id": i, "property": "tensile_strength", "value": n} for n, i in enumerate(identifiers)])
    )
    return path


def _dataset_sources():
    registry = SourceRegistry()
    registry.register(
        SourceDefinition(
            source_id="qc-panel",
            name="QC panel",
            domain="materials",
            adapter_id="graph-dataset",
            required_parameters=("path",),
            capabilities=(),
        )
    )
    return registry


def _mixed_adapters():
    base = graph_dataset_binding()
    registry = AdapterRegistry()
    registry.register(
        AdapterBinding(
            adapter_id="graph-dataset",
            build_adapter=base.build_adapter,
            build_extractor=_MixedExtractor,
            version=base.version,
        )
    )
    return registry


def _run_dataset(root, identifiers, *, started_at="2026-08-25T00:00:00Z", pool=None):
    path = _dataset(root, identifiers)
    plan = AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(path)})
    pool = pool if pool is not None else ClassifiedPool(FilesystemEvidenceStore(root / "evidence"), POLICY)
    recorded = execute_plan_recorded(
        plan,
        _dataset_sources(),
        _mixed_adapters(),
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


def _run_noaa(root, *, pool=None):
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="noaa-cm",
            name="NOAA CO-OPS Tides & Currents",
            domain="environmental-observations",
            adapter_id="noaa-water-level-measurements",
            required_parameters=("station", "product", "start_date", "end_date"),
            capabilities=("incremental",),
        )
    )
    adapters = AdapterRegistry()
    adapters.register(
        noaa_water_level_measurement_binding(
            datum="MLLW", units="metric", fetch_bytes=lambda url: MLLW_BYTES
        )
    )
    pool = pool if pool is not None else ClassifiedPool(FilesystemEvidenceStore(root / "evidence"), POLICY)
    recorded = execute_plan_recorded(
        AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-cm", parameters=dict(NOAA_PARAMETERS)),
        sources,
        adapters,
        pool,
        CheckpointStore(root / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
        executions=ExecutionRecordStore(root),
        quarantine=QuarantineStore(root),
        runtime=RUNTIME,
        started_at="2026-08-25T00:00:00Z",
        finished_at="2026-08-25T00:00:01Z",
    )
    return recorded, pool


# ------------------------------------------- the measured accounting rule


def test_a_partial_refusal_does_not_count_against_the_rejection_rate(tmp_path):
    """The finding that decided the design.

    Four records in: three observations admitted, one refused at
    `extraction`, one relationship refused on an observation that WAS
    admitted. accepted + terminal = 4 = the records offered. Folding the
    partial refusal in would report 2/5 = 0.40 for a run whose real
    rejection rate is 1/4 = 0.25."""
    recorded, _ = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    assert metrics.accepted == 3
    assert metrics.terminal_refusals == 1
    assert metrics.partial_refusals == 1
    assert metrics.attempts == 4, "accepted + terminal must equal the records offered"
    assert metrics.rejection_rate == 0.25
    assert metrics.rejection_rate != 2 / 5

    naive = len(recorded.result.admission_failures) / (
        metrics.accepted + len(recorded.result.admission_failures)
    )
    assert naive == pytest.approx(0.4)
    assert metrics.rejection_rate != naive


def test_the_admitted_observation_behind_the_partial_refusal_really_is_in_the_pool(tmp_path):
    """The rate above is only correct if `orphan` was genuinely admitted.
    Measured directly rather than inferred from the metric."""
    _, pool = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))

    contents = [json.loads(pool.get_record(o.record_ids[0]).raw_content)["id"] for o in pool.all_observations()]
    assert sorted(contents) == ["ok1", "ok2", "orphan"]
    assert "bad" not in contents
    assert pool.all_claimed_relationships() == (), "the refused edge was admitted anyway"


def test_every_stage_the_pipeline_can_emit_is_classified():
    """A stage `run_scout` can emit but this module does not classify
    would be silently dropped from every rate."""
    pipeline = (
        Path(__file__).resolve().parent.parent
        / "vendor/scout-retrieval-agent/scout/pipeline.py"
    ).read_text()
    emitted = {
        line.split('stage="', 1)[1].split('"', 1)[0]
        for line in pipeline.splitlines()
        if 'stage="' in line
    }
    assert emitted == set(STAGES)
    assert set(TERMINAL_STAGES).isdisjoint(PARTIAL_STAGES)


# ---------------------------------------------------- per-invariant rates


def test_rates_are_reported_per_stage_and_code(tmp_path):
    recorded, _ = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    by_code = {(c.stage, c.code): c for c in metrics.by_code}
    assert set(by_code) == {("extraction", "MISSING_MODEL_CONFIDENCE"), ("relationship", "UNKNOWN_LABEL")}

    terminal = by_code[("extraction", "MISSING_MODEL_CONFIDENCE")]
    assert terminal.count == 1
    assert terminal.rate == 0.25

    partial = by_code[("relationship", "UNKNOWN_LABEL")]
    assert partial.count == 1
    assert partial.rate is None, "a refused edge divided by admissions has no meaning"

    assert metrics.by_stage == {"extraction": 1, "relationship": 1}


def test_by_code_is_deterministically_ordered(tmp_path):
    recorded, _ = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))
    quarantine = QuarantineStore(tmp_path)
    first = rejection_metrics(recorded.execution, quarantine)
    second = rejection_metrics(recorded.execution, quarantine)

    assert first == second
    assert [(c.stage, c.code) for c in first.by_code] == sorted((c.stage, c.code) for c in first.by_code)


def test_a_clean_run_has_a_zero_rate_and_no_codes(tmp_path):
    recorded, _ = _run_noaa(tmp_path)
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    assert metrics.accepted > 0
    assert metrics.terminal_refusals == 0
    assert metrics.partial_refusals == 0
    assert metrics.rejection_rate == 0.0, "zero refusals over real attempts IS a rate of zero"
    assert metrics.by_code == ()
    assert metrics.by_stage == {}


def test_a_run_that_attempted_nothing_has_no_rate_rather_than_zero(tmp_path):
    """Absence, not a convenient zero -- the same discipline
    `output_fingerprint` follows on a failed execution."""
    root = tmp_path / "unknown"
    root.mkdir()
    plan = AcquisitionPlan(plan_id="p", source_id="does-not-exist", parameters={"path": "x"})
    recorded = execute_plan_recorded(
        plan,
        _dataset_sources(),
        _mixed_adapters(),
        ClassifiedPool(FilesystemEvidenceStore(root / "evidence"), POLICY),
        CheckpointStore(root / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
        executions=ExecutionRecordStore(root),
        quarantine=QuarantineStore(root),
        runtime=RUNTIME,
    )
    metrics = rejection_metrics(recorded.execution, QuarantineStore(root))

    assert metrics.attempts == 0
    assert metrics.rejection_rate is None
    assert metrics.rejection_rate != 0.0


def test_missing_quarantine_records_are_detected_not_averaged_over(tmp_path):
    """A rate computed over refusals that were silently lost would
    understate itself. The execution record already says how many there
    were, so the two are cross-checked."""
    recorded, _ = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))
    assert recorded.execution.admission_failure_count == 2

    for path in (tmp_path / "quarantine").glob("*.json"):
        path.unlink()
        break

    with pytest.raises(QuarantineAccountingError, match="recorded 2 refused"):
        rejection_metrics(recorded.execution, QuarantineStore(tmp_path))


def test_an_unknown_stage_is_refused_rather_than_counted_as_terminal(tmp_path):
    """Swapped for a bogus-stage record rather than added alongside one,
    so the COUNT still matches and this test exercises the stage check
    instead of passing on the accounting check that precedes it."""
    recorded, _ = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))
    quarantine = QuarantineStore(tmp_path)
    assert recorded.execution.admission_failure_count == 2

    victim = next((tmp_path / "quarantine").glob("*.json"))
    victim.unlink()
    quarantine.put(make_quarantine_record(recorded.execution.id, stage="invented", errors=()))
    assert len(quarantine.for_execution(recorded.execution.id)) == 2, "the count must still match"

    with pytest.raises(QuarantineAccountingError, match="names stage 'invented'"):
        rejection_metrics(recorded.execution, quarantine)


# ------------------------------------------------- unclassified backlog


def test_the_backlog_counts_the_durable_corpus(tmp_path):
    _, pool = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))
    backlog = unclassified_backlog(pool.store, pool.register)

    by_category = {c.category: c for c in backlog.categories}
    assert set(by_category) == set(FilesystemEvidenceStore.categories())

    # Everything the policy covers is classified...
    for category in ("sources", "documents", "records", "observations"):
        assert by_category[category].total > 0
        assert by_category[category].unclassified == 0

    # ...and the Referent honestly is not. `ClassifiedPool` never
    # classifies one, because an identity anchor asserts nothing.
    assert by_category["referents"].total == 1
    assert by_category["referents"].unclassified == 1

    assert backlog.unclassified == 1
    assert backlog.classified == backlog.total - 1
    assert backlog.unclassified_fraction == pytest.approx(1 / backlog.total)


def test_an_unclassified_corpus_is_reported_as_wholly_unclassified(tmp_path):
    """A pool persisted before `class_assigned_at_ingest` existed has no
    assignments on disk. The backlog says so rather than assuming."""
    silent = SourceClassPolicy(id="source_policy:none", by_source_kind={})
    root = tmp_path / "legacy"
    root.mkdir()
    pool = ClassifiedPool(FilesystemEvidenceStore(root / "evidence"), silent)
    _run_dataset(root, ("ok1", "ok2"), pool=pool)

    backlog = unclassified_backlog(pool.store, pool.register)
    assert backlog.total > 0
    assert backlog.classified == 0
    assert backlog.unclassified == backlog.total
    assert backlog.unclassified_fraction == 1.0


def test_an_empty_store_has_no_backlog_fraction(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    backlog = unclassified_backlog(store, ClassRegister())

    assert backlog.total == 0
    assert backlog.unclassified == 0
    assert backlog.unclassified_fraction is None


def test_the_backlog_is_recomputable_after_a_restart(tmp_path):
    _, pool = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))
    before = unclassified_backlog(pool.store, pool.register)

    restarted_store = FilesystemEvidenceStore(tmp_path / "evidence")
    restarted_register = ClassAssignmentStore(tmp_path / "evidence").restore()
    assert unclassified_backlog(restarted_store, restarted_register) == before


# ------------------------------------------------------------- the report


def test_the_report_covers_every_recorded_run_beside_the_backlog(tmp_path):
    first, pool = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"), started_at="2026-08-25T00:00:00Z")
    second, _ = _run_dataset(
        tmp_path, ("ok1", "bad", "orphan", "ok2"), started_at="2026-08-26T00:00:00Z", pool=pool
    )

    report = ingest_report(
        ExecutionRecordStore(tmp_path), QuarantineStore(tmp_path), pool.store, pool.register
    )
    assert [r.execution_id for r in report.runs] == [first.execution.id, second.execution.id]
    assert report.backlog.total > 0

    # The second run re-acquired identical bytes, so nothing new was
    # admitted -- but the refusals fired again, and the rate reflects it.
    assert report.runs[0].rejection_rate == 0.25
    assert report.runs[1].outcome == "duplicate"


def test_the_report_can_be_scoped_to_one_operation(tmp_path):
    dataset_run, pool = _run_dataset(tmp_path, ("ok1", "bad"))
    _run_noaa(tmp_path, pool=pool)

    everything = ingest_report(
        ExecutionRecordStore(tmp_path), QuarantineStore(tmp_path), pool.store, pool.register
    )
    scoped = ingest_report(
        ExecutionRecordStore(tmp_path),
        QuarantineStore(tmp_path),
        pool.store,
        pool.register,
        operation_id=dataset_run.execution.operation_id,
    )

    assert len(everything.runs) == 2
    assert [r.execution_id for r in scoped.runs] == [dataset_run.execution.id]
    assert scoped.backlog == everything.backlog, "the backlog is standing, not per-operation"


def test_the_report_is_recomputable_from_disk_alone(tmp_path):
    """No new identity, nothing persisted: a report is derived from
    records that already exist, so a fresh process reproduces it."""
    _, pool = _run_dataset(tmp_path, ("ok1", "bad", "orphan", "ok2"))
    live = ingest_report(
        ExecutionRecordStore(tmp_path), QuarantineStore(tmp_path), pool.store, pool.register
    )

    reopened = ingest_report(
        ExecutionRecordStore(tmp_path),
        QuarantineStore(tmp_path),
        FilesystemEvidenceStore(tmp_path / "evidence"),
        ClassAssignmentStore(tmp_path / "evidence").restore(),
    )
    assert reopened == live


def test_metrics_introduce_no_identity_and_are_never_persisted(tmp_path):
    recorded, pool = _run_dataset(tmp_path, ("ok1", "bad"))
    report = ingest_report(
        ExecutionRecordStore(tmp_path), QuarantineStore(tmp_path), pool.store, pool.register
    )

    for view in (report, report.backlog, *report.runs, *report.runs[0].by_code, *report.backlog.categories):
        assert not hasattr(view, "id"), f"{type(view).__name__} carries an identity"

    before = {p.name for p in tmp_path.rglob("*.json")}
    ingest_report(ExecutionRecordStore(tmp_path), QuarantineStore(tmp_path), pool.store, pool.register)
    assert {p.name for p in tmp_path.rglob("*.json")} == before, "computing a report wrote something"
    assert pool.register.class_of(recorded.execution.id) == "unclassified"
