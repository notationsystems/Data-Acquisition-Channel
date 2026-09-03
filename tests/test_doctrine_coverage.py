"""The trigger on the doctrine source list, and the population that made
it worth having.

A zero doctrine regeneration diff certifies that `architecture/`'s
projection is current. It certifies that only for the files
`architecture/doctrine.yaml` NAMES. This file measures the rest -- and
fails when the deferral recorded in `architecture/doctrine_coverage.yaml`
stops being valid, so the parked decision cannot fade the way two earlier
ones did.

Nothing here decides whether the source list should be derived.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARCHITECTURE = REPO_ROOT / "architecture"
COVERAGE = loads((ARCHITECTURE / "doctrine_coverage.yaml").read_text())
DEFERRAL = COVERAGE["the_deferral"]

# The two artifacts covered by neither the projection nor a test, pinned
# as of 2026-08-27. This is a BASELINE OF A KNOWN GAP, never a permission:
# the trigger below fires the moment a third joins them.
# TIGHTENED 2026-08-27, by the trigger firing on the SHRINK direction:
# selection_rule_defect.yaml was re-measured and bound
# (tests/test_selection_rule_defect.py), and leaving it in this baseline
# would have been the stale allowance the message warns about.
# TIGHTENED AGAIN 2026-09-03, by the same trigger firing on the same
# direction: tests/test_ecosystem_census.py now reads
# kalman_validation_preregistration.yaml AND asserts a pinned digest of
# its content, so it is bound rather than merely mentioned -- the
# distinction this file's own `naming_is_not_reading` note draws.
#
# The set is now EMPTY, and two constructs below used to consume it: a
# `for artifact in KNOWN_UNBOUND` loop and a `KNOWN_UNBOUND <= shared`
# subset assertion. Both pass trivially over an empty set. Emptying the
# baseline and leaving them would have manufactured two vacuous
# assertions in the same edit that closed a real gap, so both were
# replaced rather than left to read green over nothing.
KNOWN_UNBOUND = frozenset()


def _doctrine_sources() -> set:
    return {s.split("/")[-1] for s in loads((ARCHITECTURE / "doctrine.yaml").read_text())["sources"]}


def _architecture_artifacts() -> set:
    return {p.name for p in ARCHITECTURE.glob("*.yaml")} - {"doctrine.yaml"}


def _named_by_a_test() -> set:
    """Every architecture artifact some test names.

    A LOWER BOUND on binding, and deliberately not claimed as more: a
    test that names a file without asserting anything about its content
    passes here. See `what_this_check_cannot_see` in the record.
    """
    # This file is excluded WHOLESALE. Two attempts got it wrong and the
    # trigger caught both, which is the argument for the trigger:
    #   1. excluding it entirely left doctrine_coverage.yaml -- which this
    #      file genuinely binds -- reading as unbound;
    #   2. excluding only the KNOWN_UNBOUND literal let this file's own
    #      mention of kalman_validation_preregistration.yaml (in the
    #      naming-is-not-reading test) count as binding it. That is the
    #      exact false positive the record warns about, committed inside
    #      the check that warns about it.
    # So: this file's mentions never count, and the one artifact it really
    # does bind is added back explicitly and asserted below.
    # A TEST MAY DECLARE THAT NAMING IS NOT BINDING.
    #
    # The detector asks whether any test NAMES an artifact, which is a
    # lower bound on binding and has now produced a false positive in the
    # other direction: tests/test_kalman_preregistration_currency.py
    # names the shared pre-registration to re-derive two arithmetic
    # identities, which is not asserting its claims -- and its own record
    # says so. The detector counted it bound and the two tests disagreed.
    #
    # Resolved by DECLARATION rather than by a second filename exclusion.
    # A test that reads an artifact without binding it says so in a
    # module-level DOES_NOT_BIND tuple, and this subtracts exactly those
    # names for exactly that file. That is a property any test can use,
    # not a list of files this check happens to know about -- which is
    # what the growing-exclusion-list shape would have been.
    corpus = []
    for path in sorted((REPO_ROOT / "tests").glob("*.py")):
        if path.name == "test_doctrine_coverage.py":
            continue
        text = path.read_text()
        disclaimed = set()
        for line in text.splitlines():
            if line.startswith("DOES_NOT_BIND"):
                disclaimed = {token.strip().strip("\"'") for token in
                              line.split("(", 1)[-1].rstrip(")").split(",") if token.strip()}
        corpus.append((text, disclaimed))

    named = set()
    for artifact in _architecture_artifacts():
        if any(artifact in text and artifact not in disclaimed for text, disclaimed in corpus):
            named.add(artifact)
    return named | {"doctrine_coverage.yaml"}


def test_the_projection_does_not_cover_every_architecture_artifact():
    """The measurement itself, asserted so it cannot quietly stop being
    true. If the list ever does cover everything, the deferral below is
    moot and this fails to say so."""
    artifacts, sources = _architecture_artifacts(), _doctrine_sources()
    assert sources < artifacts, (
        "every architecture artifact is now a doctrine source. The deferral in "
        "architecture/doctrine_coverage.yaml is resolved by circumstance and should be retired "
        "rather than left standing."
    )
    assert len(artifacts - sources) >= 2, "the excluded population should be re-measured"


def test_the_deferral_on_the_doctrine_source_list_still_holds():
    """THE TRIGGER. The deferral is valid while the exclusions are
    curation rather than drift -- which is measurable: an excluded
    artifact bound by its own test is covered by something, and one bound
    by nothing is covered by nothing at all.

    A third artifact in neither category means the exclusions have stopped
    being deliberate, and the parked decision has to be taken."""
    outside = _architecture_artifacts() - _doctrine_sources()
    unbound = outside - _named_by_a_test()

    assert unbound == set(KNOWN_UNBOUND), (
        f"the unbound set moved: {sorted(unbound ^ KNOWN_UNBOUND)}. If it GREW, an artifact is now "
        "covered by neither the doctrine projection nor any test, the exclusions are drift rather "
        "than curation, and the deferral in architecture/doctrine_coverage.yaml has LAPSED -- the "
        "source-list decision has to be taken rather than deferred again. If it SHRANK, bind the "
        "baseline down; a stale allowance is how a gap becomes permanent."
    )
    section = COVERAGE["one_artifact_is_not_covered_for_currency"]
    for artifact in KNOWN_UNBOUND:                       # empty today; kept for the regrow case
        assert artifact in section["measured"], (
            f"{artifact} is unbound and the record does not name it"
        )
    # The empty case says something the loop cannot, so it is asserted
    # rather than left as the loop's silence.
    if not KNOWN_UNBOUND:
        assert "no artifact in architecture/ is unbound" in section["measured"], (
            "the baseline is empty and the record still describes an unbound artifact"
        )


def test_the_deferral_is_recorded_as_undecided_and_not_as_a_plan():
    assert COVERAGE["status"] == "measured_and_deferred"
    assert "UNDECIDED" in DEFERRAL["not_a_decision"]
    assert "neither has been chosen" in DEFERRAL["not_a_decision"]
    assert DEFERRAL["trigger_enforced_by"].endswith(
        "test_doctrine_coverage.py::test_the_deferral_on_the_doctrine_source_list_still_holds"
    )
    assert "lapses" in DEFERRAL["deferred_while"], (
        "a deferral must state the condition that ends it, or it is an omission with a date on it"
    )


def test_the_reporting_rule_is_not_what_is_deferred():
    """The decision is parked; the obligation not to offer a vacuous green
    as evidence is not."""
    assert "must not be offered as evidence" in DEFERRAL["what_it_does_not_defer"]


def test_this_records_own_artifact_is_bound_and_the_recursion_is_stated():
    """doctrine_coverage.yaml is itself outside the source list, so its own
    zero-diff is vacuous by exactly the property it records. It is bound
    by this file -- which is what the record says every excluded artifact
    but two already is."""
    assert "doctrine_coverage.yaml" in _architecture_artifacts()
    assert "doctrine_coverage.yaml" not in _doctrine_sources(), (
        "this artifact is outside the projection, so its own zero-diff is vacuous by exactly the "
        "property it records"
    )
    assert "doctrine_coverage.yaml" in _named_by_a_test()

    # And the binding is real rather than asserted: this module loads the
    # artifact and reads fields out of it, which is what the union in
    # _named_by_a_test claims on its behalf.
    assert COVERAGE["subject"] == "doctrine_coverage"
    assert DEFERRAL is COVERAGE["the_deferral"]


def test_the_remaining_unbound_artifact_is_shared_and_covered_for_divergence():
    """CORRECTION to this record's first version, which said the artifact
    was covered by NOTHING.

    It is one of exactly two files in architecture/ that BOTH repositories
    hold, so architecture/exchange/verify_pair_landed.py compares it byte
    for byte. That is coverage for DIVERGENCE and not for CURRENCY -- a
    byte-identical pair of equally stale artifacts passes every check
    either repository has -- but it is not nothing, and the distinction is
    why binding it is a joint act rather than DAQ's to do alone.

    SKIPPED rather than assumed when the counterparty is not on disk: a
    claim about the intersection measured against a missing repository is
    the vacuous pass this repository has filed repeatedly."""
    scl = pathlib.Path("/home/user/scientific-compute-layer-scl-")
    if not (scl / "architecture").is_dir():
        import pytest
        pytest.skip("counterparty not present; the intersection cannot be measured here")

    ours = {p.name for p in ARCHITECTURE.glob("*.yaml")}
    theirs = {p.name for p in (scl / "architecture").glob("*.yaml")}
    shared = ours & theirs
    assert shared, "the intersection is empty; nothing below is a measurement"
    # The subset assertion this replaced is vacuous now that the baseline
    # is empty. What it was protecting is still real and is asserted
    # directly: the two jointly-held artifacts must stay in the
    # intersection, because an artifact that leaves it becomes one DAQ
    # could bind unilaterally -- which the record says it cannot.
    jointly_held = {"kalman_validation_preregistration.yaml", "proof_integrity.yaml"}
    assert jointly_held <= shared, (
        f"a jointly-held artifact left the intersection: {sorted(jointly_held - shared)}. "
        "It is then bindable by one party alone, which the joint-reissue rule forbids."
    )
    assert KNOWN_UNBOUND <= shared

    import hashlib
    for name in sorted(shared):
        ours_bytes = (ARCHITECTURE / name).read_bytes()
        theirs_bytes = (scl / "architecture" / name).read_bytes()
        assert hashlib.sha256(ours_bytes).digest() == hashlib.sha256(theirs_bytes).digest(), (
            f"architecture/{name} has DIVERGED across the pair. A shared artifact edited on one "
            "side is exactly the rule the two sides can come to disagree about."
        )

    section = COVERAGE["one_artifact_is_not_covered_for_currency"]
    assert "DIVERGENCE, not CURRENCY" in section["what_it_is_covered_FOR_and_what_it_is_not"]
    assert "JOINT ACT" in section["and_this_is_why_binding_it_is_not_daqs_to_do_alone"]


def test_the_check_states_its_own_limit_rather_than_overclaiming():
    """`names` is not `reads`. The record must carry that bound, and the
    live example of a reference that binds nothing."""
    limit = COVERAGE["what_this_check_cannot_see"]
    assert "LOWER BOUND" in limit["naming_is_not_reading"]
    # And the measured false positive in the other direction, with the
    # repair that is a declaration rather than a second filename.
    assert "counted it BOUND" in limit["and_it_produced_a_false_positive_in_the_OTHER_direction"]
    assert "DOES_NOT_BIND" in limit["the_repair_is_a_declaration_not_a_second_exclusion"]
    assert "verify_pair_landed.py" in limit["naming_is_not_reading"]

    verifier = (ARCHITECTURE / "exchange" / "verify_pair_landed.py").read_text()
    assert "kalman_validation_preregistration.yaml" in verifier, (
        "the recorded near-miss must be real: a dated enumeration naming an artifact that no test "
        "asserts membership of"
    )
    assert "SHARED_AS_ENUMERATED_UNTIL_2026_08_26" in verifier
