"""Phase T (completion): the semantic path from scientific state to the
acquisition boundary, and the dependency directions that make it a seam
rather than a coupling.

    ModelState -> diagnosis -> InformationGap -> EvidenceRequirement
                                                      |
                                                      v
                                            AcquisitionIntent   (neutral)
                                                      |
                                                      v
                                     an operator / DAF chooses a source

The last step is deliberately NOT taken automatically anywhere in this
repository. These tests compose it by hand, which is the point: the
scientific layer states what it needs, and something else decides how.

FIXTURE PROVENANCE (unchanged from tests/test_state_gap_frontier.py):
the DAF acquisition path is real and unmodified; the measurement VALUES
are a synthetic scientific fixture, because no DAF-reachable source is a
materials experiment (Phase M's standing finding).
"""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from evidence.admission import admit_claimed_relationship, admit_observation, admit_record
from evidence.pool import EvidencePool
from evidence.types import make_claimed_relationship, make_observation, make_record
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.information import NOT_DETERMINABLE, estimate_information_value
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, ModelStateInformationValueModel
from materials.program import make_material_program_query
from materials.specification import EvidenceRequirement

from boundary.acquisition_intent import AcquisitionIntent, make_acquisition_intent
from science.acquisition_seam import intent_for, intents_for
from science.information_gap import diagnose_information_gap
from helpers_state_gap import (
    ENGINE,
    FORMULATION,
    PROCESS,
    acquire_measurements,
    measurement,
    trajectory,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AT_25C = {"temperature": 25, "temperature_unit": "C"}


def _top_level_imports(package_name):
    """Every top-level package imported by any module in `package_name`."""
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


def _contextual_iteration(pool, context):
    """An iteration whose criterion carries a real conditioning context --
    `materials.decision.Criterion`'s own documented example shape."""
    query = make_material_program_query([FORMULATION], PROCESS, ("tensile_strength",))
    criterion = make_criterion("tensile_strength", ">=", 80, context=context)
    return reevaluate_program(pool, ENGINE, query, (criterion,))


# ====================================================================
# 1-3. the gap itself
# ====================================================================

def test_gap_is_deterministic_and_separates_gap_identity_from_state_identity(tmp_path):
    """Items 1 and 3. Equal inputs give equal gaps; and the gap is
    ANCHORED to a state without BEING one -- two different states yield
    different gaps, while the gap never becomes part of the state."""
    dataset = tmp_path / "shared" / "panel.json"
    _pool, iteration, candidate, (s0, s1, s2) = trajectory(tmp_path / "a", dataset=dataset)
    _pool_b, iteration_b, candidate_b, (t0, t1, _t2) = trajectory(tmp_path / "b", dataset=dataset)

    gap_1 = diagnose_information_gap(s1, candidate, iteration)
    assert gap_1 == diagnose_information_gap(s1, candidate, iteration), "deterministic"
    assert gap_1 == diagnose_information_gap(t1, candidate_b, iteration_b), "same inputs, same gap"

    assert diagnose_information_gap(s0, candidate, iteration) != gap_1
    assert diagnose_information_gap(s2, candidate, iteration) != gap_1
    assert gap_1.state_id == s1.id and t0.id == s0.id

    # the gap references the state; the state knows nothing of the gap
    assert not hasattr(s1, "gap") and not hasattr(s1, "gaps")
    assert set(s1.__dataclass_fields__) == {"id", "samples"}


def test_gap_is_immutable(tmp_path):
    """Item 2."""
    _pool, iteration, candidate, (_s0, s1, _s2) = trajectory(tmp_path)
    gap = diagnose_information_gap(s1, candidate, iteration)

    with pytest.raises(FrozenInstanceError):
        gap.state_id = "tampered"  # type: ignore[misc]
    assert isinstance(gap.reasons, tuple) and isinstance(gap.requirements, tuple)


# ====================================================================
# 4-5. gap -> requirement -> intent
# ====================================================================

def test_the_gap_already_carries_its_requirements_verbatim(tmp_path):
    """Item 4. No `gap_to_requirement()` function exists, deliberately:
    `InformationGap.requirements` IS that mapping, holding the vendored
    `EvidenceRequirement`s unmodified. A function returning them would be
    a wrapper with no content."""
    _pool, iteration, candidate, (_s0, s1, _s2) = trajectory(tmp_path)
    gap = diagnose_information_gap(s1, candidate, iteration)

    assert gap.requirements
    for requirement in gap.requirements:
        assert isinstance(requirement, EvidenceRequirement)
        assert requirement.property == "tensile_strength"
        assert requirement.formulation.natural_key == FORMULATION
        assert requirement.criterion.operator == ">=" and requirement.criterion.target == 80.0


def test_intent_identity_is_deterministic_and_content_derived(tmp_path):
    """Item 5. Two requirements wanting the same class of evidence give
    the SAME intent id -- which is exactly what makes 'many mechanisms,
    one intent' checkable. Mapping insertion order does not matter."""
    _pool, iteration, candidate, (_s0, s1, _s2) = trajectory(tmp_path)
    requirement = diagnose_information_gap(s1, candidate, iteration).requirements[0]

    assert intent_for(requirement) == intent_for(requirement)

    forwards = make_acquisition_intent(
        subject_natural_key="f1", subject_kind="formulation", property="tensile_strength",
        role="OBSERVED", target_context={"temperature": 25, "temperature_unit": "C"},
    )
    backwards = make_acquisition_intent(
        subject_natural_key="f1", subject_kind="formulation", property="tensile_strength",
        role="OBSERVED", target_context={"temperature_unit": "C", "temperature": 25},
    )
    assert forwards.id == backwards.id, "identity is content-derived, not insertion-ordered"

    different_context = make_acquisition_intent(
        subject_natural_key="f1", subject_kind="formulation", property="tensile_strength",
        role="OBSERVED", target_context={"temperature": 80, "temperature_unit": "C"},
    )
    assert different_context.id != forwards.id, (
        "evidence gathered at 80 C does not answer a question about 25 C"
    )


def test_intent_carries_conditioning_context_and_no_decision_threshold(tmp_path):
    """The seam's headline case, with a real conditioning context rather
    than an empty one: "tensile strength for formulation-f1 at 25 C".

    The criterion's own threshold (>= 80) is deliberately absent -- that
    is a decision applied to evidence after acquisition, not a property
    of the evidence wanted."""
    pool = acquire_measurements(tmp_path, [measurement("ts-001", 78), measurement("ts-002", 84)])
    iteration = _contextual_iteration(pool, AT_25C)
    assert iteration.decision.formulations[0].properties[0].observed_status == "INCOMPARABLE", (
        "no existing evidence was gathered at 25 C"
    )

    seen = {}
    for candidate in sorted(generate_candidates(iteration.specification).candidates, key=lambda c: c.id):
        gap = diagnose_information_gap(EMPTY_MODEL_STATE, candidate, iteration)
        if gap is None:
            continue
        for intent in intents_for(gap):
            seen[intent.role] = intent

    assert set(seen) == {"OBSERVED", "PREDICTED"}
    for intent in seen.values():
        assert dict(intent.target_context) == AT_25C
        assert intent.subject_natural_key == FORMULATION
        assert intent.subject_kind == "formulation"
        assert intent.property == "tensile_strength"

    assert seen["OBSERVED"].id != seen["PREDICTED"].id, (
        "a measurement source cannot satisfy a request for a prediction"
    )
    assert set(seen["OBSERVED"].__dataclass_fields__) == {
        "id", "subject_natural_key", "subject_kind", "property", "role", "target_context"
    }, "no threshold, no gap category, no pool state, no source"


# ====================================================================
# 6-9. the boundaries
# ====================================================================

def test_dependency_directions_are_structural(tmp_path):
    """Items 7 and Step 6.1/6.6, at the AST level over every module.

    The whole seam rests on these: `science` may not name `daf`,
    `boundary` may name neither `materials` nor `daf` nor `science` (so
    both sides can read it), and `daf` may name none of the scientific
    layers -- which is what lets DAF acquire evidence with no scientific
    layer present at all."""
    science_imports = _top_level_imports("science")
    assert "daf" not in science_imports, "science must never import daf"
    assert "materials" in science_imports and "boundary" in science_imports

    boundary_imports = _top_level_imports("boundary")
    for forbidden in ("materials", "daf", "science"):
        assert forbidden not in boundary_imports, (
            f"boundary must stay neutral; importing {forbidden} would exclude one side"
        )
    assert "evidence" in boundary_imports, "only the substrate both sides already share"

    daf_imports = _top_level_imports("daf")
    for forbidden in ("materials", "science", "boundary"):
        assert forbidden not in daf_imports, (
            f"daf must be able to acquire with no scientific layer present; it imports {forbidden}"
        )


def test_diagnosis_and_translation_never_touch_the_evidence_pool(tmp_path, monkeypatch):
    """Items 8 and 9 / Step 6.2. Every EvidencePool method is made to
    raise, and the whole gap -> requirement -> intent path still runs."""
    _pool, iteration, candidate, (_s0, s1, _s2) = trajectory(tmp_path)
    samples_before = {key: tuple(values) for key, values in s1.samples.items()}

    def _forbidden(*args, **kwargs):
        raise AssertionError("the scientific seam must never touch EvidencePool")

    for method_name in (
        "get_source", "get_document", "get_record", "get_observation", "get_referent",
        "has_source", "has_document", "has_record", "has_observation", "has_referent",
        "put_source", "put_document", "put_record", "put_observation",
    ):
        monkeypatch.setattr(EvidencePool, method_name, _forbidden)

    gap = diagnose_information_gap(s1, candidate, iteration)
    intents = intents_for(gap)
    assert intents and all(isinstance(i, AcquisitionIntent) for i in intents)

    assert s1.id == gap.state_id
    assert {key: tuple(values) for key, values in s1.samples.items()} == samples_before, (
        "diagnosis and translation mutate nothing"
    )


def test_translating_a_requirement_performs_no_acquisition(tmp_path, monkeypatch):
    """Step 6.3/6.5. `intent_for` must not execute anything -- proven by
    making the DAF execution entry point raise if called."""
    from daf.scheduling import runner

    _pool, iteration, candidate, (_s0, s1, _s2) = trajectory(tmp_path)
    requirement = diagnose_information_gap(s1, candidate, iteration).requirements[0]

    monkeypatch.setattr(
        runner, "execute_plan",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("translation must not acquire")),
    )
    intent = intent_for(requirement)
    assert intent.property == "tensile_strength"


# ====================================================================
# 10 + Step 6.7. the complete path, and many mechanisms per intent
# ====================================================================

def test_complete_path_from_acquired_evidence_to_acquisition_intent(tmp_path):
    """Item 10 -- the stop condition, end to end, deterministically."""
    pool, iteration, candidate, (s0, s1, s2) = trajectory(tmp_path)

    # acquired evidence really is what the analysis rests on
    acquired = [o for o in pool.all_observations() if o.extraction_method == "json:graph_dataset_v1"]
    assert len(acquired) == 2

    gap = diagnose_information_gap(s1, candidate, iteration)
    assert gap.state_id == s1.id and gap.requirements

    intents = intents_for(gap)
    assert len(intents) == 1
    intent = intents[0]
    assert (intent.subject_natural_key, intent.property, intent.role) == (
        FORMULATION, "tensile_strength", "OBSERVED"
    )

    # the intent is reproducible from the same trajectory, and it is the
    # last thing this phase produces -- nothing executes it
    assert intents_for(diagnose_information_gap(s1, candidate, iteration))[0].id == intent.id
    assert diagnose_information_gap(s0, candidate, iteration).state_id == s0.id
    assert diagnose_information_gap(s2, candidate, iteration).state_id == s2.id


def test_one_intent_can_be_satisfied_by_structurally_different_mechanisms(tmp_path):
    """Step 6.7, the invariant the brief calls out as most important.

    The SAME intent is satisfied twice by genuinely different mechanisms:
    a real DAF acquisition, and direct manual admission by an operator
    with no DAF involvement at all. The intent is byte-identical in both
    cases, because it names no mechanism.

    Only two mechanisms are exercised -- the point is that the
    abstraction does not PREVENT others, not that they all exist."""
    intent = make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property="tensile_strength", role="OBSERVED", target_context={},
    )

    # --- mechanism A: the real DAF acquisition pipeline ----------------
    daf_pool = acquire_measurements(
        tmp_path / "via_daf", [measurement("ts-101", 83), measurement("ts-102", 86)]
    )
    daf_values = {
        o.content["value"] for o in daf_pool.all_observations()
        if o.content.get("property") == intent.property
    }
    assert daf_values == {83, 86}

    # --- mechanism B: manual admission, no DAF whatsoever --------------
    manual_pool = acquire_measurements(tmp_path / "via_manual", [measurement("seed", 80)])
    formulation = next(r for r in manual_pool.all_referents() if r.natural_key == FORMULATION)
    process = next(r for r in manual_pool.all_referents() if r.natural_key == PROCESS)
    document_id = manual_pool.get_record(manual_pool.all_observations()[0].record_ids[0]).document_id

    record = make_record(document_id=document_id, locator="lab-notebook-p7", raw_content="manual entry")
    admit_record(manual_pool, record)
    manual_pool.put_record(record)
    observation = make_observation(
        record_ids=(record.id,), extraction_method="human_transcription",
        content={"property": intent.property, "value": 90, "unit": "MPa"},
        confidence=1.0, extracted_at="2026-08-25T03:00:00Z",
    )
    admit_observation(manual_pool, observation)
    manual_pool.put_observation(observation)
    relationship = make_claimed_relationship(
        from_referent_id=formulation.id, to_referent_id=process.id,
        type="tested_during", observation_id=observation.id, confidence=1.0,
    )
    admit_claimed_relationship(manual_pool, relationship)
    manual_pool.put_claimed_relationship(relationship)

    manual_values = {
        o.content["value"] for o in manual_pool.all_observations()
        if o.content.get("property") == intent.property
    }
    assert 90 in manual_values
    assert {o.extraction_method for o in manual_pool.all_observations()} == {
        "json:graph_dataset_v1", "human_transcription"
    }, "two genuinely different provenances in one pool"

    # the intent did not change to accommodate either mechanism
    assert intent == make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property="tensile_strength", role="OBSERVED", target_context={},
    )
    assert not {"source_id", "adapter_id", "plan_id", "url", "parameters", "mechanism"} & set(
        intent.__dataclass_fields__
    )


# ====================================================================
# Step 7. information value stays connected, and stays honest
# ====================================================================

def test_the_seam_connects_to_information_value_without_estimating_gain(tmp_path):
    """Step 7. The existing information-value machinery is reachable from
    the gap and travels with it; `expected_information_gain` remains
    NOT_DETERMINABLE at every point, including where the OBSERVED value
    is a real number."""
    _pool, iteration, candidate, (_s0, _s1, s2) = trajectory(tmp_path)
    gap = diagnose_information_gap(s2, candidate, iteration)

    assert gap.estimate.estimate == 16.0, "observed information value is determinate at S2"
    assert gap.expected_information_gain == NOT_DETERMINABLE
    assert gap.estimate.information_value.expected_information_gain == NOT_DETERMINABLE

    # the same machinery, called directly, agrees -- the seam composed it
    # rather than reimplementing it
    direct = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(s2))
    assert direct == gap.estimate

    # and the intent carries neither number, in either direction
    intent = intents_for(gap)[0]
    assert not any(
        field in intent.__dataclass_fields__
        for field in ("estimate", "expected_information_gain", "information_value", "priority")
    )


def test_intent_json_shape_is_readable_without_any_scientific_import():
    """A practical consequence of neutrality: an intent reduces to plain
    JSON, so an operator, a queue, or a scheduler can carry it without
    importing `materials`, `science`, or `daf`."""
    intent = make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property="tensile_strength", role="OBSERVED", target_context=AT_25C,
    )
    payload = {
        "id": intent.id, "subject_natural_key": intent.subject_natural_key,
        "subject_kind": intent.subject_kind, "property": intent.property,
        "role": intent.role, "target_context": dict(intent.target_context),
    }
    round_tripped = json.loads(json.dumps(payload, sort_keys=True))
    assert round_tripped["target_context"] == {"temperature": 25, "temperature_unit": "C"}
    assert round_tripped["id"] == intent.id
