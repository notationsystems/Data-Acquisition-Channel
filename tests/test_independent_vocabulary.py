"""Phase 24: does Phase 23's mechanism generalize to terminology that
someone else authored, without needing an ontology?

    independently authored terminology  ("ultimate tensile strength")
              |
              v  explicit, evidence-backed mapping   bridge/vocabulary.py
    canonical concept                   ("tensile_strength")
              |
              v  resolve_sources(..., vocabulary)
    CandidateSource  ->  explicit selection  ->  Phase 21  ->  DAF  ->  Evidence

THE EVIDENCE IS REAL AND RECORDED. Unlike Phase 23's proof fixture, every
mapping here is backed by terminology retrieved from Wikidata's SPARQL
endpoint during this phase and stored verbatim in
`tests/fixtures/wikidata_mechanical_property_terms.json`, so each claim
is re-checkable rather than asserted.

TWO THINGS THE EVIDENCE FORCED, both of which are the point of the phase:

  * `tensile force` is published as an alias of Q76005 (ultimate tensile
    strength). It is NOT encoded: force is measured in newtons and
    strength in pascals, so they are dimensionally different quantities.
    An alias list is a starting point for curation, not an import.
  * `elastic modulus` is published BOTH as an alias of Q2091584 (Young's
    modulus) AND as its own concept, Q192005. The second is correct --
    "elastic modulus" names the general family (Young's, shear, bulk) --
    so it is declared RELATED_BUT_NOT_EQUIVALENT and never matches.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from materials.analysis import MaterialQuestion, analyze
from materials.model_state import predict

from boundary.acquisition_intent import make_acquisition_intent
from bridge.intent_execution import operationalize_intent
from bridge.source_capability import PROPERTY_NOT_DECLARED, SourceCapability, resolve_sources
from bridge.vocabulary import (
    EXACT_EQUIVALENT,
    PROPERTY,
    RELATED,
    AmbiguousVocabulary,
    VocabularyMapping,
    make_vocabulary,
)
from daf.catalog.checkpoint import CheckpointStore
from daf.orchestration.adapter_registry import AdapterRegistry
from daf.orchestration.bindings import graph_dataset_binding
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry
from daf.scheduling.runner import execute_plan
from helpers_state_gap import ENGINE, FORMULATION, measurement, trajectory
from science.acquisition_seam import intents_for
from science.information_gap import diagnose_information_gap

EVIDENCE_FILE = Path(__file__).resolve().parent / "fixtures" / "wikidata_mechanical_property_terms.json"

# Citations. Each names the entity whose published label/alias set
# supports the mapping; all are present in EVIDENCE_FILE.
UTS_ITEM = "wikidata:Q76005"
UTS_PROPERTY = "wikidata:P5479"
YOUNGS = "wikidata:Q2091584"
ELASTIC = "wikidata:Q192005"

# --- Vocabulary A: the terminology of the UTS *concept* item ----------
VOCABULARY_A = make_vocabulary(
    (
        VocabularyMapping(PROPERTY, "ultimate tensile strength", "tensile_strength", EXACT_EQUIVALENT, UTS_ITEM),
        VocabularyMapping(PROPERTY, "UTS", "tensile_strength", EXACT_EQUIVALENT, UTS_ITEM),
        VocabularyMapping(PROPERTY, "ultimate strength", "tensile_strength", EXACT_EQUIVALENT, UTS_ITEM),
        VocabularyMapping(PROPERTY, "modulus of elasticity", "youngs_modulus", EXACT_EQUIVALENT, YOUNGS),
        VocabularyMapping(PROPERTY, "Young modulus", "youngs_modulus", EXACT_EQUIVALENT, YOUNGS),
        # evidence-backed NON-equivalence, recorded so it stays rejected
        VocabularyMapping(PROPERTY, "elastic modulus", "youngs_modulus", RELATED, ELASTIC),
    )
)

# --- Vocabulary B: an independently authored source using symbols -----
VOCABULARY_B = make_vocabulary(
    (
        VocabularyMapping(PROPERTY, "Rm", "tensile_strength", EXACT_EQUIVALENT, UTS_PROPERTY),
        VocabularyMapping(PROPERTY, "Ftu", "tensile_strength", EXACT_EQUIVALENT, UTS_PROPERTY),
    )
)

MATDB_SOURCE = SourceDefinition(
    source_id="matdb", name="Materials database", domain="materials",
    adapter_id="graph-dataset", required_parameters=("path",),
)
# The source speaks the external vocabulary, verbatim.
MATDB_CAPABILITY = SourceCapability(
    source_id="matdb",
    properties=("ultimate tensile strength", "modulus of elasticity"),
    subject_kinds=("formulation",), roles=("OBSERVED",),
    context_keys=("temperature", "temperature_unit"),
)
SYMBOL_CAPABILITY = SourceCapability(
    source_id="matdb", properties=("Rm",), subject_kinds=("formulation",), roles=("OBSERVED",),
)


def _registry():
    registry = SourceRegistry()
    registry.register(MATDB_SOURCE)
    return registry


def _intent(property_name, context=None):
    return make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind="formulation",
        property=property_name, role="OBSERVED", target_context=context or {},
    )


# ====================================================================
# The evidence itself
# ====================================================================

def test_the_recorded_evidence_supports_every_encoded_mapping():
    """Each EXACT_EQUIVALENT mapping's alias must actually appear in the
    published label/alias set of the entity it cites. This is what makes
    the vocabulary auditable rather than merely asserted."""
    evidence = json.loads(EVIDENCE_FILE.read_text())
    entities = evidence["entities"]
    assert evidence["retrieved_from"] == "https://query.wikidata.org/sparql"

    published = {
        f"wikidata:{qid}": {entry["label"], *entry["aliases"]}
        for qid, entry in entities.items()
    }

    for vocabulary in (VOCABULARY_A, VOCABULARY_B):
        for mapping in vocabulary.mappings:
            if mapping.relationship != EXACT_EQUIVALENT:
                continue
            assert mapping.evidence in published, f"{mapping.evidence} is not in the recorded evidence"
            assert mapping.alias in published[mapping.evidence], (
                f"{mapping.alias!r} is not published under {mapping.evidence}"
            )


def test_a_published_alias_was_deliberately_not_encoded():
    """`tensile force` is published as an alias of Q76005 and is NOT
    encoded: force (N) and strength (Pa) are dimensionally different, so
    the published list contains an error. Importing an alias set
    wholesale would have imported it."""
    evidence = json.loads(EVIDENCE_FILE.read_text())
    assert "tensile force" in evidence["entities"]["Q76005"]["aliases"], (
        "the fixture must still contain the alias this test is about"
    )
    assert VOCABULARY_A.canonical_for(PROPERTY, "tensile force") == "tensile force"
    assert not any(m.alias == "tensile force" for m in VOCABULARY_A.mappings)

    resolution = resolve_sources(_intent("tensile force"), (MATDB_CAPABILITY,), _registry(), VOCABULARY_A)
    assert resolution.candidates == ()


# ====================================================================
# Section 4. external terminology reaches a candidate
# ====================================================================

@pytest.mark.parametrize("requested", ["tensile_strength", "UTS", "ultimate strength"])
def test_external_terminology_resolves_to_a_candidate(requested):
    """Section 4. The source declares `ultimate tensile strength`; the
    requirement may be phrased any of the evidence-backed ways."""
    resolution = resolve_sources(_intent(requested), (MATDB_CAPABILITY,), _registry(), VOCABULARY_A)
    assert [c.source_id for c in resolution.candidates] == ["matdb"]

    match = next(m for m in resolution.candidates[0].term_matches if m.dimension == PROPERTY)
    assert match.requested == requested
    assert match.canonical == "tensile_strength"
    assert match.declared == "ultimate tensile strength", "the source's own wording survives"


def test_a_second_canonical_concept_works_the_same_way():
    """`modulus of elasticity` -> `youngs_modulus`, from a different
    cited entity, proving the mechanism is not tuned to one concept."""
    resolution = resolve_sources(_intent("youngs_modulus"), (MATDB_CAPABILITY,), _registry(), VOCABULARY_A)
    assert [c.source_id for c in resolution.candidates] == ["matdb"]
    match = next(m for m in resolution.candidates[0].term_matches if m.dimension == PROPERTY)
    assert match.declared == "modulus of elasticity" and match.canonical == "youngs_modulus"


# ====================================================================
# Section 5. false equivalence, tested aggressively
# ====================================================================

@pytest.mark.parametrize(
    "requested",
    [
        "elastic modulus",     # published as an alias, but declared RELATED
        "yield_strength",      # Q3807177 -- a distinct concept
        "yield strength",
        "yield stress",
        "flexural modulus",    # Q5459047 -- a distinct concept
        "bending modulus",
        "tensile_modulus",
        "fracture_strength",
        "strength",
        "modulus",
    ],
)
def test_neighbouring_concepts_are_never_admitted_by_association(requested):
    """Section 5. Encoding `ultimate tensile strength -> tensile_strength`
    must not license any nearby mechanical property. Each of these is
    either a distinct Wikidata concept or has no declaration at all."""
    resolution = resolve_sources(_intent(requested), (MATDB_CAPABILITY,), _registry(), VOCABULARY_A)
    assert resolution.candidates == ()
    assert PROPERTY_NOT_DECLARED in resolution.mismatches[0].reasons


def test_a_related_declaration_records_the_link_without_ever_matching():
    """The RELATED relationship is the smallest representation the
    evidence forced. It is inspectable, and it is inert in matching --
    which is precisely the point: recording that `elastic modulus` is
    related to `youngs_modulus` is what keeps it from being re-proposed
    as an equivalence by the next reader of the alias list."""
    assert VOCABULARY_A.related_terms(PROPERTY, "youngs_modulus") == ("elastic modulus",)
    assert VOCABULARY_A.related_terms(PROPERTY, "elastic modulus") == ("youngs_modulus",)

    # inert in every matching operation
    assert VOCABULARY_A.canonical_for(PROPERTY, "elastic modulus") == "elastic modulus"
    assert VOCABULARY_A.declares(PROPERTY, "elastic modulus") is False
    assert resolve_sources(
        _intent("elastic modulus"), (MATDB_CAPABILITY,), _registry(), VOCABULARY_A
    ).candidates == ()

    # and it is not an ambiguity, because it asserts the opposite of one
    both = make_vocabulary(
        (
            VocabularyMapping(PROPERTY, "elastic modulus", "youngs_modulus", RELATED, ELASTIC),
            VocabularyMapping(PROPERTY, "Young modulus", "youngs_modulus", EXACT_EQUIVALENT, YOUNGS),
        )
    )
    assert both.canonical_for(PROPERTY, "Young modulus") == "youngs_modulus"
    assert both.canonical_for(PROPERTY, "elastic modulus") == "elastic modulus"


def test_relationships_are_validated_and_ambiguity_still_applies():
    with pytest.raises(ValueError, match="relationship must be one of"):
        VocabularyMapping(PROPERTY, "a", "b", "PROBABLY_THE_SAME")

    with pytest.raises(AmbiguousVocabulary, match="more than one canonical term"):
        make_vocabulary(
            (
                VocabularyMapping(PROPERTY, "UTS", "tensile_strength", EXACT_EQUIVALENT, UTS_ITEM),
                VocabularyMapping(PROPERTY, "UTS", "yield_strength", EXACT_EQUIVALENT, UTS_ITEM),
            )
        )


# ====================================================================
# Section 6. two independently authored vocabularies
# ====================================================================

def test_two_vocabularies_reach_one_canonical_concept_while_staying_distinct():
    """Section 6. Vocabulary A speaks words, Vocabulary B speaks symbols
    (`Rm`, `Ftu`, from the Wikidata PROPERTY entity rather than the
    concept item). Both reach `tensile_strength`; neither is merged into
    the other, and which source term matched stays recoverable."""
    a = resolve_sources(_intent("UTS"), (MATDB_CAPABILITY,), _registry(), VOCABULARY_A)
    b = resolve_sources(_intent("tensile_strength"), (SYMBOL_CAPABILITY,), _registry(), VOCABULARY_B)

    assert [c.source_id for c in a.candidates] == ["matdb"]
    assert [c.source_id for c in b.candidates] == ["matdb"]

    a_match = next(m for m in a.candidates[0].term_matches if m.dimension == PROPERTY)
    b_match = next(m for m in b.candidates[0].term_matches if m.dimension == PROPERTY)
    assert a_match.canonical == b_match.canonical == "tensile_strength", "same concept"
    assert a_match.declared == "ultimate tensile strength"
    assert b_match.declared == "Rm"
    assert a_match.declared != b_match.declared, "A and B remain distinguishable"

    # the vocabularies themselves are separate objects with separate citations
    assert VOCABULARY_A != VOCABULARY_B
    assert {m.evidence for m in VOCABULARY_B.mappings} == {UTS_PROPERTY}
    assert UTS_PROPERTY not in {m.evidence for m in VOCABULARY_A.mappings}

    # and neither knows the other's terms
    assert VOCABULARY_A.canonical_for(PROPERTY, "Rm") == "Rm"
    assert VOCABULARY_B.canonical_for(PROPERTY, "UTS") == "UTS"


# ====================================================================
# Section 7. conditioning dimensions survive normalization
# ====================================================================

def test_normalizing_a_property_never_rewrites_experimental_conditions():
    """Section 7. Vocabulary maps TERMINOLOGY, never values. Tensile
    strength at 25 C stays distinct from tensile strength at 100 C, and
    water level at MLLW from water level at STND."""
    at_25 = _intent("UTS", {"temperature": 25, "temperature_unit": "C"})
    at_100 = _intent("UTS", {"temperature": 100, "temperature_unit": "C"})
    assert at_25.id != at_100.id, "different conditions are different intents"

    both = [
        resolve_sources(intent, (MATDB_CAPABILITY,), _registry(), VOCABULARY_A)
        for intent in (at_25, at_100)
    ]
    assert all(r.candidates for r in both), "both are answerable by this source"
    assert both[0].candidates[0] != both[1].candidates[0], "but they are not the same request"
    assert both[0].candidates[0].intent_id != both[1].candidates[0].intent_id

    # context VALUES are never canonicalized -- only key names ever are
    for value in ("MLLW", "STND", "25", "C"):
        assert VOCABULARY_A.canonical_for(PROPERTY, value) == value

    mllw = make_acquisition_intent(
        subject_natural_key="8454000", subject_kind="monitoring_station",
        property="water_level", role="OBSERVED", target_context={"datum": "MLLW"},
    )
    stnd = make_acquisition_intent(
        subject_natural_key="8454000", subject_kind="monitoring_station",
        property="water_level", role="OBSERVED", target_context={"datum": "STND"},
    )
    assert mllw.id != stnd.id, "a vocabulary cannot make two datums the same measurement"


# ====================================================================
# Section 8. identity invariants, again
# ====================================================================

def test_adding_evidence_backed_mappings_changes_no_identity(tmp_path):
    """Section 8, measured: the same dataset acquired through a plan
    reached with the external vocabulary is byte-identical to one reached
    without it."""
    from daf.storage.durable_pool import DurablePool
    from daf.storage.filesystem_store import FilesystemEvidenceStore

    dataset = tmp_path / "shared" / "matdb.json"
    dataset.parent.mkdir(parents=True, exist_ok=True)
    dataset.write_text(json.dumps([measurement("ts-801", 97)]))

    canonical_capability = SourceCapability(
        source_id="matdb", properties=("tensile_strength",),
        subject_kinds=("formulation",), roles=("OBSERVED",),
    )

    def _acquire(root, intent, capability, vocabulary):
        sources = _registry()
        resolution = resolve_sources(intent, (capability,), sources, vocabulary)
        assert resolution.candidates
        plan = operationalize_intent(
            intent, sources.get(resolution.candidates[0].source_id),
            plan_id="phase24-plan", parameters={"path": str(dataset)},
        )
        pool = DurablePool(FilesystemEvidenceStore(root / "evidence"))
        adapters = AdapterRegistry()
        adapters.register(graph_dataset_binding())
        result = execute_plan(
            plan, sources, adapters, pool, CheckpointStore(root / "ck"),
            requested_at="2026-08-25T10:00:00Z",
        )
        assert result.outcome.value == "acquired"
        observation = pool.all_observations()[0]
        record = pool.get_record(observation.record_ids[0])
        document = pool.get_document(record.document_id)
        return {
            "plan_id": plan.plan_id, "source_id": plan.source_id,
            "artifact_id": {a.artifact_id for a in result.artifacts},
            "version_id": {a.version_id for a in result.artifacts},
            "document_id": document.id, "evidence_source_id": document.source_id,
            "record_id": record.id, "observation_id": observation.id,
        }

    from bridge.vocabulary import EMPTY_VOCABULARY

    without = _acquire(tmp_path / "a", _intent("tensile_strength"), canonical_capability, EMPTY_VOCABULARY)
    with_external = _acquire(tmp_path / "b", _intent("UTS"), MATDB_CAPABILITY, VOCABULARY_A)
    assert without == with_external, "vocabulary participates in no identity"


def test_model_state_identity_is_untouched_by_external_vocabulary(tmp_path):
    _pool, iteration, candidate, (s0, s1, s2) = trajectory(tmp_path)
    before = (s0.id, s1.id, s2.id)

    intent = intents_for(diagnose_information_gap(s1, candidate, iteration))[0]
    resolve_sources(intent, (MATDB_CAPABILITY,), _registry(), VOCABULARY_A)

    assert (s0.id, s1.id, s2.id) == before
    assert predict(s1, candidate).sample_count == 1


# ====================================================================
# Section 9. the full loop, driven by external terminology
# ====================================================================

def test_external_terminology_drives_the_complete_loop(tmp_path):
    """Section 9 and the stop condition (Outcome A). A requirement
    phrased in an independently authored vocabulary reaches real acquired
    evidence, with selection still explicit and the scientific state
    untouched by acquisition."""
    pool, _iteration, candidate, (_s0, s1, _s2) = trajectory(tmp_path)
    external_intent = _intent("UTS")

    sources = _registry()
    assert resolve_sources(external_intent, (MATDB_CAPABILITY,), sources).candidates == (), (
        "unreachable without the vocabulary"
    )
    resolution = resolve_sources(external_intent, (MATDB_CAPABILITY,), sources, VOCABULARY_A)
    assert [c.source_id for c in resolution.candidates] == ["matdb"]

    # --- EXPLICIT selection ---------------------------------------------
    selected = sources.get(resolution.candidates[0].source_id)
    dataset = tmp_path / "matdb.json"
    dataset.write_text(json.dumps([measurement("ts-901", 97), measurement("ts-902", 94)]))
    plan = operationalize_intent(
        external_intent, selected, plan_id="phase24-loop", parameters={"path": str(dataset)}
    )
    serialized = json.dumps(dict(plan.parameters))
    for term in ("UTS", "tensile_strength", "ultimate tensile strength"):
        assert term not in serialized, "semantic normalization is not parameter translation"

    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())
    result = execute_plan(
        plan, sources, adapters, pool, CheckpointStore(tmp_path / "ck2"),
        requested_at="2026-08-25T10:00:00Z",
    )
    assert result.outcome.value == "acquired" and len(result.artifacts) == 2

    answer = analyze(pool, ENGINE, MaterialQuestion(material_natural_key=FORMULATION, property="tensile_strength"))
    assert {97, 94} <= {o.content["value"] for o in answer.observed}
    assert predict(s1, candidate).sample_count == 1, "acquisition moved no scientific state"
