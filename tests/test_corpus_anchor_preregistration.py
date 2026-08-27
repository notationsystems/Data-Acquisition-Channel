"""B.1's predictions, pinned before the anchors exist.

The pin makes a retrospective edit a visible second act rather than a
quiet one; the real guarantee is the commit order, which places this
before any anchor is in the tree. Stated rather than assumed -- a pin
described as tamper-proof would be the proxy-for-its-target shape.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "corpus_anchor_preregistration.yaml"
PREREG = loads(ARTIFACT.read_text())
PINNED = "855c88c43e37302cd0de8750a25cd1f265a0b4368df42745db68d63e18de067d"


def test_the_predictions_have_not_been_edited_since_they_were_recorded():
    assert hashlib.sha256(ARTIFACT.read_bytes()).hexdigest() == PINNED, (
        "if a prediction turned out wrong, the RESULT says so -- this file is not corrected "
        "to match. Changing it and this pin together is a deliberate act to be argued for."
    )


def test_no_anchor_is_in_the_tree_at_the_commit_that_records_these():
    """What the commit order is supposed to establish, asserted rather
    than trusted. Expected to fail once the anchors land, and to be
    RETIRED in that commit with the digest unchanged."""
    fixtures = {p.name.lower() for p in (REPO_ROOT / "tests" / "fixtures").iterdir()}
    for anchor in ("omnisec", "wingpc", "polyanalytik"):
        assert not any(anchor in name for name in fixtures), (
            f"an anchor fixture for {anchor} exists; retire this assertion in the commit that "
            "adds it, with the pre-registration digest unchanged"
        )


def test_every_prediction_declares_its_basis():
    for name, body in PREREG["predictions"].items():
        assert "prediction" in body, f"{name} states no prediction"
        assert any(word in body.get("basis", "") for word in ("OPEN", "MEASURED")), (
            f"{name} does not say whether it rests on measured behaviour"
        )
    assert any(b["basis"].startswith("OPEN") for b in PREREG["predictions"].values()), (
        "every prediction resting on measured behaviour would make this a description"
    )


def test_the_permeation_prediction_is_grounded_in_the_forward_model_measurement():
    """It came from measuring why an acceptance test failed, not from
    reading about chromatography."""
    permeation = PREREG["predictions"]["the_permeation_bound_is_computable_or_it_is_not"]
    assert "1.899" in permeation["where_it_came_from"]
    assert "no broadening at all" in permeation["where_it_came_from"]
    assert permeation["basis"] == "OPEN"
    assert "the_permeation_bound" in PREREG["the_prediction_most_likely_to_be_wrong"]


def test_the_uncertainty_vocabulary_really_has_no_repeatability_member():
    """The measurement that makes the sigma prediction checkable now
    rather than only against an anchor."""
    from science.admissibility import UNCERTAINTY_KINDS

    assert UNCERTAINTY_KINDS == ("stated", "estimated", "propagated", "absent")
    for member in UNCERTAINTY_KINDS:
        assert "repeat" not in member and "rsd" not in member and "replicate" not in member
    assert "None of those names a repeatability statistic" in PREREG["predictions"][
        "sigma_and_rsd_are_not_uncertainty"]["the_measurement_that_settles_it"]
