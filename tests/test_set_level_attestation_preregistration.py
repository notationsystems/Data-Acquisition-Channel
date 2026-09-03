"""Pinned before any code was written for it.

The commit order is the guarantee; the digest makes a later edit a
visible second act. P5 is a STOP CONDITION -- if the build turns out to
need a change to either per-cell vocabulary, the approach is wrong.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402
from science.admissibility import UNCERTAINTY_KINDS  # noqa: E402
from science.table import ABSENCE_REASONS  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "set_level_attestation_preregistration.yaml"
PINNED = "f013ef8973f9510d843d9834d86b8c21751f10f2222255277bc2b8d6a02f3982"
PREREG = loads(ARTIFACT.read_text())


def test_the_predictions_have_not_been_edited_since_they_were_recorded():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == PINNED


def test_it_was_recorded_before_any_code_existed_for_it():
    """The discriminating case: a prediction written after the build is
    not one. Retires itself when the result lands."""
    if (REPO_ROOT / "architecture" / "set_level_attestation_result.yaml").exists():
        return
    assert PREREG["status"] == "recorded_before_any_code_is_written"
    for module in ("science/set_attestation.py", "daf/attestation.py"):
        assert not (REPO_ROOT / module).exists(), (
            f"{module} exists while the predictions still claim to precede it"
        )


def test_the_stop_condition_is_recorded_as_one():
    p5 = PREREG["predictions"]["p5_nothing_in_the_per_cell_vocabularies_needs_to_change"]
    # Asserted against what the pinned record SAYS. A first version of
    # this looked for the word "stop" in a sentence that does not use it;
    # the record is pinned by digest, so the test is what was wrong.
    assert "would show the approach is wrong" in p5["it_is_a_stop_condition_and_not_a_hope"]
    assert "the right move is to stop" in p5["prediction"]
    # And the vocabularies it names, as they stand before the build.
    assert UNCERTAINTY_KINDS == ("stated", "estimated", "propagated", "absent")
    assert set(ABSENCE_REASONS) == {"not_measured", "below_detection", "above_range",
                                    "withheld", "lost_in_acquisition"}


def test_every_prediction_says_what_it_rests_on():
    for name, body in PREREG["predictions"].items():
        assert body["basis"] in ("OPEN", "MEASURED as a fact about the tree"), name
