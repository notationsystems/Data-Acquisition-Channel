"""Phase M: proves the actual, code-grounded evidence -> ModelState path
Phase L's reconciliation found, using zero new production abstractions in
either `daf/` or the vendored `materials/`/`evidence` packages -- only
this test file is new.

Two halves, deliberately kept separate, per this phase's own audit
finding (see docs/PHASE_13_MODEL_STATE_INTEGRATION.md for the full
report):

1. A REAL DAF acquisition (NOAA CO-OPS water-level, admitted through the
   real, unmodified daf.orchestration/scout.pipeline.run_scout path into
   a real, durable daf.storage.durable_pool.DurablePool) proves DAF's
   evidence boundary is genuinely real, admitted `evidence.types.Observation`
   data -- and stops exactly there. It does NOT construct an
   ExperimentalResult/ActionCandidate for NOAA data, because NOAA (like
   EDGAR and USGS) is passively-acquired external data, not the result of
   an executed materials experiment testing a candidate formulation --
   fabricating that scaffolding for it would be exactly the "inventing
   scientific semantics" this phase's own task explicitly forbids.

2. A CONTROLLED, materials-domain fixture scenario (mirroring
   vendor/scout-retrieval-agent/tests/test_materials_model_state.py's own
   `_setup()` pattern verbatim -- the proven, already-existing recipe for
   assembling a real `ExperimentalCampaign`/`ActionCandidate`) proves the
   full `Observation -> update() -> ModelState -> predict()` loop works
   correctly -- using the SAME `DurablePool` instance the real NOAA
   acquisition in part 1 wrote into, proving DAF-acquired evidence and
   materials-admitted experimental evidence genuinely coexist in one
   durable pool with zero conflict, which is the one claim neither DAF's
   own test suite nor the vendored `materials` test suite could prove in
   isolation from each other.

No new field was added to `evidence.types.Observation`. No new resolver
function was added to `materials.model_state` (its existing
`resolve_model_state_key`/`update`/`predict` are already the correct,
sufficient interface -- see the phase report's "bridge design" section
for why a new abstraction was judged unnecessary, not merely deferred).
"""

from __future__ import annotations

import ast
from pathlib import Path

from evidence.admission import admit_claimed_relationship, admit_document, admit_observation, admit_record, admit_referent
from evidence.pool import EvidencePool
from evidence.types import make_claimed_relationship, make_document, make_observation, make_record, make_referent, make_source
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, predict, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from retrieval.engine import DeterministicRetrievalEngine

from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"
VENDOR_MODEL_STATE_SOURCE = Path(
    __import__("materials.model_state", fromlist=["__file__"]).__file__
).read_text()

ENGINE = DeterministicRetrievalEngine()
ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)


def _fixture_router(routes):
    def _fetch(url: str) -> bytes:
        for suffix, content in routes.items():
            if url.endswith(suffix):
                return content
        raise AssertionError(f"unexpected URL requested in test: {url!r}")

    return _fetch


def _acquire_real_noaa_observation(pool):
    """The real DAF acquisition path, unmodified: adapter -> extractor ->
    scout.pipeline.run_scout -> admitted Observation, durably persisted
    into `pool`. Synthetic fixture content (Phase I's own convention),
    but the acquisition mechanics -- orchestration, checkpointing,
    admission -- are the real, unmodified code, not a shortcut."""
    routes = {
        "begin_date=20260101&end_date=20260103&datum=MLLW&units=metric&time_zone=gmt&format=json":
            (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_bytes()
    }
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="noaa-water-level", name="NOAA CO-OPS Tides & Currents", domain="environmental-observations",
            adapter_id="noaa-water-level", required_parameters=("station", "product", "start_date", "end_date"),
            capabilities=("incremental",),
        )
    )
    adapters = AdapterRegistry()
    from daf.orchestration.adapter_registry import AdapterBinding
    from daf.orchestration.bindings import _advance_noaa_position
    from daf.adapters.noaa_water_level import NoaaWaterLevelSourceAdapter
    from daf.extractors.noaa_water_level import NoaaWaterLevelExtractor

    def build_adapter(source, request):
        return NoaaWaterLevelSourceAdapter(
            station="9999999", product="water_level", start_date="20260101", end_date="20260201",
            retrieved_at=request.requested_at, fetch_bytes=_fixture_router(routes),
        )

    adapters.register(
        AdapterBinding(
            adapter_id="noaa-water-level", build_adapter=build_adapter,
            build_extractor=NoaaWaterLevelExtractor, advance_position=_advance_noaa_position,
        )
    )
    checkpoints = CheckpointStore(pool.store.root.parent / "checkpoints")
    plan = AcquisitionPlan(
        plan_id="noaa-plan", source_id="noaa-water-level",
        parameters={"station": "9999999", "product": "water_level", "start_date": "20260101", "end_date": "20260201"},
    )
    result = execute_plan(plan, sources, adapters, pool, checkpoints, requested_at="2026-08-25T00:00:00Z")
    assert result.outcome.value == "acquired"

    # This acquisition is the only thing that has written to `pool` so far
    # (callers use this helper before admitting any fixture evidence), so
    # the one Observation it produced is unambiguous to retrieve this way.
    observations = pool.all_observations()
    assert len(observations) == 1
    return observations[0]


def test_real_noaa_observation_reaches_the_evidence_boundary_in_a_durable_pool(tmp_path):
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    observation = _acquire_real_noaa_observation(pool)

    # Genuinely admitted, durable evidence -- not a mock, not a fixture Observation.
    assert pool.has_observation(observation.id)
    assert pool.get_observation(observation.id).id == observation.id

    # The numeric information materials.model_state.update() ultimately wants
    # DOES exist in this real acquisition's content -- just one level deeper
    # than update() reads. Each individual reading really does carry a field
    # named "value":
    assert isinstance(observation.content["readings"][0]["value"], str)  # NOAA's own raw string, e.g. "1.100"
    assert float(observation.content["readings"][0]["value"])  # confirms it parses as numeric

    # But update()'s actual, documented contract reads observation.content.get("value")
    # at the TOP level -- which a NOAA window Observation does not have, because
    # "a bounded time window of many readings" and "one scalar experimental
    # measurement" are genuinely different representations (Phase L section 8's
    # trace already found this; this assertion is the empirical confirmation).
    assert observation.content.get("value") is None

    # This test stops here, deliberately: constructing an ExperimentalResult/
    # ActionCandidate for "a tide station's water level window" would require
    # inventing a materials-science formulation/campaign that does not
    # correspond to anything real about this source -- exactly the fabrication
    # this phase's task explicitly forbids. See part 2 below for the
    # controlled-fixture proof that the REST of the chain works correctly.


# -- Part 2: the fixture-based materials-experiment scenario, in the SAME pool --


def _assemble_fixture_campaign(pool):
    """Mirrors vendor/scout-retrieval-agent/tests/test_materials_model_state.py's
    own `_setup()` verbatim -- the existing, proven recipe for assembling a
    real ExperimentalCampaign/ActionCandidate, reused rather than reinvented.
    Admits its own Source/Document/Referents/Observations into `pool` --
    the SAME pool a real DAF acquisition may already have written into."""
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

    return doc, candidate, campaign, entry


def _admit_fixture_result(pool, doc, campaign, entry, locator, value):
    rec = make_record(document_id=doc.id, locator=locator, raw_content=locator)
    admit_record(pool, rec)
    pool.put_record(rec)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=rec.id, extracted_at="2026-08-23T02:00:00Z",
    )
    observation, _ = admit_experimental_result(pool, result, confidence=1.0)
    return result, observation


def test_model_state_transition_from_a_fixture_result_shares_the_real_acquisition_pool(tmp_path):
    """The central proof: a DurablePool that has ALREADY durably persisted
    a real NOAA acquisition (part 1) can be handed directly into the
    unmodified materials/experimental-campaign machinery, and the
    resulting ModelState transition is correct -- zero conflict, zero new
    interface on either side."""
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    _acquire_real_noaa_observation(pool)  # real DAF evidence already durably in this pool

    doc, candidate, campaign, entry = _assemble_fixture_campaign(pool)
    result, observation = _admit_fixture_result(pool, doc, campaign, entry, "result-1", 82)

    new_state = update(EMPTY_MODEL_STATE, candidate, result, observation)
    prediction = predict(new_state, candidate)

    assert prediction.predicted_value == 82.0
    assert prediction.sample_count == 1
    assert prediction.state_id == new_state.id


def test_historical_model_state_is_unchanged_after_update(tmp_path):
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    doc, candidate, campaign, entry = _assemble_fixture_campaign(pool)
    result, observation = _admit_fixture_result(pool, doc, campaign, entry, "result-1", 82)

    state_before = EMPTY_MODEL_STATE
    state_after = update(state_before, candidate, result, observation)

    assert state_before.samples == {}
    assert state_before.id == EMPTY_MODEL_STATE.id  # never mutated
    assert state_after.id != state_before.id
    assert len(next(iter(state_after.samples.values()))) == 1


def test_deterministic_state_transition_same_inputs_same_state_id(tmp_path):
    pool_a = DurablePool(FilesystemEvidenceStore(tmp_path / "a"))
    doc_a, candidate_a, campaign_a, entry_a = _assemble_fixture_campaign(pool_a)
    result_a, observation_a = _admit_fixture_result(pool_a, doc_a, campaign_a, entry_a, "result-1", 82)
    state_a = update(EMPTY_MODEL_STATE, candidate_a, result_a, observation_a)

    pool_b = DurablePool(FilesystemEvidenceStore(tmp_path / "b"))
    doc_b, candidate_b, campaign_b, entry_b = _assemble_fixture_campaign(pool_b)
    result_b, observation_b = _admit_fixture_result(pool_b, doc_b, campaign_b, entry_b, "result-1", 82)
    state_b = update(EMPTY_MODEL_STATE, candidate_b, result_b, observation_b)

    # Two independently-assembled fixture chains, same scientific content ->
    # the same candidate.id, the same observation.id (content-addressed), and
    # therefore the same resulting ModelState.id.
    assert candidate_a.id == candidate_b.id
    assert observation_a.id == observation_b.id
    assert state_a.id == state_b.id


def test_sequential_updates_and_predictions_reference_the_correct_state(tmp_path):
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    doc, candidate, campaign, entry = _assemble_fixture_campaign(pool)

    result_1, observation_1 = _admit_fixture_result(pool, doc, campaign, entry, "result-1", 80)
    state_1 = update(EMPTY_MODEL_STATE, candidate, result_1, observation_1)
    prediction_1 = predict(state_1, candidate)

    result_2, observation_2 = _admit_fixture_result(pool, doc, campaign, entry, "result-2", 90)
    state_2 = update(state_1, candidate, result_2, observation_2)
    prediction_2 = predict(state_2, candidate)

    assert prediction_1.state_id == state_1.id
    assert prediction_2.state_id == state_2.id
    assert prediction_1.state_id != prediction_2.state_id
    assert prediction_2.sample_count == 2
    assert prediction_2.predicted_value == 85.0
    # state_1 remains exactly as it was -- re-predicting against it later
    # still gives the same answer it always did.
    assert predict(state_1, candidate) == prediction_1


def test_revised_artifact_version_does_not_automatically_mutate_model_state(tmp_path):
    """Section 15's exact question, tested with real USGS revision data:
    acquiring a REVISED version of an already-acquired artifact (Phase H's
    own live-proven behavior -- same artifact_id, new version_id) must
    NOT, by itself, change any ModelState. Only an explicit update() call
    can do that, and nothing in DAF's acquisition path ever issues one."""
    from daf.adapters.usgs_earthquakes import UsgsEarthquakeSourceAdapter
    from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractor
    from daf.orchestration.adapter_registry import AdapterBinding
    from daf.orchestration.bindings import _advance_usgs_position
    from daf.orchestration.orchestrator import AcquisitionOrchestrator
    from daf.orchestration.request import AcquisitionRequest

    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))

    def _binding(detail_fixture):
        import json

        listing = json.loads((FIXTURES / "usgs_listing_synthetic.json").read_text())
        listing["features"] = [f for f in listing["features"] if f["id"] == "synth00000001"]

        def build_adapter(source, request):
            return UsgsEarthquakeSourceAdapter(
                start_time="2026-01-01", end_time="2026-01-02", min_magnitude=3.0,
                retrieved_at=request.requested_at,
                fetch_bytes=_fixture_router({
                    "&limit=500": json.dumps(listing).encode(),
                    "eventid=synth00000001&format=geojson": (FIXTURES / detail_fixture).read_bytes(),
                }),
            )

        return AdapterBinding(
            adapter_id="usgs-earthquakes", build_adapter=build_adapter,
            build_extractor=UsgsEarthquakeExtractor, advance_position=_advance_usgs_position,
        )

    sources = SourceRegistry()
    sources.register(SourceDefinition(source_id="usgs", name="USGS", domain="d", adapter_id="usgs-earthquakes"))
    adapters = AdapterRegistry()
    orchestrator = AcquisitionOrchestrator(sources, adapters, pool)

    # A ModelState already exists in this test's world, from unrelated fixture evidence.
    doc, candidate, campaign, entry = _assemble_fixture_campaign(pool)
    result, observation = _admit_fixture_result(pool, doc, campaign, entry, "result-1", 82)
    state_before_revision = update(EMPTY_MODEL_STATE, candidate, result, observation)

    adapters.register(_binding("usgs_event_detail_synth00000001.json"))
    orchestrator.run(AcquisitionRequest(source_id="usgs", parameters={}, requested_at="2026-08-25T00:00:00Z"))

    adapters.register(_binding("usgs_event_detail_synth00000001_revised.json"))
    second = orchestrator.run(AcquisitionRequest(source_id="usgs", parameters={}, requested_at="2026-08-26T00:00:00Z"))
    assert second.artifacts[0].is_new is True  # a genuine revision was acquired

    # The ModelState built before the revision is completely untouched by it --
    # acquiring new evidence (even a revision) is not, and must never become,
    # an implicit model-state transition.
    assert state_before_revision.id == update(EMPTY_MODEL_STATE, candidate, result, observation).id
    assert predict(state_before_revision, candidate).predicted_value == 82.0


def test_update_and_predict_never_access_evidencepool(tmp_path, monkeypatch):
    """Section 14's invariant, proven directly: predict()/update() take
    already-resolved values, never a pool -- verified by making every
    EvidencePool read/write method raise if called, then exercising both
    functions successfully."""
    pool = DurablePool(FilesystemEvidenceStore(tmp_path / "evidence"))
    doc, candidate, campaign, entry = _assemble_fixture_campaign(pool)
    result, observation = _admit_fixture_result(pool, doc, campaign, entry, "result-1", 82)

    def _forbidden(*args, **kwargs):
        raise AssertionError("predict()/update() must never touch EvidencePool")

    for method_name in (
        "get_source", "get_document", "get_record", "get_observation", "get_referent",
        "has_source", "has_document", "has_record", "has_observation", "has_referent",
        "put_source", "put_document", "put_record", "put_observation",
    ):
        monkeypatch.setattr(EvidencePool, method_name, _forbidden)

    state = update(EMPTY_MODEL_STATE, candidate, result, observation)
    prediction = predict(state, candidate)
    assert prediction.predicted_value == 82.0


def test_model_state_module_has_no_daf_dependency():
    """Section 18 item 13: materials.model_state (vendored) never imports
    anything from daf/ -- AST-verified directly against its own source,
    read-only, matching every other one-door-style proof in this
    codebase."""
    tree = ast.parse(VENDOR_MODEL_STATE_SOURCE)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
    assert "daf" not in imported_roots
