"""Predictions about a technique this contract was never written for.

Pinned before any candidate was fetched. The commit order is the
guarantee; the digest only makes a later edit a visible second act.

Two anchors have met the acquisition path and both were GPC/SEC. The
untested claim is that the contract is about MEASUREMENTS rather than
about chromatograms, and a third chromatogram could not test it.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "third_anchor_preregistration.yaml"
PINNED = "070eece7be75adec877dd96bacc1fdee424779d2e6e2be05d4afaa0fcb0db832"
PREREG = loads(ARTIFACT.read_text())


def test_the_predictions_have_not_been_edited_since_they_were_recorded():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == PINNED, (
        "if a prediction turned out wrong, the RESULT says so -- this file is not "
        "corrected to match. Changing it and this pin together is a deliberate act."
    )


def test_every_prediction_states_what_would_falsify_it_or_says_what_it_rests_on():
    """A prediction with neither is a description, and describes nothing yet."""
    for name, body in PREREG["predictions"].items():
        assert "prediction" in body, name
        assert "basis" in body, f"{name} does not say whether it is MEASURED or OPEN"


def test_the_candidate_criteria_exclude_the_technique_already_anchored():
    """The point of the third anchor is that it is not a fourth chromatogram."""
    must_be = PREREG["the_candidate_criteria"]["must_be"]
    assert "NOT size-exclusion chromatography" in must_be
    disqualifies = PREREG["the_candidate_criteria"]["disqualifies"]
    assert "under another name" in disqualifies, (
        "a GPC measurement relabelled would satisfy the letter and defeat the point"
    )


def test_this_file_is_committed_before_any_third_anchor_fixture_exists():
    """The discriminating case: a prediction written after the reading is not one.

    Fails in the state where a fixture declared as the third anchor is in
    the tree at the moment these predictions are first recorded. It stops
    being meaningful once the result lands -- and is retired then, in the
    same commit, exactly as the corpus guard was.
    """
    result = REPO_ROOT / "architecture" / "third_anchor_result.yaml"
    if result.exists():
        return  # the reading happened; this guard has done its work
    fixtures = REPO_ROOT / "tests" / "fixtures"
    assert PREREG["status"] == "recorded_before_any_candidate_is_fetched"
    for path in fixtures.iterdir():
        text = path.read_text(errors="replace")[:4000]
        assert "third_anchor" not in text, (
            f"{path.name} names the third anchor while the predictions still claim "
            "to precede it"
        )
