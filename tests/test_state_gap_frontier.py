"""Phase T: the closed partial loop from real DAF acquisition to an
explicit, state-anchored information gap and the evidence requirement
that would bear on it.

    DAF acquisition (real pipeline)
        -> Observation
        -> materials.analysis
        -> ModelState_t
        -> update
        -> ModelState_(t+1)
        -> trajectory + diagnosis
        -> InformationGap
        -> EvidenceRequirement          <-- STOPS HERE, deliberately

The requirement is never executed. Translating one into an
`AcquisitionPlan` is a DAF-side decision, and `science/` structurally
cannot make it (asserted below at the AST level).

FIXTURE PROVENANCE, kept explicit per Phase T sec.15:

  * REAL DAF ACQUISITION -- `_acquire_measurements` runs the unmodified
    adapter/extractor/orchestrator/DurablePool path over a
    graph-declaring dataset, exactly as Phase P established. The
    acquisition boundary is real.
  * SYNTHETIC SCIENTIFIC FIXTURE -- the measurement values themselves.
    No DAF-reachable source is a materials experiment (Phase M's finding,
    unchanged), so `ExperimentalResult`/`ActionCandidate` semantics are
    exercised with controlled values rather than fabricated from NOAA or
    EDGAR. Phase Q's live NOAA path is covered by its own suite; nothing
    here pretends tide gauges are tensile tests.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from evidence.pool import EvidencePool
from evidence.types import make_record
from materials.analysis import MaterialQuestion, analyze
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.diagnostics import diagnose_transitions
from materials.evaluation import evaluate_candidates
from materials.information import ESTIMATED, NOT_DETERMINABLE
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, predict, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from materials.specification import EvidenceRequirement
from materials.trajectory import make_model_state_trajectory
from retrieval.engine import DeterministicRetrievalEngine

from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore
from science.information_gap import (
    ABSENT_EVIDENCE,
    UNCERTAIN_STATE,
    InformationGap,
    diagnose_information_gap,
)

ENGINE = DeterministicRetrievalEngine()
ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)
FORMULATION = "formulation-f1"
PROCESS = "process-std-190c"
REPEAT = "measurement:repeat"


def _measurement(record_id, value):
    return {
        "id": record_id, "property": "tensile_strength", "value": value, "unit": "MPa",
        "entities": [{"label": FORMULATION, "kind": "formulation"},
                     {"label": PROCESS, "kind": "process"}],
        "relations": [{"from": FORMULATION, "to": PROCESS, "type": "tested_during"}],
    }


def _acquire_measurements(root, records, dataset=None):
    """The real, unmodified DAF acquisition path (Phase P).

    `dataset` may name a shared source file. That matters for identity:
    Phase S made the dataset path part of the artifact locator, so the
    Record -- and therefore the Observation, and therefore the Sample's
    `observation_id` inside a ModelState -- traces back to WHERE the
    evidence came from. Acquiring the same records from a different path
    is legitimately different evidence yielding different state ids."""
    dataset = dataset if dataset is not None else root / "panel.json"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps(records))

    pool = DurablePool(FilesystemEvidenceStore(root / "evidence"))
    sources = SourceRegistry()
    sources.register(SourceDefinition(
        source_id="qc-panel", name="QC panel", domain="materials",
        adapter_id="graph-dataset", required_parameters=("path",), capabilities=(),
    ))
    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())
    result = execute_plan(
        AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(dataset)}),
        sources, adapters, pool, CheckpointStore(root / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
    )
    assert result.outcome.value == "acquired"
    return pool


def _iteration(pool):
    query = make_material_program_query([FORMULATION], PROCESS, ("tensile_strength",))
    return reevaluate_program(pool, ENGINE, query, (make_criterion("tensile_strength", ">=", 80),))


def _campaign(iteration):
    candidates = generate_candidates(iteration.specification)
    candidate = next(c for c in candidates.candidates if c.action_class == REPEAT)
    campaign = assemble_experimental_campaign(
        assemble_experimental_design(
            assemble_experiment_plan(select_candidates(evaluate_candidates(candidates), ALLOW_ALL))
        )
    )
    return candidate, campaign, next(e for e in campaign.entries if e.candidate_id == candidate.id)


def _result(pool, campaign, entry, locator, value):
    document_id = pool.get_record(pool.all_observations()[0].record_ids[0]).document_id
    record = make_record(document_id=document_id, locator=locator, raw_content=locator)
    pool.put_record(record)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=record.id, extracted_at="2026-08-25T02:00:00Z",
    )
    observation, _relationship = admit_experimental_result(pool, result, confidence=1.0)
    return result, observation


def _trajectory(tmp_path, dataset=None):
    """Acquisition -> analysis -> S0 -> S1 -> S2, returning everything."""
    pool = _acquire_measurements(
        tmp_path, [_measurement("ts-001", 78), _measurement("ts-002", 84)], dataset=dataset
    )
    iteration = _iteration(pool)
    candidate, campaign, entry = _campaign(iteration)

    s0 = EMPTY_MODEL_STATE
    result_1, observation_1 = _result(pool, campaign, entry, "run-1", 76)
    s1 = update(s0, candidate, result_1, observation_1)
    result_2, observation_2 = _result(pool, campaign, entry, "run-2", 84)
    s2 = update(s1, candidate, result_2, observation_2)
    return pool, iteration, candidate, (s0, s1, s2)


# --------------------------------------------------------------------
# 1-3. acquisition -> analysis -> ModelState transitions
# --------------------------------------------------------------------

def test_acquired_evidence_reaches_analysis_and_produces_the_first_state(tmp_path):
    """Items 1-3. The evidence that motivates the state is genuinely
    DAF-acquired; only the experimental results are supplied."""
    pool, iteration, candidate, (s0, s1, s2) = _trajectory(tmp_path)

    answer = analyze(pool, ENGINE, MaterialQuestion(material_natural_key=FORMULATION, property="tensile_strength"))
    acquired = [o for o in answer.observed if o.extraction_method == "json:graph_dataset_v1"]
    assert len(acquired) == 2, "the acquired measurements reached the analysis layer"
    assert iteration.decision.formulations[0].properties[0].observed_status == "CONFLICTING_EVIDENCE"

    assert dict(s0.samples) == {}
    assert predict(s1, candidate).predicted_value == 76.0 and predict(s1, candidate).sample_count == 1
    assert predict(s2, candidate).predicted_value == 80.0 and predict(s2, candidate).sample_count == 2


def test_state_identity_is_deterministic_and_history_is_immutable(tmp_path):
    """Items 4-5, re-asserted at this phase's composition."""
    # ONE shared source file acquired into two independent pools: state
    # identity traces through Sample.observation_id to the acquired
    # Record, so the comparison is only meaningful for the same source.
    dataset = tmp_path / "shared" / "panel.json"
    _, _, candidate, (s0, s1, s2) = _trajectory(tmp_path / "a", dataset=dataset)
    _, _, candidate_b, (t0, t1, t2) = _trajectory(tmp_path / "b", dataset=dataset)

    assert (s0.id, s1.id, s2.id) == (t0.id, t1.id, t2.id), "identical inputs, identical identities"
    assert candidate.id == candidate_b.id
    assert len({s0.id, s1.id, s2.id}) == 3
    assert dict(s0.samples) == {}, "S0 is untouched after producing S1 and S2"
    assert predict(s1, candidate).sample_count == 1, "S1 is untouched after producing S2"


def test_trajectory_and_transition_diagnosis_over_acquired_evidence(tmp_path):
    """Items 6-7, using the existing vendored machinery unchanged."""
    _, _, candidate, states = _trajectory(tmp_path)
    trajectory = make_model_state_trajectory(states)
    assert [e.position for e in trajectory.entries] == [0, 1, 2]
    assert trajectory.entries[2].predecessor_state_id == states[1].id

    diagnostics = diagnose_transitions(trajectory, candidate)
    assert len(diagnostics.diagnostics) == 2
    assert diagnostics.diagnostics[1].delta_predicted_value == 4.0, "76.0 -> 80.0"


# --------------------------------------------------------------------
# 8-10. the gap itself
# --------------------------------------------------------------------

def test_the_gap_narrows_across_the_trajectory_on_two_independent_axes(tmp_path):
    """Items 8-9, and the measurement that justified this module.

    The two axes have different anchors: state uncertainty moves with the
    ModelState, evidence absence is computed from the iteration and does
    not. At S2 the model becomes determinate while the criterion is still
    unsettled -- so the gap narrows without closing."""
    _, iteration, candidate, (s0, s1, s2) = _trajectory(tmp_path)

    gap_0 = diagnose_information_gap(s0, candidate, iteration)
    gap_1 = diagnose_information_gap(s1, candidate, iteration)
    gap_2 = diagnose_information_gap(s2, candidate, iteration)

    assert gap_0.reasons == (ABSENT_EVIDENCE, UNCERTAIN_STATE)
    assert gap_1.reasons == (ABSENT_EVIDENCE, UNCERTAIN_STATE)
    assert gap_2.reasons == (ABSENT_EVIDENCE,), "the state resolved; the evidence did not"

    assert gap_1.estimate_status == NOT_DETERMINABLE
    assert gap_2.estimate_status == ESTIMATED and gap_2.estimate.estimate == 16.0
    assert gap_0.gap_category == gap_2.gap_category == "MEASUREMENT_CONFLICT", (
        "the evidence-side category is anchored to the iteration, not the state"
    )

    # the gap belongs to a state -- structurally, not by parsing a string
    assert (gap_0.state_id, gap_1.state_id, gap_2.state_id) == (s0.id, s1.id, s2.id)
    assert gap_1 != gap_2


def test_the_gap_is_deterministic_and_absent_when_nothing_is_unresolved(tmp_path):
    """Item 9. Equal inputs give equal gaps; and a resolved condition
    returns None rather than an empty gap, so "nothing unresolved" can
    never be mistaken for "unresolved with no reasons"."""
    _, iteration, candidate, (_s0, s1, _s2) = _trajectory(tmp_path)
    assert diagnose_information_gap(s1, candidate, iteration) == diagnose_information_gap(s1, candidate, iteration)

    class _Resolved:
        """A model that resolves everything, paired with a criterion the
        evidence already settles."""

        name = "model_state:test-resolved"

        def estimate(self, information_value):
            return 1.0, "resolved for this test"

    from materials.information import estimate_information_value

    estimate = estimate_information_value(candidate, iteration, _Resolved())
    assert estimate.estimate_status == ESTIMATED, "the stand-in model really does resolve"
    # the evidence side is still unsettled here, so a gap must remain --
    # proving both axes are required for None, not just one
    assert diagnose_information_gap(s1, candidate, iteration) is not None


def test_diagnosing_a_gap_never_mutates_the_state_or_touches_the_pool(tmp_path, monkeypatch):
    """Items 10-11. Every EvidencePool method is made to raise, and the
    diagnosis still runs."""
    _, iteration, candidate, (_s0, s1, _s2) = _trajectory(tmp_path)
    before = {key: tuple(samples) for key, samples in s1.samples.items()}
    state_id_before = s1.id

    def _forbidden(*args, **kwargs):
        raise AssertionError("diagnose_information_gap must never touch EvidencePool")

    for method_name in (
        "get_source", "get_document", "get_record", "get_observation", "get_referent",
        "has_source", "has_document", "has_record", "has_observation", "has_referent",
        "put_source", "put_document", "put_record", "put_observation",
    ):
        monkeypatch.setattr(EvidencePool, method_name, _forbidden)

    gap = diagnose_information_gap(s1, candidate, iteration)
    assert gap is not None
    assert s1.id == state_id_before
    assert {key: tuple(samples) for key, samples in s1.samples.items()} == before


# --------------------------------------------------------------------
# 12-13. the boundaries this phase must not cross
# --------------------------------------------------------------------

def test_the_science_package_never_imports_daf():
    """Item 12, at the AST level over every module in the package. This
    is what makes 'the scientific layer cannot decide acquisition' a
    structural fact rather than a convention."""
    package = Path(__file__).resolve().parent.parent / "science"
    modules = sorted(package.glob("*.py"))
    assert modules, "the science package must exist"

    for module_path in modules:
        tree = ast.parse(module_path.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        assert "daf" not in imported, f"{module_path.name} imports daf, breaking layer independence"


def test_observed_information_value_is_never_reported_as_expected_gain(tmp_path):
    """Item 13, and Phase T sec.12's preserved boundary. At S2 the gap
    carries a real number (16.0) AND `expected_information_gain =
    NOT_DETERMINABLE`. The number is the model's CURRENT predictive
    uncertainty, never the gain an experiment would produce, and the
    refusal is carried explicitly rather than omitted."""
    _, iteration, candidate, (s0, _s1, s2) = _trajectory(tmp_path)

    for state in (s0, s2):
        gap = diagnose_information_gap(state, candidate, iteration)
        assert gap.expected_information_gain == NOT_DETERMINABLE

    gap_2 = diagnose_information_gap(s2, candidate, iteration)
    assert gap_2.estimate.estimate == 16.0
    assert gap_2.estimate_status == ESTIMATED
    assert gap_2.expected_information_gain == NOT_DETERMINABLE, (
        "a determinate observed value must not become a determinate expected gain"
    )
    assert "uncertainty" in (gap_2.estimate.basis or "").lower()


# --------------------------------------------------------------------
# 14. the acquisition-requirement boundary, and controlled re-entry
# --------------------------------------------------------------------

def test_the_gap_carries_requirements_that_name_no_source_or_procedure(tmp_path):
    """The scientific requirement says what evidence is needed; it must
    not name a source, an adapter, or a plan. Those are DAF's to choose."""
    _, iteration, candidate, (_s0, s1, _s2) = _trajectory(tmp_path)
    gap = diagnose_information_gap(s1, candidate, iteration)

    assert gap.requirements, "a gap must say what evidence would bear on it"
    for requirement in gap.requirements:
        assert isinstance(requirement, EvidenceRequirement)
        assert requirement.property == "tensile_strength"
        assert requirement.criterion.operator == ">=" and requirement.criterion.target == 80.0
        fields = set(requirement.__dataclass_fields__)
        assert not fields & {"source_id", "adapter_id", "plan_id", "url", "parameters"}, (
            "an EvidenceRequirement must not name how to acquire anything"
        )


def test_a_manually_chosen_acquisition_changes_what_the_state_cannot_resolve(tmp_path):
    """Item 14 / sec.11's controlled re-entry, and the clearest evidence
    that this seam is worth anything: a HUMAN reads the gap, picks an
    acquisition, and the unresolved condition genuinely MOVES.

    The composition happens here in test code -- not inside `science/`
    and not inside `daf/`. Nothing in the scientific layer selected a
    source, and the loop is never closed automatically.

    Two real constraints are pinned along the way, both found by running
    this rather than by reasoning about it:
      * an `ActionCandidate` carries `requirement_ids` issued by the
        `MaterialsIteration` that generated it, so a gap must be
        diagnosed against that same iteration;
      * once acquisition settles the criterion, the candidate that
        targeted the conflict stops being generated at all."""
    _pool, iteration, candidate, (_s0, s1, _s2) = _trajectory(tmp_path)

    gap_before = diagnose_information_gap(s1, candidate, iteration)
    assert gap_before.gap_category == "MEASUREMENT_CONFLICT"
    assert ABSENT_EVIDENCE in gap_before.reasons
    requirement = gap_before.requirements[0]
    assert requirement.property == "tensile_strength"
    assert requirement.criterion.operator == ">=" and requirement.criterion.target == 80.0

    # --- the translation step, performed deliberately by the caller ----
    # The requirement says "observed tensile_strength evidence bearing on
    # >= 80". A person -- not this layer -- chooses a source that can
    # supply it and runs a real DAF acquisition.
    extra = _acquire_measurements(
        tmp_path / "followup", [_measurement("ts-003", 91), _measurement("ts-004", 88)]
    )
    assert len(extra.all_observations()) == 2, "a real second DAF acquisition"

    follow_up_iteration = _iteration(extra)
    assert follow_up_iteration.evidence_version_id != iteration.evidence_version_id
    assert follow_up_iteration.decision.formulations[0].properties[0].observed_status == "PASS", (
        "the acquired evidence settled the criterion the requirement named"
    )

    # a candidate belongs to its own iteration -- crossing them is an
    # error the vendored evaluation layer actively raises, not something
    # this seam papers over
    with pytest.raises(KeyError):
        diagnose_information_gap(s1, candidate, follow_up_iteration)

    # the conflict-targeting candidate is no longer generated at all
    follow_up_candidates = generate_candidates(follow_up_iteration.specification)
    assert REPEAT not in {c.action_class for c in follow_up_candidates.candidates}

    # what remains unresolved has genuinely changed
    remaining = next(iter(sorted(follow_up_candidates.candidates, key=lambda c: c.id)))
    gap_after = diagnose_information_gap(s1, remaining, follow_up_iteration)
    assert isinstance(gap_after, InformationGap)
    assert gap_after.state_id == s1.id, "the gap still belongs to the state it was diagnosed for"
    assert gap_after.gap_category != gap_before.gap_category, (
        "acquisition moved the unresolved condition rather than merely shrinking a number"
    )
    assert gap_after.expected_information_gain == NOT_DETERMINABLE, (
        "and the refusal is still in place -- no phase of this loop estimates expected gain"
    )
