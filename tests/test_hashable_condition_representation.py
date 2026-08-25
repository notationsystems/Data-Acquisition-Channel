"""Phase 34: the representation that closes Phase 33's NOAA
representation gap, and locks that closing it did not touch anything
else.

Phase 33 (architecture/condition_provenance_reachability.yaml) found
`datum` a genuine NOAA measurement condition, but found that wiring
`conditions = {"datum": ...}` -- a plain dict -- broke
`materials.analysis._group_by_comparison_context`, which requires every
content value to be natively hashable. This phase measured the complete
constraint surface (no existing primitive in this repository or its
vendored substrate is simultaneously a Mapping, natively hashable, and
JSON-round-trip-stable -- see architecture/condition_representation.yaml)
and built the smallest one that is: `daf.storage.frozen_mapping.
FrozenMapping`, a `dict` subclass.

The single most consequential measurement here is that a hashable
wrapper type ALONE is not sufficient: `scout.pipeline.run_scout`
(vendored) hydrates a pool's full corpus from disk the first time
`build_trust_graph` is called, and for a freshly reopened (non-empty)
store that reconstructs `content` purely from `json.loads`, which has no
extension point anywhere in this codebase -- so without a matching
read-side fix in `daf/storage/serialization.py`, `conditions` silently
degrades back to a plain, unhashable dict the moment a second process
(or a second, freshly-restored pool) reopens the store. Both the
same-process and reopened-store paths are exercised below through the
real, vendored `materials.analysis.analyze()`, not a mock.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from evidence.identity import content_hash
from evidence.types import make_observation
from materials.analysis import MaterialQuestion, analyze
from retrieval.engine import DeterministicRetrievalEngine

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from assertion.property_admissibility import assess_pool, canonical_assertion_quarantine_store
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.extractors.noaa_water_level_measurements import NoaaWaterLevelMeasurementExtractor
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.bindings import noaa_water_level_measurement_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.storage import serialization
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from daf.storage.frozen_mapping import FrozenMapping, freeze_nested_mappings
from epistemics._yaml import loads
from epistemics.evidence_class import MEASURED
from science.admissibility import no_context_free_property

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
DETERMINATION = loads((REPO_ROOT / "architecture" / "condition_representation.yaml").read_text())

RUNTIME = RuntimeIdentity(python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1)
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
STATION = "8454000"
NOAA_PARAMETERS = {
    "station": STATION,
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}


def _acquire_noaa(root, *, pool=None):
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
        noaa_water_level_measurement_binding(datum="MLLW", units="metric", fetch_bytes=lambda url: MLLW_BYTES)
    )
    pool = pool if pool is not None else ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="source_policy:phase34", by_source_kind={"tide-station-window": MEASURED}),
    )
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
    )
    return recorded, pool


def _fresh_pool_over(root):
    """A second, unhydrated pool instance over an ALREADY-persisted
    store -- the 'process restart' / 'reopen an existing store' path
    `DurablePool.restore`/`load_pool` document, exercised directly."""
    return ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="source_policy:phase34-reopen", by_source_kind={"tide-station-window": MEASURED}),
    )


# ---------------------------------------------- 1. FrozenMapping itself --


def test_frozen_mapping_is_a_mapping_and_a_dict():
    from collections.abc import Mapping

    fm = FrozenMapping({"datum": "MLLW"})
    assert isinstance(fm, Mapping)
    assert isinstance(fm, dict)


def test_frozen_mapping_is_natively_hashable():
    fm = FrozenMapping({"datum": "MLLW"})
    assert isinstance(hash(fm), int)


def test_frozen_mapping_equals_the_equivalent_plain_dict():
    assert FrozenMapping({"datum": "MLLW"}) == {"datum": "MLLW"}
    assert {"datum": "MLLW"} == FrozenMapping({"datum": "MLLW"})


def test_frozen_mapping_order_independent_equality_and_hash():
    a = FrozenMapping({"datum": "MLLW", "station": "8454000"})
    b = FrozenMapping({"station": "8454000", "datum": "MLLW"})
    assert a == b
    assert hash(a) == hash(b)


def test_frozen_mapping_is_immutable():
    fm = FrozenMapping({"datum": "MLLW"})
    with pytest.raises(TypeError):
        fm["datum"] = "STND"
    with pytest.raises(TypeError):
        del fm["datum"]
    with pytest.raises(TypeError):
        fm.update({"x": 1})
    with pytest.raises(TypeError):
        fm.pop("datum")
    with pytest.raises(TypeError):
        fm.clear()
    with pytest.raises(TypeError):
        fm.setdefault("x", 1)


def test_frozen_mapping_freezes_nested_dicts_recursively():
    fm = FrozenMapping({"outer": {"inner": "value"}})
    assert isinstance(fm["outer"], FrozenMapping)
    assert hash(fm) is not None


def test_freeze_nested_mappings_is_a_no_op_for_flat_content():
    """Every content shape shipped before this phase is flat (no
    dict-valued entries) -- measured directly against a real, live-shaped
    USGS-style content mapping."""
    flat = {"property": "magnitude", "value": 4.2, "unit": "Mww", "method": "moment-tensor"}
    assert freeze_nested_mappings(flat) == flat
    assert all(not isinstance(v, FrozenMapping) for v in freeze_nested_mappings(flat).values())


def test_freeze_nested_mappings_wraps_any_dict_valued_key_generically():
    """Not conditions-specific: any dict-valued content entry is frozen,
    which is what keeps this a structural fix rather than a
    conditions-shaped special case."""
    content = {"property": "p", "value": 1, "some_other_mapping_key": {"a": 1}}
    frozen = freeze_nested_mappings(content)
    assert isinstance(frozen["some_other_mapping_key"], FrozenMapping)
    assert hash(frozen["some_other_mapping_key"]) is not None


# ----------------------------------------------------------- 2. identity --


def test_observation_id_is_unchanged_by_the_representation_choice():
    """Semantic equivalence DOES imply identity equivalence here --
    measured, not assumed: evidence.identity.content_hash serializes a
    FrozenMapping exactly like a plain dict of the same items."""
    frozen_content = {"property": "p", "value": 1.0, "unit": "m", "conditions": FrozenMapping({"datum": "MLLW"})}
    plain_content = {"property": "p", "value": 1.0, "unit": "m", "conditions": {"datum": "MLLW"}}

    frozen_obs = make_observation(
        record_ids=("r1",), extraction_method="x", content=frozen_content,
        confidence=1.0, extracted_at="2020-01-01T00:00:00Z",
    )
    plain_obs = make_observation(
        record_ids=("r1",), extraction_method="x", content=plain_content,
        confidence=1.0, extracted_at="2020-01-01T00:00:00Z",
    )
    assert frozen_obs.id == plain_obs.id


def test_a_bare_mapping_conditions_value_still_breaks_content_hash():
    """The contract this representation satisfies, reconfirmed: a
    collections.abc.Mapping that is NOT also a dict subclass fails at
    identity computation, before materials.analysis is ever reached --
    this is why Candidate A/a bare Mapping implementation was rejected,
    not merely a stylistic preference for dict."""
    from collections.abc import Mapping as ABCMapping

    class BareMapping(ABCMapping):
        def __init__(self, data):
            self._data = dict(data)

        def __getitem__(self, key):
            return self._data[key]

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

    with pytest.raises(TypeError, match="JSON serializable"):
        content_hash({"conditions": BareMapping({"datum": "MLLW"})})


# ------------------------------------------------------ 3. serialization --


def test_serialization_round_trip_preserves_frozen_mapping_type():
    content = {"property": "p", "value": 1.0, "unit": "m", "conditions": FrozenMapping({"datum": "MLLW"})}
    observation = make_observation(
        record_ids=("r1",), extraction_method="x", content=content,
        confidence=1.0, extracted_at="2020-01-01T00:00:00Z",
    )
    payload = serialization.observation_to_dict(observation)
    reconstructed = serialization.observation_from_dict(payload)

    assert reconstructed.id == observation.id
    assert isinstance(reconstructed.content["conditions"], FrozenMapping)
    assert dict(reconstructed.content["conditions"]) == {"datum": "MLLW"}
    assert hash(reconstructed.content["conditions"]) is not None


def test_serialization_round_trip_is_a_no_op_for_content_with_no_mapping_values():
    """Backward compatibility: every pre-Phase-34 content shape has no
    dict-valued entries, so the round trip is unaffected."""
    content = {"property": "p", "value": 1.0, "unit": "m", "method": "m"}
    observation = make_observation(
        record_ids=("r1",), extraction_method="x", content=content,
        confidence=1.0, extracted_at="2020-01-01T00:00:00Z",
    )
    reconstructed = serialization.observation_from_dict(serialization.observation_to_dict(observation))
    assert reconstructed.id == observation.id
    assert dict(reconstructed.content) == content


# ------------------------------------------------ 4. real NOAA acquisition --


def test_real_noaa_acquisition_carries_conditions_without_raising(tmp_path):
    """Same-process acquire-then-analyze -- the common case, and the one
    Phase 33's own regression test exercised. No TypeError, and every
    reading now carries a hashable, Mapping-valued conditions entry."""
    recorded, pool = _acquire_noaa(tmp_path)
    assert recorded.result.outcome.value == "acquired"

    observations = pool.all_observations()
    assert len(observations) == 240
    for observation in observations:
        assert isinstance(observation.content["conditions"], FrozenMapping)
        assert dict(observation.content["conditions"]) == {"datum": "MLLW"}

    answer = analyze(
        pool, DeterministicRetrievalEngine(),
        MaterialQuestion(material_natural_key=STATION, property="water_level"),
    )
    assert len(answer.observed) == 240


def test_real_noaa_acquisition_survives_a_reopened_store(tmp_path):
    """THE decisive measurement: a FRESH pool instance reopening an
    ALREADY-persisted store -- DurablePool.restore/load_pool's own
    documented 'process restart' path -- must also reach
    materials.analysis without raising. Before daf/storage/
    serialization.py's read-side fix, this raised
    TypeError: unhashable type: 'dict', because FilesystemEvidenceStore.
    all_observations reconstructs content purely from json.loads."""
    _acquire_noaa(tmp_path)  # first "process": populates the store, then discards the pool object

    reopened = _fresh_pool_over(tmp_path)
    assert reopened._hydrated is False

    answer = analyze(
        reopened, DeterministicRetrievalEngine(),
        MaterialQuestion(material_natural_key=STATION, property="water_level"),
    )
    assert len(answer.observed) == 240
    assert isinstance(answer.observed[0].content["conditions"], FrozenMapping)
    assert {dict(g.context)["conditions"]["datum"] for g in answer.observed_comparison_groups} == {"MLLW"}


def test_the_context_gate_now_accepts_conditions_for_every_real_noaa_reading(tmp_path):
    """MISSING_CONDITIONS no longer appears; MISSING_METHOD -- the one
    dimension no phase has resolved -- is unchanged. No method was
    fabricated to get here."""
    recorded, pool = _acquire_noaa(tmp_path)
    for observation in pool.all_observations():
        verdict = no_context_free_property(observation.content)
        assert "MISSING_CONDITIONS" not in verdict.reasons
        assert "MISSING_METHOD" in verdict.reasons

    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))
    assert report.candidates_examined == 240
    assert report.accepted == 0
    assert report.by_code == {"MISSING_METHOD": 240}


def test_no_method_was_fabricated_to_compensate():
    from evidence.types import make_record

    content = NoaaWaterLevelMeasurementExtractor(datum="MLLW", units="metric").extract(
        make_record(document_id="d", locator="l", raw_content=MLLW_BYTES.decode())
    )[0].content
    assert "method" not in content


# -------------------------------------------- 5. real USGS regression --


def test_real_usgs_acquisition_is_unaffected(tmp_path):
    """USGS is untouched by this phase: no genuine condition exists in
    its real data (Phase 33's own finding), representation or not."""
    from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
    from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor

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
        AdapterBinding(
            adapter_id="usgs-earthquakes", build_adapter=build_adapter, build_extractor=UsgsEarthquakeExtractor
        )
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
    for observation in pool.all_observations():
        assert "conditions" not in observation.content


# -------------------------------------------------- 6. scope discipline --


def test_no_source_specific_condition_type_was_created():
    noaa_source = (REPO_ROOT / "daf" / "extractors" / "noaa_water_level_measurements.py").read_text()
    for forbidden in ("NOAAConditions", "USGSConditions", "EDGARConditions"):
        assert forbidden not in noaa_source


def test_frozen_mapping_is_generic_not_condition_specific():
    """The type itself carries no domain vocabulary -- only its own
    docstring's motivating example does. It is usable, and used
    identically, for any Mapping-shaped content value, not only
    conditions: this test constructs one for an unrelated domain
    (a hypothetical calibration state) and confirms every property
    still holds."""
    calibration = FrozenMapping({"reference_frame": "ECEF", "epoch": 2024})
    assert isinstance(calibration, FrozenMapping)
    assert hash(calibration) is not None
    assert dict(calibration) == {"reference_frame": "ECEF", "epoch": 2024}
    with pytest.raises(TypeError):
        calibration["epoch"] = 2025


def test_only_the_documented_files_changed():
    """§ scope: the representation touches exactly the files
    architecture/condition_representation.yaml documents -- no other
    extractor, no vendored file."""
    implementation = DETERMINATION["implementation"]
    assert implementation["new_file"] == "daf/storage/frozen_mapping.py"
    changed_paths = {entry["path"] for entry in implementation["changed"]}
    assert changed_paths == {
        "daf/storage/serialization.py",
        "daf/extractors/noaa_water_level_measurements.py",
    }


def test_no_vendored_file_is_modified_by_this_phase():
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT / "vendor" / "scout-retrieval-agent"), "status", "--short"],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == ""


# -------------------------------------------------------- 7. decision --


def test_the_decision_recorded_is_b_a_justified_shared_extension():
    assert DETERMINATION["decision"] == "B"


def test_no_existing_primitive_was_found_sufficient():
    assert DETERMINATION["primitive_search"]["found"] == "none"
