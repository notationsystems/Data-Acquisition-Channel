"""Chemistry/property admissibility, wired against REAL acquired evidence.

    ClassifiedPool (real, unmodified acquisition)
        |
        v  Observations whose content declares a "property"
    science.admissibility.no_context_free_property  (UNCHANGED gate)
        |
    admissible ------------------- inadmissible
        |                                |
    (stays evidence)          QuarantineRecord, stage="canonical_assertion"
                               (daf.execution.quarantine, UNCHANGED types)

Every acquisition here runs the real, unmodified Scout/DAF path -- a
direct `no_context_free_property(...)` or `admit_observation(...)` call
is used ONLY to establish gate semantics in isolation, and is never
counted as acquisition-reachability evidence, matching Phase 28's
established discipline for the same distinction.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from assertion.property_admissibility import (
    CANONICAL_ASSERTION_STAGE,
    assess_pool,
    canonical_assertion_quarantine_store,
    property_candidates,
)
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.metrics import rejection_metrics
from daf.execution.quarantine import QuarantineIdentityMismatch, quarantine_record_to_dict
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding, noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics._yaml import loads
from epistemics.evidence_class import ASSERTED, MEASURED

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CONTRACT = loads((REPO_ROOT / "architecture" / "property_admissibility.yaml").read_text())

RUNTIME = RuntimeIdentity(python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1)
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
NOAA_PARAMETERS = {
    "station": "8454000",
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}

# The one real materials-property declaration used throughout this test
# file. It satisfies EVERY key `no_context_free_property` requires --
# authored, per architecture/property_admissibility.yaml's own note, to
# the same acquisition-real/measurement-synthetic standard this
# repository has used for every materials-campaign fixture since Phase M.
ADMISSIBLE_RECORD = {
    "id": "ts-001",
    "property": "tensile_strength",
    "value": 78.0,
    "unit": "MPa",
    "method": "ASTM_E8",
    "conditions": {"temperature_c": 23, "specimen": "dogbone-A", "strain_rate_per_s": 0.001},
    "uncertainty_kind": "stated",
    "uncertainty": 1.2,
    "entities": [{"label": "formulation-f1", "kind": "formulation"}],
    "relations": [],
}
# The same property, declared the way every DAF source declares one
# TODAY -- bare scalar, no method, no conditions, no uncertainty kind.
BARE_RECORD = {
    "id": "ts-002-bare",
    "property": "tensile_strength",
    "value": 80.0,
    "unit": "MPa",
    "entities": [{"label": "formulation-f1", "kind": "formulation"}],
    "relations": [],
}


def _noaa_pool_and_execution(root, *, started_at="2026-08-25T00:00:00Z"):
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
    pool = ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="source_policy:phase29", by_source_kind={"tide-station-window": MEASURED}),
    )
    recorded = execute_plan_recorded(
        AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-cm", parameters=dict(NOAA_PARAMETERS)),
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


def _graph_pool_and_execution(root, records, *, started_at="2026-08-25T00:00:00Z"):
    path = root / "panel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records))
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
    pool = ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="source_policy:phase29", by_source_kind={"dataset": ASSERTED}),
    )
    recorded = execute_plan_recorded(
        AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(path)}),
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


# ------------------------------------------------- 1/2. real acquisition


def test_real_noaa_acquisition_reaches_property_extraction(tmp_path):
    """Real, unmodified adapter -> extractor -> run_scout -> pool.
    Nothing is manually constructed."""
    recorded, pool = _noaa_pool_and_execution(tmp_path)

    assert recorded.result.outcome.value == "acquired"
    observations = pool.all_observations()
    assert len(observations) == 240
    assert all("property" in o.content for o in observations)
    assert all(o.content["property"] == "water_level" for o in observations)


def test_real_graph_dataset_acquisition_reaches_property_extraction(tmp_path):
    recorded, pool = _graph_pool_and_execution(tmp_path, [ADMISSIBLE_RECORD])

    assert recorded.result.outcome.value == "acquired"
    observations = pool.all_observations()
    assert len(observations) == 1
    assert observations[0].content["property"] == "tensile_strength"


# ------------------------------------------------------ 3. context gate


def test_the_context_gate_rejects_every_real_noaa_reading(tmp_path):
    """The measured result this phase is built on. All 240 real,
    recorded NOAA readings fail identically -- deterministic, and for
    the same reason every time: the shipped extractor supplies no
    method and no conditions mapping.

    Phase 32 resolved MISSING_UNCERTAINTY_KIND (sigma is a source-stated
    standard deviation, wired as uncertainty/uncertainty_kind) without
    touching method or conditions -- see
    tests/test_noaa_uncertainty_provenance.py for that determination in
    full; this test only re-locks the resulting rejection set."""
    recorded, pool = _noaa_pool_and_execution(tmp_path)
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert report.candidates_examined == 240
    assert report.accepted == 0
    assert report.refused == 240
    assert report.by_code == {
        "MISSING_CONDITIONS": 240,
        "MISSING_METHOD": 240,
    }
    assert report.rejection_rate == 1.0


def test_the_context_gate_accepts_a_fully_specified_property(tmp_path):
    recorded, pool = _graph_pool_and_execution(tmp_path, [ADMISSIBLE_RECORD])
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert report.candidates_examined == 1
    assert report.accepted == 1
    assert report.refused == 0
    assert report.by_code == {}
    assert report.verdicts[0].admissibility.admissible
    assert report.verdicts[0].admissibility.reasons == ()


def test_the_gate_was_not_reshaped_to_accommodate_the_source():
    """The context gate is called on `Observation.content` verbatim.
    Nothing in `assertion/` adds, renames, or infers a key."""
    source = (REPO_ROOT / "assertion" / "property_admissibility.py").read_text()
    assert "no_context_free_property(candidate.content)" in source
    for forbidden in ("content[", "content.setdefault", "content.update", "dict(candidate.content,"):
        assert forbidden not in source, f"content was reshaped: {forbidden!r} found"


# ---------------------------------------------------- 4. quantity gate


def test_the_quantity_gate_fires_independently_of_the_context_gate():
    """Exercised directly, as unit semantics -- not counted as
    acquisition reachability, matching Phase 28's discipline."""
    from science.admissibility import quantity_is_typed

    typed = quantity_is_typed(ADMISSIBLE_RECORD)
    assert typed.admissible

    untyped = quantity_is_typed(BARE_RECORD)
    assert not untyped.admissible
    assert untyped.reasons == ("MISSING_UNCERTAINTY_KIND",)

    # `no_context_free_property` folds in exactly these same reasons --
    # measured, not assumed.
    from science.admissibility import no_context_free_property

    assert set(untyped.reasons) <= set(no_context_free_property(BARE_RECORD).reasons)


def test_absent_uncertainty_kind_is_distinct_from_a_declared_stated_value():
    """§6: uncertainty representation is not inferred. `absent` must be
    declared explicitly; a bare scalar with no `sigma` at all is refused,
    never silently treated as `absent`."""
    from science.admissibility import ABSENT, quantity_is_typed

    explicit_absent = dict(BARE_RECORD, uncertainty_kind=ABSENT, uncertainty=None)
    assert quantity_is_typed(explicit_absent).admissible

    assert not quantity_is_typed(BARE_RECORD).admissible, (
        "a missing uncertainty_kind field must never be silently treated as ABSENT"
    )


# ------------------------------------------------------- 5. method block


def test_a_source_that_supplies_no_method_is_rejected_not_completed():
    """§7: the shipped NOAA extractor supplies no method-block field of
    any kind, and none is invented here. Verified against the real
    extractor source, not merely against its output."""
    extractor_source = (
        REPO_ROOT / "daf" / "extractors" / "noaa_water_level_measurements.py"
    ).read_text()
    assert '"method"' not in extractor_source
    assert "'method'" not in extractor_source


# --------------------------------------------------- 6/7/8. quarantine


def test_a_rejected_property_is_quarantined_with_full_linkage(tmp_path):
    recorded, pool = _noaa_pool_and_execution(tmp_path)
    quarantine = canonical_assertion_quarantine_store(tmp_path)
    report = assess_pool(pool, recorded.execution.id, quarantine)

    stored = quarantine.for_execution(recorded.execution.id)
    assert len(stored) == report.refused == 240
    for record in stored:
        assert record.execution_id == recorded.execution.id
        assert record.stage == CANONICAL_ASSERTION_STAGE
        assert {e.code for e in record.errors} <= {
            "MISSING_METHOD",
            "MISSING_CONDITIONS",
            "MISSING_UNCERTAINTY_KIND",
        }
        assert all(e.object_type == "Observation" for e in record.errors)

    # Every quarantined verdict names the observation it came from.
    quarantined_ids = {v.candidate.observation_id for v in report.verdicts if not v.admissible}
    assert quarantined_ids == {o.id for o in pool.all_observations()}


def test_the_canonical_assertion_quarantine_is_separate_from_scout_admission_quarantine(tmp_path):
    """The whole reason for a second store. Mixing the two would break
    Phase 27/28's admission_failure_count cross-check."""
    recorded, pool = _noaa_pool_and_execution(tmp_path)
    assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    scout_quarantine = QuarantineStore(tmp_path)
    assert scout_quarantine.for_execution(recorded.execution.id) == ()
    assert recorded.execution.admission_failure_count == 0

    # And Phase 27's own metric is provably unaffected.
    metrics = rejection_metrics(recorded.execution, scout_quarantine)
    assert metrics.attempts == 240
    assert metrics.rejection_rate == 0.0
    assert metrics.by_code == ()


def test_the_quarantine_records_are_tamper_evident(tmp_path):
    """Reuses QuarantineRecord's own identity discipline unmodified."""
    recorded, pool = _graph_pool_and_execution(tmp_path, [BARE_RECORD])
    quarantine = canonical_assertion_quarantine_store(tmp_path)
    assess_pool(pool, recorded.execution.id, quarantine)

    stored = quarantine.for_execution(recorded.execution.id)
    assert len(stored) == 1
    payload = quarantine_record_to_dict(stored[0])
    path = quarantine.root / f"{stored[0].id}.json"
    path.write_text(json.dumps(dict(payload, stage="tampered")))

    with pytest.raises(QuarantineIdentityMismatch):
        canonical_assertion_quarantine_store(tmp_path).all_records()


# ---------------------------------------- 9. prediction vs measurement


def test_no_prediction_path_exists_to_collapse_into_measurement(tmp_path):
    """§9. Nothing in this repository computes or predicts a property
    value, so nothing here could classify one as measured evidence --
    verified over the real acquisition-authored source, not assumed."""
    for path in sorted((REPO_ROOT / "assertion").rglob("*.py")):
        source = path.read_text()
        for token in ("predict", "forecast", "model.generate", "inference"):
            assert token not in source.lower()

    # And the class every real candidate actually carries is exactly
    # what ClassifiedPool assigned at ingest -- never re-derived here.
    _, pool = _noaa_pool_and_execution(tmp_path)
    for o in pool.all_observations()[:5]:
        assert pool.register.class_of(o.id) == MEASURED


# ---------------------------------------------------- 10. rejection metrics


def test_property_admissibility_report_matches_the_measured_contract(tmp_path):
    recorded, pool = _noaa_pool_and_execution(tmp_path)
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    measured = CONTRACT["measured_reachability"]["noaa_water_level_measurements"]
    assert report.candidates_examined == measured["candidates_examined"]
    assert report.accepted == measured["accepted"]
    assert report.refused == measured["refused"]
    assert set(report.by_code) == set(measured["reasons"])


def test_a_run_with_no_property_candidates_reports_no_rate_not_a_zero(tmp_path):
    """§10's absence discipline, mirrored from Phase 27's
    output_fingerprint/rejection_rate handling."""
    recorded, pool = _graph_pool_and_execution(
        tmp_path, [{"id": "no-property", "value": 1, "entities": [], "relations": []}]
    )
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert report.candidates_examined == 0
    assert report.rejection_rate is None
    assert report.rejection_rate != 0.0


def test_terminal_partial_denominator_semantics_are_untouched(tmp_path):
    """§11/§13 regression: the Phase 27/28 terminal-rate denominator is
    computed over ACQUISITION attempts and must not change shape or
    value because a property-admissibility pass also ran."""
    recorded, pool = _noaa_pool_and_execution(tmp_path)
    before = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    after = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))
    assert before == after
    assert after.attempts == 240
    assert after.terminal_refusals == 0
    assert after.rejection_rate == 0.0


# --------------------------------------------------- 11. execution provenance


def test_execution_and_artifact_identity_stay_distinct_from_property_verdicts(tmp_path):
    recorded, pool = _noaa_pool_and_execution(tmp_path)
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    verdict = report.verdicts[0]
    assert verdict.candidate.execution_id == recorded.execution.id
    assert verdict.candidate.observation_id != recorded.execution.id
    assert verdict.candidate.observation_id != recorded.execution.operation_id
    assert verdict.candidate.observation_id not in recorded.execution.artifact_ids
    # The ExecutionRecord itself is untouched by the property pass.
    assert recorded.execution.admission_failure_count == 0


# ------------------------------------------------- 12. evidence boundary


def test_no_evidence_pool_write_path_exists_in_assertion():
    """AST proof, the same discipline `tests/test_execution_record.py`
    already applies to `daf/execution/`."""
    offenders = []
    for path in sorted((REPO_ROOT / "assertion").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.startswith(("put_", "admit_")):
                offenders.append(f"{path.name}:{name}")
    assert offenders == []


def test_a_refused_property_remains_real_admitted_evidence(tmp_path):
    """A canonical-assertion refusal is not an admission refusal. The
    Observation stays exactly what it was: real, retrievable evidence."""
    recorded, pool = _noaa_pool_and_execution(tmp_path)
    before_fingerprint = pool.fingerprint()

    assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert pool.fingerprint() == before_fingerprint, "a canonical-assertion pass changed the evidence pool"
    for o in pool.all_observations():
        assert pool.has_observation(o.id)
        assert pool.register.class_of(o.id) == MEASURED
        assert pool.register.admissible_for_canonical_assertion(o.id), (
            "class-level canonical admissibility (Phase 25) is a separate question from "
            "property-level context admissibility (this phase); the class check must still pass"
        )


def test_assertion_is_never_imported_by_an_existing_layer():
    """The one-directional composition this package exists to provide.
    `daf`, `science`, `boundary`, `bridge`, `epistemics` must never
    import it, or the layering becomes a cycle."""
    for package in CONTRACT["layering"]["forbidden_importers_of_assertion"]:
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" in path.as_posix():
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    assert name.split(".")[0] != "assertion", f"{path}: imports assertion"


# ------------------------------------------------------ 13. identity


def test_no_chemistry_identity_policy_is_invoked_or_invented(tmp_path):
    """§13. Neither exercised source is a chemical substance, and no
    identity-policy machinery exists in this repository to invoke."""
    assert not (REPO_ROOT / "verticals").exists()
    invariants = loads((REPO_ROOT / "architecture" / "invariants.yaml").read_text())
    by_id = {i["id"]: i for i in invariants["invariants"]}
    assert by_id["identity_policy_declared"]["status"] == "absent"
    assert by_id["no_point_identity_for_distributions"]["status"] == "absent"


# ------------------------------------------------------ 14. determinism


def test_repeated_real_acquisition_produces_identical_admissibility_verdicts(tmp_path):
    recorded, pool = _noaa_pool_and_execution(tmp_path, started_at="2026-08-25T00:00:00Z")
    first = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    second_recorded, _ = _noaa_pool_and_execution(tmp_path, started_at="2026-08-26T00:00:00Z")
    second = assess_pool(pool, second_recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert first.execution_id != second.execution_id, "two runs are two executions"
    assert first.candidates_examined == second.candidates_examined
    assert first.accepted == second.accepted
    assert first.refused == second.refused
    assert first.by_code == second.by_code
    assert first.rejection_rate == second.rejection_rate


def test_property_candidates_are_deterministically_ordered(tmp_path):
    _, pool = _graph_pool_and_execution(tmp_path, [ADMISSIBLE_RECORD, BARE_RECORD])
    first = property_candidates(pool, "exec-a")
    second = property_candidates(pool, "exec-a")
    assert first == second
    assert [c.observation_id for c in first] == sorted(c.observation_id for c in first)


# -------------------------------------------------- 16/17. accepted / rejected


def test_accepted_property_end_to_end(tmp_path):
    """§16's full checklist, on one real (acquisition-real, per the
    canonical contract's own note) property observation."""
    recorded, pool = _graph_pool_and_execution(tmp_path, [ADMISSIBLE_RECORD])
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    observation = pool.all_observations()[0]
    verdict = report.verdicts[0]
    assert verdict.candidate.observation_id == observation.id
    assert verdict.admissible
    assert verdict.quarantine_record_id is None
    assert pool.has_observation(observation.id)
    assert pool.register.class_of(observation.id) == ASSERTED
    assert pool.register.admissible_for_canonical_assertion(observation.id)
    assert observation.content["method"] == "ASTM_E8"
    assert observation.content["conditions"]["specimen"] == "dogbone-A"


def test_rejected_property_end_to_end_is_a_natural_source_failure(tmp_path):
    """§17, preferring a naturally occurring source failure over a
    synthesized one -- real recorded NOAA bytes, unmodified extractor."""
    recorded, pool = _noaa_pool_and_execution(tmp_path)
    quarantine = canonical_assertion_quarantine_store(tmp_path)
    report = assess_pool(pool, recorded.execution.id, quarantine)

    assert report.refused == 240
    observation = pool.all_observations()[0]
    assert pool.has_observation(observation.id), "the rejected property remains real evidence"
    linked = quarantine.for_execution(recorded.execution.id)
    assert len(linked) == 240
    assert any(
        v.candidate.observation_id == observation.id and v.quarantine_record_id is not None
        for v in report.verdicts
    )
