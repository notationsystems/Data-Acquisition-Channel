"""The epistemic boundary, enforced.

Four things are proved here, in order of how expensive they become to
repair once records exist:

  1. The substrate is a LOOP entered at acquisition, and derived state's
     only exit is back through acquisition.
  2. An evidence object's class is fixed in the call that admits it, and
     survives persistence, restart, mutation and tampering.
  3. A computation cannot classify itself as measured or asserted, and no
     interpretive layer can write evidence at all.
  4. Everything the synchronization prompts describe but this repository
     does not have is absent -- checked, so the check fails the day one
     appears rather than the day someone notices.

Fixture provenance: the class tests run the REAL, unmodified DAF
acquisition path over recorded NOAA CO-OPS bytes and a graph-declaring
dataset. Nothing here simulates ingest.
"""

from __future__ import annotations

import ast
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import epistemics  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from daf.catalog.checkpoint import CheckpointStore
from daf.catalog.plan import AcquisitionPlan
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import (
    graph_dataset_binding,
    noaa_water_level_measurement_binding,
)
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from daf.storage.class_store import ClassAssignmentStore
from daf.storage.classified_pool import ClassifiedPool, SourceClassPolicy
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics import _yaml
from epistemics.control_graph import (
    ACQUISITION,
    DERIVED_STATE,
    EVIDENCE,
    STAGES,
    ControlGraphViolation,
    Transition,
    load_control_graph,
    validate_control_graph,
)
from epistemics.evidence_class import (
    ASSERTED,
    DERIVED,
    INGEST_CLASSES,
    MEASURED,
    STATUSES_NOT_CLASSES,
    UNCLASSIFIED,
    VOCABULARY_MAP,
    ClassIdentityMismatch,
    ClassReassignment,
    ProposalClassRefused,
    UnknownEvidenceClass,
    assignment_from_dict,
    assignment_to_dict,
    canonical_class,
    make_class_assignment,
)
from epistemics.invariants import load_invariants

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = REPO_ROOT / "architecture"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MLLW_BYTES = (FIXTURES / "noaa_live_8454000_20240115_mllw.json").read_bytes()

# The declared policy. A source kind absent from this mapping produces no
# assignment at all, which is the point of `test_an_undeclared_source_...`.
POLICY = SourceClassPolicy(
    id="source_policy:phase25",
    by_source_kind={
        # A tide gauge reading with a reported sigma is a measurement.
        "tide-station-window": MEASURED,
        # A dataset file states values; nobody here operated an instrument.
        "dataset": ASSERTED,
    },
)
NOAA_PARAMETERS = {
    "station": "8454000",
    "product": "water_level",
    "start_date": "20240115",
    "end_date": "20240115",
}


def _noaa_pool(root, policy=POLICY, register=None):
    pool = ClassifiedPool(
        FilesystemEvidenceStore(root / "evidence"), policy, register=register
    )
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
        noaa_water_level_measurement_binding(
            datum="MLLW", units="metric", fetch_bytes=lambda url: MLLW_BYTES
        )
    )
    result = execute_plan(
        AcquisitionPlan(plan_id="noaa-plan", source_id="noaa-cm", parameters=dict(NOAA_PARAMETERS)),
        sources,
        adapters,
        pool,
        CheckpointStore(root / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
    )
    assert result.outcome.value == "acquired"
    return pool


def _dataset_pool(root, policy=POLICY):
    dataset = root / "panel.json"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(
        json.dumps(
            [
                {
                    "id": "m1",
                    "property": "tensile_strength",
                    "value": 78.0,
                    "unit": "MPa",
                    "entities": [{"label": "formulation-f1", "kind": "formulation"}],
                    "relations": [],
                }
            ]
        )
    )
    pool = ClassifiedPool(FilesystemEvidenceStore(root / "evidence"), policy)
    sources = SourceRegistry()
    sources.register(
        SourceDefinition(
            source_id="qc-panel",
            name="QC panel",
            domain="materials",
            adapter_id="graph-dataset",
            required_parameters=("path",),
            capabilities=(),
        )
    )
    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())
    result = execute_plan(
        AcquisitionPlan(plan_id="qc-plan", source_id="qc-panel", parameters={"path": str(dataset)}),
        sources,
        adapters,
        pool,
        CheckpointStore(root / "checkpoints"),
        requested_at="2026-08-25T00:00:00Z",
    )
    assert result.outcome.value == "acquired"
    return pool


# ---------------------------------------------------------------- loop


def test_the_control_graph_is_a_single_acquisition_first_loop():
    transitions, forbidden = load_control_graph()
    validate_control_graph(transitions, forbidden)
    assert len(transitions) == len(STAGES)
    assert {t.source for t in transitions} == set(STAGES)


def test_the_return_edge_is_the_only_way_out_of_derived_state():
    transitions, _ = load_control_graph()
    exits = tuple(t for t in transitions if t.source == DERIVED_STATE)
    assert len(exits) == 1
    assert exits[0].target == ACQUISITION
    assert exits[0].mandatory and exits[0].exclusive


def test_a_graph_where_derived_state_writes_evidence_is_refused():
    """The correction stated as a failure. A stack cannot express this;
    only a closed loop can, because the prohibition is a property of an
    edge."""
    transitions, forbidden = load_control_graph()
    bypass = transitions + (
        Transition(
            source=DERIVED_STATE,
            target=EVIDENCE,
            via="a proposal writing itself in",
            enforced_by="nothing",
        ),
    )
    with pytest.raises(ControlGraphViolation, match="outgoing transitions"):
        validate_control_graph(bypass, forbidden)


def test_a_graph_that_does_not_reach_every_stage_is_refused():
    _, forbidden = load_control_graph()
    short = (
        Transition(ACQUISITION, EVIDENCE, "run_scout", "x"),
        Transition(EVIDENCE, ACQUISITION, "shortcut", "x"),
    )
    with pytest.raises(ControlGraphViolation):
        validate_control_graph(short, forbidden)


def test_evidence_is_written_only_by_the_acquisition_path():
    """AST, not grep. The evidence write boundary measured across the
    whole repository: exactly two modules in the vendored substrate call
    a pool mutator, and no layer this project authored does."""
    writers = set()
    for path in sorted(REPO_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "__pycache__" in rel or rel.startswith("tests/") or "/tests/" in rel:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name.startswith(("put_", "admit_")):
                writers.add(rel)
    # DAF's own storage layer IMPLEMENTS put_* (and calls super()), which
    # is why it appears; it is the persistence side of the same one door.
    interpretive = {
        w
        for w in writers
        if w.startswith(("science/", "bridge/", "boundary/", "epistemics/"))
    }
    assert interpretive == set(), f"an interpretive layer writes evidence: {sorted(interpretive)}"
    assert "vendor/scout-retrieval-agent/scout/pipeline.py" in writers


# --------------------------------------------------- class at ingest


def test_the_class_vocabulary_agrees_with_the_canonical_yaml():
    """Code and canonical data are two representations of one fact. This
    is the check that stops them drifting."""
    document = _yaml.loads((ARCHITECTURE / "evidence_class.yaml").read_text())
    assert tuple(document["ingest_classes"]) == INGEST_CLASSES
    assert document["migration_state"] == UNCLASSIFIED
    assert dict(document["vocabulary_map"]) == dict(VOCABULARY_MAP)
    assert tuple(document["statuses_not_classes"]) == STATUSES_NOT_CLASSES


def test_validated_is_a_status_not_a_class():
    assert "validated" not in VOCABULARY_MAP
    assert "validated" not in INGEST_CLASSES
    with pytest.raises(UnknownEvidenceClass, match="claim-level status"):
        canonical_class("validated")
    with pytest.raises(UnknownEvidenceClass, match="claim-level status"):
        make_class_assignment("e", "observation", "validated", "policy")


def test_class_is_assigned_in_the_same_call_that_admits_the_object(tmp_path):
    pool = _noaa_pool(tmp_path)
    observations = pool.all_observations()
    assert observations, "the NOAA fixture produced no observations"
    for observation in observations:
        assert pool.register.class_of(observation.id) == MEASURED
        assert pool.register.admissible_for_canonical_assertion(observation.id)
    # The whole chain, not only the observation.
    for record in (pool.get_record(r) for o in observations for r in o.record_ids):
        assert pool.register.class_of(record.id) == MEASURED
        document = pool.get_document(record.document_id)
        assert pool.register.class_of(document.id) == MEASURED
        assert pool.register.class_of(document.source_id) == MEASURED


def test_class_survives_persistence_restart_and_retrieval(tmp_path):
    """A new process against the same store. The register is rebuilt from
    disk, not carried over."""
    pool = _noaa_pool(tmp_path)
    before = {o.id: pool.register.class_of(o.id) for o in pool.all_observations()}

    restored = ClassAssignmentStore(tmp_path / "evidence").restore()
    after = {evidence_id: restored.class_of(evidence_id) for evidence_id in before}

    assert after == before
    assert set(after.values()) == {MEASURED}


def test_attempted_reclassification_is_refused(tmp_path):
    pool = _noaa_pool(tmp_path)
    observation = pool.all_observations()[0]
    other = make_class_assignment(observation.id, "observation", ASSERTED, "source_policy:other")
    with pytest.raises(ClassReassignment, match="refusing to reclassify"):
        pool.register.assign(other)
    assert pool.register.class_of(observation.id) == MEASURED


def test_an_assignment_cannot_be_mutated_in_place():
    assignment = make_class_assignment("e", "observation", MEASURED, "policy")
    with pytest.raises(FrozenInstanceError):
        assignment.evidence_class = ASSERTED  # type: ignore[misc]


def test_deserialization_with_an_altered_class_is_refused(tmp_path):
    """The on-disk tamper case. The class participates in the content
    hash, so editing it makes the record re-hash to something other than
    the id it is stored under."""
    pool = _noaa_pool(tmp_path)
    observation = pool.all_observations()[0]
    stored = assignment_to_dict(pool.register.assignment_for(observation.id))

    tampered = dict(stored, evidence_class=ASSERTED)
    with pytest.raises(ClassIdentityMismatch, match="no longer matches its own"):
        assignment_from_dict(tampered)

    # And through the store, on the real file.
    path = tmp_path / "evidence" / "evidence_classes" / f"{stored['id']}.json"
    assert path.exists()
    path.write_text(json.dumps(tampered))
    with pytest.raises(ClassIdentityMismatch):
        ClassAssignmentStore(tmp_path / "evidence").restore()


def test_a_wholesale_rewrite_under_a_new_id_is_caught_at_restore(tmp_path):
    """The other half of the tamper story: re-hashing consistently avoids
    the identity check, and then loses to the append-only store, because
    the original assignment is still there and two classes for one
    evidence id is a reassignment."""
    pool = _noaa_pool(tmp_path)
    observation = pool.all_observations()[0]

    forged = make_class_assignment(observation.id, "observation", ASSERTED, "source_policy:phase25")
    ClassAssignmentStore(tmp_path / "evidence").put(forged)

    with pytest.raises(ClassReassignment):
        ClassAssignmentStore(tmp_path / "evidence").restore()


def test_an_undeclared_source_kind_yields_unclassified_and_is_inadmissible(tmp_path):
    """§22's migration state, live rather than hypothetical. There is no
    bypass argument that would make this admissible."""
    silent = SourceClassPolicy(id="source_policy:empty", by_source_kind={})
    pool = _noaa_pool(tmp_path, policy=silent)

    observations = pool.all_observations()
    assert observations
    for observation in observations:
        assert pool.register.class_of(observation.id) == UNCLASSIFIED
        assert not pool.register.admissible_for_canonical_assertion(observation.id)
        assert not pool.register.admissible_for_training(observation.id)
    assert len(pool.register) == 0

    backlog = pool.register.unclassified(tuple(o.id for o in observations))
    assert len(backlog) == len(observations)


def test_two_sources_of_different_classes_stay_separate(tmp_path):
    noaa = _noaa_pool(tmp_path / "a")
    dataset = _dataset_pool(tmp_path / "b")
    assert {noaa.register.class_of(o.id) for o in noaa.all_observations()} == {MEASURED}
    assert {dataset.register.class_of(o.id) for o in dataset.all_observations()} == {ASSERTED}


# ------------------------------------------- proposals are not evidence


def test_a_derivation_cannot_be_classified_measured_or_asserted():
    for refused in (MEASURED, ASSERTED):
        with pytest.raises(ProposalClassRefused, match="produced by computation"):
            make_class_assignment("d", "derived_value", refused, "policy")
        with pytest.raises(ProposalClassRefused):
            make_class_assignment("g", "derived_grounding", refused, "policy")


def test_a_derived_value_admitted_through_the_pool_is_classified_derived(tmp_path):
    from evidence.types import make_derived_value

    pool = _dataset_pool(tmp_path)
    observation = pool.all_observations()[0]
    derived = make_derived_value(
        derived_from=(observation.id,),
        method="mean",
        content={"property": "tensile_strength", "value": 78.0, "unit": "MPa"},
        confidence=1.0,
        derived_at="2026-08-25T01:00:00Z",
    )
    pool.put_derived_value(derived)

    assert pool.register.class_of(derived.id) == DERIVED
    # Admissible for canonical assertion, inadmissible for training: a
    # derivation may be asserted, but training on it is the circularity.
    assert pool.register.admissible_for_canonical_assertion(derived.id)
    assert not pool.register.admissible_for_training(derived.id)


def test_a_derivation_never_inherits_the_class_of_its_inputs(tmp_path):
    from evidence.types import make_derived_value

    pool = _noaa_pool(tmp_path)
    observation = pool.all_observations()[0]
    assert pool.register.class_of(observation.id) == MEASURED

    derived = make_derived_value(
        derived_from=(observation.id,),
        method="daily_mean",
        content={"property": "water_level", "value": 1.0, "unit": "m"},
        confidence=1.0,
        derived_at="2026-08-25T01:00:00Z",
    )
    pool.put_derived_value(derived)
    assert pool.register.class_of(derived.id) == DERIVED


# ------------------------------------------------------ provenance_total


def test_every_acquired_object_traces_to_a_source(tmp_path):
    pool = _noaa_pool(tmp_path)
    for observation in pool.all_observations():
        for record_id in observation.record_ids:
            record = pool.get_record(record_id)
            document = pool.get_document(record.document_id)
            assert pool.get_source(document.source_id) is not None


# --------------------------------------- what this repository does not have


def _authored_sources():
    for package in ("daf", "science", "boundary", "bridge", "epistemics"):
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" not in path.as_posix():
                yield path


def test_no_training_loop_exists():
    """`no_circular_training`, checked rather than asserted. Vacuous
    today; it stops being vacuous the day someone adds a fit step."""
    forbidden = ("fit(", "backward(", "train_step", "optimizer.step", "gradient")
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _authored_sources()
        if any(token in path.read_text() for token in forbidden)
    ]
    assert offenders == []


def test_expected_information_gain_is_still_not_determinable():
    """`metric_before_optimization`. The vendored constant every phase
    since Phase 39 has preserved."""
    from materials.value import NOT_DETERMINABLE, evaluate_candidate_information_values  # noqa: F401

    source = (REPO_ROOT / "vendor/scout-retrieval-agent/materials/value.py").read_text()
    assert "expected_information_gain=NOT_DETERMINABLE" in source
    assert NOT_DETERMINABLE == "NOT_DETERMINABLE"


def test_no_agent_execution_exists():
    """`agent_concurrence_is_not_corroboration` and the whole model
    binding set are blocked by this one fact, so it is measured once."""
    tokens = ("anthropic", "openai", "mistral", "api_key", "chat.completions")
    offenders = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in _authored_sources()
        if any(token in path.read_text().lower() for token in tokens)
    ]
    assert offenders == []

    document = _yaml.loads((ARCHITECTURE / "model_binding.yaml").read_text())
    assert document["bindings"] == {}
    assert document["execution_retention"]["status"] == "no_agent_execution_in_repository"


def test_no_evidence_records_are_committed_to_this_repository():
    """§22's INSPECT, answered. Every pool in this repository is built per
    run against a temporary root, so there is no legacy corpus to migrate
    -- and any pool persisted before this phase has zero assignments on
    disk and is therefore wholly unclassified by construction."""
    document = _yaml.loads((ARCHITECTURE / "invariants.yaml").read_text())
    assert document["migration"]["committed_records_in_repository"] == 0
    assert not list(REPO_ROOT.glob("**/evidence/observations/*.json"))


def test_the_retraction_gap_is_recorded_and_not_quietly_built():
    """§9 directs recording the gap, not building the retraction system.
    Checked both ways: the record exists, and no delete path was added."""
    document = _yaml.loads((ARCHITECTURE / "invariants.yaml").read_text())
    assert document["retraction"]["status"] == "absent"

    store = (REPO_ROOT / "daf/storage/filesystem_store.py").read_text()
    for token in ("def delete", "def remove", "def retract", "unlink("):
        assert token not in store, f"a retraction path appeared: {token}"


# ------------------------------------------------------------ layering


def test_epistemics_is_a_leaf_layer():
    """`epistemics` is added BENEATH every existing layer, so no verified
    boundary had to move to accommodate it."""
    forbidden = ("daf", "science", "boundary", "bridge", "materials", "scout", "core")
    for path in sorted((REPO_ROOT / "epistemics").rglob("*.py")):
        if "__pycache__" in path.as_posix():
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                assert root not in forbidden, f"{path.name} imports {name}"


def test_epistemics_touches_the_substrate_only_through_content_hash():
    """The one vendored import allowed, because introducing a second
    identity scheme is the alternative."""
    imported = set()
    for path in sorted((REPO_ROOT / "epistemics").rglob("*.py")):
        if "__pycache__" in path.as_posix():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("evidence"):
                imported.add((node.module, tuple(a.name for a in node.names)))
    assert imported == {("evidence.identity", ("content_hash",))}


def test_the_invariant_ledger_names_every_test_in_this_file_it_claims():
    """A status of `enforced` pointing at this file must point at
    something that actually runs."""
    named = {
        inv.id
        for inv in load_invariants()
        if inv.enforcement and "test_epistemic_boundary.py" in inv.enforcement
    }
    assert named, "no invariant claims enforcement here"
    assert "class_assigned_at_ingest" in named
    assert "proposals_are_not_evidence" in named
