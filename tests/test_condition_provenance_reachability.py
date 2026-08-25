"""Whether any DAF-reachable source provides a genuine measurement
condition -- and, separately, whether the existing shared representation
could carry one if found.

Two independent findings, neither a clean accept AT THE TIME THIS PHASE
RAN:

    USGS earthquakes    no genuine condition exists in the real,
                        acquired source data at all. Still true; no
                        later phase touched this.

    NOAA water level    a genuine condition (datum) DOES exist, but
                        wiring it through the existing conditions
                        representation (a Mapping-valued content key)
                        breaks materials.analysis's real, vendored,
                        already-tested comparison-context mechanism,
                        which requires every content value to be
                        hashable.

RESOLVED IN PHASE 34, for NOAA alone: `daf.storage.frozen_mapping.
FrozenMapping` is a Mapping-valued, natively hashable, JSON-round-trip-
stable representation, and NOAA's `conditions` now uses it. USGS is
unaffected -- it has no genuine condition to carry, representation or
not. See tests/test_hashable_condition_representation.py and
architecture/condition_representation.yaml for that determination in
full; the tests below that assert MISSING_CONDITIONS/no-conditions-key
for NOAA were updated in place, with a note, rather than left to assert
something no longer true.

Nothing here fabricates a condition, and nothing here weakens either
gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from materials.analysis import MaterialQuestion, analyze
from retrieval.engine import DeterministicRetrievalEngine

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from assertion.property_admissibility import assess_pool, canonical_assertion_quarantine_store
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics._yaml import loads
from epistemics.evidence_class import MEASURED

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DETERMINATION = loads(
    (REPO_ROOT / "architecture" / "condition_provenance_reachability.yaml").read_text()
)
CANDIDATES = DETERMINATION["candidates"]
FINDINGS = DETERMINATION["findings"]

RUNTIME = RuntimeIdentity(python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1)
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
STND_BYTES = (FIXTURES / "noaa_live_8454000_20240115_stnd.json").read_bytes()
STATION = "8454000"
NOAA_PARAMETERS = {
    "station": STATION,
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}


def _candidate(source: str, field: str) -> dict:
    for entry in CANDIDATES:
        if entry["source"] == source and entry["field"] == field:
            return entry
    raise AssertionError(f"no candidate recorded for {source}/{field}")


def _acquire_noaa(root, payload, datum, *, pool=None, started_at="2026-08-25T00:00:00Z"):
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
        noaa_water_level_measurement_binding(datum=datum, units="metric", fetch_bytes=lambda url: payload)
    )
    pool = pool if pool is not None else ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="source_policy:phase33", by_source_kind={"tide-station-window": MEASURED}),
    )
    recorded = execute_plan_recorded(
        AcquisitionPlan(
            plan_id=f"noaa-plan-{datum}", source_id="noaa-cm", parameters=dict(NOAA_PARAMETERS)
        ),
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


# ------------------------------------------------------- 1. source sweep


def test_the_source_sweep_covers_every_shipped_extractor():
    """§2: every production extractor this repository ships, including
    the ones with no property/value pair at all, is accounted for --
    none silently skipped."""
    sources = set(DETERMINATION["sources_inspected"])
    assert sources == {
        "noaa_water_level_measurements",
        "usgs_earthquakes",
        "edgar_daily_index",
        "arxiv",
        "noaa_water_level_window",
        "local_dataset_generic",
    }
    for name in ("edgar_daily_index", "arxiv", "noaa_water_level_window"):
        assert name in DETERMINATION["not_property_shaped"]


def test_not_property_shaped_sources_have_no_property_key_measured_directly():
    """The exclusions are measured against real extractor output, not
    merely asserted in the canonical YAML."""
    from evidence.types import make_record

    from daf.extractors.arxiv import ArxivExtractor
    from daf.extractors.noaa_water_level import NoaaWaterLevelExtractor

    arxiv_content = ArxivExtractor().extract(
        make_record(
            document_id="d",
            locator="l",
            raw_content="<entry><id>http://arxiv.org/abs/1</id></entry>",
        )
    )[0].content
    assert "property" not in arxiv_content

    window_raw = json.dumps(
        {
            "metadata": {"id": STATION, "name": "n"},
            "data": [{"t": "2024-01-15 00:00", "v": "0.1", "f": "0,0,0,0", "q": "v"}],
        }
    )
    window_content = NoaaWaterLevelExtractor().extract(
        make_record(document_id="d", locator="l", raw_content=window_raw)
    )[0].content
    assert "property" not in window_content


# ------------------------------------------------ 2/3/4. classification


def test_every_usgs_candidate_is_reconsidered_and_none_is_promoted():
    """§7: explicit reconsideration of every previously-classified USGS
    field, none reversed without new evidence."""
    for field in ("place", "origin_time", "depth_km", "status", "magnitude_type"):
        entry = _candidate("usgs_earthquakes", field)
        assert entry["classification"] != "measurement_condition"


def test_depth_km_reconsideration_is_explicit_and_evidence_based():
    """The one USGS field most plausibly promotable on general
    geophysics grounds -- explicitly reconsidered and explicitly not
    promoted for lack of source-specific evidence, per §5/§7."""
    entry = _candidate("usgs_earthquakes", "depth_km")
    assert entry["classification"] == "identity_metadata"
    assert "reconsidered" in entry["evidence"]


def test_network_field_is_absent_from_every_real_usgs_fixture():
    """A candidate that would plausibly be a genuine condition if
    present -- confirmed absent, not merely assumed absent."""
    for path in sorted(FIXTURES.glob("usgs_*.json")):
        payload = json.loads(path.read_text()) if path.read_text().strip() else {}
        text = json.dumps(payload)
        for forbidden in ("magSource", '"net"', '"nst"', '"gap"', '"dmin"', '"rms"'):
            assert forbidden not in text, f"{path.name} unexpectedly carries {forbidden}"


def test_noaa_station_id_and_measurement_time_remain_identity_not_condition():
    for field in ("station_id", "measurement_time"):
        entry = _candidate("noaa_water_level_measurements", field)
        assert entry["classification"] == "identity_metadata"


def test_noaa_datum_is_classified_a_genuine_measurement_condition():
    """The positive semantic finding, evidenced three ways: the real
    fixture pair, this repository's own pre-existing test comment, and
    the gate's own definition of what a condition is."""
    entry = _candidate("noaa_water_level_measurements", "datum")
    assert entry["classification"] == "measurement_condition"

    mllw = json.loads(MLLW_BYTES)["data"][0]
    stnd = json.loads(STND_BYTES)["data"][0]
    assert mllw["t"] == stnd["t"], "same instant"
    assert float(mllw["v"]) != float(stnd["v"]), "different number under a different datum"

    existing_test_source = (REPO_ROOT / "tests" / "test_live_scientific_observation.py").read_text()
    assert "datum` is a genuine scientific conditioning variable in its own right" in existing_test_source


# ------------------------------------------------- 5/6. re-examination


def test_usgs_finding_is_a_clean_negative():
    assert FINDINGS["usgs_earthquakes"]["verdict"] == "no_genuine_condition_found"
    assert FINDINGS["usgs_earthquakes"]["action_taken"] == "none"


def test_noaa_finding_is_a_representation_gap_not_a_negative_or_a_fix():
    """The precise, three-way result this phase actually reached --
    neither 'accepted', nor 'no condition exists', but 'exists and
    blocked'."""
    finding = FINDINGS["noaa_water_level_measurements"]
    assert finding["verdict"] == "representation_gap"
    assert finding["action_taken"] == "none"
    assert "reverted" in finding["reversibility"]


# --------------------------------- 9. conditions contract, measured --


def test_the_conditions_contract_requires_an_inherently_unhashable_type():
    """§9: read directly from the real gate source, not inferred."""
    import inspect

    from science.admissibility import no_context_free_property as gate

    source = inspect.getsource(gate)
    assert "isinstance(conditions, Mapping)" in source


def test_wiring_a_mapping_condition_into_noaa_breaks_real_materials_analysis(tmp_path):
    """The measurement that decided this phase's outcome, reproduced
    directly through the real acquisition pipeline rather than only
    described in prose. A thin extractor subclass adds EXACTLY the one
    key the rejected wiring would have added -- everything else (the
    real adapter, real run_scout admission, real entity/relationship
    creation) is the genuine pipeline, so the resulting pool has the
    same graph connectivity a real acquisition would."""
    from dataclasses import dataclass, replace

    from daf.extractors.noaa_water_level_measurements import NoaaWaterLevelMeasurementExtractor
    from daf.orchestration.adapter_registry import AdapterBinding

    @dataclass(frozen=True)
    class _ConditionsPoisonedExtractor(NoaaWaterLevelMeasurementExtractor):
        def extract(self, record):
            return tuple(
                replace(candidate, content={**candidate.content, "conditions": {"datum": self.datum}})
                for candidate in super().extract(record)
            )

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
    base = noaa_water_level_measurement_binding(datum="MLLW", units="metric", fetch_bytes=lambda url: MLLW_BYTES)
    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(
            adapter_id="noaa-water-level-measurements",
            build_adapter=base.build_adapter,
            build_extractor=lambda: _ConditionsPoisonedExtractor(datum="MLLW", units="metric"),
        )
    )
    pool = ClassifiedPool(
        FilesystemEvidenceStore(tmp_path / "evidence"),
        SourceClassPolicy(id="source_policy:phase33", by_source_kind={"tide-station-window": MEASURED}),
    )
    recorded = execute_plan_recorded(
        AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-cm", parameters=dict(NOAA_PARAMETERS)),
        sources,
        adapters,
        pool,
        CheckpointStore(tmp_path / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
        executions=ExecutionRecordStore(tmp_path),
        quarantine=QuarantineStore(tmp_path),
        runtime=RUNTIME,
    )
    assert recorded.result.outcome.value == "acquired"
    assert "conditions" in pool.all_observations()[0].content

    with pytest.raises(TypeError, match="unhashable"):
        analyze(
            pool,
            DeterministicRetrievalEngine(),
            MaterialQuestion(material_natural_key=STATION, property="water_level"),
        )


def test_the_incompatibility_is_general_not_noaa_specific(tmp_path):
    """§9/§11: confirms the gap would block ANY future graph-reachable
    source, not only NOAA -- checked against a synthetic content shape
    unrelated to any real extractor."""
    synthetic = {"property": "p", "value": 1.0, "conditions": {"x": "y"}}
    context = {k: v for k, v in synthetic.items() if k not in ("property", "value")}
    with pytest.raises(TypeError, match="unhashable"):
        hash(tuple(sorted(context.items())))


# ------------------------------------------- no fabricated condition path


def test_no_extractor_declares_a_conditions_key():
    """§20: no source-specific condition schema, no fabricated condition,
    anywhere in the shipped extractors.

    CORRECTED IN PHASE 34: NOAA is now the one exception, and it is
    exactly that -- an exception, not a reopening of §20. Phase 33 found
    `datum` a genuine measurement condition; Phase 34 found a
    representation that could carry it (`daf.storage.frozen_mapping.
    FrozenMapping`, a generic, shared, non-NOAA-specific type) without
    breaking materials.analysis. Every OTHER extractor still declares
    none, and NOAA's own declaration uses the shared representation, not
    a bespoke `NOAAConditions`-shaped schema."""
    noaa_path = REPO_ROOT / "daf" / "extractors" / "noaa_water_level_measurements.py"
    for path in sorted((REPO_ROOT / "daf" / "extractors").glob("*.py")):
        if path == noaa_path:
            continue
        assert '"conditions"' not in path.read_text(), f"{path.name} declares conditions"
    noaa_source = noaa_path.read_text()
    assert '"conditions"' in noaa_source
    assert "FrozenMapping" in noaa_source, "NOAA's conditions must use the shared representation"
    assert "NOAAConditions" not in noaa_source, "no source-specific condition schema was created"


def test_the_noaa_extractor_was_left_exactly_as_phase_32_produced_it():
    """The Phase 33 attempted wiring left no trace: at that time, the
    extractor's content shape was exactly Phase 32's, no more, no fewer
    keys.

    CORRECTED IN PHASE 34: this is no longer the live extractor's shape
    -- Phase 34 legitimately added `conditions` (a hashable, immutable
    `FrozenMapping`, not the plain dict Phase 33 reverted). This test now
    locks the Phase 34 shape; see
    tests/test_hashable_condition_representation.py for the
    determination that justifies the addition."""
    from evidence.types import make_record

    from daf.extractors.noaa_water_level_measurements import NoaaWaterLevelMeasurementExtractor
    from daf.storage.frozen_mapping import FrozenMapping

    content = NoaaWaterLevelMeasurementExtractor(datum="MLLW", units="metric").extract(
        make_record(document_id="d", locator="l", raw_content=MLLW_BYTES.decode())
    )[0].content
    assert set(content) == {
        "property", "value", "unit", "datum", "station_id", "measurement_time",
        "sigma", "uncertainty", "uncertainty_kind", "conditions",
    }
    assert isinstance(content["conditions"], FrozenMapping)
    assert dict(content["conditions"]) == {"datum": "MLLW"}


# ---------------------------------------- real acquisition, unchanged --


def test_real_noaa_acquisition_is_unchanged_from_phase_32(tmp_path):
    """CORRECTED IN PHASE 34: MISSING_CONDITIONS no longer appears --
    resolved by this phase's representation change, not by any new
    source semantics. MISSING_METHOD, the dimension no phase has
    resolved, is unchanged."""
    recorded, pool = _acquire_noaa(tmp_path, MLLW_BYTES, "MLLW")
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert report.candidates_examined == 240
    assert report.accepted == 0
    assert report.refused == 240
    assert report.by_code == {"MISSING_METHOD": 240}


def test_real_usgs_acquisition_is_unchanged_from_phase_31(tmp_path):
    from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
    from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor
    from daf.orchestration.adapter_registry import AdapterBinding

    routes = {
        "eventid=synth00000001": (FIXTURES / "usgs_event_detail_synth00000001.json").read_bytes(),
        "eventid=synth00000002": (FIXTURES / "usgs_event_detail_synth00000002.json").read_bytes(),
        "eventid=synth00000003": (FIXTURES / "usgs_event_detail_synth00000003.json").read_bytes(),
        "starttime=": (FIXTURES / "usgs_listing_synthetic.json").read_bytes(),
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
    recorded = execute_plan_recorded(
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


def test_the_incomparable_finding_is_still_intact(tmp_path):
    """The Phase 17 finding this entire investigation was careful never
    to touch, re-verified once more against real acquisition."""
    pool = ClassifiedPool(
        FilesystemEvidenceStore(tmp_path / "evidence"),
        SourceClassPolicy(id="p", by_source_kind={"tide-station-window": MEASURED}),
    )
    _acquire_noaa(tmp_path, MLLW_BYTES, "MLLW", pool=pool)
    _acquire_noaa(tmp_path, STND_BYTES, "STND", pool=pool)

    answer = analyze(
        pool, DeterministicRetrievalEngine(),
        MaterialQuestion(material_natural_key=STATION, property="water_level"),
    )
    assert {dict(g.context)["datum"] for g in answer.observed_comparison_groups} == {"MLLW", "STND"}
