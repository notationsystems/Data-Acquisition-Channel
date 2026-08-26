"""Phase 35: does the Phase 34 condition representation stay correct
across the COMPLETE durable scientific lifecycle?

Phase 34 asked "can conditions be represented?" and answered yes.
Phase 35 asks whether that representation survives acquisition →
persistence → process termination → reopen → hydration → admissibility →
analysis, and answers: **for NOAA yes, for the substrate as a whole not
uniformly.**

THE ASYMMETRY THIS PHASE MEASURED. Phase 34 applied
`freeze_nested_mappings` at ONE of the two boundaries where a Mapping
value enters an `Observation` -- the READ side
(`daf/storage/serialization.py`). The WRITE side was fixed only for NOAA,
by hand, inside NOAA's own extractor. `daf.extractors.graph_dataset`
passes every non-structural key through verbatim by design, so a source
record that declares a `conditions` object still produces a plain,
unhashable `dict`. Measured consequence, and it is the exact MIRROR of
the Phase 34 bug:

    graph_dataset + conditions + a relation:
        same process   -> materials.analysis RAISES unhashable type: 'dict'
        after reopen   -> materials.analysis SUCCEEDS (FrozenMapping)

The reason the same-process case is the broken one is itself measured
(see `test_a_same_process_acquisition_never_round_trips_its_own_content`):
`scout.pipeline.run_scout` calls `build_trust_graph(pool)` at the start of
every acquisition, which hydrates the pool while the store is still
EMPTY, permanently setting `DurablePool._hydrated = True` before the first
`put_observation`. So a same-process acquire-then-analyze hands
`materials.analysis` the extractor's own in-memory objects and never
reconstructs anything -- `observation_from_dict` is called zero times.
The read-side fix cannot help there, because the read side never runs.

Nothing in this file changes production behaviour. Per Phase 35 §7 the
extractors are inventoried, not modified; per §9 no conflict policy is
invented. The gaps are LOCKED as characterization tests so they cannot
change silently, and recorded in
`architecture/condition_lifecycle.yaml`.

PHASE 37 UPDATE. `write_side_asymmetry` is now CLOSED, and closed the
way Phase 35 said it would have to be: not inside `graph_dataset`, which
would have been per-source patching, but at
`daf/extractors/_passthrough.py` -- the one seam both verbatim
pass-through extractors share. The two tests that locked the gap open
are INVERTED rather than deleted, since the shapes they name are exactly
the regression surface. The other three gaps stand unchanged, so
`closure.substrate` is still `not_closed`; one gap closing is not
substrate closure and the record does not claim it is.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from evidence.identity import content_hash
from evidence.types import make_observation, make_record
from materials.analysis import (
    MaterialQuestion,
    _comparison_context,
    _group_by_comparison_context,
    analyze,
)
from retrieval.engine import DeterministicRetrievalEngine

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from assertion.property_admissibility import assess_pool, canonical_assertion_quarantine_store
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.execution.identity import RuntimeIdentity
from daf.execution.recorded import execute_plan_recorded
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding, noaa_water_level_measurement_binding
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
RESTART_DRIVER = REPO_ROOT / "tests" / "helpers_phase35_restart.py"
LIFECYCLE = loads((REPO_ROOT / "architecture" / "condition_lifecycle.yaml").read_text())

RUNTIME = RuntimeIdentity(python_version="3.11.0", platform="linux-a", hostname="host-a", process_id=1)
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()
STATION = "8454000"
NOAA_PARAMETERS = {
    "station": STATION,
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}

# A graph-reachable record that declares conditions: entities AND a
# relation, because `retrieval.engine` reaches an Observation only
# through a ClaimedRelationship -- an entity-only record is admitted but
# invisible to analysis (measured; see the inert variant below).
GRAPH_RECORD_WITH_CONDITIONS = {
    "id": "ts-001",
    "property": "tensile_strength",
    "value": 78.0,
    "unit": "MPa",
    "method": "ASTM_E8",
    "conditions": {"temperature_c": 23, "specimen": "dogbone-A", "strain_rate_per_s": 0.001},
    "uncertainty_kind": "stated",
    "uncertainty": 1.2,
    "entities": [
        {"label": "formulation-f1", "kind": "formulation"},
        {"label": "process-a", "kind": "process"},
    ],
    "relations": [{"from": "formulation-f1", "to": "process-a", "type": "tested_during"}],
}


def _noaa_pool(root, *, pool=None, policy_id="source_policy:phase35"):
    return pool if pool is not None else ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id=policy_id, by_source_kind={"tide-station-window": MEASURED}),
    )


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
    pool = _noaa_pool(root, pool=pool)
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


def _acquire_graph(root, record):
    dataset = root / "dataset.json"
    dataset.write_text(json.dumps([record]))
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="gd",
            name="graph dataset",
            domain="test",
            adapter_id="graph-dataset",
            required_parameters=("path",),
            capabilities=(),
        )
    )
    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())
    pool = ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"),
        SourceClassPolicy(id="p", by_source_kind={"graph-dataset": MEASURED}),
    )
    recorded = execute_plan_recorded(
        AcquisitionPlan(plan_id="gd-plan", source_id="gd", parameters={"path": str(dataset)}),
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


def _content_fingerprint(content) -> str:
    return content_hash({"content": dict(sorted(content.items()))})


# ============================================ 1-2. acquisition + persistence


def test_real_noaa_acquisition_persists_conditions_to_disk_as_plain_json(tmp_path):
    """The representation is a LAYER ABOVE the bytes, deliberately: the
    on-disk form is an ordinary JSON object, so nothing about
    persistence depends on a Python type being encoded."""
    _, pool = _acquire_noaa(tmp_path)
    observation = min(pool.all_observations(), key=lambda o: o.id)

    path = tmp_path / "evidence" / "observations" / f"{observation.id}.json"
    raw = json.loads(path.read_text())
    assert raw["content"]["conditions"] == {"datum": "MLLW"}
    assert isinstance(raw["content"]["conditions"], dict)
    assert "FrozenMapping" not in path.read_text()


def test_a_same_process_acquisition_never_round_trips_its_own_content(tmp_path):
    """WHY the read-side fix alone cannot be the whole story, measured
    rather than argued: `run_scout` hydrates the pool while the store is
    still empty (via `build_trust_graph`), so `_hydrated` is already True
    before the first `put_observation` and `observation_from_dict` is
    never called during acquisition at all."""
    calls = []
    original = serialization.observation_from_dict

    def counting(payload):
        calls.append(payload["id"])
        return original(payload)

    serialization.observation_from_dict = counting
    try:
        _, pool = _acquire_noaa(tmp_path)
        assert pool._hydrated is True
        assert calls == [], "acquisition reconstructed an Observation from JSON -- premise changed"
    finally:
        serialization.observation_from_dict = original


# ==================================================== 3. fresh-process restart


def _run_driver(subcommand, store_dir):
    return subprocess.run(
        [sys.executable, str(RESTART_DRIVER), subcommand, str(store_dir)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300, check=False,
    )


def _driver_keys(output):
    return {
        line.split("=", 1)[0].strip(): line.split("=", 1)[1].strip()
        for line in output.splitlines()
        if "=" in line
    }


def test_conditions_survive_a_real_two_os_process_restart(tmp_path):
    """§12, the first-class test: two genuinely separate interpreters
    sharing nothing but a filesystem path. Not two objects in one
    process."""
    store_dir = tmp_path / "store" / "evidence"
    store_dir.mkdir(parents=True)

    acquire = _run_driver("acquire", store_dir)
    assert acquire.returncode == 0, acquire.stderr
    analyze_run = _run_driver("analyze", store_dir)
    assert analyze_run.returncode == 0, analyze_run.stderr

    before, after = _driver_keys(acquire.stdout), _driver_keys(analyze_run.stdout)
    assert before, "driver produced no key=value output"
    assert set(before) == set(after)
    for key in sorted(before):
        assert before[key] == after[key], f"{key} differed across the restart boundary"

    assert before["conditions_type"] == "FrozenMapping"
    assert before["conditions_hashable"] == "True"
    assert before["conditions_immutable"] == "True"
    assert before["admissibility_by_code"] == "[('MISSING_METHOD', 240)]"
    assert before["analysis_observed_count"] == "240"


def test_the_restart_driver_agrees_with_the_same_process_result(tmp_path):
    """§12's other half: the subprocess result must AGREE with what an
    in-process acquisition of the same fixture produces."""
    store_dir = tmp_path / "store" / "evidence"
    store_dir.mkdir(parents=True)
    acquire = _run_driver("acquire", store_dir)
    assert acquire.returncode == 0, acquire.stderr
    subprocess_keys = _driver_keys(acquire.stdout)

    _, pool = _acquire_noaa(tmp_path / "inproc")
    observations = sorted(pool.all_observations(), key=lambda o: o.id)
    assert subprocess_keys["observation_count"] == str(len(observations))
    assert subprocess_keys["first_observation_id"] == observations[0].id
    assert subprocess_keys["content_fingerprint"] == _content_fingerprint(observations[0].content)
    assert subprocess_keys["pool_fingerprint"] == pool.fingerprint()


# ================================================ 4-5. identity + reconstruction


def test_identity_is_preserved_across_hydration(tmp_path):
    """§3, measured on every one of the 240 real observations -- not the
    first one only."""
    _, pool_a = _acquire_noaa(tmp_path)
    before = sorted(pool_a.all_observations(), key=lambda o: o.id)

    pool_b = _noaa_pool(tmp_path, policy_id="source_policy:phase35-reopen")
    after = sorted(pool_b.all_observations(), key=lambda o: o.id)

    assert [o.id for o in before] == [o.id for o in after]
    assert [_content_fingerprint(o.content) for o in before] == [
        _content_fingerprint(o.content) for o in after
    ]
    assert pool_a.fingerprint() == pool_b.fingerprint()


def test_frozen_mapping_is_reconstructed_on_every_hydrated_observation(tmp_path):
    _acquire_noaa(tmp_path)
    pool = _noaa_pool(tmp_path, policy_id="source_policy:phase35-reopen")
    hydrated = pool.all_observations()

    assert len(hydrated) == 240
    for observation in hydrated:
        conditions = observation.content["conditions"]
        assert isinstance(conditions, FrozenMapping)
        assert dict(conditions) == {"datum": "MLLW"}


# ============================================================= 6. hash stability


def test_native_hash_is_process_local_but_content_hash_is_not():
    """A MEASURED correction to the naive reading of §2's "hashability"
    invariant. What must survive a restart is that hashing SUCCEEDS and
    that `content_hash` is stable -- NOT the value of `hash()`, which
    Python deliberately randomizes per interpreter (PYTHONHASHSEED).

    This is correct rather than a defect: the only consumer of the native
    hash, `materials.analysis._group_by_comparison_context`, uses it as a
    dict key WITHIN one process and never persists or compares it. A test
    asserting a stable native hash across processes would be asserting
    something Python does not promise and this architecture does not
    need."""
    script = (
        "import daf\n"
        "from daf.storage.frozen_mapping import FrozenMapping\n"
        "from evidence.identity import content_hash\n"
        "fm = FrozenMapping({'datum': 'MLLW'})\n"
        "print(hash(fm))\n"
        "print(content_hash({'conditions': fm}))\n"
    )
    runs = []
    for _ in range(3):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120, check=False,
        )
        assert result.returncode == 0, result.stderr
        native, digest = result.stdout.split()
        runs.append((native, digest))

    assert len({digest for _, digest in runs}) == 1, "content_hash must be process-stable"
    assert len({native for native, _ in runs}) > 1, (
        "native hash is expected to be process-local; if this ever fails, PYTHONHASHSEED "
        "was pinned and the invariant this test documents was not actually exercised"
    )


def test_native_hash_is_stable_within_one_process(tmp_path):
    """The invariant `_group_by_comparison_context` actually relies on."""
    _, pool = _acquire_noaa(tmp_path)
    conditions = [o.content["conditions"] for o in pool.all_observations()]
    assert len({hash(c) for c in conditions}) == 1
    assert len({c for c in conditions}) == 1


# ================================================== 7-8. immutability + round trip


def test_hydrated_conditions_are_still_immutable(tmp_path):
    _acquire_noaa(tmp_path)
    pool = _noaa_pool(tmp_path, policy_id="source_policy:phase35-reopen")
    conditions = pool.all_observations()[0].content["conditions"]

    for mutate in (
        lambda: conditions.__setitem__("datum", "STND"),
        lambda: conditions.__delitem__("datum"),
        lambda: conditions.update({"x": 1}),
        lambda: conditions.pop("datum"),
        lambda: conditions.clear(),
        lambda: conditions.setdefault("x", 1),
    ):
        with pytest.raises(TypeError):
            mutate()


def test_serialization_round_trip_is_idempotent(tmp_path):
    """Round-tripping TWICE must be identical to round-tripping once --
    the property that makes repeated reopen/rewrite cycles safe."""
    _, pool = _acquire_noaa(tmp_path)
    observation = min(pool.all_observations(), key=lambda o: o.id)

    once = serialization.observation_from_dict(serialization.observation_to_dict(observation))
    twice = serialization.observation_from_dict(serialization.observation_to_dict(once))

    assert once.id == twice.id == observation.id
    assert dict(once.content) == dict(twice.content)
    assert type(once.content["conditions"]) is type(twice.content["conditions"]) is FrozenMapping


# ==================================================== 9-12. admissibility/analysis


def test_noaa_terminal_refusal_is_missing_method_before_and_after_restart(tmp_path):
    """§4: conditions passing must not accidentally resolve method."""
    recorded, pool_a = _acquire_noaa(tmp_path)
    before = assess_pool(pool_a, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path / "a"))

    pool_b = _noaa_pool(tmp_path, policy_id="source_policy:phase35-reopen")
    after = assess_pool(pool_b, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path / "b"))

    for report in (before, after):
        assert report.candidates_examined == 240
        assert report.accepted == 0
        assert report.refused == 240
        assert report.by_code == {"MISSING_METHOD": 240}

    for observation in pool_b.all_observations():
        assert "method" not in observation.content


def test_real_analysis_agrees_before_and_after_restart(tmp_path):
    """§5 cases 1 and 2, through the real vendored consumer."""
    _, pool_a = _acquire_noaa(tmp_path)
    question = MaterialQuestion(material_natural_key=STATION, property="water_level")
    before = analyze(pool_a, DeterministicRetrievalEngine(), question)

    pool_b = _noaa_pool(tmp_path, policy_id="source_policy:phase35-reopen")
    after = analyze(pool_b, DeterministicRetrievalEngine(), question)

    assert len(before.observed) == len(after.observed) == 240
    assert len(before.observed_comparison_groups) == len(after.observed_comparison_groups)
    assert before.observed_disagreement == after.observed_disagreement is None
    assert {dict(g.context)["conditions"]["datum"] for g in after.observed_comparison_groups} == {"MLLW"}


def test_an_observation_without_conditions_still_analyses(tmp_path):
    """§5 case 3: the absence of conditions is not made fatal by the
    representation's existence -- USGS-shaped content still groups."""
    content = {"property": "p", "value": 1.0, "unit": "m", "method": "m"}
    context = _comparison_context(content, "value")
    groups = _group_by_comparison_context([(context, 1.0)])
    assert len(groups) == 1
    assert "conditions" not in dict(groups[0].context)


# ============================================================ 13. quarantine


def test_the_refusal_persists_and_reloads_identically(tmp_path):
    """§11: the real refusal path, persisted and reloaded through a
    FRESH store object. Quarantine is not redesigned here -- only
    exercised."""
    recorded, pool = _acquire_noaa(tmp_path)
    written = canonical_assertion_quarantine_store(tmp_path)
    report = assess_pool(pool, recorded.execution.id, written)
    assert report.refused == 240

    reloaded = canonical_assertion_quarantine_store(tmp_path)
    records = reloaded.for_execution(recorded.execution.id)
    assert len(records) == 240
    for record in records:
        assert record.execution_id == recorded.execution.id
        assert record.stage == "canonical_assertion"
        assert {e.code for e in record.errors} == {"MISSING_METHOD"}

    assert sorted(r.id for r in records) == sorted(
        r.id for r in written.for_execution(recorded.execution.id)
    )


def test_the_quarantine_record_never_embeds_the_condition_value(tmp_path):
    """Measured, and load-bearing: because a QuarantineRecord carries only
    id/execution_id/stage/errors, the FrozenMapping representation is not
    part of the quarantine contract at all -- so the Phase 34 class of
    round-trip bug cannot arise on this path."""
    recorded, pool = _acquire_noaa(tmp_path)
    store = canonical_assertion_quarantine_store(tmp_path)
    assess_pool(pool, recorded.execution.id, store)

    blob = "".join(path.read_text() for path in sorted(store.root.glob("*.json")))
    for absent in ("conditions", "datum", "MLLW", "FrozenMapping", '"content"'):
        assert absent not in blob, f"{absent!r} unexpectedly persisted into quarantine"


# ============================================================= 14. USGS regression


def test_usgs_semantics_are_unchanged(tmp_path):
    """§6: the FrozenMapping extension must not alter USGS."""
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
            source_id="usgs-quakes", name="USGS Earthquakes", domain="environmental-observations",
            adapter_id="usgs-earthquakes",
            required_parameters=("start_time", "end_time", "min_magnitude"), capabilities=("incremental",),
        )
    )

    def build_adapter(source, request):
        return UsgsEarthquakeSourceAdapter(
            start_time=str(request.parameters["start_time"]),
            end_time=str(request.parameters["end_time"]),
            min_magnitude=float(request.parameters["min_magnitude"]),
            retrieved_at=request.requested_at, fetch_bytes=router,
        )

    adapters = AdapterRegistry()
    adapters.register(
        AdapterBinding(adapter_id="usgs-earthquakes", build_adapter=build_adapter,
                       build_extractor=UsgsEarthquakeExtractor)
    )
    pool = ClassifiedPool(
        FilesystemEvidenceStore(tmp_path / "evidence"),
        SourceClassPolicy(id="p", by_source_kind={"event-detail": MEASURED}),
    )
    recorded = execute_plan_recorded(
        AcquisitionPlan(plan_id="usgs-plan", source_id="usgs-quakes",
                        parameters={"start_time": "2026-01-01", "end_time": "2026-01-02", "min_magnitude": 1.0}),
        sources, adapters, pool, CheckpointStore(tmp_path / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z", executions=ExecutionRecordStore(tmp_path),
        quarantine=QuarantineStore(tmp_path), runtime=RUNTIME,
    )
    report = assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))
    assert report.candidates_examined == 3
    assert report.accepted == 0
    assert set(report.by_code) == {"MISSING_CONDITIONS", "MISSING_UNCERTAINTY_KIND"}

    reopened = ClassifiedPool(
        FilesystemEvidenceStore(tmp_path / "evidence"),
        SourceClassPolicy(id="p2", by_source_kind={"event-detail": MEASURED}),
    )
    for observation in reopened.all_observations():
        assert "conditions" not in observation.content
        assert observation.content["method"]


# ==================================================== 15. multi-condition


def _multi(conditions):
    return make_observation(
        record_ids=("r",), extraction_method="x",
        content={
            "property": "p", "value": 1.0, "unit": "m", "method": "m",
            "uncertainty": 0.1, "uncertainty_kind": "stated", "conditions": conditions,
        },
        confidence=1.0, extracted_at="2020-01-01T00:00:00Z",
    )


def test_multiple_conditions_are_order_independent_end_to_end():
    """§8: equality, hash, identity, serialization and REAL grouping all
    agree regardless of declaration order."""
    a = FrozenMapping({"datum": "MLLW", "temperature_c": 20, "pressure_kpa": 101})
    b = FrozenMapping({"pressure_kpa": 101, "datum": "MLLW", "temperature_c": 20})

    assert a == b and hash(a) == hash(b)
    assert _multi(a).id == _multi(b).id
    assert _multi(a).id == _multi({"datum": "MLLW", "temperature_c": 20, "pressure_kpa": 101}).id

    grouped = _group_by_comparison_context(
        [(_comparison_context(_multi(a).content, "value"), 1.0),
         (_comparison_context(_multi(b).content, "value"), 2.0)]
    )
    assert len(grouped) == 1, "same conditions in a different order must be ONE comparison group"


def test_differing_conditions_form_distinct_comparison_groups():
    same = FrozenMapping({"datum": "MLLW", "temperature_c": 20})
    other = FrozenMapping({"datum": "STND", "temperature_c": 20})
    grouped = _group_by_comparison_context(
        [(_comparison_context(_multi(same).content, "value"), 1.0),
         (_comparison_context(_multi(other).content, "value"), 2.0)]
    )
    assert len(grouped) == 2


def test_multiple_conditions_survive_the_round_trip():
    observation = _multi(FrozenMapping({"datum": "MLLW", "temperature_c": 20, "pressure_kpa": 101}))
    back = serialization.observation_from_dict(serialization.observation_to_dict(observation))

    assert back.id == observation.id
    assert isinstance(back.content["conditions"], FrozenMapping)
    assert dict(back.content["conditions"]) == {"datum": "MLLW", "temperature_c": 20, "pressure_kpa": 101}
    assert no_context_free_property(back.content).admissible


# =============================== 16. malformed / degenerate — CHARACTERIZATION


@pytest.mark.parametrize(
    "label,conditions,admissible,groups",
    [
        ("empty FrozenMapping", FrozenMapping({}), False, True),
        ("bare string", "MLLW", False, True),
        ("null-valued condition", FrozenMapping({"datum": None}), True, True),
        ("empty-string condition", FrozenMapping({"datum": ""}), True, True),
        ("nested FrozenMapping", FrozenMapping({"a": FrozenMapping({"b": 1})}), True, True),
        ("list-valued condition", FrozenMapping({"a": [1, 2, 3]}), True, False),
        ("plain dict", {"datum": "MLLW"}, True, False),
    ],
)
def test_degenerate_condition_values_behave_as_measured(label, conditions, admissible, groups):
    """§9: CHARACTERIZATION, not policy. This records what the substrate
    does today; it invents no conflict semantics and adds no validation.

    Two rows are genuine measured GAPS, locked here so they cannot drift:

      * `null-valued`/`empty-string` conditions are ADMISSIBLE. The gate
        checks that `conditions` is a non-empty Mapping; it never
        inspects the VALUES, so a semantically vacuous condition passes.
      * `list-valued` conditions are admissible AND identity-stable but
        BREAK the real consumer -- `FrozenMapping.__hash__` cannot hash a
        list, and `freeze_nested_mappings` does not recurse into lists.
        This is the Phase 33 defect one level deeper.
    """
    content = {
        "property": "p", "value": 1.0, "unit": "m", "method": "m",
        "uncertainty": 0.1, "uncertainty_kind": "stated", "conditions": conditions,
    }
    assert no_context_free_property(content).admissible is admissible

    if groups:
        assert len(_group_by_comparison_context([(_comparison_context(content, "value"), 1.0)])) == 1
    else:
        with pytest.raises(TypeError, match="unhashable"):
            _group_by_comparison_context([(_comparison_context(content, "value"), 1.0)])


def test_absent_conditions_is_refused_and_still_groups():
    content = {"property": "p", "value": 1.0, "unit": "m", "method": "m",
               "uncertainty": 0.1, "uncertainty_kind": "stated"}
    verdict = no_context_free_property(content)
    assert not verdict.admissible and "MISSING_CONDITIONS" in verdict.reasons
    assert len(_group_by_comparison_context([(_comparison_context(content, "value"), 1.0)])) == 1


# ============================ THE MEASURED GAP: write-side asymmetry (§7)


def test_graph_dataset_now_freezes_the_conditions_it_passes_through(tmp_path):
    """INVERTED IN PHASE 37, deliberately, and the inversion is the point.

    This began as a characterization lock asserting that `graph_dataset`
    still produced a plain dict, with the instruction that closing the
    gap must update `architecture/condition_lifecycle.yaml` rather than
    this assertion. Phase 37 closed it -- not inside `graph_dataset`,
    which is what Phase 35 refused, but at
    `daf.extractors._passthrough`, the single seam both verbatim
    pass-through extractors share. So the assertion is inverted rather
    than deleted: this record is what the gap WAS, and it stays here as
    the regression surface."""
    _, pool = _acquire_graph(tmp_path, GRAPH_RECORD_WITH_CONDITIONS)
    observation = pool.all_observations()[0]

    conditions = observation.content["conditions"]
    assert isinstance(conditions, FrozenMapping), (
        "the write-side asymmetry has reopened -- a pass-through extractor is emitting a plain dict "
        "again, which fails in-process and is repaired only by a restart"
    )
    assert dict(conditions) == {"specimen": "dogbone-A", "strain_rate_per_s": 0.001, "temperature_c": 23}
    assert hash(conditions) == hash(FrozenMapping(dict(conditions)))


def test_the_two_lifecycle_positions_no_longer_disagree(tmp_path):
    """INVERTED IN PHASE 37. The gap WAS: same acquisition, two lifecycle
    positions, opposite outcomes -- in-process it RAISED
    `TypeError: unhashable type: 'dict'`, after a reopen it SUCCEEDED.
    Phase 34's bug was the other way round; both were the same root
    cause, a Mapping-valued content entry whose representation was
    imposed at only one of the two boundaries.

    Now BOTH positions succeed, and this test asserts the agreement
    rather than the divergence -- because agreement between the two is
    the property that actually matters. A one-sided fix would still pass
    a test that only checked one side."""
    _, pool = _acquire_graph(tmp_path, GRAPH_RECORD_WITH_CONDITIONS)
    question = MaterialQuestion(material_natural_key="formulation-f1", property="tensile_strength")

    in_process = analyze(pool, DeterministicRetrievalEngine(), question)

    reopened = ClassifiedPool(
        FilesystemEvidenceStore(tmp_path / "evidence"),
        SourceClassPolicy(id="p2", by_source_kind={"graph-dataset": MEASURED}),
    )
    after_restart = analyze(reopened, DeterministicRetrievalEngine(), question)

    assert len(in_process.observed) == len(after_restart.observed) == 1
    for answer in (in_process, after_restart):
        assert isinstance(answer.observed[0].content["conditions"], FrozenMapping)
    assert in_process.observed[0].id == after_restart.observed[0].id, (
        "identity must not depend on which side of a process boundary the observation was read"
    )


def test_the_gap_needs_conditions_and_a_relation_together(tmp_path):
    """Why this has stayed latent: the shipped `ADMISSIBLE_RECORD` in
    tests/test_property_admission_integration.py declares conditions but
    NO relation, and `retrieval.engine` reaches an Observation only
    through a ClaimedRelationship -- so analysis never touches it."""
    inert = dict(GRAPH_RECORD_WITH_CONDITIONS, relations=[],
                 entities=[{"label": "formulation-f1", "kind": "formulation"}])
    _, pool = _acquire_graph(tmp_path, inert)

    answer = analyze(
        pool, DeterministicRetrievalEngine(),
        MaterialQuestion(material_natural_key="formulation-f1", property="tensile_strength"),
    )
    assert len(answer.observed) == 0, "an entity-only record is admitted but unreachable"


# ============================ PHASE 34 DOCUMENTATION CORRECTION (§7 inventory)


def test_two_shipped_extractors_already_emitted_dict_valued_content():
    """CORRECTS PHASE 34. `architecture/condition_representation.yaml`
    claimed `freeze_nested_mappings` was "a no-op for every content shape
    shipped before this phase (measured: no extractor has ever produced a
    dict-valued content entry)". That claim is FALSE, and this test is
    the measurement that shows it: EDGAR has always emitted
    `form_type_counts`, and the window-shaped NOAA extractor
    `quality_counts`.

    The practical impact is nil -- both emit `entities=(), relations=()`
    so neither is reachable through `materials.analysis`, and
    `Observation.id` is unchanged either way -- but the claim was wrong
    and is corrected in the YAML rather than left standing."""
    from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractor
    from daf.extractors.noaa_water_level import NoaaWaterLevelExtractor

    def _record(raw):
        return make_record(document_id="d", locator="l", raw_content=raw)

    edgar = EdgarDailyIndexExtractor().extract(
        _record((FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_text())
    )[0]
    window = NoaaWaterLevelExtractor().extract(
        _record((FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_text())
    )[0]

    assert isinstance(edgar.content["form_type_counts"], dict)
    assert isinstance(window.content["quality_counts"], dict)
    assert edgar.entities == () and edgar.relations == ()
    assert window.entities == () and window.relations == ()


def test_freeze_nested_mappings_does_not_recurse_into_lists():
    """The measured boundary of the read-side fix, locked. EDGAR's
    `filings` and the window extractor's `readings` are lists of dicts
    and stay plain -- which is why a list-valued condition breaks
    grouping (see the degenerate-value characterization above)."""
    frozen = freeze_nested_mappings({"filings": [{"x": 1}], "counts": {"y": 2}})
    assert isinstance(frozen["counts"], FrozenMapping)
    assert isinstance(frozen["filings"], list)
    assert isinstance(frozen["filings"][0], dict)
    assert not isinstance(frozen["filings"][0], FrozenMapping)


# ================================================== 17. evidence boundary


def test_frozen_mapping_creates_no_evidence_write_path():
    """§10: the representation module imports nothing that could reach an
    EvidencePool, and nothing in the analysis path writes evidence."""
    import ast

    source = (REPO_ROOT / "daf" / "storage" / "frozen_mapping.py").read_text()
    tree = ast.parse(source)
    imported = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imported <= {"typing", "__future__"}, f"unexpected imports: {sorted(imported)}"

    # Checked against the AST's executable names, not the raw text: this
    # module's DOCSTRING legitimately explains the run_scout/pool
    # hydration mechanism, and a substring scan would flag its own
    # explanation of why it exists.
    referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for forbidden in ("EvidencePool", "put_observation", "run_scout", "pool", "store"):
        assert forbidden not in referenced, f"{forbidden!r} is referenced in executable code"


def test_analysis_output_is_never_written_back_to_the_pool(tmp_path):
    """§10: analysing an observation must not add anything to the pool."""
    _, pool = _acquire_noaa(tmp_path)
    before_fingerprint = pool.fingerprint()
    before_count = len(pool.all_observations())

    analyze(pool, DeterministicRetrievalEngine(),
            MaterialQuestion(material_natural_key=STATION, property="water_level"))

    assert pool.fingerprint() == before_fingerprint
    assert len(pool.all_observations()) == before_count


def test_admissibility_assessment_is_never_written_back_to_the_pool(tmp_path):
    recorded, pool = _acquire_noaa(tmp_path)
    before_fingerprint = pool.fingerprint()

    assess_pool(pool, recorded.execution.id, canonical_assertion_quarantine_store(tmp_path))

    assert pool.fingerprint() == before_fingerprint


# ======================================================= architecture record


def test_the_lifecycle_determination_matches_what_was_measured():
    assert LIFECYCLE["closure"]["noaa"] == "closed"
    assert LIFECYCLE["closure"]["substrate"] == "not_closed"
    gaps = {gap["id"] for gap in LIFECYCLE["gaps"]}
    assert gaps == {
        "write_side_asymmetry",
        "list_valued_conditions",
        "vacuous_condition_values",
        "phase_34_no_op_claim_incorrect",
    }
    by_id = {gap["id"]: gap for gap in LIFECYCLE["gaps"]}
    assert by_id["write_side_asymmetry"]["action_taken"] == "closed_in_phase_37", (
        "the gap was closed at daf/extractors/_passthrough.py; the record must say so"
    )
    for gap_id in ("list_valued_conditions", "vacuous_condition_values",
                   "phase_34_no_op_claim_incorrect"):
        assert by_id[gap_id]["action_taken"] == "recorded_not_fixed"


def test_every_lifecycle_boundary_is_recorded():
    boundaries = [entry["boundary"] for entry in LIFECYCLE["lifecycle_trace"]]
    assert boundaries == sorted(set(boundaries), key=boundaries.index), "duplicate boundary recorded"
    assert len(boundaries) == 11
