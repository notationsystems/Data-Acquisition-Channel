"""Phase Q: a REAL external scientific source carried through the
existing acquisition apparatus to the scientific-analysis boundary.

Source: NOAA CO-OPS Tides & Currents, station 8454000 (Providence, RI),
product `water_level`, 2024-01-15, datum MLLW, units metric. The
responses in `tests/fixtures/noaa_live_8454000_*.json` are VERBATIM
bytes recorded from the live public API during this phase (transcript in
docs/PHASE_17_LIVE_SCIENTIFIC_OBSERVATION.md). They are replayed here
through the adapter's own `fetch_bytes` injection point so the suite is
deterministic and offline, while every other stage -- URL construction,
windowing, admission, extraction, graph declaration, durable storage --
is the real, unmodified code path. This is the same discipline Phase I
and Phase M already established for NOAA.

WHAT THIS PHASE IS ANSWERING. "Can the DAF acquire real scientific
observations and deliver them through the existing SCOUT/evidence
architecture without corrupting their scientific semantics?" The answer
these tests support is yes for acquisition, admission, identity,
restart and the trust graph -- and, importantly, that the honest
scientific verdict at the analysis boundary is INCOMPARABLE, which is
CORRECT rather than a failure. See
`test_real_measurements_are_correctly_reported_as_not_repeated_measurements`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evidence.types import make_record
from materials.analysis import MaterialQuestion, analyze
from retrieval.engine import DeterministicRetrievalEngine

from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.extractors.noaa_water_level_measurements import (
    NoaaMeasurementExtractionError,
    NoaaWaterLevelMeasurementExtractor,
)
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
STND_BYTES = (FIXTURES / "noaa_live_8454000_20240115_stnd.json").read_bytes()
PRELIMINARY_BYTES = (FIXTURES / "noaa_live_8454000_preliminary.json").read_bytes()

STATION = "8454000"
PARAMETERS = {
    "station": STATION, "product": "water_level",
    "start_date": "20240115", "end_date": "20240115",
}
# Phase R added datum/units to the NOAA locator so two scientifically
# different quantities no longer collapse onto one artifact identity.
WINDOW_LOCATOR = f"{STATION}:water_level:MLLW:metric:20240115:20240115"
ENGINE = DeterministicRetrievalEngine()


def _sources(source_id="noaa-cm"):
    registry = SourceRegistry()
    registry.register(SourceDefinition(
        source_id=source_id, name="NOAA CO-OPS Tides & Currents",
        domain="environmental-observations", adapter_id="noaa-water-level-measurements",
        required_parameters=("station", "product", "start_date", "end_date"),
        capabilities=("incremental",),
    ))
    return registry


def _adapters(payload=MLLW_BYTES, datum="MLLW", units="metric"):
    registry = AdapterRegistry()
    registry.register(noaa_water_level_measurement_binding(
        datum=datum, units=units, fetch_bytes=lambda url: payload,
    ))
    return registry


def _acquire(root, payload=MLLW_BYTES, datum="MLLW", units="metric", source_id="noaa-cm", pool=None):
    """The real acquisition path end to end, replaying recorded real bytes."""
    pool = pool if pool is not None else DurablePool(FilesystemEvidenceStore(root / "evidence"))
    plan = AcquisitionPlan(plan_id="noaa-cm-plan", source_id=source_id, parameters=dict(PARAMETERS))
    result = execute_plan(
        plan, _sources(source_id), _adapters(payload, datum, units), pool,
        CheckpointStore(root / "checkpoints"), requested_at="2026-08-25T00:00:00Z",
    )
    return pool, result


def _extract(payload=MLLW_BYTES, datum="MLLW", units="metric"):
    record = make_record(document_id="doc-1", locator=WINDOW_LOCATOR, raw_content=payload.decode())
    return NoaaWaterLevelMeasurementExtractor(datum=datum, units=units).extract(record)


def test_real_measurements_are_admitted_with_the_declared_trust_graph(tmp_path):
    """Adapter + extractor + admission, against real recorded bytes."""
    pool, result = _acquire(tmp_path)
    assert result.outcome.value == "acquired"

    observations = pool.all_observations()
    assert len(observations) == 240, "one Observation per real 6-minute reading in the window"

    # the graph the source itself establishes -- station and vertical datum
    assert {(r.natural_key, r.kind) for r in pool.all_referents()} == {
        (STATION, "monitoring_station"), ("MLLW", "vertical_datum"),
    }
    relationships = pool.all_claimed_relationships()
    assert len(relationships) == 240 and {r.type for r in relationships} == {"referenced_to"}
    assert {r.observation_id for r in relationships} == {o.id for o in observations}, (
        "every relationship carries the reading it concerns, which is what makes it reachable"
    )

    # real values, real units, one durably stored window artifact
    values = sorted(o.content["value"] for o in observations)
    assert values[0] == -0.204 and values[-1] == 1.711, "the real tidal range in this window"
    assert {o.content["unit"] for o in observations} == {"m"}
    assert {a.locator for a in result.artifacts} == {WINDOW_LOCATOR}


def test_observation_content_carries_only_scientific_fields(tmp_path):
    """Section 3's classification, enforced: acquisition metadata,
    revision metadata and source identity are all kept out of content."""
    pool, _ = _acquire(tmp_path)
    observation = pool.all_observations()[0]

    assert set(observation.content) == {
        "property", "value", "unit", "datum", "station_id", "measurement_time", "sigma"
    }
    for excluded in ("q", "f", "s", "t", "v", "name", "lat", "lon", "product", "time_zone"):
        assert excluded not in observation.content

    assert observation.content["property"] == "water_level"
    assert observation.content["datum"] == "MLLW"
    assert isinstance(observation.content["value"], float), (
        "NOAA returns numeric strings; materials.analysis._as_float ASSERTS a numeric type"
    )
    assert observation.extraction_method == "json:noaa_water_level_measurement_v1"


def test_quality_flag_is_revision_metadata_and_never_comparison_context():
    """The `q` flag is excluded from content deliberately. NOAA revises
    preliminary readings into verified ones for the SAME timestamp; were
    `q` part of content, a reading and its own later correction would sit
    in different comparison contexts and could never be seen to disagree.

    Both fixtures are real: the 2024 window is entirely verified, the
    recent window entirely preliminary."""
    assert {r["q"] for r in json.loads(MLLW_BYTES)["data"]} == {"v"}
    assert {r["q"] for r in json.loads(PRELIMINARY_BYTES)["data"]} == {"p"}

    for payload in (MLLW_BYTES, PRELIMINARY_BYTES):
        assert all("q" not in c.content for c in _extract(payload))

    # a preliminary and a verified reading of the same quantity differ only
    # in value, so they share one comparison context and genuinely conflict
    verified = _extract(MLLW_BYTES)[0].content
    preliminary = _extract(PRELIMINARY_BYTES)[0].content
    assert set(verified) == set(preliminary)


def test_real_measurements_are_correctly_reported_as_not_repeated_measurements(tmp_path):
    """Section 9's boundary, and the central scientific finding.

    `materials.analysis` consumes the real acquired evidence without
    complaint. Its verdict is that each reading sits in its OWN
    comparison context -- because `measurement_time` is a genuine
    scientific conditioning variable, so a level at 00:00 and one at
    00:06 are measurements of DIFFERENT quantities. INCOMPARABLE is
    therefore the correct answer for a tide-gauge series, not a defect.

    Contrast Phase 16, where a unique-per-record field splitting the
    context WAS a defect -- because there the field was an acquisition
    locator, not a scientific variable. Same mechanics, opposite verdict;
    the classification is what decides it."""
    pool, _ = _acquire(tmp_path)

    answer = analyze(pool, ENGINE, MaterialQuestion(material_natural_key=STATION, property="water_level"))
    assert len(answer.observed) == 240, "all real readings reached the analysis layer"
    assert len(answer.observed_comparison_groups) == 240, "one context per distinct measurement time"
    assert all(len(g.values) == 1 for g in answer.observed_comparison_groups)
    assert answer.observed_disagreement is None, (
        "no disagreement is claimed, because no two readings measure the same quantity"
    )

    context = dict(answer.observed_comparison_groups[0].context)
    assert context["datum"] == "MLLW" and context["station_id"] == STATION
    assert "measurement_time" in context and "value" not in context


def test_identity_is_deterministic_and_reacquisition_is_recognised_as_duplicate(tmp_path):
    """Section 10: the source window is immutable once verified, so
    re-acquiring it must yield the SAME identities, not new evidence."""
    pool, first = _acquire(tmp_path / "a")
    first_ids = sorted(o.id for o in pool.all_observations())

    # same bytes, same pool -> recognised as already held
    _, again = _acquire(tmp_path / "a", pool=pool)
    assert again.outcome.value == "duplicate"
    assert sorted(o.id for o in pool.all_observations()) == first_ids, "no duplicate evidence admitted"

    # same bytes, an entirely independent pool -> identical content-addressed ids
    other_pool, _ = _acquire(tmp_path / "b")
    assert sorted(o.id for o in other_pool.all_observations()) == first_ids
    assert {a.version_id for a in first.artifacts} == {a.version_id for a in again.artifacts}


def test_restart_preserves_artifact_version_and_scientific_semantics(tmp_path):
    """Section 8. Process 1 acquires and persists; process 2 opens a
    fresh DurablePool over the same on-disk store and must recover the
    same artifact version, the same observation identities and the same
    analysis result."""
    root = tmp_path / "station"
    pool_1, result_1 = _acquire(root)
    version_ids = {a.version_id for a in result_1.artifacts}
    observation_ids = sorted(o.id for o in pool_1.all_observations())
    answer_1 = analyze(pool_1, ENGINE, MaterialQuestion(material_natural_key=STATION, property="water_level"))
    del pool_1

    # --- restart: nothing in memory, only what is on disk -----------------
    pool_2 = DurablePool(FilesystemEvidenceStore(root / "evidence"))
    assert sorted(o.id for o in pool_2.all_observations()) == observation_ids
    assert {r.natural_key for r in pool_2.all_referents()} == {STATION, "MLLW"}

    for version_id in version_ids:
        assert pool_2.has_document(version_id), "the raw acquired artifact survives the restart"

    answer_2 = analyze(pool_2, ENGINE, MaterialQuestion(material_natural_key=STATION, property="water_level"))
    assert len(answer_2.observed) == len(answer_1.observed)
    assert [o.id for o in answer_2.observed] == [o.id for o in answer_1.observed]
    assert len(answer_2.observed_comparison_groups) == len(answer_1.observed_comparison_groups)


def test_the_same_window_under_a_different_datum_is_a_different_artifact(tmp_path):
    """The real-data facts Phase 17 measured, now asserting the Phase R
    fix. MLLW and STND are different vertical datums: NOAA reports
    0.136 m and 1.2 m for the SAME instant at the SAME station. Phase 17
    found both collapsing onto one artifact identity, because the locator
    omitted the datum; Phase R added datum/units to it.

    Full identity analysis lives in tests/test_noaa_artifact_identity.py;
    this keeps the original real-data observation that motivated it."""
    mllw_first = json.loads(MLLW_BYTES)["data"][0]
    stnd_first = json.loads(STND_BYTES)["data"][0]
    assert mllw_first["t"] == stnd_first["t"]
    assert float(mllw_first["v"]) == 0.136 and float(stnd_first["v"]) == 1.2

    pool, mllw_result = _acquire(tmp_path / "separated", MLLW_BYTES, datum="MLLW")
    _, stnd_result = _acquire(tmp_path / "separated", STND_BYTES, datum="STND", pool=pool)
    assert {a.locator for a in mllw_result.artifacts} != {a.locator for a in stnd_result.artifacts}
    assert {a.artifact_id for a in mllw_result.artifacts} != {a.artifact_id for a in stnd_result.artifacts}
    assert {a.version_id for a in mllw_result.artifacts} != {a.version_id for a in stnd_result.artifacts}

    # unchanged by the identity fix: analysis keeps them apart because
    # `datum` is a genuine scientific conditioning variable in its own right
    answer = analyze(pool, ENGINE, MaterialQuestion(material_natural_key=STATION, property="water_level"))
    assert {dict(g.context)["datum"] for g in answer.observed_comparison_groups} == {"MLLW", "STND"}


def test_extractor_rejects_malformed_or_unusable_responses():
    """Never silently degrades -- a partial parse would admit evidence
    with a wrong datum or a missing value."""
    with pytest.raises(NoaaMeasurementExtractionError, match="not valid JSON"):
        _extract(b"{not json")

    with pytest.raises(NoaaMeasurementExtractionError, match="metadata"):
        _extract(json.dumps({"data": []}).encode())

    with pytest.raises(NoaaMeasurementExtractionError, match="station id"):
        _extract(json.dumps({"metadata": {}, "data": []}).encode())

    with pytest.raises(NoaaMeasurementExtractionError, match="missing 't'/'v'"):
        _extract(json.dumps({"metadata": {"id": STATION}, "data": [{"t": "2024-01-15 00:00"}]}).encode())

    with pytest.raises(NoaaMeasurementExtractionError, match="non-numeric"):
        _extract(json.dumps({"metadata": {"id": STATION}, "data": [{"t": "x", "v": "n/a"}]}).encode())

    with pytest.raises(NoaaMeasurementExtractionError, match="unknown NOAA units"):
        _extract(MLLW_BYTES, units="furlongs")


def test_units_and_datum_come_from_the_request_not_from_the_response():
    """The response body echoes neither, so the binding is the single
    place they are fixed. A reading extracted under different declared
    units carries a different unit symbol for identical bytes -- which is
    exactly why adapter and extractor must be parameterised together."""
    assert "MLLW" not in MLLW_BYTES.decode() and "metric" not in MLLW_BYTES.decode()

    metric = _extract(MLLW_BYTES, units="metric")[0].content
    english = _extract(MLLW_BYTES, units="english")[0].content
    assert metric["unit"] == "m" and english["unit"] == "ft"
    assert metric["value"] == english["value"], "same bytes, same number -- only the declared unit differs"

    stnd = _extract(MLLW_BYTES, datum="STND")[0].content
    assert stnd["datum"] == "STND" and metric["datum"] == "MLLW"
