"""Phase P: DAF-acquired evidence reaching the scientific decision layer
for the first time.

THE FRONTIER THIS CLOSES. Phases M, N and O each proved a piece of the
scientific loop, but every one of them built its evidence by hand with
`make_observation`/`admit_observation`, bypassing DAF's acquisition
pipeline entirely. The reason was not noticed until it was measured:
every DAF extractor emits `entities=()`, `relations=()`, so acquired
evidence lands in the pool with no referents and no relationships, and
`materials.iteration.reevaluate_program` cannot reach it at all --

    KeyError: no Referent with natural_key 'process-std-190c' in pool

`scout.pipeline.run_scout` has always admitted extractor-declared
entities/relations; no DAF extractor had ever used that path.
`daf.extractors.graph_dataset.GraphDatasetExtractor` is that use, and
these tests are the proof that the composition

    real acquisition -> admitted evidence graph -> gap analysis ->
    decision -> candidates -> experiment -> ModelState

now runs on evidence DAF actually acquired, with no hand-built fixture
observations anywhere in the path.

THE DEFECT THESE TESTS ALSO LOCK DOWN. Running the composition for the
first time surfaced a real boundary bug: the paired adapter's required
`id` field (its acquisition locator) was flowing into
`Observation.content`, where `materials.analysis._comparison_context`
treats every non-value key as comparison context -- so every acquired
measurement landed in its own single-member group and the property's
status was permanently INCOMPARABLE. See
`test_acquisition_locator_never_enters_scientific_comparison_context`.
"""

from __future__ import annotations

import json

import pytest
from evidence.types import make_document, make_record
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
from daf.extractors.graph_dataset import GraphDatasetExtractionError, GraphDatasetExtractor
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore

ENGINE = DeterministicRetrievalEngine()
ALLOW_ALL = SelectionPolicy(
    allowed_action_classes=None, allow_already_represented_context=True,
    allow_redundant=True, allow_not_determinable_feasibility=True, max_selected=None,
)
FORMULATION = "formulation-f1"
PROCESS = "process-std-190c"


def _measurement(record_id, value):
    """One dataset record that declares its own trust-graph structure.
    The labels/kinds/relation type are the SOURCE's vocabulary -- the
    extractor supplies none of them."""
    return {
        "id": record_id,
        "property": "tensile_strength", "value": value, "unit": "MPa",
        "entities": [
            {"label": FORMULATION, "kind": "formulation"},
            {"label": PROCESS, "kind": "process"},
        ],
        "relations": [{"from": FORMULATION, "to": PROCESS, "type": "tested_during"}],
    }


def _acquire(root, records, dataset=None):
    """The real, unmodified DAF acquisition path -- source registry,
    adapter binding, plan, checkpoint store, execute_plan -- writing into
    a real DurablePool. No fixture Observation is admitted anywhere.

    `dataset` may name a shared source file; when omitted each call gets
    its own. The distinction matters for identity: the adapter builds
    `Record.locator` as `f"{path}#{id}"`, so acquiring the same records
    from a DIFFERENT path is legitimately different evidence with
    different ids -- provenance is part of identity here, by design."""
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
    plan = AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(dataset)})

    result = execute_plan(
        plan, sources, adapters, pool, CheckpointStore(root / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
    )
    assert result.outcome.value == "acquired"
    return pool, result


def _iteration(pool):
    query = make_material_program_query([FORMULATION], PROCESS, ("tensile_strength",))
    return reevaluate_program(pool, ENGINE, query, (make_criterion("tensile_strength", ">=", 80),))


def _extract_one(payload):
    doc = make_document(
        source_id="s", raw_content="d", retrieval_method="manual_entry", retrieved_at="2026-08-25T00:00:00Z"
    )
    record = make_record(document_id=doc.id, locator="row-1", raw_content=json.dumps(payload))
    return GraphDatasetExtractor().extract(record)[0]


def test_acquisition_admits_the_declared_evidence_graph(tmp_path):
    """The half no DAF extractor had ever used: run_scout turns declared
    entities/relations into admitted Referents/ClaimedRelationships."""
    pool, result = _acquire(tmp_path, [_measurement("ts-001", 78), _measurement("ts-002", 84)])
    assert len(result.artifacts) == 2

    assert len(pool.all_observations()) == 2
    referents = {r.natural_key: r.kind for r in pool.all_referents()}
    assert referents == {FORMULATION: "formulation", PROCESS: "process"}

    relationships = pool.all_claimed_relationships()
    assert len(relationships) == 2, "one per acquired record, each declaring the same link"
    by_id = {r.id: r for r in pool.all_referents()}
    for relationship in relationships:
        assert by_id[relationship.from_referent_id].natural_key == FORMULATION
        assert by_id[relationship.to_referent_id].natural_key == PROCESS
        assert relationship.type == "tested_during"
        assert pool.has_observation(relationship.observation_id)


def test_acquired_evidence_alone_drives_the_scientific_decision_layer(tmp_path):
    """The exact call that failed before this phase -- reevaluate_program
    over a pool containing ONLY DAF-acquired evidence -- now produces a
    real gap analysis, decision and candidate set."""
    pool, _ = _acquire(tmp_path, [_measurement("ts-001", 78), _measurement("ts-002", 84)])
    iteration = _iteration(pool)

    decision = iteration.decision.formulations[0].properties[0]
    assert decision.observed_status == "CONFLICTING_EVIDENCE"
    assert decision.evidence.observed_disagreement is not None
    assert (decision.evidence.observed_disagreement.minimum,
            decision.evidence.observed_disagreement.maximum) == (78.0, 84.0)

    # every Observation backing that decision came out of the acquisition
    assert {o.extraction_method for o in decision.evidence.observed} == {"json:graph_dataset_v1"}

    candidates = generate_candidates(iteration.specification)
    assert "measurement:repeat" in {c.action_class for c in candidates.candidates}


def test_acquisition_locator_never_enters_scientific_comparison_context(tmp_path):
    """Regression test for the defect this phase found by measurement.

    The adapter REQUIRES a per-record `id` and uses it to build the
    Record locator. Left in Observation.content it becomes part of
    materials' comparison context, making every acquired measurement
    incomparable with every other one -- permanently INCOMPARABLE status
    no matter how much evidence is acquired."""
    pool, _ = _acquire(tmp_path, [_measurement("ts-001", 78), _measurement("ts-002", 84)])

    for observation in pool.all_observations():
        assert "id" not in observation.content, "the acquisition locator is not scientific content"
        assert "entities" not in observation.content and "relations" not in observation.content
        assert set(observation.content) == {"property", "value", "unit"}

    # nothing is lost: acquisition identity still resolves through the Record
    locators = {pool.get_record(rid).locator for o in pool.all_observations() for rid in o.record_ids}
    assert {loc.rsplit("#", 1)[1] for loc in locators} == {"ts-001", "ts-002"}

    # and the two measurements are now genuinely comparable to each other
    groups = _iteration(pool).decision.formulations[0].properties[0].evidence.observed_comparison_groups
    assert len(groups) == 1, "one shared comparison context, not one group per record"
    assert dict(groups[0].context) == {"unit": "MPa"}
    assert sorted(groups[0].values) == [78.0, 84.0]


def test_acquired_evidence_reaches_a_model_state_transition(tmp_path):
    """Continuity with Phases N/O: the candidate the acquired evidence
    produced drives a real campaign, result and ModelState transition.
    The evidence that motivated the experiment is acquired; only the
    experimental result itself is supplied, as it must be."""
    pool, _ = _acquire(tmp_path, [_measurement("ts-001", 78), _measurement("ts-002", 84)])
    iteration = _iteration(pool)

    candidates = generate_candidates(iteration.specification)
    candidate = next(c for c in candidates.candidates if c.action_class == "measurement:repeat")
    campaign = assemble_experimental_campaign(
        assemble_experimental_design(
            assemble_experiment_plan(select_candidates(evaluate_candidates(candidates), ALLOW_ALL))
        )
    )
    entry = next(e for e in campaign.entries if e.candidate_id == candidate.id)

    acquired = pool.all_observations()[0]
    document_id = pool.get_record(acquired.record_ids[0]).document_id
    record = make_record(document_id=document_id, locator="run-1", raw_content="run-1")
    pool.put_record(record)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": 81, "unit": "MPa"},
        record_id=record.id, extracted_at="2026-08-25T02:00:00Z",
        extraction_method="measurement:campaign_execution",
    )
    observation, _relationship = admit_experimental_result(pool, result, confidence=1.0)

    state = update(EMPTY_MODEL_STATE, candidate, result, observation)
    prediction = predict(state, candidate)
    assert prediction.predicted_value == 81.0
    assert prediction.state_id == state.id


def test_acquisition_to_decision_is_deterministic(tmp_path):
    """The SAME source file acquired into two independent on-disk pools:
    identical observation identities, identical referent identities,
    identical decision and candidates."""
    dataset = tmp_path / "shared" / "panel.json"
    records = [_measurement("ts-001", 78), _measurement("ts-002", 84)]

    def _run(root):
        pool, _ = _acquire(root, records, dataset=dataset)
        iteration = _iteration(pool)
        decision = iteration.decision.formulations[0].properties[0]
        return (
            tuple(sorted(o.id for o in pool.all_observations())),
            tuple(sorted(r.id for r in pool.all_referents())),
            decision.observed_status,
            tuple(sorted(c.action_class for c in generate_candidates(iteration.specification).candidates)),
        )

    first, second = _run(tmp_path / "a"), _run(tmp_path / "b")
    assert first == second
    assert len(first[0]) == 2 and len(first[1]) == 2, "the comparison is over real, non-empty evidence"


def test_extractor_transports_declared_structure_without_inventing_any(tmp_path):
    """Domain neutrality, proven behaviourally rather than by inspection:
    a record from an entirely unrelated domain, carrying no property and
    no value at all, extracts exactly as well. The extractor supplies no
    vocabulary of its own."""
    candidate = _extract_one({
        "id": "obs-42", "target": "M31", "band": "H-alpha", "exposure_seconds": 900,
        "entities": [{"label": "m31", "kind": "galaxy"}, {"label": "telescope-a", "kind": "instrument"}],
        "relations": [{"from": "m31", "to": "telescope-a", "type": "observed_with"}],
    })

    assert dict(candidate.content) == {"target": "M31", "band": "H-alpha", "exposure_seconds": 900}
    assert [(e.label, e.kind) for e in candidate.entities] == [("m31", "galaxy"), ("telescope-a", "instrument")]
    assert [(r.from_label, r.to_label, r.type) for r in candidate.relations] == [
        ("m31", "telescope-a", "observed_with")
    ]
    assert candidate.extraction_method == "json:graph_dataset_v1"


def test_extractor_rejects_malformed_declarations_loudly():
    """Never silently degrades to an empty graph -- which would
    reintroduce exactly the unreachable-evidence condition this phase
    exists to fix."""
    with pytest.raises(GraphDatasetExtractionError, match="non-empty 'entities'"):
        _extract_one({"id": "r", "value": 1})

    with pytest.raises(GraphDatasetExtractionError, match="non-empty 'entities'"):
        _extract_one({"id": "r", "value": 1, "entities": []})

    with pytest.raises(GraphDatasetExtractionError, match="not among"):
        _extract_one({
            "id": "r", "entities": [{"label": "a", "kind": "k"}],
            "relations": [{"from": "a", "to": "ghost", "type": "t"}],
        })

    with pytest.raises(GraphDatasetExtractionError, match="entity kind"):
        _extract_one({"id": "r", "entities": [{"label": "a"}]})

    document = make_document(
        source_id="s", raw_content="d", retrieval_method="manual_entry", retrieved_at="2026-08-25T00:00:00Z"
    )
    not_json = make_record(document_id=document.id, locator="row-1", raw_content="{not json")
    with pytest.raises(GraphDatasetExtractionError, match="not valid JSON"):
        GraphDatasetExtractor().extract(not_json)
