"""Phase 21: executing a previously-created `AcquisitionIntent` through
the existing DAF machinery, without either side learning about the other.

    EvidenceRequirement -> AcquisitionIntent      (science/, Phase 20)
                                |
                                v  operationalize_intent()   bridge/
                          AcquisitionPlan
                                |
                                v  execute_plan()            daf/ (unchanged)
                      DAF -> SCOUT -> DurablePool
                                |
                                v  analyze()                 materials/
                          scientific Observation
                                |
                                v  update()  <-- EXPLICIT caller step
                          ModelState_(t+1)

The last arrow is never taken as a side effect of acquisition. These
tests assert that directly: after a successful acquisition the state is
byte-identical until the caller calls `update` itself.

FIXTURE PROVENANCE: the DAF acquisition path is real and unmodified; the
measurement VALUES are a synthetic scientific fixture, because no
DAF-reachable source is a materials experiment (Phase M's standing
finding).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from evidence.types import make_record
from materials.analysis import MaterialQuestion, analyze
from materials.model_state import predict, update
from materials.results import admit_experimental_result, make_experimental_result

from boundary.acquisition_intent import make_acquisition_intent
from bridge.intent_execution import IntentNotOperationalizable, operationalize_intent
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore
from science.acquisition_seam import intents_for
from science.information_gap import diagnose_information_gap
from helpers_state_gap import (
    ENGINE,
    FORMULATION,
    campaign_for,
    measurement,
    trajectory,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AT_25C = {"temperature": 25, "temperature_unit": "C"}

PANEL_SOURCE = SourceDefinition(
    source_id="qc-panel-2", name="QC panel 2", domain="materials",
    adapter_id="graph-dataset", required_parameters=("path",), capabilities=(),
)
# A source that DOES declare the conditioning keys as request parameters.
# The graph-dataset adapter ignores them -- this proves the mapping
# plumbing, not that this particular adapter conditions on temperature.
CONDITIONED_SOURCE = SourceDefinition(
    source_id="qc-panel-25c", name="QC panel at 25C", domain="materials",
    adapter_id="graph-dataset",
    required_parameters=("path", "temperature", "temperature_unit"), capabilities=(),
)


def _dataset(root, name, records):
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(json.dumps(records))
    return path


def _registries(source):
    sources = SourceRegistry()
    sources.register(source)
    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())
    return sources, adapters


def _intent_from_state(tmp_path):
    """The real Phase 20 path: trajectory -> gap -> requirement -> intent."""
    pool, iteration, candidate, states = trajectory(tmp_path)
    gap = diagnose_information_gap(states[1], candidate, iteration)
    return pool, iteration, candidate, states, intents_for(gap)[0]


def _top_level_imports(package_name):
    package = REPO_ROOT / package_name
    modules = sorted(package.rglob("*.py"))
    assert modules, f"{package_name} must exist and contain modules"
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
# A. intent -> plan determinism
# ====================================================================

def test_operationalization_is_deterministic(tmp_path):
    """Section 13A / 11. Same intent, source, plan_id and parameters
    produce an equal plan. No wall clock, no random id."""
    _pool, _iteration, _candidate, _states, intent = _intent_from_state(tmp_path)
    dataset = _dataset(tmp_path / "f", "followup.json", [measurement("ts-201", 91)])

    first = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="intent-plan-1", parameters={"path": str(dataset)}
    )
    second = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="intent-plan-1", parameters={"path": str(dataset)}
    )
    assert first == second
    assert (first.plan_id, first.source_id, dict(first.parameters), first.mode) == (
        "intent-plan-1", "qc-panel-2", {"path": str(dataset)}, "snapshot"
    )


def test_operationalization_performs_no_acquisition(tmp_path, monkeypatch):
    """Purity: building a plan touches nothing."""
    from daf.scheduling import runner

    _pool, _iteration, _candidate, _states, intent = _intent_from_state(tmp_path)
    monkeypatch.setattr(
        runner, "execute_plan",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("operationalization must not acquire")),
    )
    plan = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="p", parameters={"path": "/nowhere.json"}
    )
    assert isinstance(plan, AcquisitionPlan)


# ====================================================================
# B/C. context preservation, and explicit failure when unmappable
# ====================================================================

def test_conditioning_context_reaches_the_plan_when_the_source_declares_it():
    """Section 13B. temperature=25 C survives intent -> plan, carried into
    the parameter the caller mapped it onto."""
    intent = make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property="tensile_strength", role="OBSERVED", target_context=AT_25C,
    )
    plan = operationalize_intent(
        intent, CONDITIONED_SOURCE, plan_id="p-25c", parameters={"path": "/data/panel.json"},
        context_parameters={"temperature": "temperature", "temperature_unit": "temperature_unit"},
    )
    assert dict(plan.parameters) == {
        "path": "/data/panel.json", "temperature": 25, "temperature_unit": "C"
    }
    assert dict(intent.target_context) == AT_25C, "the intent itself is unchanged"


def test_unmappable_context_fails_explicitly_rather_than_being_dropped():
    """Section 13C, the critical negative case. Silently acquiring
    without the conditioning context would return evidence that looks
    responsive and does not answer the question."""
    intent = make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property="tensile_strength", role="OBSERVED", target_context=AT_25C,
    )

    with pytest.raises(IntentNotOperationalizable, match="has no parameter mapping"):
        operationalize_intent(
            intent, PANEL_SOURCE, plan_id="p", parameters={"path": "/data/panel.json"}
        )

    # a mapping onto a parameter the source does not declare is also refused
    with pytest.raises(IntentNotOperationalizable, match="does not declare parameter"):
        operationalize_intent(
            intent, PANEL_SOURCE, plan_id="p", parameters={"path": "/data/panel.json"},
            context_parameters={"temperature": "temperature", "temperature_unit": "temperature_unit"},
        )

    # and a mapping that would silently overwrite a caller parameter is an
    # ambiguity only the caller can resolve
    with pytest.raises(IntentNotOperationalizable, match="only the caller can decide"):
        operationalize_intent(
            intent, CONDITIONED_SOURCE, plan_id="p",
            parameters={"path": "/d.json", "temperature": 60, "temperature_unit": "C"},
            context_parameters={"temperature": "temperature", "temperature_unit": "temperature_unit"},
        )


def test_an_intent_with_no_context_needs_no_mapping():
    """The common case stays simple: nothing to map, nothing to declare."""
    intent = make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property="tensile_strength", role="OBSERVED", target_context={},
    )
    plan = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="p", parameters={"path": "/data/panel.json"}
    )
    assert dict(plan.parameters) == {"path": "/data/panel.json"}


# ====================================================================
# D/E. real DAF execution, and the closed scientific loop
# ====================================================================

def test_the_complete_loop_from_state_to_next_state(tmp_path):
    """Sections 13D, 13E and the stop condition, end to end with the real
    DAF pipeline and an explicit caller-driven state transition."""
    pool, iteration, candidate, (s0, s1, _s2), intent = _intent_from_state(tmp_path)
    dataset = _dataset(
        tmp_path / "f", "followup.json", [measurement("ts-201", 91), measurement("ts-202", 88)]
    )

    # --- operationalization: the caller picks the source ---------------
    plan = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="intent-plan-1", parameters={"path": str(dataset)}
    )

    # --- DAF execution, unmodified -------------------------------------
    sources, adapters = _registries(PANEL_SOURCE)
    result = execute_plan(
        plan, sources, adapters, pool, CheckpointStore(tmp_path / "ck2"),
        requested_at="2026-08-25T04:00:00Z",
    )
    assert result.outcome.value == "acquired" and len(result.artifacts) == 2

    # --- SCOUT admission reached the durable pool and the analysis -----
    answer = analyze(pool, ENGINE, MaterialQuestion(material_natural_key=FORMULATION, property="tensile_strength"))
    assert {91, 88} <= {o.content["value"] for o in answer.observed}

    # --- acquisition did NOT move the scientific state -----------------
    assert predict(s1, candidate).sample_count == 1

    # --- the caller, explicitly, performs the state transition ---------
    follow_candidate, campaign, entry = campaign_for(iteration)
    document_id = pool.get_record(pool.all_observations()[0].record_ids[0]).document_id
    record = make_record(document_id=document_id, locator="run-3", raw_content="run-3")
    pool.put_record(record)
    experimental_result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 91, "unit": "MPa"},
        record_id=record.id, extracted_at="2026-08-25T05:00:00Z",
    )
    observation, _relationship = admit_experimental_result(pool, experimental_result, confidence=1.0)
    s_next = update(s1, follow_candidate, experimental_result, observation)

    assert s_next.id != s1.id != s0.id
    assert predict(s_next, follow_candidate).sample_count == 2
    assert predict(s1, candidate).sample_count == 1, "history remains immutable"


def test_acquisition_alone_never_moves_the_model_state(tmp_path):
    """Section 13F, isolated from the loop above so the claim cannot ride
    on anything else: run the acquisition, change nothing else, and the
    state is byte-identical."""
    pool, _iteration, candidate, (_s0, s1, _s2), intent = _intent_from_state(tmp_path)
    dataset = _dataset(tmp_path / "f", "followup.json", [measurement("ts-201", 91)])
    before_id = s1.id
    before_samples = {key: tuple(values) for key, values in s1.samples.items()}

    plan = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="p", parameters={"path": str(dataset)}
    )
    sources, adapters = _registries(PANEL_SOURCE)
    result = execute_plan(
        plan, sources, adapters, pool, CheckpointStore(tmp_path / "ck2"),
        requested_at="2026-08-25T04:00:00Z",
    )
    assert result.succeeded

    assert s1.id == before_id
    assert {key: tuple(values) for key, values in s1.samples.items()} == before_samples
    assert predict(s1, candidate).sample_count == 1


# ====================================================================
# G. restart
# ====================================================================

def test_evidence_acquired_through_an_intent_survives_restart(tmp_path):
    """Section 13G, using the existing DurablePool restart machinery."""
    pool, _iteration, _candidate, _states, intent = _intent_from_state(tmp_path)
    dataset = _dataset(tmp_path / "f", "followup.json", [measurement("ts-201", 91)])
    plan = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="p", parameters={"path": str(dataset)}
    )
    sources, adapters = _registries(PANEL_SOURCE)
    execute_plan(
        plan, sources, adapters, pool, CheckpointStore(tmp_path / "ck2"),
        requested_at="2026-08-25T04:00:00Z",
    )
    observation_ids = sorted(o.id for o in pool.all_observations())
    fingerprint = pool.fingerprint()
    del pool

    restarted = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    assert sorted(o.id for o in restarted.all_observations()) == observation_ids
    assert restarted.fingerprint() == fingerprint


def test_repeating_an_intent_derived_plan_preserves_deduplication(tmp_path):
    """Section 9.9: the bridge changes nothing about DAF identity or
    duplicate semantics."""
    pool, _iteration, _candidate, _states, intent = _intent_from_state(tmp_path)
    dataset = _dataset(tmp_path / "f", "followup.json", [measurement("ts-201", 91)])
    plan = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="p", parameters={"path": str(dataset)}
    )
    sources, adapters = _registries(PANEL_SOURCE)
    checkpoints = CheckpointStore(tmp_path / "ck2")

    first = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T04:00:00Z")
    ids_after_first = sorted(o.id for o in pool.all_observations())
    second = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T05:00:00Z")

    assert first.outcome.value == "acquired" and second.outcome.value == "duplicate"
    assert {a.artifact_id for a in first.artifacts} == {a.artifact_id for a in second.artifacts}
    assert sorted(o.id for o in pool.all_observations()) == ids_after_first


# ====================================================================
# H/I. identity separation and failure semantics
# ====================================================================

def test_every_identity_in_the_loop_stays_distinct(tmp_path):
    """Section 13H / 10. intent id, plan id, source id, artifact id,
    version id, observation id and ModelState id are seven different
    things and none is derived from another."""
    pool, _iteration, _candidate, (_s0, s1, _s2), intent = _intent_from_state(tmp_path)
    dataset = _dataset(tmp_path / "f", "followup.json", [measurement("ts-201", 91)])
    plan = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="intent-plan-1", parameters={"path": str(dataset)}
    )
    sources, adapters = _registries(PANEL_SOURCE)
    result = execute_plan(
        plan, sources, adapters, pool, CheckpointStore(tmp_path / "ck2"),
        requested_at="2026-08-25T04:00:00Z",
    )
    artifact = result.artifacts[0]
    observation = next(
        o for o in pool.all_observations() if o.content.get("value") == 91
    )

    identities = [
        intent.id, plan.plan_id, plan.source_id,
        artifact.artifact_id, artifact.version_id, observation.id, s1.id,
    ]
    assert len(set(identities)) == len(identities), "no two identities coincide"
    assert plan.plan_id != intent.id, "a plan id is not a scientific identity"
    assert artifact.artifact_id != observation.id


def test_acquisition_failures_are_reported_and_never_touch_scientific_state(tmp_path):
    """Sections 9.2, 9.4, 9.5, 9.7 and 13I. Unknown source, disabled
    source and a genuine adapter failure are all reported through the
    existing DAF result type -- and none of them moves the ModelState or
    mutates the intent."""
    pool, _iteration, candidate, (_s0, s1, _s2), intent = _intent_from_state(tmp_path)
    dataset = _dataset(tmp_path / "f", "followup.json", [measurement("ts-201", 91)])
    before_id = s1.id
    before_samples = {key: tuple(values) for key, values in s1.samples.items()}
    intent_before = intent

    sources, adapters = _registries(PANEL_SOURCE)
    checkpoints = CheckpointStore(tmp_path / "ck2")

    # unknown source -- the plan names a source no registry knows
    unknown_plan = AcquisitionPlan(
        plan_id="p", source_id="nonexistent", parameters={"path": str(dataset)}
    )
    unknown = execute_plan(unknown_plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T04:00:00Z")
    assert unknown.outcome.value == "source_unavailable" and "UNKNOWN_SOURCE" in (unknown.error or "")

    # disabled source
    disabled_source = SourceDefinition(
        source_id="qc-disabled", name="disabled", domain="materials",
        adapter_id="graph-dataset", required_parameters=("path",), enabled=False,
    )
    disabled_sources, disabled_adapters = _registries(disabled_source)
    disabled_plan = operationalize_intent(
        intent, disabled_source, plan_id="p-dis", parameters={"path": str(dataset)}
    )
    disabled = execute_plan(
        disabled_plan, disabled_sources, disabled_adapters, pool, checkpoints,
        requested_at="2026-08-25T04:00:00Z",
    )
    assert disabled.outcome.value == "source_unavailable" and "SOURCE_DISABLED" in (disabled.error or "")

    # a real acquisition failure: the dataset the plan names does not exist
    missing_plan = operationalize_intent(
        intent, PANEL_SOURCE, plan_id="p-missing", parameters={"path": str(tmp_path / "absent.json")}
    )
    failed = execute_plan(missing_plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T04:00:00Z")
    assert not failed.succeeded and failed.error

    # nothing scientific moved, and the intent is untouched
    assert s1.id == before_id
    assert {key: tuple(values) for key, values in s1.samples.items()} == before_samples
    assert predict(s1, candidate).sample_count == 1
    assert intent == intent_before and dict(intent.target_context) == {}


# ====================================================================
# Section 14. structural dependency directions
# ====================================================================

def test_the_bridge_is_the_only_layer_that_names_both_sides():
    """Section 14. The bridge exists precisely so that no other package
    has to see both an intent and a plan."""
    science_imports = _top_level_imports("science")
    assert "daf" not in science_imports and "bridge" not in science_imports

    boundary_imports = _top_level_imports("boundary")
    for forbidden in ("materials", "daf", "science", "bridge"):
        assert forbidden not in boundary_imports

    daf_imports = _top_level_imports("daf")
    for forbidden in ("materials", "science", "boundary", "bridge"):
        assert forbidden not in daf_imports, f"daf must not import {forbidden}"

    bridge_imports = _top_level_imports("bridge")
    assert "daf" in bridge_imports and "boundary" in bridge_imports, (
        "the bridge is deliberately allowed to name both sides"
    )
    for forbidden in ("materials", "science"):
        assert forbidden not in bridge_imports, (
            f"the bridge operates on the neutral intent, so it must not need {forbidden}"
        )
