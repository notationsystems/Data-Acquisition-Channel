"""Phase 22: which registered sources could potentially satisfy a
scientific requirement -- and, more importantly, which could not.

    EvidenceRequirement -> AcquisitionIntent          (Phase 20)
                                |
                                v  resolve_sources()  (Phase 22, bridge/)
                        CandidateSource[]
                                |
                                v  EXPLICIT human/application selection
                        operationalize_intent()       (Phase 21, bridge/)
                                |
                                v  execute_plan()     daf/ (unchanged)
                    DAF -> SCOUT -> DurablePool -> Observation
                                |
                                v  update()  <-- EXPLICIT caller step
                        ModelState_(t+1)

A capability layer earns its keep by preventing FALSE matches, so the
negative cases here are the substance: a NOAA water-level source and a
USGS earthquake source must never be offered for a tensile-strength
requirement merely because they accept arbitrary parameters.

FIXTURE PROVENANCE: the DAF acquisition path is real and unmodified; the
measurement VALUES are a synthetic scientific fixture (Phase M's
standing finding -- no DAF-reachable source is a materials experiment).
The capability declarations are catalog metadata written by the test, as
an operator would write them.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from evidence.types import make_record
from materials.analysis import MaterialQuestion, analyze
from materials.model_state import predict, update
from materials.results import admit_experimental_result, make_experimental_result

from boundary.acquisition_intent import make_acquisition_intent
from bridge.intent_execution import operationalize_intent
from bridge.source_capability import (
    CONTEXT_KEYS_NOT_DECLARED,
    DISABLED,
    PROPERTY_NOT_DECLARED,
    ROLE_NOT_DECLARED,
    SUBJECT_KIND_NOT_DECLARED,
    SourceCapability,
    capability_index,
    resolve_sources,
)
from daf.catalog.checkpoint import CheckpointStore
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from helpers_state_gap import ENGINE, FORMULATION, campaign_for, measurement, trajectory
from science.acquisition_seam import intents_for
from science.information_gap import diagnose_information_gap

REPO_ROOT = Path(__file__).resolve().parent.parent
AT_25C = {"temperature": 25, "temperature_unit": "C"}

# --- a small catalog of structurally different sources ----------------
MATERIALS_SOURCE = SourceDefinition(
    source_id="materials-tensile", name="Tensile panel", domain="materials",
    adapter_id="graph-dataset", required_parameters=("path",),
)
NOAA_SOURCE = SourceDefinition(
    source_id="noaa-water", name="NOAA water level", domain="environmental-observations",
    adapter_id="noaa-water-level-measurements",
    required_parameters=("station", "product", "start_date", "end_date"),
)
USGS_SOURCE = SourceDefinition(
    source_id="usgs-quake", name="USGS earthquakes", domain="seismology",
    adapter_id="usgs-earthquakes", required_parameters=("start_time", "end_time"),
)
DISABLED_SOURCE = SourceDefinition(
    source_id="materials-disabled", name="Offline rig", domain="materials",
    adapter_id="graph-dataset", required_parameters=("path",), enabled=False,
)
UNDECLARED_SOURCE = SourceDefinition(
    source_id="undeclared-src", name="Mystery feed", domain="unknown",
    adapter_id="graph-dataset", required_parameters=("path",),
)

MATERIALS_CAPABILITY = SourceCapability(
    source_id="materials-tensile",
    properties=("tensile_strength", "modulus"), subject_kinds=("formulation",),
    roles=("OBSERVED",), context_keys=("temperature", "temperature_unit"),
)
CAPABILITIES = (
    MATERIALS_CAPABILITY,
    SourceCapability(
        source_id="noaa-water", properties=("water_level",),
        subject_kinds=("monitoring_station",), roles=("OBSERVED",), context_keys=("datum",),
    ),
    SourceCapability(
        source_id="usgs-quake", properties=("magnitude",),
        subject_kinds=("earthquake_event",), roles=("OBSERVED",),
    ),
    SourceCapability(
        source_id="materials-disabled", properties=("tensile_strength",),
        subject_kinds=("formulation",), roles=("OBSERVED",),
    ),
    SourceCapability(source_id="empty-declaration"),
)


def _registry():
    registry = SourceRegistry()
    for source in (MATERIALS_SOURCE, NOAA_SOURCE, USGS_SOURCE, DISABLED_SOURCE, UNDECLARED_SOURCE):
        registry.register(source)
    registry.register(
        SourceDefinition(
            source_id="empty-declaration", name="Declares nothing", domain="unknown",
            adapter_id="graph-dataset", required_parameters=("path",),
        )
    )
    return registry


def _tensile_intent(context=None):
    return make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property="tensile_strength", role="OBSERVED", target_context=context or {},
    )


def _mismatch(resolution, source_id):
    return next(m for m in resolution.mismatches if m.source_id == source_id)


def _top_level_imports(package_name):
    package = REPO_ROOT / package_name
    modules = sorted(package.rglob("*.py"))
    assert modules, f"{package_name} must exist"
    imported = set()
    for module_path in modules:
        tree = ast.parse(module_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
    return imported


# ====================================================================
# A/B/G. determinism, property matching, and the explanation
# ====================================================================

def test_resolution_is_deterministic_and_explains_each_match():
    """Sections 15A and 15G."""
    intent = _tensile_intent()
    first = resolve_sources(intent, CAPABILITIES, _registry())
    second = resolve_sources(intent, CAPABILITIES, _registry())
    assert first == second

    assert [c.source_id for c in first.candidates] == ["materials-tensile"]
    candidate = first.candidates[0]
    assert candidate.intent_id == intent.id
    assert candidate.matched_property == "tensile_strength"
    assert candidate.matched_subject_kind == "formulation"
    assert candidate.matched_role == "OBSERVED"
    assert candidate.matched_context_keys == ()

    # no score anywhere -- ranking would be expected information gain
    assert not any(
        field in candidate.__dataclass_fields__
        for field in ("score", "confidence", "rank", "priority", "expected_information_gain")
    )


# ====================================================================
# C/D/E/F. the negative cases -- the point of the layer
# ====================================================================

def test_structurally_different_sources_are_rejected_not_offered():
    """Section 8's headline: a tensile-strength requirement must not
    match NOAA water level or USGS earthquakes merely because those
    sources accept parameters."""
    resolution = resolve_sources(_tensile_intent(), CAPABILITIES, _registry())
    assert [c.source_id for c in resolution.candidates] == ["materials-tensile"]

    for rejected in ("noaa-water", "usgs-quake"):
        reasons = _mismatch(resolution, rejected).reasons
        assert PROPERTY_NOT_DECLARED in reasons
        assert SUBJECT_KIND_NOT_DECLARED in reasons


def test_subject_kind_mismatch_alone_is_enough_to_reject():
    """Section 15C. Same property, wrong kind of subject: a source that
    reports water level for stations cannot answer a question about a
    formulation, even when the property name happens to line up."""
    station_capability = SourceCapability(
        source_id="noaa-water", properties=("tensile_strength",),
        subject_kinds=("monitoring_station",), roles=("OBSERVED",),
    )
    resolution = resolve_sources(_tensile_intent(), (station_capability,), _registry())
    assert resolution.candidates == ()
    assert _mismatch(resolution, "noaa-water").reasons == (SUBJECT_KIND_NOT_DECLARED,)


def test_undeclared_context_rejects_and_names_the_missing_keys():
    """Section 15D. The materials source declares temperature; a source
    that does not must not be offered for a 25 C requirement."""
    resolution = resolve_sources(_tensile_intent(AT_25C), CAPABILITIES, _registry())
    assert [c.source_id for c in resolution.candidates] == ["materials-tensile"]
    assert resolution.candidates[0].matched_context_keys == ("temperature", "temperature_unit")

    disabled = _mismatch(resolution, "materials-disabled")
    assert CONTEXT_KEYS_NOT_DECLARED in disabled.reasons
    assert disabled.missing_context_keys == ("temperature", "temperature_unit")


def test_role_is_a_real_discriminator():
    """A measurement source cannot supply a prediction. Phase 20 emits
    BOTH roles for one criterion, so without this a tensile dataset would
    be offered for a PREDICTED intent."""
    predicted = make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property="tensile_strength", role="PREDICTED", target_context={},
    )
    resolution = resolve_sources(predicted, CAPABILITIES, _registry())
    assert resolution.candidates == ()
    assert ROLE_NOT_DECLARED in _mismatch(resolution, "materials-tensile").reasons


def test_unknown_and_empty_declarations_never_match():
    """Sections 15E and 10. Silence is not a declaration.

    `undeclared-src` is registered and enabled but has NO capability
    entry, so it is not considered at all -- it appears in neither
    candidates nor mismatches. `empty-declaration` declares nothing and
    is rejected on every dimension."""
    resolution = resolve_sources(_tensile_intent(), CAPABILITIES, _registry())

    named = {c.source_id for c in resolution.candidates} | {m.source_id for m in resolution.mismatches}
    assert "undeclared-src" not in named, "a source without a declaration is not a candidate"

    empty = _mismatch(resolution, "empty-declaration")
    assert PROPERTY_NOT_DECLARED in empty.reasons
    assert SUBJECT_KIND_NOT_DECLARED in empty.reasons
    assert ROLE_NOT_DECLARED in empty.reasons


def test_disabled_source_never_matches():
    """Section 15F. Even a perfectly capable source is not a candidate
    while it is disabled."""
    resolution = resolve_sources(_tensile_intent(), CAPABILITIES, _registry())
    assert "materials-disabled" not in {c.source_id for c in resolution.candidates}
    assert DISABLED in _mismatch(resolution, "materials-disabled").reasons

    # and re-enabling it makes it a candidate, so DISABLED was the only bar
    enabled = SourceRegistry()
    enabled.register(
        SourceDefinition(
            source_id="materials-disabled", name="Rig", domain="materials",
            adapter_id="graph-dataset", required_parameters=("path",), enabled=True,
        )
    )
    capability = next(c for c in CAPABILITIES if c.source_id == "materials-disabled")
    assert resolve_sources(_tensile_intent(), (capability,), enabled).candidates


def test_a_capability_for_an_unregistered_source_is_reported_not_offered():
    """A stale declaration must not become a candidate."""
    resolution = resolve_sources(_tensile_intent(), (MATERIALS_CAPABILITY,), SourceRegistry())
    assert resolution.candidates == ()
    assert "NOT_REGISTERED" in _mismatch(resolution, "materials-tensile").reasons


# ====================================================================
# J. no hidden execution
# ====================================================================

def test_resolution_performs_no_acquisition_and_touches_no_pool(monkeypatch):
    """Section 15J."""
    from daf.scheduling import runner

    monkeypatch.setattr(
        runner, "execute_plan",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("resolution must not acquire")),
    )
    resolution = resolve_sources(_tensile_intent(AT_25C), CAPABILITIES, _registry())
    assert resolution.candidates

    # nothing was mutated
    assert MATERIALS_CAPABILITY.properties == ("tensile_strength", "modulus")
    assert capability_index(CAPABILITIES)["materials-tensile"] == MATERIALS_CAPABILITY


# ====================================================================
# H/I/K. the full composition, and what it must not disturb
# ====================================================================

def test_requirement_to_candidate_to_acquisition_to_next_state(tmp_path):
    """Sections 12, 15H, 15I and the stop condition: the complete chain
    for a real measurement-shaped source, with every hand-off explicit."""
    pool, iteration, candidate, (s0, s1, _s2) = trajectory(tmp_path)

    # --- scientific side: gap -> requirement -> intent ------------------
    gap = diagnose_information_gap(s1, candidate, iteration)
    intent = intents_for(gap)[0]
    assert gap.requirements[0].property == "tensile_strength"

    # --- capability resolution ------------------------------------------
    sources = _registry()
    resolution = resolve_sources(intent, CAPABILITIES, sources)
    assert [c.source_id for c in resolution.candidates] == ["materials-tensile"]

    # --- EXPLICIT selection: a person picks one of the candidates -------
    selected = sources.get(resolution.candidates[0].source_id)

    # --- Phase 21 operationalization ------------------------------------
    dataset = tmp_path / "followup.json"
    dataset.write_text(json.dumps([measurement("ts-301", 91), measurement("ts-302", 88)]))
    plan = operationalize_intent(
        intent, selected, plan_id="capability-plan-1", parameters={"path": str(dataset)}
    )
    assert plan.source_id == "materials-tensile"

    # --- DAF execution, unchanged ---------------------------------------
    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())
    result = execute_plan(
        plan, sources, adapters, pool, CheckpointStore(tmp_path / "ck2"),
        requested_at="2026-08-25T06:00:00Z",
    )
    assert result.outcome.value == "acquired" and len(result.artifacts) == 2

    answer = analyze(pool, ENGINE, MaterialQuestion(material_natural_key=FORMULATION, property="tensile_strength"))
    assert {91, 88} <= {o.content["value"] for o in answer.observed}

    # --- resolution and acquisition did NOT move the scientific state ---
    assert predict(s1, candidate).sample_count == 1

    # --- the caller, explicitly, performs the state transition ----------
    follow_candidate, campaign, entry = campaign_for(iteration)
    document_id = pool.get_record(pool.all_observations()[0].record_ids[0]).document_id
    record = make_record(document_id=document_id, locator="run-4", raw_content="run-4")
    pool.put_record(record)
    experimental_result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 91, "unit": "MPa"},
        record_id=record.id, extracted_at="2026-08-25T07:00:00Z",
        extraction_method="measurement:campaign_execution",
    )
    observation, _relationship = admit_experimental_result(pool, experimental_result, confidence=1.0)
    s_next = update(s1, follow_candidate, experimental_result, observation)

    assert s_next.id != s1.id != s0.id
    assert predict(s_next, follow_candidate).sample_count == 2
    assert predict(s1, candidate).sample_count == 1, "history remains immutable"


def test_capability_metadata_changes_no_identity(tmp_path):
    """Section 15K / 11. Capability metadata is descriptive catalog
    state: acquiring with it present must produce byte-identical artifact
    and observation identities to acquiring without it."""
    dataset = tmp_path / "panel.json"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps([measurement("ts-401", 84)]))

    def _acquire(root):
        from daf.storage.durable_pool import DurablePool
        from daf.storage.filesystem_store import FilesystemEvidenceStore

        pool = DurablePool(FilesystemEvidenceStore(root / "evidence"))
        sources = _registry()
        adapters = AdapterRegistry()
        adapters.register(graph_dataset_binding())
        plan = operationalize_intent(
            _tensile_intent(), sources.get("materials-tensile"),
            plan_id="p", parameters={"path": str(dataset)},
        )
        result = execute_plan(
            plan, sources, adapters, pool, CheckpointStore(root / "ck"),
            requested_at="2026-08-25T06:00:00Z",
        )
        return result, sorted(o.id for o in pool.all_observations())

    # the capability declarations exist in this process either way; what
    # matters is that nothing in the acquisition path consults them
    with_caps = _acquire(tmp_path / "a")
    resolve_sources(_tensile_intent(), CAPABILITIES, _registry())  # resolution happened
    without_further = _acquire(tmp_path / "b")

    assert {a.artifact_id for a in with_caps[0].artifacts} == {
        a.artifact_id for a in without_further[0].artifacts
    }
    assert with_caps[1] == without_further[1], "observation identities unchanged"


def test_existing_explicit_acquisition_is_completely_unaffected(tmp_path):
    """Section 15H / 10. A caller who names a source_id directly, with no
    capability declaration anywhere, behaves exactly as before."""
    from daf.catalog.plan import AcquisitionPlan
    from daf.storage.durable_pool import DurablePool
    from daf.storage.filesystem_store import FilesystemEvidenceStore

    dataset = tmp_path / "panel.json"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps([measurement("ts-501", 79)]))

    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    sources = SourceRegistry()
    sources.register(UNDECLARED_SOURCE)  # deliberately has no SourceCapability
    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())

    result = execute_plan(
        AcquisitionPlan(plan_id="p", source_id="undeclared-src", parameters={"path": str(dataset)}),
        sources, adapters, pool, CheckpointStore(tmp_path / "ck"),
        requested_at="2026-08-25T06:00:00Z",
    )
    assert result.outcome.value == "acquired"
    assert len(pool.all_observations()) == 1, (
        "a source with no capability declaration still acquires normally when named explicitly"
    )


# ====================================================================
# Section 16. structural dependency directions
# ====================================================================

def test_capability_resolution_lives_where_the_dependencies_allow():
    """Section 16. Resolution matches an AcquisitionIntent (neutral)
    against a SourceDefinition (daf), so it belongs in `bridge` -- the
    one layer already permitted to name both. It needs no scientific
    import, which is why matching is against the intent rather than the
    EvidenceRequirement."""
    science_imports = _top_level_imports("science")
    assert "daf" not in science_imports and "bridge" not in science_imports

    daf_imports = _top_level_imports("daf")
    for forbidden in ("materials", "science", "boundary", "bridge"):
        assert forbidden not in daf_imports, f"daf must not import {forbidden}"

    boundary_imports = _top_level_imports("boundary")
    for forbidden in ("materials", "daf", "science", "bridge"):
        assert forbidden not in boundary_imports

    bridge_imports = _top_level_imports("bridge")
    assert "daf" in bridge_imports and "boundary" in bridge_imports
    for forbidden in ("materials", "science"):
        assert forbidden not in bridge_imports, (
            f"capability resolution must not need {forbidden}"
        )
