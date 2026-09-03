"""The twin/Codex coherence record, bound to what it asserts.

The branch relations in it were measured against remotes with a bounded
fetch of full forty-character shas. Re-measuring them here would make the
suite depend on the network and on another repository's current state, so
what is checked is the SHAPE of the claims: that every relation is
recorded with the measurement that produced it, that the scoped claim it
completes is named rather than contradicted, and that the divergence it
found is reported rather than acted on.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "twin_codex_coherence.yaml").read_text())


def test_the_verdict_rests_on_an_ancestry_measurement_and_not_on_a_reading():
    twin = RECORD["the_twin"]["the_coherence_question_answered_by_measurement"]
    assert "merge-base --is-ancestor" in twin["the_relation"]
    assert "ZERO Codex commits are absent" in twin["the_relation"]
    for sha in ("256e603e", "a86697af", "9af5655"):
        assert sha in str(twin), f"{sha} is not recorded"
    assert RECORD["the_twin"]["so_the_verdict"].startswith("COHERENT")


def test_the_divergence_is_reported_and_not_acted_on():
    """A default branch is a repository setting. This apparatus reports
    on another party's artifacts and does not change them."""
    divergence = RECORD["the_divergence_that_does_exist_and_it_is_a_pointer"]
    assert "Reported, not taken" in divergence["it_is_not_this_apparatus_s_to_change"]
    assert "what_is_NOT_claimed" in divergence
    assert "There may be a reason" in divergence["what_is_NOT_claimed"]


def test_the_scoped_claim_it_completes_is_named_rather_than_contradicted():
    """api_plane_assignment.yaml said the vocabulary appears in no
    checkout on this machine. That was TRUE and scoped. Completing it must
    not be written as a correction of something that was not wrong.
    """
    vocabulary = RECORD["the_vocabulary_the_plane_record_could_not_locate"]
    # Read the VALUE. The phrase "true and incomplete" is in the KEY, and
    # asserting against a key name is the construction this repository has
    # now caught nine times.
    scoped = vocabulary["that_claim_was_true_and_incomplete"]
    assert "true because it named its scope precisely" in scoped
    assert "incomplete because" in scoped
    assert "remains correct" in vocabulary["what_this_changes_for_the_plane_record"]

    # And the record it completes must still contain the scoped sentence.
    plane = (REPO_ROOT / "architecture" / "api_plane_assignment.yaml").read_text()
    assert "appears in NONE of" in plane and "Searched, not assumed" in plane


def test_the_first_scans_own_failure_is_recorded():
    """It grepped author names locally and reported zero Codex work.
    Both halves were wrong, and the record says so."""
    how = RECORD["how_the_two_agents_are_actually_distinguishable"]
    wrong = how["the_first_scan_was_looking_in_the_wrong_field_and_the_wrong_place"]
    assert "AUTHOR NAMES" in wrong
    assert "ref name, not an author" in wrong
    assert "never cloned" in wrong


def test_the_profile_divergence_is_concrete_and_neither_side_is_called_wrong():
    profile = RECORD["what_the_fabric_profile_claims_about_this_repository"]
    assert "notation://{kind}/{authority}/{local-id}" in profile[
        "where_it_diverges_and_the_divergence_is_concrete"]
    # `" ".join(a_mapping.keys())` is the SAME defect as joining the
    # mapping itself, and tests/test_mapping_join_defect.py did not catch
    # it because the argument is a call rather than a bare name. Widened
    # there after this line was written. The assertion reads the value.
    assert "different questions" in profile["what_is_NOT_claimed"]

    # The claim that no notation:// scheme exists here is checkable.
    hits = []
    for path in REPO_ROOT.rglob("*.py"):
        if any(part in path.parts for part in ("vendor", ".git", "__pycache__")):
            continue
        # This module NAMES the scheme in order to check it is absent, so
        # it detects itself. A self-detecting guard is a defect this
        # programme has hit before; the exclusion is one file and it is
        # stated rather than done by a filename pattern that would also
        # hide a real use written next to it.
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue
        if "notation://" in path.read_text():
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == [], f"a notation:// identity now exists here: {hits}"


def test_the_record_says_how_to_re_measure_rather_than_asking_to_be_believed():
    assert "one command per claim" in RECORD["what_this_record_must_not_become"]
    assert "FULL forty-character shas" in RECORD["what_this_record_must_not_become"]
