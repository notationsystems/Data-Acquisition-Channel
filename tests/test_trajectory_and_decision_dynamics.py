"""Phase O: the State-Space system inspecting its own trajectory and
making an explicit scientific decision about what should happen next --

    S0
      -> predict
      -> candidate comparison
      -> experiment
      -> S1
      -> transition analysis
      -> information update
      -> next legitimate decision
      -> S2

proven end to end against a real daf.storage.durable_pool.DurablePool.

THE AUDIT'S CENTRAL FINDING (docs/PHASE_15_TRAJECTORY_AND_DECISION_DYNAMICS.md):
every mechanism this phase asks for ALREADY EXISTS in the vendored
State-Space system, built by its own Phases 56-57 -- `materials.trajectory`
(`ModelStateTrajectory`/`prediction_evolution`/`compare_predictions`) and
`materials.diagnostics.diagnose_transitions` are precisely the
"trajectory representation" and "analyze_transition(S_t, S_(t+1)) ->
TransitionAnalysis" this phase describes, and `materials.value`/
`materials.utility`/`materials.ranking` are precisely its
"candidate comparison". No new production code is therefore written in
this phase, in DAF or in the vendored packages; what did not exist
anywhere is the COMPOSITION of those layers into the single closed
decision cycle the stop condition names, exercised over DAF's own
durable pool. That composition is what this module proves.

TWO DISTINCTIONS THIS MODULE IS CAREFUL NEVER TO BLUR, both of which the
vendored architecture already encodes structurally:

  OBSERVED information value -- what
  `materials.model_state.ModelStateInformationValueModel` reads off a
  ModelState that already exists (`predict(state, candidate).uncertainty`).
  A real number once >= 2 samples exist; NOT_DETERMINABLE before that.

  EXPECTED information gain -- what a candidate WOULD teach if run.
  `materials.value.CandidateInformationValue.expected_information_gain`
  is hard-coded to NOT_DETERMINABLE (vendored `materials/value.py`), and
  this phase does not invent an estimator for it. Ranking therefore
  operates only on caller-SUPPLIED benefit/cost, never on an estimated
  information gain -- the exact seam section 9 asks to be documented
  rather than filled, asserted directly in
  `test_candidate_comparison_at_a_single_state`.
"""

from __future__ import annotations

import pytest
from evidence.admission import admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source
from materials.assessment import assess
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.diagnostics import diagnose_transitions
from materials.evaluation import evaluate_candidates
from materials.information import NOT_DETERMINABLE, estimate_information_value
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, ModelStateInformationValueModel, predict, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.ranking import DESCENDING, RANKED, UNRANKED, RankingPolicy, rank_candidates
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from materials.trajectory import compare_predictions, make_model_state_trajectory, prediction_evolution
from materials.utility import ExperimentUtilityInput, evaluate_utility_set
from materials.value import evaluate_candidate_information_values
from retrieval.engine import DeterministicRetrievalEngine

from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

REPEAT = "measurement:repeat"
VALIDATION = "model_validation:unspecified"

ENGINE = DeterministicRetrievalEngine()
ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


def _pool(root):
    return DurablePool(FilesystemEvidenceStore(root))


def _build_campaign(pool):
    """The existing campaign-assembly pipeline against a real DurablePool
    -- the same proven recipe tests/test_experimental_state_loop.py and
    tests/test_model_state_integration.py already use, kept self-contained
    per this repository's existing one-module-one-fixture test convention."""
    source = make_source(kind="lab_notebook", name="QC")
    pool.put_source(source)
    doc = make_document(
        source_id=source.id, raw_content="panel", retrieval_method="manual_entry", retrieved_at="2026-08-23T00:00:00Z"
    )
    admit_document(pool, doc)
    pool.put_document(doc)
    process = make_referent(natural_key="process-std-190c", kind="process")
    admit_referent(pool, process)
    pool.put_referent(process)
    formulation = make_referent(natural_key="formulation-f1", kind="formulation")
    admit_referent(pool, formulation)
    pool.put_referent(formulation)

    for locator, value in (("ts-a", 78), ("ts-b", 84)):
        rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
        admit_record(pool, rec)
        pool.put_record(rec)
        obs = make_observation(
            record_ids=(rec.id,), extraction_method="human_transcription",
            content={"property": "tensile_strength", "value": value, "unit": "MPa"},
            confidence=1.0, extracted_at="2026-08-23T00:00:00Z",
        )
        admit_observation(pool, obs)
        pool.put_observation(obs)
        rel = make_claimed_relationship(
            from_referent_id=formulation.id, to_referent_id=process.id,
            type="tested_during", observation_id=obs.id, confidence=1.0,
        )
        admit_claimed_relationship(pool, rel)
        pool.put_claimed_relationship(rel)

    criterion = make_criterion("tensile_strength", ">=", 80)
    query = make_material_program_query(["formulation-f1"], "process-std-190c", ("tensile_strength",))
    iteration = reevaluate_program(pool, ENGINE, query, (criterion,))
    candidates = generate_candidates(iteration.specification)
    candidate = next(c for c in candidates.candidates if c.action_class == REPEAT)

    evaluations = evaluate_candidates(candidates)
    selection = select_candidates(evaluations, ALLOW_ALL)
    plan = assemble_experiment_plan(selection)
    design = assemble_experimental_design(plan)
    campaign = assemble_experimental_campaign(design)
    entry = next(e for e in campaign.entries if e.candidate_id == candidate.id)

    return doc, iteration, candidate, campaign, entry


def _run_result(pool, doc, campaign, entry, locator, value):
    """ExperimentalCampaignEntry -> ExperimentalResult -> Observation."""
    rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    )
    observation, relationship = admit_experimental_result(pool, result, confidence=1.0)
    return result, observation, relationship


def _walk_two_transitions(pool):
    """S0 -> S1 -> S2 for one candidate, keeping every intermediate object
    the trajectory/diagnostics layers need: each transition's prediction is
    assessed against the observation that actually produced the NEXT state
    (materials.assessment.assess), which is exactly the pairing
    diagnose_transitions expects."""
    doc, iteration, candidate, campaign, entry = _build_campaign(pool)

    s0 = EMPTY_MODEL_STATE
    p0 = predict(s0, candidate)
    result_1, observation_1, _ = _run_result(pool, doc, campaign, entry, "run-1", 76)
    assessment_0 = assess(p0, result_1, observation_1)
    s1 = update(s0, candidate, result_1, observation_1)

    p1 = predict(s1, candidate)
    result_2, observation_2, _ = _run_result(pool, doc, campaign, entry, "run-2", 84)
    assessment_1 = assess(p1, result_2, observation_2)
    s2 = update(s1, candidate, result_2, observation_2)

    return {
        "doc": doc, "iteration": iteration, "candidate": candidate,
        "campaign": campaign, "entry": entry,
        "states": (s0, s1, s2), "predictions": (p0, p1),
        "assessments": (assessment_0, assessment_1),
        "observations": (observation_1, observation_2),
        "results": (result_1, result_2),
    }


def test_stop_condition_trajectory_walk(tmp_path):
    """The complete cycle the stop condition names, object by object.
    Every arrow below is an existing, unmodified vendored operation; this
    test asserts what each one actually produced rather than only that it
    succeeded."""
    pool = _pool(tmp_path / "evidence")
    doc, iteration, candidate, campaign, entry = _build_campaign(pool)

    # --- S0 -------------------------------------------------------------
    s0 = EMPTY_MODEL_STATE
    assert dict(s0.samples) == {}

    # --- S0 -> prediction ----------------------------------------------
    p0 = predict(s0, candidate)
    assert p0.state_id == s0.id, "prediction must name the state it was read from"
    assert p0.predicted_value is None and p0.uncertainty is None and p0.sample_count == 0

    # --- prediction -> candidate comparison (an explicit decision) ------
    candidate_set = generate_candidates(iteration.specification)
    assert {c.action_class for c in candidate_set.candidates} == {REPEAT, VALIDATION}
    information_values = evaluate_candidate_information_values(candidate_set, iteration)
    utilities = evaluate_utility_set(
        information_values, {candidate.id: ExperimentUtilityInput(benefit=10.0, cost=2.0)}
    )
    ranking = rank_candidates(utilities, RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED))
    chosen = next(r for r in ranking.rankings if r.rank == 1)
    assert chosen.candidate_id == candidate.id, "the ranked-first candidate is the one carried into the experiment"

    # --- candidate -> experiment -> Observation --------------------------
    result_1, observation_1, relationship_1 = _run_result(pool, doc, campaign, entry, "run-1", 76)
    assert result_1.candidate_id == candidate.id
    assert observation_1.content["value"] == 76
    assert relationship_1.observation_id == observation_1.id
    assert pool.has_observation(observation_1.id), "the evidence is explicit and durably admitted"

    # --- prediction assessed against the observation that produced S1 ----
    assessment_0 = assess(p0, result_1, observation_1)
    assert assessment_0.state_id == s0.id and assessment_0.candidate_id == candidate.id
    assert assessment_0.observed_value == 76.0
    assert assessment_0.residual is None, "no predicted value at S0, so no residual -- never guessed as zero"

    # --- experiment -> S1 ------------------------------------------------
    s1 = update(s0, candidate, result_1, observation_1)
    assert s1.id != s0.id
    assert dict(s0.samples) == {}, "S0 remains immutable after producing S1"

    p1 = predict(s1, candidate)
    assert p1.state_id == s1.id and p1.predicted_value == 76.0 and p1.sample_count == 1

    # --- S1 -> transition analysis --------------------------------------
    trajectory_1 = make_model_state_trajectory((s0, s1))
    assert [e.position for e in trajectory_1.entries] == [0, 1]
    assert trajectory_1.entries[0].predecessor_state_id is None
    assert trajectory_1.entries[1].predecessor_state_id == s0.id

    diagnostics_1 = diagnose_transitions(trajectory_1, candidate, (assessment_0,))
    assert len(diagnostics_1.diagnostics) == 1
    d0 = diagnostics_1.diagnostics[0]
    assert (d0.predecessor_state_id, d0.successor_state_id) == (s0.id, s1.id)
    assert d0.observation_value == 76.0
    assert d0.assessment is assessment_0, "the assessment is embedded whole, never reconstructed"
    assert d0.delta_predicted_value is None, "S0 had no predicted value; a delta against None is None"

    # --- information update ---------------------------------------------
    before = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(s0))
    after = estimate_information_value(candidate, iteration, ModelStateInformationValueModel(s1))
    assert before.model_name == f"model_state:{s0.id}"
    assert after.model_name == f"model_state:{s1.id}"
    assert before.estimate_status == after.estimate_status == NOT_DETERMINABLE

    # --- next legitimate decision (over the pool the experiment enlarged) -
    next_iteration = reevaluate_program(pool, ENGINE, iteration.query, iteration.criteria)
    assert next_iteration.evidence_version_id != iteration.evidence_version_id, (
        "the new experimental evidence is visible to the next decision"
    )
    next_candidates = generate_candidates(next_iteration.specification)
    assert any(c.action_class == REPEAT for c in next_candidates.candidates), (
        "the decision layer still proposes a legitimate next experiment"
    )

    # --- S1 -> S2 ---------------------------------------------------------
    result_2, observation_2, _ = _run_result(pool, doc, campaign, entry, "run-2", 84)
    assessment_1 = assess(p1, result_2, observation_2)
    assert assessment_1.residual == 8.0, "84 observed against 76 predicted"
    s2 = update(s1, candidate, result_2, observation_2)

    trajectory = make_model_state_trajectory((s0, s1, s2))
    diagnostics = diagnose_transitions(trajectory, candidate, (assessment_0, assessment_1))
    assert len(diagnostics.diagnostics) == 2
    d1 = diagnostics.diagnostics[1]
    assert (d1.predecessor_state_id, d1.successor_state_id) == (s1.id, s2.id)
    assert d1.delta_predicted_value == 4.0, "76.0 -> 80.0"
    assert d1.delta_uncertainty is None, "S1 had no uncertainty (n=1); a delta against None is None"
    assert d1.residual_against_previous_prediction == 8.0
    assert d1.observation_value == 84.0

    # every historical state survives the whole walk untouched
    assert dict(s0.samples) == {}
    assert predict(s1, candidate).predicted_value == 76.0
    assert predict(s2, candidate).predicted_value == 80.0
    assert len({s0.id, s1.id, s2.id}) == 3


def test_candidate_comparison_at_a_single_state(tmp_path):
    """Section 18: two legitimate candidates against the same state, and
    exactly what the architecture can and cannot compare between them.

    CAN compare: structural information value (gap category, current
    status, value kind) and caller-SUPPLIED utility.
    CANNOT compare: expected information gain -- structurally
    NOT_DETERMINABLE for every candidate, and this phase does not
    estimate it."""
    pool = _pool(tmp_path / "evidence")
    _doc, iteration, candidate, _campaign, _entry = _build_campaign(pool)
    candidate_set = generate_candidates(iteration.specification)
    repeat = next(c for c in candidate_set.candidates if c.action_class == REPEAT)
    validation = next(c for c in candidate_set.candidates if c.action_class == VALIDATION)
    assert repeat.id == candidate.id and repeat.id != validation.id

    information_values = evaluate_candidate_information_values(candidate_set, iteration)
    by_id = {v.candidate_id: v for v in information_values.values}

    # structural comparison IS supported, and the two differ meaningfully
    assert by_id[repeat.id].value_kind == "TESTS_CONFLICT"
    assert by_id[repeat.id].current_status == "CONFLICTING_EVIDENCE"
    assert by_id[validation.id].value_kind == "RESOLVES_MISSING_EVIDENCE"
    assert by_id[validation.id].current_status == "INSUFFICIENT_EVIDENCE"

    # THE SEAM: expected information gain is never estimated, for either
    assert by_id[repeat.id].expected_information_gain == NOT_DETERMINABLE
    assert by_id[validation.id].expected_information_gain == NOT_DETERMINABLE

    # ranking operates only on caller-supplied benefit/cost
    utilities = evaluate_utility_set(
        information_values, {repeat.id: ExperimentUtilityInput(benefit=10.0, cost=2.0)}
    )
    by_candidate = {u.candidate_id: u for u in utilities.utilities}
    assert by_candidate[repeat.id].utility == 8.0
    assert by_candidate[validation.id].utility is None, "nothing was supplied, and nothing is guessed"

    ranking = rank_candidates(utilities, RankingPolicy(direction=DESCENDING, unknown_utility_policy=UNRANKED))
    ranked = {r.candidate_id: r for r in ranking.rankings}
    assert (ranked[repeat.id].rank, ranked[repeat.id].ranking_status) == (1, RANKED)
    assert (ranked[validation.id].rank, ranked[validation.id].ranking_status) == (None, NOT_DETERMINABLE), (
        "an unsupplied utility is listed but never ranked -- never silently placed last as if judged"
    )


def test_information_gap_closes_across_the_trajectory(tmp_path):
    """Section 17: a controlled case where information is insufficient at
    S0, an experiment resolves it, and the information STATUS differs
    afterwards -- expressed purely through existing information/value
    semantics, with no expected-information-gain prediction anywhere."""
    walk = _walk_two_transitions(_pool(tmp_path / "evidence"))
    candidate, iteration = walk["candidate"], walk["iteration"]
    s0, s1, s2 = walk["states"]

    estimates = [
        estimate_information_value(candidate, iteration, ModelStateInformationValueModel(state))
        for state in (s0, s1, s2)
    ]
    assert [e.estimate_status for e in estimates] == [NOT_DETERMINABLE, NOT_DETERMINABLE, "ESTIMATED"]
    assert [e.estimate for e in estimates] == [None, None, 16.0]

    # the STRUCTURAL information value is identical at every state -- only
    # the model-derived number changed. The two must never be conflated.
    assert estimates[0].information_value == estimates[2].information_value
    assert estimates[0].model_name != estimates[2].model_name


def test_trajectory_and_diagnostics_are_deterministic_across_independent_runs(tmp_path):
    """Section 15: the entire cycle run twice from independent initial
    objects and independent on-disk pools. State identities, transition
    analysis, and candidate evaluation must all match exactly."""

    def _run(root):
        pool = _pool(root)
        walk = _walk_two_transitions(pool)
        candidate = walk["candidate"]
        trajectory = make_model_state_trajectory(walk["states"])
        diagnostics = diagnose_transitions(trajectory, candidate, walk["assessments"])
        information_values = evaluate_candidate_information_values(
            generate_candidates(walk["iteration"].specification), walk["iteration"]
        )
        return {
            "state_ids": tuple(s.id for s in walk["states"]),
            "candidate_id": candidate.id,
            "deltas": tuple(
                (d.predecessor_state_id, d.successor_state_id, d.delta_predicted_value, d.delta_uncertainty,
                 d.observation_value, d.residual_against_previous_prediction)
                for d in diagnostics.diagnostics
            ),
            "evaluation": tuple(
                (v.candidate_id, v.value_kind, v.current_status, v.expected_information_gain)
                for v in information_values.values
            ),
        }

    first, second = _run(tmp_path / "a"), _run(tmp_path / "b")
    assert first["state_ids"] == second["state_ids"], "S0, S1 and S2 identities all reproduce"
    assert len(set(first["state_ids"])) == 3
    assert first["candidate_id"] == second["candidate_id"]
    assert first["deltas"] == second["deltas"], "transition analysis reproduces exactly"
    assert first["evaluation"] == second["evaluation"], "candidate evaluation reproduces exactly"


def test_new_evidence_alone_does_not_advance_the_trajectory(tmp_path):
    """Sections 13/16, re-proven at the trajectory level: admitting further
    evidence into the very pool the trajectory was built over changes
    neither any existing state, nor the trajectory, nor its diagnostics.
    A state transition requires an explicit update() call and nothing
    else can substitute for one."""
    pool = _pool(tmp_path / "evidence")
    walk = _walk_two_transitions(pool)
    candidate = walk["candidate"]
    trajectory = make_model_state_trajectory(walk["states"])
    diagnostics_before = diagnose_transitions(trajectory, candidate, walk["assessments"])
    state_ids_before = tuple(s.id for s in walk["states"])

    # a real, admitted experimental result -- deliberately never applied
    _result, observation, _relationship = _run_result(
        pool, walk["doc"], walk["campaign"], walk["entry"], "run-unapplied", 999
    )
    assert pool.has_observation(observation.id), "the new evidence really is in the pool"

    assert tuple(s.id for s in walk["states"]) == state_ids_before
    assert diagnose_transitions(trajectory, candidate, walk["assessments"]) == diagnostics_before
    assert predict(walk["states"][2], candidate).predicted_value == 80.0, (
        "the value 999 never entered any state, because update() was never called for it"
    )

    # and the acquisition-side pool growth is not itself a scientific step
    assert len(make_model_state_trajectory(walk["states"]).entries) == 3


def test_trajectory_rejects_a_sequence_no_update_chain_could_produce(tmp_path):
    """The trajectory layer's own structural invariant: ordering is
    caller-supplied but verified, never inferred. A misordered sequence is
    rejected rather than silently accepted and analysed."""
    walk = _walk_two_transitions(_pool(tmp_path / "evidence"))
    s0, s1, s2 = walk["states"]

    assert len(make_model_state_trajectory((s0, s1, s2)).entries) == 3
    with pytest.raises(ValueError, match="not a valid successor"):
        make_model_state_trajectory((s2, s1))
    with pytest.raises(ValueError, match="at least one ModelState"):
        make_model_state_trajectory(())


def test_transition_analysis_never_reaches_the_evidence_pool(tmp_path, monkeypatch):
    """Section 7's boundary, proven directly: the trajectory/diagnostics
    layer analyses objects the caller already holds. Every EvidencePool
    method is made to raise, and the full analysis still runs."""
    pool = _pool(tmp_path / "evidence")
    walk = _walk_two_transitions(pool)
    candidate = walk["candidate"]

    def _forbidden(*args, **kwargs):
        raise AssertionError("trajectory analysis must never touch EvidencePool")

    for method_name in (
        "get_source", "get_document", "get_record", "get_observation", "get_referent",
        "has_source", "has_document", "has_record", "has_observation", "has_referent",
        "put_source", "put_document", "put_record", "put_observation",
    ):
        monkeypatch.setattr(EvidencePool, method_name, _forbidden)

    trajectory = make_model_state_trajectory(walk["states"])
    steps = prediction_evolution(trajectory, candidate, walk["assessments"])
    assert [s.prediction.predicted_value for s in steps] == [None, 76.0, 80.0]

    diagnostics = diagnose_transitions(trajectory, candidate, walk["assessments"])
    assert [d.delta_predicted_value for d in diagnostics.diagnostics] == [None, 4.0]

    delta = compare_predictions(steps[1].prediction, steps[2].prediction)
    assert delta.delta_predicted_value == 4.0
    assert delta.from_state_id == walk["states"][1].id and delta.to_state_id == walk["states"][2].id
