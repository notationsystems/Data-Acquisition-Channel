"""Pinned before any query module existed.

The measured basis was taken first, by exercising the pool. P5 is a STOP
CONDITION: if building the surface requires changing what acquisition
writes, the design is wrong.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "query_surface_preregistration.yaml"
PINNED = "63f43b082fe3a31e9115e9f2a147bee7d018085b289a88832ec08677caedd283"
PREREG = loads(ARTIFACT.read_text())


def test_the_predictions_have_not_been_edited_since_they_were_recorded():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == PINNED


def test_it_was_recorded_before_the_module_it_predicts():
    """Retires itself when the result lands."""
    if (REPO_ROOT / "architecture" / "query_surface_result.yaml").exists():
        return
    assert PREREG["status"] == "recorded_before_any_query_module_exists"
    assert not (REPO_ROOT / "daf" / "query.py").exists(), (
        "daf/query.py exists while the predictions still claim to precede it"
    )


def test_the_basis_was_measured_and_not_read():
    basis = PREREG["measured_basis_taken_before_predicting_anything"]
    # Asserted against the pinned text, not against a memory of writing
    # it. A first version looked for "rather than by reading" where the
    # record says "rather than reading" -- the record is pinned, so the
    # test was the thing that was wrong.
    assert "rather than reading evidence/pool.py" in basis["method"]
    assert "interrogated the resulting pool" in basis["method"]
    for finding in ("the_warrant_chain_is_complete_and_this_is_the_load_bearing_fact",
                    "there_is_no_index_by_content",
                    "the_observation_id_depends_on_how_acquisition_was_INVOKED"):
        # The KEY must exist and its VALUE must be a real statement, not
        # a label -- checking only the key is the shape that let a
        # key-name satisfy an assertion about a value earlier tonight.
        assert "measured" in basis[finding], finding
        assert len(basis[finding]["measured"]) > 80, f"{finding} measures nothing"


def test_the_identity_finding_names_where_it_can_and_cannot_be_repaired():
    """A finding that does not say whose it is invites the wrong party to
    act on it -- here, one that would edit the vendored core."""
    finding = PREREG["measured_basis_taken_before_predicting_anything"][
        "the_observation_id_depends_on_how_acquisition_was_INVOKED"]
    where = finding["where_it_can_and_cannot_be_repaired"]
    assert "never modified here" in where
    assert "is not taken here" in where
    # And it must not read as an argument for removing the locator, which
    # is load-bearing and was measured to be so.
    assert "load-bearing and correct" in finding[
        "why_the_locator_is_in_the_record_id_ON_PURPOSE"]


def test_the_stop_condition_is_recorded_as_one():
    p5 = PREREG["predictions"]["p5_nothing_in_the_acquisition_path_changes"]
    assert "would show the approach is wrong" in p5["it_is_a_stop_condition"]
