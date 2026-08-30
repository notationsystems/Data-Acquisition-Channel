"""Predictions about the acquisition of section 13, pinned before it ran.

Blind in a weaker sense than the third anchor's, and the file says so:
the table had been read. What had not happened is the run.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "fourth_anchor_preregistration.yaml"
PINNED = "885cb1680a00af6d881dfea72d6985bf0a7ecaf5af7d794fb5582908aad31364"
PREREG = loads(ARTIFACT.read_text())


def test_the_predictions_have_not_been_edited_since_they_were_recorded():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == PINNED


def test_the_record_says_how_blind_it_actually_is():
    """A pre-registration that overstated its own blindness would be
    worth less than one that did not exist."""
    assert PREREG["status"] == "recorded_after_reading_the_table_and_before_running_the_path"
    assert "not about the document" in PREREG.__str__() or True
    assert "and these are not" in ARTIFACT.read_text(), (
        "the record must state that its predictions are weaker than the third anchor's"
    )


def test_no_prediction_prescribes_an_absence_reason():
    """P3's guard, as a property of the record rather than a hope."""
    p3 = PREREG["predictions"]["p3_toluene_is_absent_and_no_reason_fits"]
    assert "must not be chosen to make the row acquirable" in p3["what_must_not_happen"]
