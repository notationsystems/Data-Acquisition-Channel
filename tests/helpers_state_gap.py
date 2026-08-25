"""Shared fixture composition for the scientific-state tests.

Extracted when a second test module needed the same
acquisition -> analysis -> S0 -> S1 -> S2 setup. Two copies of this were
already one too many; a third would have guaranteed they drifted.

FIXTURE PROVENANCE, stated once here rather than in each caller:

  * REAL DAF ACQUISITION -- `acquire_measurements` runs the unmodified
    adapter/extractor/orchestrator/DurablePool path over a
    graph-declaring dataset, exactly as Phase P established.
  * SYNTHETIC SCIENTIFIC FIXTURE -- the measurement values. No
    DAF-reachable source is a materials experiment (Phase M's standing
    finding), so `ExperimentalResult`/`ActionCandidate` semantics use
    controlled values rather than pretending a tide gauge is a tensile
    test. Phase Q's live NOAA path is proven in its own suite.
"""

from __future__ import annotations

import json

from evidence.types import make_record
from materials.campaign import assemble_experimental_campaign
from materials.candidates import generate_candidates
from materials.decision import make_criterion
from materials.design import assemble_experimental_design
from materials.evaluation import evaluate_candidates
from materials.iteration import reevaluate_program
from materials.model_state import EMPTY_MODEL_STATE, update
from materials.plan import assemble_experiment_plan
from materials.program import make_material_program_query
from materials.results import admit_experimental_result, make_experimental_result
from materials.selection import SelectionPolicy, select_candidates
from retrieval.engine import DeterministicRetrievalEngine

from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
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
REPEAT = "measurement:repeat"


def measurement(record_id, value):
    """One dataset record declaring its own trust-graph structure."""
    return {
        "id": record_id, "property": "tensile_strength", "value": value, "unit": "MPa",
        "entities": [{"label": FORMULATION, "kind": "formulation"},
                     {"label": PROCESS, "kind": "process"}],
        "relations": [{"from": FORMULATION, "to": PROCESS, "type": "tested_during"}],
    }


def acquire_measurements(root, records, dataset=None):
    """The real, unmodified DAF acquisition path.

    `dataset` may name a shared source file. That matters for identity:
    Phase S made the dataset path part of the artifact locator, so the
    Record -- and therefore the Observation, and therefore the Sample's
    `observation_id` inside a ModelState -- traces back to WHERE the
    evidence came from. Acquiring the same records from a different path
    is legitimately different evidence yielding different state ids, so
    determinism comparisons must share one source."""
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


def iteration_for(pool):
    query = make_material_program_query([FORMULATION], PROCESS, ("tensile_strength",))
    return reevaluate_program(pool, ENGINE, query, (make_criterion("tensile_strength", ">=", 80),))


def campaign_for(iteration):
    candidates = generate_candidates(iteration.specification)
    candidate = next(c for c in candidates.candidates if c.action_class == REPEAT)
    campaign = assemble_experimental_campaign(
        assemble_experimental_design(
            assemble_experiment_plan(select_candidates(evaluate_candidates(candidates), ALLOW_ALL))
        )
    )
    return candidate, campaign, next(e for e in campaign.entries if e.candidate_id == candidate.id)


def result_for(pool, campaign, entry, locator, value):
    document_id = pool.get_record(pool.all_observations()[0].record_ids[0]).document_id
    record = make_record(document_id=document_id, locator=locator, raw_content=locator)
    pool.put_record(record)
    result = make_experimental_result(
        campaign, entry, content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        record_id=record.id, extracted_at="2026-08-25T02:00:00Z",
    )
    observation, _relationship = admit_experimental_result(pool, result, confidence=1.0)
    return result, observation


def trajectory(root, dataset=None):
    """Acquisition -> analysis -> S0 -> S1 -> S2, returning everything."""
    pool = acquire_measurements(
        root, [measurement("ts-001", 78), measurement("ts-002", 84)], dataset=dataset
    )
    iteration = iteration_for(pool)
    candidate, campaign, entry = campaign_for(iteration)

    s0 = EMPTY_MODEL_STATE
    result_1, observation_1 = result_for(pool, campaign, entry, "run-1", 76)
    s1 = update(s0, candidate, result_1, observation_1)
    result_2, observation_2 = result_for(pool, campaign, entry, "run-2", 84)
    s2 = update(s1, candidate, result_2, observation_2)
    return pool, iteration, candidate, (s0, s1, s2)
