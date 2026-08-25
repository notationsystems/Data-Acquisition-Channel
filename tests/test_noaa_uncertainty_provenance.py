"""NOAA `sigma`, wired against the real uncertainty gate -- and NOAA
remains correctly rejected, for reasons this phase deliberately left
untouched.

    real NOAA acquisition (adapter -> extractor -> run_scout -> pool)
        |
        v  Observation.content now carries uncertainty/uncertainty_kind
           whenever the source reports `s`
    science.admissibility.quantity_is_typed   (UNCHANGED)
        |
    MISSING_UNCERTAINTY_KIND:  resolved (sigma is a source-stated standard
                                deviation, not an inference from its name)
    MISSING_CONDITIONS:  still refused -- untouched, Phase 29's finding
    MISSING_METHOD:      still refused -- untouched, Phase 29's finding

This is Phase 32's central result: correctly resolving uncertainty does
not, by itself, make a source admissible, and must not be allowed to
look like it solved conditions or method too. Neither gate was weakened,
and sigma was not fabricated into a kind the source does not establish.
"""

from __future__ import annotations

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
from daf.extractors.noaa_water_level_measurements import (
    SIGMA_UNCERTAINTY_KIND,
    NoaaWaterLevelMeasurementExtractor,
)
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics._yaml import loads
from epistemics.evidence_class import MEASURED
from science.admissibility import ABSENT, no_context_free_property, quantity_is_typed

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DETERMINATIONS = loads(
    (REPO_ROOT / "architecture" / "uncertainty_provenance_reachability.yaml").read_text()
)["determinations"]
NOAA = DETERMINATIONS["noaa_water_level_sigma"]

RUNTIME = RuntimeIdentity(python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1)
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
NOAA_PARAMETERS = {
    "station": "8454000",
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}


def _acquire_noaa(root, payload=MLLW_BYTES, *, started_at="2026-08-25T00:00:00Z"):
    """The real, unmodified NOAA acquisition path: adapter -> extractor
    -> run_scout -> ClassifiedPool, wrapped with execution recording."""
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
        noaa_water_level_measurement_binding(datum="MLLW", units="metric", fetch_bytes=lambda url: payload)
    )
    pool = ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="source_policy:phase32", by_source_kind={"tide-station-window": MEASURED}),
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


# ------------------------------------------------ 1. sigma source semantics


def test_sigma_is_present_on_every_real_recorded_reading():
    """Measured against the real fixture, not assumed -- the actual
    presence pattern that determines whether uncertainty resolves for
    every reading or only some."""
    payload = json.loads(MLLW_BYTES)
    rows = payload["data"]
    assert len(rows) == 240
    assert all("s" in row and row["s"] not in (None, "") for row in rows)


def test_sigma_semantics_are_not_inferred_from_the_field_name():
    """§2/§3: the classification is grounded in the extractor's own
    documented, real-response reconnaissance, not in the string 'sigma'
    looking statistical."""
    source = (REPO_ROOT / "daf" / "extractors" / "noaa_water_level_measurements.py").read_text()
    assert "standard deviation of" in source
    assert "1-second" in source
    assert NOAA["source_semantics"].startswith("CO-OPS 6-minute water-level products")


# ---------------------------------------- 2. uncertainty-kind mapping is correct


def test_uncertainty_kind_is_stated_not_estimated_propagated_or_absent(tmp_path):
    _, pool = _acquire_noaa(tmp_path)
    for o in pool.all_observations():
        assert o.content["uncertainty_kind"] == "stated" == SIGMA_UNCERTAINTY_KIND


def test_absent_was_considered_and_rejected_for_this_source_too():
    """Phase 30/31's distinction, applied here: a source that DOES report
    a number is the opposite case from one that explicitly declares no
    error. `absent` would misstate what `s` says."""
    assert ABSENT not in NOAA["uncertainty_kind_decision"].split()
    assert "opposite of what s says" in NOAA["uncertainty_kind_decision"]


def test_no_fabricated_uncertainty_kind_appears_anywhere_in_the_extractor():
    """§6/§16: none of the plausible-but-unearned alternatives were
    written into the extractor even as a rejected option in code."""
    source = (REPO_ROOT / "daf" / "extractors" / "noaa_water_level_measurements.py").read_text()
    for forbidden in ('"estimated"', '"propagated"', 'uncertainty_kind = "absent"'):
        assert forbidden not in source


# ------------------------------------------------- 3. uncertainty value


def test_uncertainty_value_is_sigma_unmodified(tmp_path):
    _, pool = _acquire_noaa(tmp_path)
    for o in pool.all_observations():
        assert o.content["uncertainty"] == o.content["sigma"]
        assert isinstance(o.content["uncertainty"], float)


def test_uncertainty_unit_matches_the_value_unit_by_statistical_definition():
    """A standard deviation is expressed in the measured quantity's own
    unit -- not a convention invented here, and not a separate field the
    existing contract requires or that this phase added."""
    assert "standard deviation of a quantity is expressed in that quantity" in NOAA["value_decision"]
    source = (REPO_ROOT / "daf" / "extractors" / "noaa_water_level_measurements.py").read_text()
    assert '"uncertainty_unit"' not in source


# --------------------------------------------- 4. missing uncertainty rejected


def test_a_reading_lacking_sigma_remains_genuinely_missing_uncertainty():
    raw = json.dumps(
        {
            "metadata": {"id": "8454000"},
            "data": [{"t": "2024-01-15 00:00", "v": "0.136"}],
        }
    )
    content = NoaaWaterLevelMeasurementExtractor(datum="MLLW", units="metric").extract(
        __import__("evidence.types", fromlist=["make_record"]).make_record(
            document_id="d", locator="l", raw_content=raw
        )
    )[0].content

    assert "uncertainty" not in content
    assert "uncertainty_kind" not in content
    verdict = quantity_is_typed(content)
    assert "MISSING_UNCERTAINTY_KIND" in verdict.reasons


# -------------------------------------------- 5/6. conditions/method independent


def test_conditions_remain_independently_rejected(tmp_path):
    _, pool = _acquire_noaa(tmp_path)
    for o in pool.all_observations():
        assert "conditions" not in o.content
        verdict = no_context_free_property(o.content)
        assert "MISSING_CONDITIONS" in verdict.reasons


def test_method_remains_independently_rejected(tmp_path):
    _, pool = _acquire_noaa(tmp_path)
    for o in pool.all_observations():
        assert "method" not in o.content
        verdict = no_context_free_property(o.content)
        assert "MISSING_METHOD" in verdict.reasons


def test_uncertainty_resolution_did_not_silently_resolve_the_other_two(tmp_path):
    """§7's exact distinction, checked in one place: resolved + two
    unresolved, never conflated with fully resolved or fully unresolved."""
    _, pool = _acquire_noaa(tmp_path)
    verdict = no_context_free_property(pool.all_observations()[0].content)

    assert not verdict.admissible
    assert set(verdict.reasons) == {"MISSING_CONDITIONS", "MISSING_METHOD"}
    assert "MISSING_UNCERTAINTY_KIND" not in verdict.reasons
    assert "MISSING_UNIT" not in verdict.reasons
    assert "MISSING_PROPERTY" not in verdict.reasons
    assert "MISSING_VALUE" not in verdict.reasons


# --------------------------------------------------- 7/8. real acquisition


def test_real_acquisition_examines_every_reading_as_a_property_candidate(tmp_path):
    recorded, pool = _acquire_noaa(tmp_path)
    assert recorded.result.outcome.value == "acquired"

    candidates = property_candidates(pool, recorded.execution.id)
    assert len(candidates) == 240


def test_the_real_acquisition_result_matches_the_canonical_determination(tmp_path):
    recorded, pool = _acquire_noaa(tmp_path)
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    measured = NOAA["real_acquisition_result"]
    assert report.candidates_examined == measured["candidates_examined"]
    assert report.accepted == measured["accepted"]
    assert report.refused == measured["refused"]
    assert set(report.by_code) == set(measured["reasons"])


# ------------------------------------------------- 9. evidence pool gating


def test_no_reading_is_admitted_to_canonical_assertion(tmp_path):
    recorded, pool = _acquire_noaa(tmp_path)
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))
    assert report.accepted == 0
    assert all(not v.admissible for v in report.verdicts)


def test_a_rejected_reading_remains_real_admitted_evidence(tmp_path):
    recorded, pool = _acquire_noaa(tmp_path)
    before = pool.fingerprint()

    assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert pool.fingerprint() == before, "a canonical-assertion pass changed the evidence pool"
    for o in pool.all_observations():
        assert pool.has_observation(o.id)
        assert pool.register.class_of(o.id) == MEASURED


# ------------------------------------------------------- 10. quarantine


def test_rejected_readings_are_quarantined_with_full_linkage(tmp_path):
    recorded, pool = _acquire_noaa(tmp_path)
    quarantine = canonical_assertion_quarantine_store(tmp_path)
    report = assess_pool(pool, recorded.execution.id, quarantine)

    stored = quarantine.for_execution(recorded.execution.id)
    assert len(stored) == report.refused == 240
    for record in stored:
        assert record.execution_id == recorded.execution.id
        assert record.stage == CANONICAL_ASSERTION_STAGE
        assert {e.code for e in record.errors} <= {"MISSING_CONDITIONS", "MISSING_METHOD"}

    scout_quarantine = QuarantineStore(tmp_path)
    assert scout_quarantine.for_execution(recorded.execution.id) == ()
    assert recorded.execution.admission_failure_count == 0


def test_the_quarantine_records_are_tamper_evident(tmp_path):
    recorded, pool = _acquire_noaa(tmp_path)
    quarantine = canonical_assertion_quarantine_store(tmp_path)
    assess_pool(pool, recorded.execution.id, quarantine)

    stored = quarantine.for_execution(recorded.execution.id)[0]
    payload = quarantine_record_to_dict(stored)
    path = quarantine.root / f"{stored.id}.json"
    path.write_text(json.dumps(dict(payload, stage="tampered")))

    with pytest.raises(QuarantineIdentityMismatch):
        canonical_assertion_quarantine_store(tmp_path).all_records()


# ------------------------------------------------------ 11. identity


def test_observation_identity_changed_and_is_disclosed(tmp_path):
    """§10: the content-addressed identity DID change for every reading
    that carries sigma. Verified directly -- the SAME record_ids a real
    acquisition produced, re-hashed with the pre-Phase-32 content shape
    (uncertainty/uncertainty_kind stripped), yield a DIFFERENT
    observation id, isolating the change to content alone."""
    from evidence.types import make_observation

    _, pool = _acquire_noaa(tmp_path)
    new_observation = pool.all_observations()[0]

    old_shape_content = {
        key: value
        for key, value in new_observation.content.items()
        if key not in ("uncertainty", "uncertainty_kind")
    }
    assert set(old_shape_content) == {
        "property", "value", "unit", "datum", "station_id", "measurement_time", "sigma"
    }

    old_shape_observation = make_observation(
        record_ids=new_observation.record_ids,
        extraction_method=new_observation.extraction_method,
        content=old_shape_content,
        confidence=new_observation.confidence,
        extracted_at=new_observation.extracted_at,
    )

    assert new_observation.id != old_shape_observation.id, (
        "content genuinely changed and the identity change must be real, not concealed"
    )
    assert new_observation.record_ids == old_shape_observation.record_ids, (
        "the underlying record -- what was actually fetched -- did not change"
    )


def test_artifact_identity_is_unaffected_by_the_content_addition(tmp_path):
    first, _ = _acquire_noaa(tmp_path / "a", started_at="2026-08-25T00:00:00Z")
    second, _ = _acquire_noaa(tmp_path / "b", started_at="2026-08-26T00:00:00Z")

    assert first.execution.artifact_ids == second.execution.artifact_ids
    assert first.execution.id != second.execution.id


def test_the_incomparable_finding_is_unaffected_by_the_content_addition(tmp_path):
    """§11's evidence-boundary spirit, extended: the Phase 17 finding
    this extractor's own docstring names must survive this addition. The
    canonical determination's own claim, checked against the real,
    changed extractor rather than merely trusted."""
    assert "INCOMPARABLE" in NOAA["identity_impact"] or "singleton" in NOAA["identity_impact"]
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(REPO_ROOT / "tests" / "test_live_scientific_observation.py::test_real_measurements_are_correctly_reported_as_not_repeated_measurements"),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ------------------------------------------ 12. USGS unchanged (cross-source)


def test_usgs_phase_31_behavior_is_unchanged_by_the_noaa_extension(tmp_path):
    """§9: neither domain's semantics leaked into the other."""
    from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
    from daf.execution.recorded import execute_plan_recorded as execute_plan_recorded_usgs
    from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor
    from daf.orchestration.adapter_registry import AdapterBinding

    fixtures = Path(__file__).resolve().parent / "fixtures"
    routes = {
        "eventid=synth00000001": (fixtures / "usgs_event_detail_synth00000001.json").read_bytes(),
        "eventid=synth00000002": (fixtures / "usgs_event_detail_synth00000002.json").read_bytes(),
        "eventid=synth00000003": (fixtures / "usgs_event_detail_synth00000003.json").read_bytes(),
        "starttime=": (fixtures / "usgs_listing_synthetic.json").read_bytes(),
    }

    def router(url):
        for marker, content in routes.items():
            if marker in url:
                return content
        raise AssertionError(url)

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
            fetch_bytes=router,
        )

    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(adapter_id="usgs-earthquakes", build_adapter=build_adapter, build_extractor=UsgsEarthquakeExtractor)
    )
    pool = ClassifiedPool(
        FilesystemEvidenceStore(tmp_path / "evidence"),
        SourceClassPolicy(id="p", by_source_kind={"event-detail": MEASURED}),
    )
    recorded = execute_plan_recorded_usgs(
        AcquisitionPlan(
            plan_id="usgs-plan",
            source_id="usgs-quakes",
            parameters={"start_time": "2026-01-01", "end_time": "2026-01-02", "min_magnitude": 1.0},
        ),
        sources,
        adapters,
        pool,
        CheckpointStore(tmp_path / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
        executions=ExecutionRecordStore(tmp_path),
        quarantine=QuarantineStore(tmp_path),
        runtime=RUNTIME,
    )
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))
    assert report.candidates_examined == 3
    assert report.accepted == 0
    assert set(report.by_code) == {"MISSING_CONDITIONS", "MISSING_UNCERTAINTY_KIND"}


# ------------------------------------------------------------- 13. no bypass


def test_no_evidence_pool_bypass_exists():
    import ast

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


# --------------------------------------------------------- 14. rejection metrics


def test_phase_27_28_metrics_are_unaffected_by_the_uncertainty_extension(tmp_path):
    recorded, _ = _acquire_noaa(tmp_path)
    metrics = rejection_metrics(recorded.execution, QuarantineStore(tmp_path))

    assert metrics.accepted == 240
    assert metrics.terminal_refusals == 0
    assert metrics.attempts == 240
    assert metrics.rejection_rate == 0.0
    assert metrics.by_code == ()


def test_repeated_real_acquisition_produces_identical_admissibility_verdicts(tmp_path):
    first_recorded, first_pool = _acquire_noaa(tmp_path, started_at="2026-08-25T00:00:00Z")
    first = assess_pool(first_pool, first_recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    second_recorded, _ = _acquire_noaa(tmp_path, started_at="2026-08-26T00:00:00Z")
    second = assess_pool(
        first_pool, second_recorded.execution.id, canonical_assertion_quarantine_store(tmp_path)
    )

    assert first.by_code == second.by_code
    assert first.rejection_rate == second.rejection_rate
    assert first_recorded.execution.id != second_recorded.execution.id
