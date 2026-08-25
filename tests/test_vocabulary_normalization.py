"""Phase 23: explicit alias -> canonical normalization in front of Phase
22's capability resolution.

    lexical requirement (UTS)
            |
            v  explicit, declared mapping        bridge/vocabulary.py
    canonical concept (tensile_strength)
            |
            v  resolve_sources(..., vocabulary)  bridge/source_capability.py
    CandidateSource[]  (carrying requested / canonical / declared)
            |
            v  EXPLICIT selection -> Phase 21 -> DAF -> SCOUT -> Evidence

THE VOCABULARY CONTENT HERE IS A PROOF FIXTURE, NOT AN ONTOLOGY. The
audit measured every real source in this repository and found NO two
labels denoting the same scientific concept: `graph_dataset` reports
record-declared properties, `noaa_water_level_measurements` reports
`water_level`, and nothing else reports a property at all. The
`UTS -> tensile_strength` mappings below therefore demonstrate the
MECHANISM and assert nothing about materials science.

The negative cases are the substance. Lexical similarity must never
create a match: `tensile_strength` vs `tensile_modulus`, `viscosity` vs
`modulus`, `strength` vs `tensile_strength` all stay rejected unless
someone explicitly wrote the equivalence down.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from materials.analysis import MaterialQuestion, analyze
from materials.model_state import predict

from boundary.acquisition_intent import make_acquisition_intent
from bridge.intent_execution import operationalize_intent
from bridge.source_capability import (
    PROPERTY_NOT_DECLARED,
    ROLE_NOT_DECLARED,
    SUBJECT_KIND_NOT_DECLARED,
    SourceCapability,
    resolve_sources,
)
from bridge.vocabulary import (
    CONTEXT_KEY,
    DIMENSIONS,
    EMPTY_VOCABULARY,
    PROPERTY,
    ROLE,
    SUBJECT_KIND,
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

# A source whose own terminology differs from the requirement's.
LAB_SOURCE = SourceDefinition(
    source_id="lab-uts", name="Tensile lab", domain="materials",
    adapter_id="graph-dataset", required_parameters=("path",),
)
LAB_CAPABILITY = SourceCapability(
    source_id="lab-uts",
    properties=("ultimate_tensile_strength",), subject_kinds=("formulation",),
    roles=("OBSERVED",), context_keys=("test_temperature",),
)

# PROOF FIXTURE -- see the module docstring.
VOCABULARY = make_vocabulary(
    (
        VocabularyMapping(PROPERTY, "UTS", "tensile_strength"),
        VocabularyMapping(PROPERTY, "ultimate_tensile_strength", "tensile_strength"),
        VocabularyMapping(CONTEXT_KEY, "test_temperature", "temperature"),
    )
)


def _registry(source=LAB_SOURCE):
    registry = SourceRegistry()
    registry.register(source)
    return registry


def _intent(property_name="tensile_strength", subject_kind="formulation", role="OBSERVED", context=None):
    return make_acquisition_intent(
        subject_natural_key=FORMULATION, subject_kind=subject_kind,
        property=property_name, role=role, target_context=context or {},
    )


def _property_match(candidate):
    return next(m for m in candidate.term_matches if m.dimension == PROPERTY)


# ====================================================================
# A/B. explicit alias match, and Phase 22 behaviour preserved
# ====================================================================

def test_an_explicit_alias_turns_a_rejected_source_into_a_candidate():
    """Section 16A and 14: the same requirement, the same source, and
    the only difference is a declared mapping."""
    intent = _intent("tensile_strength")

    without = resolve_sources(intent, (LAB_CAPABILITY,), _registry())
    assert without.candidates == ()
    assert PROPERTY_NOT_DECLARED in without.mismatches[0].reasons

    with_vocabulary = resolve_sources(intent, (LAB_CAPABILITY,), _registry(), VOCABULARY)
    assert [c.source_id for c in with_vocabulary.candidates] == ["lab-uts"]


def test_the_requirement_side_may_also_be_an_alias():
    """`UTS` is what the scientist asked for; the source says
    `ultimate_tensile_strength`; both canonicalize to the same concept."""
    resolution = resolve_sources(_intent("UTS"), (LAB_CAPABILITY,), _registry(), VOCABULARY)
    assert [c.source_id for c in resolution.candidates] == ["lab-uts"]
    match = _property_match(resolution.candidates[0])
    assert (match.requested, match.canonical, match.declared) == (
        "UTS", "tensile_strength", "ultimate_tensile_strength"
    )


def test_exact_matching_still_works_with_no_vocabulary_at_all():
    """Section 16B. Adding this layer changes no existing behaviour:
    without a vocabulary, terms are compared literally."""
    exact_capability = SourceCapability(
        source_id="lab-uts", properties=("tensile_strength",),
        subject_kinds=("formulation",), roles=("OBSERVED",),
    )
    resolution = resolve_sources(_intent("tensile_strength"), (exact_capability,), _registry())
    assert [c.source_id for c in resolution.candidates] == ["lab-uts"]

    match = _property_match(resolution.candidates[0])
    assert match.via_alias is False, "no mapping was needed or used"
    assert match.requested == match.canonical == match.declared == "tensile_strength"

    assert EMPTY_VOCABULARY.canonical_for(PROPERTY, "anything") == "anything"
    assert EMPTY_VOCABULARY.declares(PROPERTY, "anything") is False


# ====================================================================
# C + section 17. unknown terms, and lexical similarity that must not match
# ====================================================================

@pytest.mark.parametrize(
    "requested",
    ["strength", "tensile_modulus", "viscosity", "modulus", "melt_viscosity", "Tensile_Strength"],
)
def test_lexically_similar_terms_never_match_without_an_explicit_mapping(requested):
    """Sections 16C and 17, made permanent. None of these is declared, so
    none may broaden the requirement -- including a case difference,
    which is a lexical variation this layer deliberately does not
    normalize."""
    resolution = resolve_sources(_intent(requested), (LAB_CAPABILITY,), _registry(), VOCABULARY)
    assert resolution.candidates == ()
    assert PROPERTY_NOT_DECLARED in resolution.mismatches[0].reasons


def test_an_unrelated_source_stays_rejected_even_with_a_vocabulary():
    """Section 14's second half: normalization must not make everything
    match. NOAA water level is still not a tensile-strength source."""
    noaa = SourceCapability(
        source_id="lab-uts", properties=("water_level",),
        subject_kinds=("monitoring_station",), roles=("OBSERVED",),
    )
    resolution = resolve_sources(_intent("UTS"), (noaa,), _registry(), VOCABULARY)
    assert resolution.candidates == ()
    reasons = resolution.mismatches[0].reasons
    assert PROPERTY_NOT_DECLARED in reasons and SUBJECT_KIND_NOT_DECLARED in reasons


# ====================================================================
# D. ambiguity is rejected, deterministically and order-independently
# ====================================================================

def test_one_alias_with_two_canonical_targets_is_rejected():
    """Section 16D / 12. The vocabulary is refused; no interpretation is
    chosen, and declaration order does not matter."""
    conflicting = [
        VocabularyMapping(PROPERTY, "UTS", "tensile_strength"),
        VocabularyMapping(PROPERTY, "UTS", "ultimate_modulus"),
    ]
    for ordering in (conflicting, list(reversed(conflicting))):
        with pytest.raises(AmbiguousVocabulary, match="more than one canonical term"):
            make_vocabulary(ordering)


def test_a_chain_is_rejected_rather_than_followed():
    """Resolving `UTS -> X -> tensile_strength` transitively would be
    inference. A term that is both an alias and a canonical target makes
    the canonical form depend on where the chain is entered, so the
    vocabulary is refused instead."""
    with pytest.raises(AmbiguousVocabulary, match="both an alias and a canonical target"):
        make_vocabulary(
            (
                VocabularyMapping(PROPERTY, "UTS", "interim_term"),
                VocabularyMapping(PROPERTY, "interim_term", "tensile_strength"),
            )
        )


def test_the_same_alias_in_two_dimensions_is_not_a_conflict():
    """Dimensions are independent namespaces, so declaring `temperature`
    in two of them is legitimate rather than ambiguous."""
    vocabulary = make_vocabulary(
        (
            VocabularyMapping(CONTEXT_KEY, "test_temperature", "temperature"),
            VocabularyMapping(PROPERTY, "test_temperature", "sample_temperature"),
        )
    )
    assert vocabulary.canonical_for(CONTEXT_KEY, "test_temperature") == "temperature"
    assert vocabulary.canonical_for(PROPERTY, "test_temperature") == "sample_temperature"


def test_malformed_mappings_are_rejected_at_construction():
    with pytest.raises(ValueError, match="dimension must be one of"):
        VocabularyMapping("not_a_dimension", "a", "b")
    with pytest.raises(ValueError, match="non-empty"):
        VocabularyMapping(PROPERTY, "", "b")
    with pytest.raises(ValueError, match="dimension must be one of"):
        EMPTY_VOCABULARY.canonical_for("not_a_dimension", "a")
    assert set(DIMENSIONS) == {PROPERTY, SUBJECT_KIND, ROLE, CONTEXT_KEY}


# ====================================================================
# E. dimensions do not leak into one another
# ====================================================================

def test_a_property_alias_cannot_satisfy_subject_matching():
    """Section 16E / 7. `station -> formulation` declared in the PROPERTY
    dimension must have no effect on subject-kind comparison."""
    cross_dimensional = make_vocabulary((VocabularyMapping(PROPERTY, "station", "formulation"),))
    capability = SourceCapability(
        source_id="lab-uts", properties=("tensile_strength",),
        subject_kinds=("formulation",), roles=("OBSERVED",),
    )
    resolution = resolve_sources(
        _intent("tensile_strength", subject_kind="station"), (capability,), _registry(), cross_dimensional
    )
    assert resolution.candidates == ()
    assert resolution.mismatches[0].reasons == (SUBJECT_KIND_NOT_DECLARED,)


def test_context_keys_normalize_in_their_own_dimension():
    """The source conditions on `test_temperature`; the requirement asks
    about `temperature`. An explicit CONTEXT_KEY mapping joins them."""
    intent = _intent(context={"temperature": 25})
    without = resolve_sources(intent, (LAB_CAPABILITY,), _registry())
    assert without.candidates == () and without.mismatches[0].missing_context_keys == ("temperature",)

    resolution = resolve_sources(intent, (LAB_CAPABILITY,), _registry(), VOCABULARY)
    assert [c.source_id for c in resolution.candidates] == ["lab-uts"]
    context_match = next(m for m in resolution.candidates[0].term_matches if m.dimension == CONTEXT_KEY)
    assert (context_match.requested, context_match.canonical, context_match.declared) == (
        "temperature", "temperature", "test_temperature"
    )


# ====================================================================
# F/G/H. provenance, determinism, independence
# ====================================================================

def test_source_terminology_is_preserved_alongside_the_canonical_concept():
    """Section 16F / 5 / 10. The match explains all three vocabularies at
    once, and the source's own wording is never overwritten."""
    resolution = resolve_sources(_intent("UTS"), (LAB_CAPABILITY,), _registry(), VOCABULARY)
    candidate = resolution.candidates[0]

    match = _property_match(candidate)
    assert match.requested == "UTS", "what the scientist asked"
    assert match.canonical == "tensile_strength", "what the catalog mapped it to"
    assert match.declared == "ultimate_tensile_strength", "what the source calls it"
    assert match.via_alias is True

    # the capability object itself is untouched
    assert LAB_CAPABILITY.properties == ("ultimate_tensile_strength",)
    assert candidate.matched_property == "tensile_strength", "canonical is surfaced flat too"


def test_normalization_is_deterministic_and_order_independent():
    """Section 16G."""
    intent = _intent("UTS")
    first = resolve_sources(intent, (LAB_CAPABILITY,), _registry(), VOCABULARY)
    second = resolve_sources(intent, (LAB_CAPABILITY,), _registry(), VOCABULARY)
    assert first == second

    reordered = make_vocabulary(tuple(reversed(VOCABULARY.mappings)))
    assert reordered == VOCABULARY, "the same mappings in any order are the same vocabulary"
    assert resolve_sources(intent, (LAB_CAPABILITY,), _registry(), reordered) == first


def test_unrelated_mappings_do_not_change_existing_matches():
    """Section 16H."""
    baseline = resolve_sources(_intent("UTS"), (LAB_CAPABILITY,), _registry(), VOCABULARY)
    extended = make_vocabulary(
        VOCABULARY.mappings
        + (
            VocabularyMapping(PROPERTY, "sea_level", "water_level"),
            VocabularyMapping(SUBJECT_KIND, "gauge", "monitoring_station"),
            VocabularyMapping(ROLE, "MEASURED", "OBSERVED"),
        )
    )
    assert resolve_sources(_intent("UTS"), (LAB_CAPABILITY,), _registry(), extended) == baseline


def test_direction_is_one_way():
    """Section 9. `alias -> canonical` never implies the reverse, so
    nothing here can produce a parameter named `UTS` from a canonical
    requirement."""
    assert VOCABULARY.canonical_for(PROPERTY, "UTS") == "tensile_strength"
    assert VOCABULARY.canonical_for(PROPERTY, "tensile_strength") == "tensile_strength"
    assert VOCABULARY.declares(PROPERTY, "UTS") is True
    assert VOCABULARY.declares(PROPERTY, "tensile_strength") is False


# ====================================================================
# I/J. identity, and the full composition
# ====================================================================

def test_normalization_changes_no_identity_and_acquires_nothing(tmp_path, monkeypatch):
    """Section 16I / 13 / 21. Canonicalization is semantic metadata: it
    performs no acquisition and leaves every identity untouched."""
    from daf.scheduling import runner

    monkeypatch.setattr(
        runner, "execute_plan",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("normalization must not acquire")),
    )
    intent = _intent("UTS")
    before = intent.id
    resolution = resolve_sources(intent, (LAB_CAPABILITY,), _registry(), VOCABULARY)

    assert resolution.candidates
    assert intent.id == before, "an intent's identity is not canonicalized"
    assert resolution.candidates[0].intent_id == before
    assert LAB_SOURCE.source_id == "lab-uts"


def test_full_composition_from_alias_requirement_to_acquired_evidence(tmp_path):
    """Section 16J and the stop condition: a requirement expressed in the
    source's foreign terminology reaches real acquired evidence, with
    selection still explicit."""
    pool, iteration, candidate, (_s0, s1, _s2) = trajectory(tmp_path)

    # the real scientific requirement, then restated in an alias
    gap = diagnose_information_gap(s1, candidate, iteration)
    assert gap.requirements[0].property == "tensile_strength"
    real_intent = intents_for(gap)[0]
    alias_intent = _intent("UTS")
    assert alias_intent.id != real_intent.id, "different wording is a different intent identity"

    # the source speaks a different dialect and is only reachable via the mapping
    sources = _registry()
    assert resolve_sources(alias_intent, (LAB_CAPABILITY,), sources).candidates == ()
    resolution = resolve_sources(alias_intent, (LAB_CAPABILITY,), sources, VOCABULARY)
    assert [c.source_id for c in resolution.candidates] == ["lab-uts"]

    # --- EXPLICIT selection, then Phase 21 unchanged --------------------
    selected = sources.get(resolution.candidates[0].source_id)
    dataset = tmp_path / "lab.json"
    dataset.write_text(json.dumps([measurement("ts-601", 93), measurement("ts-602", 89)]))
    plan = operationalize_intent(
        alias_intent, selected, plan_id="vocab-plan-1", parameters={"path": str(dataset)}
    )
    assert "UTS" not in json.dumps(dict(plan.parameters)), (
        "normalization must never generate an acquisition parameter from a scientific alias"
    )

    adapters = AdapterRegistry()
    adapters.register(graph_dataset_binding())
    result = execute_plan(
        plan, sources, adapters, pool, CheckpointStore(tmp_path / "ck2"),
        requested_at="2026-08-25T08:00:00Z",
    )
    assert result.outcome.value == "acquired" and len(result.artifacts) == 2

    answer = analyze(pool, ENGINE, MaterialQuestion(material_natural_key=FORMULATION, property="tensile_strength"))
    assert {93, 89} <= {o.content["value"] for o in answer.observed}

    # and nothing moved the scientific state
    assert predict(s1, candidate).sample_count == 1


# ====================================================================
# Section 1.13. role is not collateral damage of a property mapping
# ====================================================================

def test_a_property_mapping_never_changes_the_role():
    """Section 1.13. Normalizing `UTS -> tensile_strength` must not make
    an OBSERVED request satisfiable by a PREDICTED-only source, nor the
    reverse. Role lives in its own dimension and no property mapping
    touches it."""
    observed_only = SourceCapability(
        source_id="lab-uts", properties=("ultimate_tensile_strength",),
        subject_kinds=("formulation",), roles=("OBSERVED",),
    )
    predicted_only = SourceCapability(
        source_id="lab-uts", properties=("ultimate_tensile_strength",),
        subject_kinds=("formulation",), roles=("PREDICTED",),
    )

    observed_request = _intent("UTS", role="OBSERVED")
    predicted_request = _intent("UTS", role="PREDICTED")

    assert resolve_sources(observed_request, (observed_only,), _registry(), VOCABULARY).candidates
    assert resolve_sources(predicted_request, (predicted_only,), _registry(), VOCABULARY).candidates

    # crossed, both directions must fail -- the property mapping succeeded
    # in each case, so ROLE is the only thing rejecting them
    for request, capability in (
        (observed_request, predicted_only), (predicted_request, observed_only)
    ):
        resolution = resolve_sources(request, (capability,), _registry(), VOCABULARY)
        assert resolution.candidates == ()
        assert resolution.mismatches[0].reasons == (ROLE_NOT_DECLARED,)

    # and the matched role is always the requested one, never rewritten
    candidate = resolve_sources(observed_request, (observed_only,), _registry(), VOCABULARY).candidates[0]
    assert candidate.matched_role == "OBSERVED"
    role_match = next(m for m in candidate.term_matches if m.dimension == ROLE)
    assert (role_match.requested, role_match.canonical, role_match.declared) == (
        "OBSERVED", "OBSERVED", "OBSERVED"
    )


# ====================================================================
# Section 1.12. context normalization is narrow, never broadening
# ====================================================================

def test_normalizing_one_context_key_leaves_the_others_untouched():
    """Section 1.12. A `test_temperature -> temperature` mapping must not
    make `temperature_unit`, `datum` or `unit` interchangeable with
    anything, nor with each other."""
    capability = SourceCapability(
        source_id="lab-uts", properties=("ultimate_tensile_strength",),
        subject_kinds=("formulation",), roles=("OBSERVED",),
        context_keys=("test_temperature", "temperature_unit"),
    )

    # the mapped key resolves; the unmapped-but-declared key matches literally
    resolution = resolve_sources(
        _intent("UTS", context={"temperature": 25, "temperature_unit": "C"}),
        (capability,), _registry(), VOCABULARY,
    )
    assert [c.source_id for c in resolution.candidates] == ["lab-uts"]
    context_matches = {
        m.requested: m for m in resolution.candidates[0].term_matches if m.dimension == CONTEXT_KEY
    }
    assert context_matches["temperature"].declared == "test_temperature"
    assert context_matches["temperature"].via_alias is True
    assert context_matches["temperature_unit"].declared == "temperature_unit"
    assert context_matches["temperature_unit"].via_alias is False, "matched without any mapping"

    # keys the source never declared stay rejected, named individually
    for undeclared in ({"datum": "MLLW"}, {"unit": "MPa"}, {"pressure": 1}):
        rejected = resolve_sources(
            _intent("UTS", context=undeclared), (capability,), _registry(), VOCABULARY
        )
        assert rejected.candidates == ()
        assert rejected.mismatches[0].missing_context_keys == tuple(undeclared)

    # and no context mapping exists that could join them
    for term in ("datum", "unit", "temperature_unit"):
        assert VOCABULARY.canonical_for(CONTEXT_KEY, term) == term


# ====================================================================
# Section 5. purity, proven structurally
# ====================================================================

def test_the_vocabulary_module_can_reach_nothing_impure():
    """Section 5. Normalization must do no I/O, read no clock and use no
    randomness. Proven at the AST level rather than by observation: the
    module imports nothing that could."""
    module_path = Path(__file__).resolve().parent.parent / "bridge" / "vocabulary.py"
    tree = ast.parse(module_path.read_text())

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])

    assert imported <= {"__future__", "dataclasses", "typing"}, (
        f"the normalization layer must stay pure; it imports {sorted(imported)}"
    )
    for impure in (
        "os", "io", "sys", "socket", "random", "time", "datetime", "pathlib",
        "urllib", "requests", "sqlite3", "subprocess", "secrets", "uuid",
    ):
        assert impure not in imported

    # Section 4: it is semantic infrastructure, so it names no layer at all
    for layer in ("daf", "science", "boundary", "bridge", "materials", "evidence"):
        assert layer not in imported, f"vocabulary must not depend on {layer}"


def test_daf_never_imports_the_normalization_layer():
    """Section 4's third invariant, stated directly about this module.

    Checked over IMPORTS rather than raw text: several DAF adapters use
    the word "vocabulary" in prose (`usgs_earthquakes.py` describes the
    "fixed vocabulary of values this adapter ever substitutes"), and a
    substring search would report that as a dependency."""
    daf_root = Path(__file__).resolve().parent.parent / "daf"
    for module_path in sorted(daf_root.rglob("*.py")):
        tree = ast.parse(module_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            else:
                continue
            for name in names:
                assert name.split(".")[0] not in {"bridge", "science", "boundary"}, (
                    f"{module_path.name} imports {name}, reversing the dependency direction"
                )


# ====================================================================
# Sections 1.9 / 6. identity is empirically unchanged by normalization
# ====================================================================

def test_normalization_changes_no_acquisition_or_evidence_identity(tmp_path):
    """Sections 1.9 and 6, measured rather than argued: the SAME dataset
    acquired through a plan reached WITHOUT a vocabulary and through a
    plan reached WITH one produces byte-identical identities at every
    level -- because normalization participates in no content hash."""
    from daf.storage.durable_pool import DurablePool
    from daf.storage.filesystem_store import FilesystemEvidenceStore

    shared_dataset = tmp_path / "shared" / "lab.json"
    shared_dataset.parent.mkdir(parents=True, exist_ok=True)
    shared_dataset.write_text(json.dumps([measurement("ts-701", 95)]))

    exact_capability = SourceCapability(
        source_id="lab-uts", properties=("tensile_strength",),
        subject_kinds=("formulation",), roles=("OBSERVED",),
    )

    def _acquire(root, intent, capability, vocabulary):
        sources = _registry()
        resolution = resolve_sources(intent, (capability,), sources, vocabulary)
        assert resolution.candidates, "this arm must reach a candidate"
        selected = sources.get(resolution.candidates[0].source_id)
        plan = operationalize_intent(
            intent, selected, plan_id="identity-plan", parameters={"path": str(shared_dataset)}
        )
        pool = DurablePool(FilesystemEvidenceStore(root / "evidence"))
        adapters = AdapterRegistry()
        adapters.register(graph_dataset_binding())
        result = execute_plan(
            plan, sources, adapters, pool, CheckpointStore(root / "ck"),
            requested_at="2026-08-25T09:00:00Z",
        )
        assert result.outcome.value == "acquired"
        observation = pool.all_observations()[0]
        record = pool.get_record(observation.record_ids[0])
        document = pool.get_document(record.document_id)
        return {
            "plan_id": plan.plan_id,
            "source_id": plan.source_id,
            "artifact_id": {a.artifact_id for a in result.artifacts},
            "version_id": {a.version_id for a in result.artifacts},
            "document_id": document.id,
            "evidence_source_id": document.source_id,
            "record_id": record.id,
            "observation_id": observation.id,
        }

    # arm A: no vocabulary needed -- the source already speaks canonically
    without = _acquire(tmp_path / "a", _intent("tensile_strength"), exact_capability, EMPTY_VOCABULARY)
    # arm B: the candidate is only reachable through an explicit mapping
    with_vocabulary = _acquire(tmp_path / "b", _intent("UTS"), LAB_CAPABILITY, VOCABULARY)

    assert without == with_vocabulary, (
        "normalization must not participate in acquisition or evidence identity"
    )

    # AcquisitionRequest semantics are likewise untouched
    from daf.catalog.plan import AcquisitionPlan

    plan = AcquisitionPlan(plan_id="identity-plan", source_id="lab-uts", parameters={"path": "x"})
    request = plan.to_request(requested_at="2026-08-25T09:00:00Z")
    assert (request.source_id, dict(request.parameters), request.requested_at) == (
        "lab-uts", {"path": "x"}, "2026-08-25T09:00:00Z"
    )


def test_normalization_changes_no_model_state_identity(tmp_path):
    """Section 1.9's last item, measured: a ModelState built over
    acquired evidence is identical whether or not a vocabulary was
    consulted on the way to acquiring it."""
    _pool, iteration, candidate, (s0, s1, s2) = trajectory(tmp_path)
    before = (s0.id, s1.id, s2.id)

    gap = diagnose_information_gap(s1, candidate, iteration)
    intent = intents_for(gap)[0]
    resolve_sources(intent, (LAB_CAPABILITY,), _registry(), VOCABULARY)

    assert (s0.id, s1.id, s2.id) == before
    assert predict(s1, candidate).sample_count == 1
    assert gap.state_id == s1.id


# ====================================================================
# Section 8. semantic normalization is not parameter translation
# ====================================================================

def test_a_canonical_requirement_never_generates_a_source_flavoured_parameter():
    """Section 8. Knowing `UTS` and `tensile_strength` are the same
    concept must not cause a plan to carry either term as an acquisition
    parameter. Parameter naming comes only from the caller's explicit
    operational mapping (Phase 21), which this phase did not extend."""
    sources = _registry()
    resolution = resolve_sources(_intent("UTS"), (LAB_CAPABILITY,), sources, VOCABULARY)
    selected = sources.get(resolution.candidates[0].source_id)

    plan = operationalize_intent(
        _intent("UTS"), selected, plan_id="p", parameters={"path": "/data/lab.json"}
    )
    assert dict(plan.parameters) == {"path": "/data/lab.json"}, (
        "the plan carries exactly what the caller supplied, and nothing derived from the vocabulary"
    )
    serialized = json.dumps(dict(plan.parameters))
    for term in ("UTS", "tensile_strength", "ultimate_tensile_strength", "property"):
        assert term not in serialized
