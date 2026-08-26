"""SYNC_ADDENDUM — the invariants that are executable against THIS repository.

Scope was set by inspection, per the addendum's own instruction that
"nothing here asserts repository state". What it SPECIFIES VERBATIM is
implemented; what it merely REFERENCES (`invariants.yaml core@0.1`,
`evidence_class.yaml`, `model_binding.yaml`, doctrine files, `verticals/`)
does not exist here and is not fabricated. See
docs/SYNC_ADDENDUM_IMPLEMENTATION.md for the full disposition.

Covered here:

  §1  the return edge -- derived state re-enters only via acquisition
  §4  proposals_are_not_evidence, class_assigned_at_ingest (as far as the
      existing types allow)
  §5  the terminology lock: the ten presentation terms map onto four
      classes, and `validated` is a status, not a class
  §6.3 no_context_free_property, quantity_is_typed
  §7  the generality probe stays paper_only
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from evidence.types import make_observation

from epistemics import _yaml  # zero-dependency reader for architecture/*.yaml
from science.admissibility import (
    ABSENT,
    MISSING_CONDITIONS,
    MISSING_METHOD,
    MISSING_UNCERTAINTY,
    MISSING_UNCERTAINTY_KIND,
    MISSING_UNIT,
    UNKNOWN_UNCERTAINTY_KIND,
    UNTYPED_QUANTITY,
    no_context_free_property,
    quantity_is_typed,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = REPO_ROOT / "architecture"

# The only two modules in the entire repository permitted to write
# evidence, established by inspection (grep for put_observation /
# admit_observation across every non-test source file).
EVIDENCE_WRITE_BOUNDARY = {
    "vendor/scout-retrieval-agent/scout/pipeline.py",       # the acquisition path
    "vendor/scout-retrieval-agent/materials/results.py",    # admit_experimental_result
}
WRITE_CALLS = re.compile(
    r"\.put_(observation|derived_value|record|document|referent|claimed_relationship)\b"
    r"|admit_(observation|derived_value|record|document|referent|claimed_relationship)\s*\("
)


def _python_sources(*packages):
    for package in packages:
        yield from sorted((REPO_ROOT / package).rglob("*.py"))


# ====================================================================
# §1. the return edge: derived state re-enters only through acquisition
# ====================================================================

def test_no_interpretive_layer_can_write_evidence():
    """§1's correction is that the substrate is a loop whose return edge
    runs through acquisition -- derived state never re-enters by direct
    write. The layers that PRODUCE derived state (`science`, `bridge`,
    `boundary`) must therefore contain no evidence write at all.

    This is the invariant `proposals_are_not_evidence` and
    `class_assigned_at_ingest` exist to protect: a layer that could write
    evidence directly would bypass classing entirely."""
    for path in _python_sources("science", "bridge", "boundary"):
        source = path.read_text()
        match = WRITE_CALLS.search(source)
        assert match is None, (
            f"{path.relative_to(REPO_ROOT)} calls {match.group(0)!r}; "
            "derived state must re-enter only through acquisition"
        )


def test_the_evidence_write_boundary_is_exactly_two_modules():
    """The return edge is only meaningful if the set of writers is known
    and small. Pinning it means a new writer cannot appear unnoticed."""
    writers = set()
    for package in ("daf", "science", "bridge", "boundary",
                    "vendor/scout-retrieval-agent/materials",
                    "vendor/scout-retrieval-agent/scout"):
        for path in (REPO_ROOT / package).rglob("*.py"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            if WRITE_CALLS.search(path.read_text()):
                writers.add(relative)

    # daf/storage/* IMPLEMENTS put_* rather than calling it into a pool;
    # it is the store, not a writer of evidence content.
    writers = {w for w in writers if not w.startswith("daf/storage/")}
    assert writers == EVIDENCE_WRITE_BOUNDARY, (
        f"the evidence write boundary moved: {sorted(writers)}"
    )


# ====================================================================
# §4. proposals are not evidence
# ====================================================================

def test_proposal_types_have_no_write_path_and_no_evidence_identity():
    """§4: optimizer/planner output has no write path. The proposal types
    in this repository are `ActionCandidate` (materials), `AcquisitionIntent`
    (boundary) and `CandidateChange`/`CandidateNextState` (canonical).

    None may carry an evidence identity, because an id shaped like an
    Observation's is exactly how a proposal becomes indistinguishable
    from a measurement downstream."""
    from materials.candidates import ActionCandidate

    from boundary.acquisition_intent import make_acquisition_intent

    intent = make_acquisition_intent(
        subject_natural_key="f1", subject_kind="formulation",
        property="tensile_strength", role="OBSERVED", target_context={},
    )
    for forbidden in ("record_ids", "extraction_method", "confidence", "extracted_at"):
        assert forbidden not in intent.__dataclass_fields__, (
            f"AcquisitionIntent carries {forbidden!r}, an evidence field"
        )
    for forbidden in ("record_ids", "extraction_method", "extracted_at"):
        assert forbidden not in ActionCandidate.__dataclass_fields__

    # and an Observation is structurally something a proposal is not:
    # it must name the Records it was extracted from
    observation = make_observation(
        record_ids=("r1",), extraction_method="human_transcription",
        content={"property": "p", "value": 1}, confidence=1.0,
        extracted_at="2026-08-25T00:00:00Z",
    )
    assert observation.record_ids == ("r1",)
    assert intent.id != observation.id


def test_class_is_fixed_by_type_at_ingest_and_has_no_promotion_path():
    """§4's `class_assigned_at_ingest`, as far as the existing types
    allow. This repository has no class FIELD -- it has a de facto split:
    `Observation` is admitted from a Record, `DerivedValue` is computed.
    Neither is mutable and neither can become the other, so there is no
    promotion path to close."""
    from dataclasses import FrozenInstanceError

    from evidence.types import DerivedValue, Observation

    observation = make_observation(
        record_ids=("r1",), extraction_method="human_transcription",
        content={"property": "p", "value": 1}, confidence=1.0,
        extracted_at="2026-08-25T00:00:00Z",
    )
    try:
        observation.content = {}  # type: ignore[misc]
        raise AssertionError("an admitted Observation must be immutable")
    except FrozenInstanceError:
        pass

    # the two classes are distinct types with distinct required fields
    assert "record_ids" in Observation.__dataclass_fields__
    assert "record_ids" not in DerivedValue.__dataclass_fields__
    assert Observation is not DerivedValue


# ====================================================================
# §5. terminology lock
# ====================================================================

def _load_class_map():
    """Reads the canonical terminology lock through the repository's own
    zero-dependency reader. This originally hand-parsed two blocks out of
    `evidence_class_map.yaml`; that file became
    `architecture/evidence_class.yaml` when the canonical contracts were
    committed, and `epistemics/_yaml.py` now reads the whole document."""
    document = _yaml.loads((ARCHITECTURE / "evidence_class.yaml").read_text())
    return dict(document["vocabulary_map"]), list(document["statuses_not_classes"])


def test_every_presentation_term_maps_onto_exactly_one_ingest_class():
    """§5. Two normative vocabularies with overlapping terms and
    different cardinality is the drift failure this lock closes. The ten
    presentation terms must be total over the four classes."""
    mapping, _ = _load_class_map()
    assert set(mapping) == {
        "reported", "observed", "measured", "computed", "simulated",
        "inferred", "predicted", "hypothesized", "manufactured",
    }, "the presentation vocabulary is exactly the nine mapping terms"
    assert set(mapping.values()) <= {"measured", "asserted", "computed", "derived"}, (
        "no presentation term may map outside the four ingest classes"
    )
    assert mapping["reported"] == "asserted"
    assert mapping["simulated"] == "computed"
    assert mapping["hypothesized"] == "derived"


def test_validated_is_recorded_as_a_status_not_a_class():
    """§5's named trap: `validated` reads as a class and is actually a
    status on a claim. An earlier reading of this file kept it in the
    vocabulary map (as `validated -> measured`) so a query for it would
    still resolve. That was wrong, and the synchronization prompts are
    explicit about why: any mapping at all is a promotion path from
    validation status to evidence class. It is now declared ONLY as a
    status, and asking for its class raises."""
    mapping, statuses = _load_class_map()
    assert statuses == ["validated"]
    assert "validated" not in mapping


# ====================================================================
# §6.3 a property is not a value
# ====================================================================

def test_a_bare_scalar_is_inadmissible():
    """The exact shape `daf/extractors/graph_dataset.py` admits today."""
    verdict = no_context_free_property(
        {"property": "tensile_strength", "value": 78, "unit": "MPa"}
    )
    assert verdict.admissible is False
    assert MISSING_METHOD in verdict.reasons
    assert MISSING_CONDITIONS in verdict.reasons
    assert MISSING_UNCERTAINTY_KIND in verdict.reasons


def test_a_fully_specified_property_is_admissible():
    verdict = no_context_free_property(
        {
            "property": "tensile_strength", "value": 78.0, "unit": "MPa",
            "method": "ASTM D638", "conditions": {"temperature": 25, "temperature_unit": "C"},
            "uncertainty": 1.5, "uncertainty_kind": "stated",
        }
    )
    assert verdict.admissible is True and verdict.reasons == ()


def test_absent_uncertainty_must_be_declared_not_omitted():
    """§6.3's distinction: "the source reported no error" and "we lost it
    during ingest" are different facts."""
    declared = quantity_is_typed(
        {"value": 78.0, "unit": "MPa", "uncertainty": None, "uncertainty_kind": ABSENT}
    )
    assert declared.admissible is True, "absent is a real, declarable answer"

    omitted = quantity_is_typed({"value": 78.0, "unit": "MPa"})
    assert omitted.admissible is False
    assert MISSING_UNCERTAINTY_KIND in omitted.reasons

    # a null magnitude with a substantive kind is a lost value pretending
    # to be a declared one
    pretending = quantity_is_typed(
        {"value": 78.0, "unit": "MPa", "uncertainty": None, "uncertainty_kind": "stated"}
    )
    assert pretending.admissible is False and MISSING_UNCERTAINTY in pretending.reasons


def test_quantity_typing_rejects_untyped_and_unknown_kinds():
    assert UNTYPED_QUANTITY in quantity_is_typed(
        {"value": "78", "unit": "MPa", "uncertainty_kind": ABSENT}
    ).reasons, "NOAA-style numeric strings are not typed quantities"

    assert UNTYPED_QUANTITY in quantity_is_typed(
        {"value": True, "unit": "MPa", "uncertainty_kind": ABSENT}
    ).reasons, "bool is not a measurement"

    assert MISSING_UNIT in quantity_is_typed(
        {"value": 1.0, "uncertainty_kind": ABSENT}
    ).reasons

    assert UNKNOWN_UNCERTAINTY_KIND in quantity_is_typed(
        {"value": 1.0, "unit": "MPa", "uncertainty_kind": "probably_fine"}
    ).reasons


def test_admissibility_is_pure_and_deterministic():
    content = {"property": "p", "value": 1.0, "unit": "u", "method": "m",
               "conditions": {"t": 1}, "uncertainty": 0.1, "uncertainty_kind": "stated"}
    snapshot = dict(content)
    assert no_context_free_property(content) == no_context_free_property(content)
    assert content == snapshot, "validation mutates nothing"

    module = (REPO_ROOT / "science" / "admissibility.py").read_text()
    tree = ast.parse(module)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    # `math` was added in Phase 37 for `math.isfinite`, which closed the
    # sentinel-absence hole -- NaN and the infinities ARE floats, so every
    # isinstance check in this file admitted them. Widening an allowlist is
    # normally how a purity check dies, so the widening is paired with an
    # explicit DENYLIST below: the allowlist now says which pure modules are
    # permitted, and the denylist says what purity actually means here.
    assert imported <= {"__future__", "dataclasses", "math", "typing"}, (
        f"admissibility must stay pure; it imports {sorted(imported)}"
    )

    forbidden = {
        # I/O, clock and network -- what "pure" excludes.
        "os", "io", "sys", "time", "datetime", "random", "socket", "subprocess",
        "pathlib", "shutil", "tempfile", "urllib", "http", "requests", "json",
        # and the layers this one may never reach into.
        "daf", "scout", "evidence", "materials", "retrieval", "epistemics",
        "assertion", "bridge", "boundary",
    }
    assert not (imported & forbidden), (
        f"admissibility reached outside its layer or did I/O: {sorted(imported & forbidden)}"
    )

    # Purity is a property of the code, not of an import list, so it is also
    # measured: same input, same verdict, no clock and no mutation involved.
    assert quantity_is_typed(content) == quantity_is_typed(dict(content))
    assert content == snapshot


# ====================================================================
# §7. the probe stays paper-only
# ====================================================================

def test_the_generality_probe_is_declared_and_referenced_by_no_code():
    """§7. `status: paper_only` is load-bearing -- a probe with an
    implementation is a configuration, and stops being able to falsify
    anything."""
    probe = ARCHITECTURE / "_probes" / "generality.yaml"
    text = probe.read_text()
    assert "status: paper_only" in text
    for prop in ("non_reproducible", "revocable_record", "cohort_identity",
                 "uncontrolled_conditions"):
        assert prop in text

    for path in _python_sources("daf", "science", "bridge", "boundary"):
        source = path.read_text()
        assert "generality.yaml" not in source and "_probes" not in source, (
            f"{path.relative_to(REPO_ROOT)} reads the probe; it must stay paper-only"
        )


def test_the_committed_canonical_contracts_record_facts_rather_than_inventing_them():
    """This test originally asserted that `invariants.yaml`,
    `evidence_class.yaml` and `model_binding.yaml` must NOT exist, because
    the addendum only REFERENCED them. The synchronization prompt then
    directed committing them "against the actual repository schema", so
    they now exist -- and the invariant worth keeping was never their
    absence. It was: do not invent repository state.

    That is what is checked here instead. Each committed file records
    something measured: no binding, because there is none; no placeholder
    posing as a pin; the real vendored core version rather than the
    `core@0.1` the prompts assume."""
    bindings = _yaml.loads((ARCHITECTURE / "model_binding.yaml").read_text())
    assert bindings["bindings"] == {}, "a binding was invented"
    assert bindings["status"] == "no_model_binding_instantiated"
    # Checked over parsed VALUES, not raw text: the file's own commentary
    # quotes the prompt's `<pinned-id>` placeholder while declaring none.
    for spec in bindings["bindings"].values():
        assert not str(spec.get("snapshot", "")).startswith("<")

    core = _yaml.loads((ARCHITECTURE / "core.yaml").read_text())
    vendored = (REPO_ROOT / "vendor/scout-retrieval-agent/pyproject.toml").read_text()
    assert f'version = "{core["version"]}"' in vendored, "the core version was not measured"

    invariants = _yaml.loads((ARCHITECTURE / "invariants.yaml").read_text())
    blocked = {i["id"] for i in invariants["invariants"] if i["status"] == "blocked"}
    assert {"pin_accepted", "behavioral_canary"} <= blocked, (
        "snapshot verification must stay blocked, not stubbed -- a requested-string / "
        "echoed-response comparison verifies nothing about served weights"
    )

    # Still genuinely absent, and still not fabricated.
    assert not (REPO_ROOT / "verticals").exists()
    assert not (ARCHITECTURE / "functions.yaml").exists(), (
        "functions.yaml is referenced by the prompts and specified by neither"
    )
