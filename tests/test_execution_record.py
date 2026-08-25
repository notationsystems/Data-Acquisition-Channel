"""`execution_recorded` -- how an artifact entered the substrate.

Every acquisition here is the real, unmodified DAF path: recorded NOAA
CO-OPS bytes and a graph-declaring dataset, through `execute_plan`, the
orchestrator, `run_scout` and `ClassifiedPool`. The wrapper under test
adds a record beside that path; it does not replace any part of it.

The three identities this file keeps apart, measured rather than argued:

    operation_id   WHICH acquisition      stable across runs
    execution_id   WHICH RUN of it        distinct per run
    artifact_id    WHAT was acquired      stable across runtimes
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from evidence.identity import content_hash
from scout.interface import ExtractionCandidate

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import (
    RuntimeIdentity,
    compute_execution_id,
    compute_operation_id,
    fingerprint,
)
from daf.execution.quarantine import QuarantineIdentityMismatch, quarantine_record_to_dict
from daf.execution.record import (
    FAILED,
    SUCCEEDED,
    ExecutionIdentityMismatch,
    ExecutionIntegrityMismatch,
    OutputWithoutSuccess,
    execution_record_from_dict,
    execution_record_to_dict,
    make_execution_record,
)
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding, noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics.evidence_class import ASSERTED, MEASURED, UNCLASSIFIED

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()

POLICY = SourceClassPolicy(
    id="source_policy:phase26",
    by_source_kind={"tide-station-window": MEASURED, "dataset": ASSERTED},
)
RUNTIME_A = RuntimeIdentity(
    python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1
)
RUNTIME_B = RuntimeIdentity(
    python_version="3.11.0", platform="linux-b", hostname="host-b", process_id=2
)
NOAA_PARAMETERS = {
    "station": "8454000",
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}


# ------------------------------------------------------------ fixtures


def _noaa_sources(source_id="noaa-cm", adapter_id="noaa-water-level-measurements"):
    registry = SourceRegistry()
    registry.register(
        SourceDefinition(
            source_id=source_id,
            name="NOAA CO-OPS Tides & Currents",
            domain="environmental-observations",
            adapter_id=adapter_id,
            required_parameters=("station", "product", "start_date", "end_date"),
            capabilities=("incremental",),
        )
    )
    return registry


def _noaa_adapters(payload=MLLW_BYTES):
    registry = AdapterRegistry()
    registry.register(
        noaa_water_level_measurement_binding(
            datum="MLLW", units="metric", fetch_bytes=lambda url: payload
        )
    )
    return registry


def _noaa_plan(plan_id="noaa-plan", source_id="noaa-cm"):
    return AcquisitionPlan(plan_id=plan_id, source_id=source_id, parameters=dict(NOAA_PARAMETERS))


def _dataset(root, value=78.0):
    path = root / "panel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "id": "m1",
                    "property": "tensile_strength",
                    "value": value,
                    "unit": "MPa",
                    "entities": [{"label": "formulation-f1", "kind": "formulation"}],
                    "relations": [],
                }
            ]
        )
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


class _UnconfidentModelExtractor:
    """A real rejection path, not a mock of one.

    `scout.pipeline.run_scout` refuses an extraction whose
    `extraction_method` names a model but supplies no confidence
    (`MISSING_MODEL_CONFIDENCE`) rather than silently defaulting it to
    1.0. That is the only admission failure this repository's own
    adapters can currently produce, so it is what the quarantine tests
    exercise -- through the unmodified pipeline."""

    def extract(self, record):
        return (
            ExtractionCandidate(
                content={"property": "tensile_strength", "value": 78.0, "unit": "MPa"},
                entities=(),
                relations=(),
                extraction_method="model:unnamed",
                confidence=None,
            ),
        )


def _rejecting_adapters():
    base = graph_dataset_binding()
    registry = AdapterRegistry()
    registry.register(
        AdapterBinding(
            adapter_id="graph-dataset",
            build_adapter=base.build_adapter,
            build_extractor=_UnconfidentModelExtractor,
            version=base.version,
        )
    )
    return registry


def _run(
    root,
    plan,
    sources,
    adapters,
    *,
    runtime=RUNTIME_A,
    started_at="2026-08-25T00:00:00Z",
    finished_at="2026-08-25T00:00:05Z",
    pool=None,
):
    store = FilesystemEvidenceStore(root / "evidence")
    pool = pool if pool is not None else ClassifiedPool(store, POLICY)
    return (
        execute_plan_recorded(
            plan,
            sources,
            adapters,
            pool,
            CheckpointStore(root / "checkpoints"),
            requested_at="2026-08-25T00:00:00Z",
            executions=ExecutionRecordStore(root),
            quarantine=QuarantineStore(root),
            runtime=runtime,
            started_at=started_at,
            finished_at=finished_at,
        ),
        pool,
    )


# ----------------------------------------- 1. record for a successful run


def test_a_successful_noaa_acquisition_is_recorded(tmp_path):
    recorded, pool = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())

    assert recorded.result.outcome.value == "acquired"
    execution = recorded.execution
    assert execution.status == SUCCEEDED
    assert execution.outcome == "acquired"
    assert execution.adapter_id == "noaa-water-level-measurements"
    assert execution.adapter_version is not None
    assert execution.started_at == "2026-08-25T00:00:00Z"
    assert execution.finished_at == "2026-08-25T00:00:05Z"
    assert execution.output_fingerprint is not None
    assert execution.artifact_ids
    assert execution.version_ids
    assert execution.parent_execution_id is None
    assert execution.error is None
    assert pool.all_observations()


def test_a_successful_graph_dataset_acquisition_is_recorded(tmp_path):
    path = _dataset(tmp_path)
    plan = AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(path)})
    recorded, pool = _run(tmp_path, plan, _dataset_sources(), _adapters_graph())

    assert recorded.result.outcome.value == "acquired"
    assert recorded.execution.status == SUCCEEDED
    assert recorded.execution.adapter_id == "graph-dataset"
    assert recorded.execution.adapter_version == graph_dataset_binding().version
    assert {pool.register.class_of(o.id) for o in pool.all_observations()} == {ASSERTED}


def _adapters_graph():
    registry = AdapterRegistry()
    registry.register(graph_dataset_binding())
    return registry


def test_the_recorded_ids_are_exactly_the_ones_the_result_carries(tmp_path):
    recorded, _ = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())
    assert recorded.execution.artifact_ids == tuple(
        sorted(a.artifact_id for a in recorded.result.artifacts)
    )
    assert recorded.execution.version_ids == tuple(
        sorted(a.version_id for a in recorded.result.artifacts)
    )


# ---------------------------------------------- 2/3. identity separation


def test_execution_identity_is_distinct_from_every_other_identity(tmp_path):
    recorded, pool = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())
    execution = recorded.execution

    observation_ids = {o.id for o in pool.all_observations()}
    record_ids = {r for o in pool.all_observations() for r in o.record_ids}
    version_ids = set(execution.version_ids)
    artifact_ids = set(execution.artifact_ids)

    everything_else = observation_ids | record_ids | version_ids | artifact_ids
    assert execution.id not in everything_else
    assert execution.operation_id not in everything_else
    assert execution.id != execution.operation_id
    # And the six kinds are pairwise distinct, not merely different from
    # the execution id.
    assert artifact_ids.isdisjoint(version_ids)
    assert observation_ids.isdisjoint(record_ids)


def test_artifact_identity_is_stable_across_execution_environments(tmp_path):
    """§8. Runtime, hostname, process id and the run's timestamps belong
    to execution identity. They must not reach artifact identity."""
    first, _ = _run(
        tmp_path / "a",
        _noaa_plan(),
        _noaa_sources(),
        _noaa_adapters(),
        runtime=RUNTIME_A,
        started_at="2026-08-25T00:00:00Z",
    )
    second, _ = _run(
        tmp_path / "b",
        _noaa_plan(),
        _noaa_sources(),
        _noaa_adapters(),
        runtime=RUNTIME_B,
        started_at="2027-01-01T12:00:00Z",
    )

    assert first.execution.id != second.execution.id, "two runs are two executions"
    assert first.execution.runtime_id != second.execution.runtime_id
    # ...and nothing about the acquired content moved.
    assert first.execution.operation_id == second.execution.operation_id
    assert first.execution.artifact_ids == second.execution.artifact_ids
    assert first.execution.version_ids == second.execution.version_ids
    assert first.execution.input_fingerprint == second.execution.input_fingerprint
    assert first.execution.output_fingerprint == second.execution.output_fingerprint


def test_operation_identity_is_a_function_of_the_plan_alone():
    a = compute_operation_id("p", "s", {"b": 2, "a": 1}, "snapshot")
    assert a == compute_operation_id("p", "s", {"a": 1, "b": 2}, "snapshot")
    assert a != compute_operation_id("p", "s", {"a": 1}, "snapshot")
    assert a != compute_operation_id("p", "s", {"a": 1, "b": 2}, "incremental")
    assert a != compute_operation_id("other", "s", {"a": 1, "b": 2}, "snapshot")


def test_execution_identity_does_not_depend_on_the_outcome():
    """The id is minted before a run starts, so it cannot change with how
    the run turns out. Two records differing only in outcome share an
    id and differ in `content_digest`."""
    common = {
        "operation_id": "op",
        "runtime_id": "rt",
        "started_at": "t0",
        "plan_id": "p",
        "source_id": "s",
        "adapter_id": "a",
        "adapter_version": "v",
        "finished_at": "t1",
        "input_fingerprint": "in",
    }
    ok = make_execution_record(
        status=SUCCEEDED, outcome="acquired", output_fingerprint="out", **common
    )
    bad = make_execution_record(
        status=FAILED, outcome="adapter_failure", output_fingerprint=None, error="boom", **common
    )
    assert ok.id == bad.id == compute_execution_id("op", "rt", "t0")
    assert ok.content_digest != bad.content_digest


# ------------------------------------------------ 4. adapter/version kept


def test_adapter_version_tracks_the_code_that_actually_runs(tmp_path):
    recorded, _ = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())
    binding = noaa_water_level_measurement_binding(
        datum="MLLW", units="metric", fetch_bytes=lambda url: MLLW_BYTES
    )
    assert recorded.execution.adapter_version == binding.version

    # It is derived from the adapter and extractor module source, so it
    # is reproducible and it is not a hand-maintained string.
    adapter_source = (REPO_ROOT / "daf/adapters/noaa_water_level.py").read_text()
    extractor_source = (REPO_ROOT / "daf/extractors/noaa_water_level_measurements.py").read_text()
    assert binding.version == content_hash(
        {
            "daf.adapters.noaa_water_level": adapter_source,
            "daf.extractors.noaa_water_level_measurements": extractor_source,
        }
    )


def test_an_undeclared_adapter_version_is_recorded_as_absent_not_guessed(tmp_path):
    base = graph_dataset_binding()
    registry = AdapterRegistry()
    registry.register(
        AdapterBinding(
            adapter_id="graph-dataset",
            build_adapter=base.build_adapter,
            build_extractor=base.build_extractor,
        )
    )
    path = _dataset(tmp_path)
    plan = AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(path)})
    recorded, _ = _run(tmp_path, plan, _dataset_sources(), registry)

    assert recorded.execution.status == SUCCEEDED
    assert recorded.execution.adapter_version is None


# ------------------------------------------------ 5. failures are retained


def test_an_unknown_source_still_produces_an_execution_record(tmp_path):
    """§10. The run failed before an adapter was even resolved. It is
    still a run that happened, and it is still auditable."""
    plan = _noaa_plan(source_id="does-not-exist")
    recorded, _ = _run(tmp_path, plan, _noaa_sources(), _noaa_adapters())

    execution = recorded.execution
    assert execution.status == FAILED
    assert execution.outcome == "source_unavailable"
    assert execution.error
    assert execution.adapter_id is None, "no adapter ran; that is a fact, not missing data"
    assert execution.adapter_version is None
    assert execution.artifact_ids == ()
    assert execution.version_ids == ()
    # The four questions §10 requires a failed run to answer:
    assert execution.plan_id and execution.source_id  # what operation, what source
    assert execution.started_at  # when
    assert execution.input_fingerprint  # what was asked for


def test_a_failed_execution_has_no_output_fingerprint(tmp_path):
    """§10: do not manufacture an output when there is none. `None` is
    not the same as a hash of the empty set."""
    recorded, _ = _run(tmp_path, _noaa_plan(source_id="does-not-exist"), _noaa_sources(), _noaa_adapters())
    assert recorded.execution.output_fingerprint is None
    assert recorded.execution.output_fingerprint != fingerprint({})

    with pytest.raises(OutputWithoutSuccess):
        make_execution_record(
            operation_id="op",
            runtime_id="rt",
            started_at="t0",
            plan_id="p",
            source_id="s",
            adapter_id=None,
            adapter_version=None,
            status=FAILED,
            outcome="adapter_failure",
            finished_at="t1",
            input_fingerprint="in",
            output_fingerprint="forged",
        )


def test_an_adapter_failure_is_recorded_with_the_adapter_named(tmp_path):
    """The source resolves, the adapter does not. The execution record
    keeps the adapter id the source declared, with no version, because
    no code ran."""
    sources = _noaa_sources(adapter_id="not-registered")
    recorded, _ = _run(tmp_path, _noaa_plan(), sources, _noaa_adapters())

    assert recorded.execution.status == FAILED
    assert recorded.execution.adapter_id == "not-registered"
    assert recorded.execution.adapter_version is None
    assert recorded.execution.output_fingerprint is None


def test_a_malformed_source_is_recorded_as_a_failed_execution(tmp_path):
    malformed = (FIXTURES / "noaa_window_malformed.json").read_bytes()
    recorded, pool = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters(malformed))

    assert recorded.execution.status == FAILED
    assert recorded.execution.outcome in ("adapter_failure", "extraction_failure")
    assert recorded.execution.error
    assert recorded.execution.adapter_version is not None, "the adapter code did run"
    assert pool.all_observations() == (), "nothing was admitted"


# ------------------------------------ 6/7. rejection lineage and quarantine


def test_a_refused_admission_is_quarantined_against_its_execution(tmp_path):
    path = _dataset(tmp_path)
    plan = AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(path)})
    recorded, pool = _run(tmp_path, plan, _dataset_sources(), _rejecting_adapters())

    assert recorded.result.admission_failures, "the rejection path did not fire"
    assert recorded.execution.admission_failure_count == len(recorded.result.admission_failures)
    assert recorded.quarantine, "the rejection was not retained"

    for quarantined in recorded.quarantine:
        assert quarantined.execution_id == recorded.execution.id
        assert quarantined.stage == "extraction"
        assert [e.code for e in quarantined.errors] == ["MISSING_MODEL_CONFIDENCE"]

    # ...and it survives to disk, still linked.
    store = QuarantineStore(tmp_path)
    assert store.for_execution(recorded.execution.id) == recorded.quarantine
    assert pool.all_observations() == (), "a refused observation was admitted anyway"


def test_quarantine_is_not_the_execution_record(tmp_path):
    """§11. One execution, many rejections; separate identities that
    reference each other rather than collapsing."""
    path = _dataset(tmp_path)
    plan = AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(path)})
    recorded, _ = _run(tmp_path, plan, _dataset_sources(), _rejecting_adapters())

    quarantined = recorded.quarantine[0]
    assert quarantined.id != recorded.execution.id
    assert quarantined.id != recorded.execution.operation_id
    assert not hasattr(quarantined, "status")
    assert not hasattr(quarantined, "adapter_id")


def test_a_successful_run_quarantines_nothing(tmp_path):
    recorded, _ = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())
    assert recorded.quarantine == ()
    assert recorded.execution.admission_failure_count == 0
    assert QuarantineStore(tmp_path).all_records() == ()


def test_execution_lineage_chains_across_runs_of_one_operation(tmp_path):
    """Two runs of the same plan: one operation, two executions, the
    second naming the first as its parent."""
    first, pool = _run(
        tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters(), started_at="2026-08-25T00:00:00Z"
    )
    second, _ = _run(
        tmp_path,
        _noaa_plan(),
        _noaa_sources(),
        _noaa_adapters(),
        started_at="2026-08-26T00:00:00Z",
        pool=pool,
    )

    assert first.execution.operation_id == second.execution.operation_id
    assert first.execution.id != second.execution.id
    assert first.execution.parent_execution_id is None
    assert second.execution.parent_execution_id == first.execution.id
    assert second.result.outcome.value == "duplicate", "the same bytes re-acquired"

    store = ExecutionRecordStore(tmp_path)
    chain = store.for_operation(first.execution.operation_id)
    assert [r.id for r in chain] == [first.execution.id, second.execution.id]


# ---------------------------------------- 8/9. persistence and tampering


def test_execution_records_survive_persistence_and_restore(tmp_path):
    recorded, _ = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())

    reopened = ExecutionRecordStore(tmp_path)
    assert reopened.has(recorded.execution.id)
    assert reopened.get(recorded.execution.id) == recorded.execution
    assert reopened.all_records() == (recorded.execution,)


def test_altering_an_identity_field_on_disk_is_detected(tmp_path):
    recorded, _ = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())
    path = tmp_path / "executions" / f"{recorded.execution.id}.json"
    payload = json.loads(path.read_text())

    path.write_text(json.dumps(dict(payload, started_at="2020-01-01T00:00:00Z")))
    with pytest.raises(ExecutionIdentityMismatch):
        ExecutionRecordStore(tmp_path).get(recorded.execution.id)


def test_altering_an_outcome_field_on_disk_is_detected(tmp_path):
    """The identity hash does not cover the outcome -- deliberately, so
    the id can exist before the outcome does. `content_digest` is what
    covers it, and this is the test that the split does not leave a
    hole."""
    recorded, _ = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())
    path = tmp_path / "executions" / f"{recorded.execution.id}.json"
    payload = json.loads(path.read_text())

    for field, forged in (
        ("outcome", "duplicate"),
        ("error", "nothing went wrong"),
        ("artifact_ids", []),
        ("output_fingerprint", content_hash({"forged": True})),
        ("adapter_version", "v-other"),
        ("admission_failure_count", 99),
        ("parent_execution_id", "someone-elses-run"),
    ):
        path.write_text(json.dumps(dict(payload, **{field: forged})))
        with pytest.raises(ExecutionIntegrityMismatch):
            ExecutionRecordStore(tmp_path).get(recorded.execution.id)


def test_altering_a_quarantine_record_on_disk_is_detected(tmp_path):
    path = _dataset(tmp_path)
    plan = AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(path)})
    recorded, _ = _run(tmp_path, plan, _dataset_sources(), _rejecting_adapters())

    quarantined = recorded.quarantine[0]
    payload = quarantine_record_to_dict(quarantined)
    target = tmp_path / "quarantine" / f"{quarantined.id}.json"
    target.write_text(json.dumps(dict(payload, stage="observation")))

    with pytest.raises(QuarantineIdentityMismatch):
        QuarantineStore(tmp_path).all_records()


def test_a_record_stored_under_the_wrong_filename_is_detected(tmp_path):
    recorded, _ = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())
    payload = execution_record_to_dict(recorded.execution)
    (tmp_path / "executions" / "not-its-id.json").write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="identifies as"):
        ExecutionRecordStore(tmp_path).all_records()


def test_the_roundtrip_is_lossless():
    record = make_execution_record(
        operation_id="op",
        runtime_id="rt",
        started_at="t0",
        plan_id="p",
        source_id="s",
        adapter_id="a",
        adapter_version=None,
        status=SUCCEEDED,
        outcome="acquired",
        finished_at="t1",
        input_fingerprint="in",
        output_fingerprint="out",
        artifact_ids=("z", "a"),
        version_ids=("v",),
    )
    assert execution_record_from_dict(execution_record_to_dict(record)) == record


# --------------------------------- 10/11. the boundary is not bypassed


def test_an_execution_record_is_not_evidence(tmp_path):
    """§14. Recording an operation must not add anything to the pool,
    and must not change the pool's own fingerprint."""
    store = FilesystemEvidenceStore(tmp_path / "evidence")
    pool = ClassifiedPool(store, POLICY)
    before = pool.fingerprint()

    recorded, _ = _run(tmp_path, _noaa_plan(source_id="does-not-exist"), _noaa_sources(), _noaa_adapters(), pool=pool)

    assert recorded.execution.status == FAILED
    assert pool.fingerprint() == before, "recording a failed run changed the evidence pool"
    assert len(pool) == 0


def test_an_execution_id_never_receives_an_evidence_class(tmp_path):
    """`class_assigned_at_ingest` has no shortcut through this package."""
    recorded, pool = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())

    assert pool.register.class_of(recorded.execution.id) == UNCLASSIFIED
    assert pool.register.class_of(recorded.execution.operation_id) == UNCLASSIFIED
    assert not pool.register.admissible_for_canonical_assertion(recorded.execution.id)
    # The evidence it describes IS classified -- the two are not the same
    # question, and only one of them has an answer.
    assert {pool.register.class_of(o.id) for o in pool.all_observations()} == {MEASURED}


def test_execution_records_live_outside_the_evidence_store(tmp_path):
    recorded, _ = _run(tmp_path, _noaa_plan(), _noaa_sources(), _noaa_adapters())

    evidence_root = tmp_path / "evidence"
    assert (tmp_path / "executions").is_dir()
    assert not (evidence_root / "executions").exists()
    assert not list(evidence_root.rglob(f"{recorded.execution.id}.json"))


def test_the_execution_package_never_writes_evidence():
    """AST. The acquisition-only evidence path is intact: nothing in
    `daf/execution/` calls a pool mutator or an admission gate."""
    offenders = []
    for path in sorted((REPO_ROOT / "daf" / "execution").rglob("*.py")):
        if "__pycache__" in path.as_posix():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.startswith(("put_", "admit_")):
                offenders.append(f"{path.name}:{name}")
    assert offenders == []


def test_the_unrecorded_acquisition_path_still_works(tmp_path):
    """Recording is additive. `execute_plan` is unchanged and callers
    that do not want a record are unaffected."""
    from daf.scheduling.runner import execute_plan

    store = FilesystemEvidenceStore(tmp_path / "evidence")
    pool = ClassifiedPool(store, POLICY)
    result = execute_plan(
        _noaa_plan(),
        _noaa_sources(),
        _noaa_adapters(),
        pool,
        CheckpointStore(tmp_path / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
    )
    assert result.outcome.value == "acquired"
    assert pool.all_observations()
    assert not (tmp_path / "executions").exists(), "an unrecorded run wrote an execution record"
