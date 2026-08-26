"""`daq_capabilities.yaml` and its pinned canonicalization.

The exchange artifacts are content-addressed and the joint decision record
is bound to their hashes. That guarantee is only as good as the
serializer's determinism, so these tests lock it -- and they lock the
things that make this artifact an ANSWER rather than a monologue:

  * regeneration is byte-identical (a hash that moves proves nothing);
  * the shared fixture matches the digest the OTHER repository records,
    which is how the two confirm they agree on the encoding before either
    artifact's hash means anything;
  * canonical output round-trips through an INDEPENDENT parser back to
    the exact input object;
  * every requirement row addressed to `daq` is answered with a measured
    status, and no answer is an intention;
  * the artifact contains no workload selection.

The canonicalizer itself is vendored byte-identically rather than
reimplemented, and `test_the_vendored_canonicalizer_is_byte_identical`
would catch a local edit to it.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCHANGE = REPO_ROOT / "architecture" / "exchange"
sys.path.insert(0, str(EXCHANGE))

import canonical_yaml as cy  # noqa: E402
from build_daq_capabilities import (  # noqa: E402
    CAPABILITIES,
    DOCUMENT,
    EXECUTION_RECORD_RESOLUTION,
    RECURSIVE_DEPTH_DETERMINATION,
    REQUIREMENT_RESPONSES,
    UNRESOLVED_EDGES,
)

yaml = pytest.importorskip("yaml")


# --------------------------------------------------- canonicalization

def test_serialization_is_deterministic():
    assert cy.canonical_bytes(DOCUMENT) == cy.canonical_bytes(DOCUMENT)
    assert cy.canonical_sha256(DOCUMENT).startswith("sha256:")


def test_shared_fixture_matches_the_digest_the_other_repository_records():
    """The agreement check. Both repositories run this against the same
    fixture bytes; a disagreement here means every downstream hash refers
    to a different encoding."""
    fixture = EXCHANGE / "canonicalization_fixture.yaml"
    recorded = (EXCHANGE / "canonicalization_fixture.sha256").read_text().strip()
    assert cy.canonical_sha256(cy.FIXTURE) == recorded
    assert cy.file_sha256(fixture) == recorded


def test_canonical_output_round_trips_through_an_independent_parser():
    """PyYAML, not our own reader -- this is what catches a value that
    silently serializes to the wrong type."""
    assert yaml.safe_load(cy.canonical_dump(cy.FIXTURE)) == cy.FIXTURE
    assert yaml.safe_load(cy.canonical_dump(DOCUMENT)) == DOCUMENT


def test_the_vendored_canonicalizer_is_byte_identical_to_its_docstring_claim():
    """It is vendored, not reimplemented. A local edit would make the two
    repositories disagree on bytes while both looked correct."""
    source = (EXCHANGE / "canonical_yaml.py").read_text()
    assert "STDLIB ONLY, deliberately" in source
    assert "import yaml" not in source, "the canonicalizer must not depend on PyYAML"


# ------------------------------------------------------- the artifact

def test_committed_artifact_matches_regeneration():
    committed = (EXCHANGE / "daq_capabilities.yaml").read_bytes()
    assert committed == cy.canonical_bytes(DOCUMENT)
    recorded = (EXCHANGE / "daq_capabilities.sha256").read_text().strip()
    assert recorded == cy.canonical_sha256(DOCUMENT)
    assert recorded == cy.file_sha256(EXCHANGE / "daq_capabilities.yaml")


def test_generator_is_reproducible_from_a_clean_run():
    before = (EXCHANGE / "daq_capabilities.yaml").read_bytes()
    subprocess.run([sys.executable, "build_daq_capabilities.py"], cwd=str(EXCHANGE),
                   check=True, capture_output=True)
    assert (EXCHANGE / "daq_capabilities.yaml").read_bytes() == before


def test_artifact_contains_no_workload_selection():
    """Measured capabilities and answers only. An artifact that ranked or
    recommended would be making the joint decision on the decision
    record's behalf."""
    assert DOCUMENT["contains_workload_selection"] is False
    text = (EXCHANGE / "daq_capabilities.yaml").read_text().lower()
    for forbidden in ("recommend", "we should", "selected_workload",
                      "highest_leverage", "ranking", "best candidate"):
        assert forbidden not in text, f"artifact appears to make a selection: {forbidden!r}"


# ------------------------------------------------ capability inventory

def test_every_capability_uses_the_fixed_vocabulary_and_traces_evidence():
    allowed = set(DOCUMENT["classification_vocabulary"])
    assert allowed == {"EXISTING", "REUSABLE", "SMALL EXTENSION", "MISSING", "OUT OF SCOPE"}
    for name, entry in CAPABILITIES.items():
        assert entry["classification"] in allowed, f"{name}: {entry['classification']}"
        assert entry["evidence"], f"{name} has no traced evidence"
        assert len(entry["evidence"]) > 40, f"{name}'s evidence is too thin to check"


def test_the_inventory_records_both_capabilities_and_gaps():
    """An inventory that is all one classification is a mood, not a
    measurement."""
    classifications = {e["classification"] for e in CAPABILITIES.values()}
    assert "EXISTING" in classifications and "MISSING" in classifications


# ------------------------------------------- answers to raised rows

def test_every_requirement_response_carries_a_measured_status():
    allowed = {"SATISFIED", "UNSATISFIED", "PARTIALLY_SATISFIED",
               "SATISFIED_WITH_A_SHAPE_MISMATCH"}
    for name, row in REQUIREMENT_RESPONSES.items():
        assert row["daf_status"] in allowed, f"{name}: {row['daf_status']}"
        assert row["measured_basis"], f"{name} answers without a measured basis"
        assert row["raised_by"].startswith("scl_requirements.yaml"), name


def test_both_kalman_blocking_rows_are_answered():
    """These are the two rows that decide whether the recursive workload
    is buildable at all, and they were raised as separate dependencies.
    Answering only one would leave the joint decision to infer the other."""
    for row in ("structured_measurement_uncertainty", "recursive_generation_depth"):
        assert row in REQUIREMENT_RESPONSES, f"{row} was raised and is unanswered"
        assert REQUIREMENT_RESPONSES[row]["daf_status"] == "UNSATISFIED"


def test_the_fourier_row_is_answered_as_satisfied_with_its_caveat_stated():
    """The one workload whose DAQ-side modality genuinely exists today.
    The caveat matters as much as the answer: DAF supplies timestamps and
    the transform takes one scalar spacing."""
    modality = REQUIREMENT_RESPONSES["ordered_scalar_sequence"]
    assert modality["daf_status"] == "SATISFIED"
    spacing = REQUIREMENT_RESPONSES["annotating_sample_spacing"]
    assert spacing["daf_status"] == "SATISFIED_WITH_A_SHAPE_MISMATCH"
    assert "360.0" in spacing["measured_basis"], "the uniformity claim must be measured"
    assert "uniformity_is_unchecked" in spacing["caveat"]


def test_a_row_whose_two_halves_differ_says_so():
    """`stable_sample_and_variable_identity` was raised as one row and has
    two different answers. Collapsing it to a single verdict would lose
    the half that is already solved."""
    row = REQUIREMENT_RESPONSES["stable_sample_and_variable_identity"]
    assert row["daf_status"] == "PARTIALLY_SATISFIED"
    assert "sample identity" in row["measured_basis"].lower()
    assert "variable identity" in row["measured_basis"].lower()


# --------------------------------------------------------- findings

def test_the_nonscalar_finding_states_one_extension_with_a_measured_reason():
    finding = DOCUMENT["nonscalar_quantity_finding"]
    assert finding["multivariate_value"]["representable"] is False
    assert finding["structured_uncertainty"]["representable"] is False
    # the asymmetry is the finding: they fail at different layers
    assert finding["multivariate_value"]["failure_layer"] != \
        finding["structured_uncertainty"]["failure_layer"]
    assert "worse" in finding["why_one_extension"]
    assert finding["measured_not_inferred"].startswith("tests/")
    assert finding["still_open_after_a_container_fix"], (
        "a container fix is not the whole answer and the artifact must say so")


def test_the_execution_record_divergence_is_answered_as_decided():
    assert EXECUTION_RECORD_RESOLUTION["status"] == "DECIDED"
    assert EXECUTION_RECORD_RESOLUTION["decided_by"] == "daf"
    assert EXECUTION_RECORD_RESOLUTION["shared_core_is_the_intersection"] is True
    core = set(EXECUTION_RECORD_RESOLUTION["shared_core"])
    for kind in ("acquisition_only", "computation_only"):
        assert core.isdisjoint(EXECUTION_RECORD_RESOLUTION[kind]), kind
    assert EXECUTION_RECORD_RESOLUTION["is_a_bend"] is False
    assert EXECUTION_RECORD_RESOLUTION["enforced_now"].startswith("tests/")


def test_the_depth_determination_routes_correctly_and_says_why():
    d = RECURSIVE_DEPTH_DETERMINATION
    assert d["implemented"] is False
    assert d["correction_mode"] == "write_it_correctly_first"
    assert d["is_a_bend"] is False
    # ...but the reasoning must name what DOES change, or "not a bend"
    # is an assurance rather than an analysis
    assert "evidence" in d["bend_reasoning"].lower()
    assert d["the_condition_that_would_make_it_a_bend"]
    assert d["bend_protocol_exists_in_daf"] is False
    assert d["proposed_rule_status"] == "offered_not_adopted", (
        "adopting the other repository's rule verbatim would make it a forwarded instruction")


def test_unresolved_edges_say_why_they_are_not_solved_here():
    for name, edge in UNRESOLVED_EDGES.items():
        assert edge["status"] == "RECORDED_UNRESOLVED", name
        assert edge["edge"], name
    unowned = UNRESOLVED_EDGES["uniformity_is_unchecked"]
    assert unowned["owner"].startswith("unassigned")
    assert unowned["why_it_is_not_solved_here"]


# ================================================ the COLLECTION class (§2.1)
#
# The always-quote rule closed the ambiguity class one level down, among
# scalars. This is the same defect one level up, measured after that fix
# landed and repaired the same way: emitter-side, by refusing the form.


def test_a_sequence_nested_directly_in_a_sequence_is_refused():
    """MEASURED BEFORE THE REFUSAL. `canonical_dump({"k": [["a"], ["b"]]})`
    emitted the compact block form `- - "a"`, which is valid YAML 1.2 that
    the two readers in this pair TYPE DIFFERENTLY: PyYAML returns
    `[["a"], ["b"]]`, the minimal reader returns the strings
    `['- "a"', '- "b"']`. Same bytes, same digest, two different values --
    exactly the condition pinning the encoding exists to rule out.

    The repair is emitter-side because there is no shape both accept:
    written out long, the minimal reader RAISES on the bare `-` rather
    than mistyping it. Teaching one reader to parse the compact form
    would leave the bytes ambiguous for every other reader, which
    relocates the problem instead of removing it -- the same argument
    that made the scalar fix emitter-side."""
    for shape in ([["a"], ["b"]], [[], [1]], [(1,)], [1, ["x"]]):
        with pytest.raises(TypeError, match="sequence nested directly in a sequence"):
            cy.canonical_dump({"k": shape})


def test_the_refusal_is_narrow_and_the_legal_shapes_still_emit():
    """A mapping inside a sequence, and a sequence inside a mapping, are
    both fine and unaffected. Only sequence-directly-inside-sequence is
    refused, so the refusal costs nothing any real artifact does."""
    for document in (
        {"k": ["a", "b"]},
        {"k": [{"a": 1}, {"b": 2}]},
        {"k": {"a": {"b": 1}}},
        {"k": [{"a": [1, 2]}]},
        {"k": [{}, {"a": 1}]},
        {"k": {"a": {}, "b": []}},
        {"k": [{"b": {"c": ["x"]}}]},
    ):
        assert yaml.safe_load(cy.canonical_dump(document)) == document


def test_the_fixture_pins_the_collection_class_not_only_scalars():
    """The scalar class is pinned by `implicit_typing_traps`. Until Phase
    37 nothing pinned the shapes where the block renderer's dash-collapse
    actually runs, which is where the divergence lived."""
    shapes = cy.FIXTURE["collection_shapes"]
    assert set(shapes) == {
        "empty_map_in_a_sequence",
        "empty_seq_under_a_key_in_a_sequence",
        "map_in_seq_in_map_in_seq",
        "seq_under_a_key_in_a_map_in_a_seq",
    }
    for value in shapes.values():
        assert yaml.safe_load(cy.canonical_dump({"v": value}))["v"] == value


# ==================================================== the ESCAPE class (§2.1)
#
# A different defect from the two above, and the difference decides the
# repair. The bytes here have exactly ONE correct meaning under YAML 1.2
# and PyYAML already returns it; the minimal reader was simply
# non-conformant. So this one is fixed reader-side -- fixing a wrong
# reader is not the reader-side normalization the always-quote rule
# forbids, and it moves no artifact and no digest.


@pytest.mark.parametrize("value", [
    'he said "x"', "a\\b", 'a\\"b', "a\nb", "a\tb", "a\rb",
    "C:\\Users\\x", 'he said "hi" # not a comment', 'he said "hi": and more',
    "\\", 'ends with "', "",
])
def test_every_escape_the_emitter_can_produce_round_trips_identically(value):
    """`_quote` escapes exactly five sequences -- backslash, double quote,
    newline, carriage return, tab -- and the always-quote rule sends EVERY
    string through it. So any value containing one of those arrives at the
    reader escaped, and until Phase 37 the minimal reader returned it with
    the backslashes still in place."""
    text = cy.canonical_dump({"k": value})
    assert yaml.safe_load(text)["k"] == value


def test_escaped_keys_round_trip_too():
    document = {'a "b"': 1, "c\\d": 2}
    assert yaml.safe_load(cy.canonical_dump(document)) == document


def test_the_emitter_refuses_a_non_finite_float():
    """Checked here rather than assumed: the shared serializer is already
    clean on the axis that produced the NaN finding elsewhere in this
    phase. `_format_float` raises rather than emitting `.nan`/`.inf`,
    which is the same writer-side rule applied one layer down."""
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="non-finite"):
            cy.canonical_dump({"k": value})
