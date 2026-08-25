"""Phase N: the smallest complete, executable scientific state-transition
loop --

    ModelState_t -> predict -> ActionCandidate -> ExperimentalCampaign ->
    ExperimentalCampaignEntry -> ExperimentalResult -> Observation ->
    update() -> ModelState_(t+1)

-- proven end to end, object by object, using exclusively existing,
unmodified vendored `materials`/`evidence` machinery (the same
campaign-assembly recipe Phase M's `tests/test_model_state_integration.py`
already proved works against a real `daf.storage.durable_pool.DurablePool`)
plus a genuinely new piece of coverage neither Phase M nor the vendored
suite exercises directly: `materials.information.estimate_information_value`
wrapped around `materials.model_state.ModelStateInformationValueModel`,
compared BEFORE and AFTER a real state transition.

No new production code exists anywhere in this phase -- the audit
(documented in docs/PHASE_14_EXPERIMENTAL_STATE_LOOP.md) found the
existing `materials.model_state`/`materials.results`/`materials.candidates`/
`materials.campaign`/`materials.information` API already sufficient for
every requirement below.
"""

from __future__ import annotations

from evidence.admission import admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent
from evidence.types import make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.information import NOT_DETERMINABLE, estimate_information_value
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, ModelStateInformationValueModel, predict, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from retrieval.engine import DeterministicRetrievalEngine

from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

ENGINE = DeterministicRetrievalEngine()
ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


def _build_campaign(pool):
    """The existing campaign-assembly pipeline, called end to end against
    a real daf.storage.durable_pool.DurablePool (section 16: durable
    evidence and scientific state transition coexisting without coupling
    their ownership) -- mirrors the proven recipe from
    vendor/scout-retrieval-agent/tests/test_materials_model_state.py and
    tests/test_model_state_integration.py exactly, reused rather than
    reinvented."""
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
    candidate = next(c for c in candidates.candidates if c.action_class == "measurement:repeat")

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


def test_full_object_by_object_state_transition_loop(tmp_path):
    """Section 15's required test: every boundary object is inspected
    directly, not just "the final call succeeded"."""
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    doc, _iteration, candidate, campaign, entry = _build_campaign(pool)

    # ModelState_t
    state_t = EMPTY_MODEL_STATE
    assert state_t.samples == {}

    # predict (against the state BEFORE any measurement -- an honest "no data yet" prediction)
    prediction_t = predict(state_t, candidate)
    assert prediction_t.state_id == state_t.id
    assert prediction_t.candidate_id == candidate.id
    assert prediction_t.predicted_value is None  # zero samples -- no mean is defined
    assert prediction_t.sample_count == 0

    # ActionCandidate -- inspect its actual identity fields
    assert candidate.property == "tensile_strength"
    assert candidate.formulation.kind == "formulation"
    assert candidate.action_class  # a real, non-empty, open string per Phase 36

    # ExperimentalCampaign / ExperimentalCampaignEntry -- inspect the actual join
    assert campaign.process_natural_key == "process-std-190c"
    assert entry.candidate_id == candidate.id
    assert entry.formulation.id == candidate.formulation.id
    assert entry.property == candidate.property

    # ExperimentalResult -- inspect what was actually obtained
    result, observation, relationship = _run_result(pool, doc, campaign, entry, "result-1", 82)
    assert result.candidate_id == candidate.id
    assert result.formulation.id == candidate.formulation.id
    assert result.property == "tensile_strength"
    assert dict(result.content) == {"property": "tensile_strength", "value": 82, "unit": "MPa"}

    # Observation -- inspect the actual admitted evidence object
    assert observation.content.get("value") == 82
    assert observation.record_ids == (result.record_id,)
    assert relationship.observation_id == observation.id
    assert relationship.from_referent_id == candidate.formulation.id
    assert pool.has_observation(observation.id)  # genuinely durable, not a bare in-memory object

    # update() -> ModelState_(t+1)
    state_t1 = update(state_t, candidate, result, observation)
    assert state_t1.id != state_t.id
    key = next(iter(state_t1.samples))
    assert [s.observation_id for s in state_t1.samples[key]] == [observation.id]
    assert [s.value for s in state_t1.samples[key]] == [82.0]

    # predict against the NEW state
    prediction_t1 = predict(state_t1, candidate)
    assert prediction_t1.state_id == state_t1.id
    assert prediction_t1.predicted_value == 82.0
    assert prediction_t1.sample_count == 1

    # historical state untouched
    assert state_t.samples == {}
    assert predict(state_t, candidate).predicted_value is None


def test_three_state_trajectory_with_recoverability(tmp_path):
    """Section 18: S0 -> S1 -> S2, each caused by an explicit experimental
    observation, with S0 and S1 independently recoverable/re-predictable
    after S2 exists."""
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    doc, _iteration, candidate, campaign, entry = _build_campaign(pool)

    s0 = EMPTY_MODEL_STATE
    prediction_s0 = predict(s0, candidate)

    result_1, observation_1, _ = _run_result(pool, doc, campaign, entry, "result-1", 76)
    s1 = update(s0, candidate, result_1, observation_1)
    prediction_s1 = predict(s1, candidate)

    result_2, observation_2, _ = _run_result(pool, doc, campaign, entry, "result-2", 84)
    s2 = update(s1, candidate, result_2, observation_2)
    prediction_s2 = predict(s2, candidate)

    assert s0.id != s1.id
    assert s1.id != s2.id
    assert s0.id != s2.id

    # S0 and S1 remain recoverable: re-predicting against them, AFTER S2 was
    # built, gives byte-identical results to what was computed at the time.
    assert predict(s0, candidate) == prediction_s0
    assert predict(s1, candidate) == prediction_s1
    assert predict(s2, candidate) == prediction_s2

    assert prediction_s0.predicted_value is None
    assert prediction_s1.predicted_value == 76.0
    assert prediction_s1.uncertainty is None  # a single sample has a mean but no defined variance
    assert prediction_s2.predicted_value == 80.0
    assert prediction_s2.uncertainty == 16.0  # population variance of (76, 84)

    # S1's own samples are an exact subset of S2's -- nothing about S1's
    # history was rewritten by the transition into S2.
    key = next(iter(s2.samples))
    assert s1.samples[key] == tuple(sample for sample in s2.samples[key] if sample.observation_id == observation_1.id)


def test_trajectory_is_deterministic_when_repeated(tmp_path):
    """Section 7: the SAME initial state, candidate, and experimental
    results, assembled independently twice, produce identical state
    identity and content at every step of the trajectory -- not just for
    one update, but for the whole S0 -> S1 -> S2 sequence."""

    def _run_trajectory(root):
        pool = DurablePool(FilesystemEvidenceStore(root))
        doc, _iteration, candidate, campaign, entry = _build_campaign(pool)
        result_1, observation_1, _ = _run_result(pool, doc, campaign, entry, "result-1", 76)
        s1 = update(EMPTY_MODEL_STATE, candidate, result_1, observation_1)
        result_2, observation_2, _ = _run_result(pool, doc, campaign, entry, "result-2", 84)
        s2 = update(s1, candidate, result_2, observation_2)
        return candidate.id, s1.id, s2.id

    candidate_id_a, s1_id_a, s2_id_a = _run_trajectory(tmp_path / "a")
    candidate_id_b, s1_id_b, s2_id_b = _run_trajectory(tmp_path / "b")

    assert candidate_id_a == candidate_id_b
    assert s1_id_a == s1_id_b
    assert s2_id_a == s2_id_b


def test_information_value_before_and_after_state_update(tmp_path):
    """Section 13: state -> uncertainty/information gap -> candidate ->
    experiment -> result -> updated state, using the EXISTING
    materials.information/materials.model_state seam
    (ModelStateInformationValueModel), never a new one. Demonstrates the
    honest "before vs after" comparison the vendored code's own docstring
    describes: predictive uncertainty is NOT_DETERMINABLE with fewer than
    2 samples, and a real number once a second, independent observation
    exists -- exactly the information gap this loop is meant to close."""
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    doc, iteration, candidate, campaign, entry = _build_campaign(pool)

    result_1, observation_1, _ = _run_result(pool, doc, campaign, entry, "result-1", 76)
    state_1 = update(EMPTY_MODEL_STATE, candidate, result_1, observation_1)

    model_before = ModelStateInformationValueModel(state_1)
    estimate_before = estimate_information_value(candidate, iteration, model_before)
    assert estimate_before.estimate_status == NOT_DETERMINABLE
    assert estimate_before.estimate is None
    assert estimate_before.model_name == f"model_state:{state_1.id}"

    result_2, observation_2, _ = _run_result(pool, doc, campaign, entry, "result-2", 84)
    state_2 = update(state_1, candidate, result_2, observation_2)

    model_after = ModelStateInformationValueModel(state_2)
    estimate_after = estimate_information_value(candidate, iteration, model_after)
    assert estimate_after.estimate_status != NOT_DETERMINABLE
    assert estimate_after.estimate == 16.0  # the same population variance predict() itself reports
    assert estimate_after.model_name == f"model_state:{state_2.id}"

    # The candidate/requirement/gap/audit/decision provenance chain
    # (Phase 46's CandidateInformationValue) is identical in both estimates
    # -- only the MODEL's own number changed, exactly the "before vs after"
    # semantic this seam exists to preserve, never a re-evaluation of the
    # underlying evidence/requirement structure.
    assert estimate_before.information_value == estimate_after.information_value


def test_revised_evidence_in_the_durable_pool_does_not_mutate_existing_state(tmp_path):
    """Sections 8/16/17, combined: acquiring genuinely NEW/revised
    evidence into the SAME durable pool an already-built ModelState came
    from must never retroactively change that ModelState -- only an
    explicit update() call may produce a new one."""
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    doc, _iteration, candidate, campaign, entry = _build_campaign(pool)
    result_1, observation_1, _ = _run_result(pool, doc, campaign, entry, "result-1", 76)
    state_1 = update(EMPTY_MODEL_STATE, candidate, result_1, observation_1)

    # New evidence is admitted into the SAME pool afterward (a later
    # measurement transcribed into the same durable store) -- but no
    # update() call is made for it.
    _run_result(pool, doc, campaign, entry, "result-2", 999)

    # state_1 is completely unaffected: same id, same samples, same prediction.
    assert state_1.id == update(EMPTY_MODEL_STATE, candidate, result_1, observation_1).id
    assert predict(state_1, candidate).predicted_value == 76.0
    assert predict(state_1, candidate).sample_count == 1
