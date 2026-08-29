"""Predictions recorded after one anchor was read and before any fixture
exists.

The pin is the same mechanism as the pre-anchor pre-registration's. What
it cannot do is make these predictions as strong as those: they were made
by a session that had read an anchor, and the artifact says so in its own
first paragraph. Asserted here rather than trusted to the reader.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "post_anchor_predictions.yaml"
RECORD = loads(ARTIFACT.read_text())


def header_prose() -> str:
    """The leading comment block as running prose. Matching against the
    wrapped source would make these assertions about line breaks."""
    block = ARTIFACT.read_text().split("extends:")[0]
    return " ".join(line.lstrip("#").strip() for line in block.splitlines())

#: This module NAMES the pre-anchor pre-registration in order to assert
#: it was not edited. That is a reference, not a binding, and the
#: doctrine-coverage sweep must not count it as one.
DOES_NOT_BIND = ("architecture/corpus_anchor_preregistration.yaml",)


def test_the_record_states_its_own_epistemic_downgrade():
    """A post-hoc prediction filed beside a pre-registration, without
    saying which is which, launders the second into the first."""
    header = header_prose()
    assert "WEAKER OBJECT THAN THE ONE BEFORE IT" in header
    assert "worth less than one made before" in header
    assert RECORD["status"] == "recorded_after_anchor_one_before_a_fixture_exists"


def test_the_pre_anchor_preregistration_was_not_edited_to_absorb_these():
    """The separation is only real if the pinned file is still pinned."""
    from test_corpus_anchor_preregistration import ARTIFACT as PREREG
    from test_corpus_anchor_preregistration import PINNED

    assert hashlib.sha256(PREREG.read_bytes()).hexdigest() == PINNED, (
        "these predictions are only a separate object while the pinned one is untouched"
    )
    p4 = RECORD["predictions_for_a_second_anchor"]["p4_the_calibration_range_is_stated_in_prose_only"]
    assert "is not edited to say so" in p4["the_pre_anchor_prediction_it_bears_on"]


def test_every_prediction_declares_its_basis():
    for section in ("predictions_resolvable_against_anchor_one",
                    "predictions_for_a_second_anchor"):
        for name, body in RECORD[section].items():
            assert "prediction" in body, f"{name} states no prediction"
            assert any(word in body.get("basis", "") for word in ("OPEN", "MEASURED")), (
                f"{name} does not say whether it rests on measured behaviour"
            )


def test_the_downsample_prediction_carries_the_measurement_it_rests_on():
    """It is the one prediction here with a magnitude, and the magnitude
    is re-derived rather than quoted."""
    from instrument.calibration import NARROW_POLYSTYRENE
    from instrument.chromatogram import (AT_SLICE_MIDPOINT, EqualAreaSlicing,
                                         EqualVolumeSlicing, IntegrationParameters,
                                         slice_area_moments, true_chromatogram)
    from instrument.distributions import flory

    chromatogram = true_chromatogram(flory(1e5), NARROW_POLYSTYRENE, 8001)
    parameters = IntegrationParameters()
    fine = slice_area_moments(chromatogram, NARROW_POLYSTYRENE, parameters, EqualVolumeSlicing())

    at_a_hundred = slice_area_moments(chromatogram, NARROW_POLYSTYRENE, parameters,
                                      EqualAreaSlicing(100, AT_SLICE_MIDPOINT))
    residual = abs(at_a_hundred.mn / fine.mn - 1.0)
    assert f"{residual:.1e}" == "1.1e-02", (
        "the prediction's stated magnitude must be this module's own number"
    )

    body = RECORD["predictions_resolvable_against_anchor_one"][
        "the_printed_slice_table_is_a_downsample_and_not_the_computation"]
    assert "1.1e-02" in body["the_measurement_behind_it"]
    assert "3.4e-05" in body["the_measurement_behind_it"]
    assert "not by zero" in body["prediction"]


def test_the_prediction_names_what_the_other_outcome_would_mean():
    """A prediction whose falsification has no stated consequence is a
    guess with a pin on it."""
    body = RECORD["predictions_resolvable_against_anchor_one"][
        "the_printed_slice_table_is_a_downsample_and_not_the_computation"]
    assert "more alarming outcome" in body["what_the_other_outcome_would_mean"]
    assert "unresolved rather than being quietly dropped" in body["what_would_make_this_unresolvable"]
    assert "Predicting the sign would be predicting the convention" in body["the_sign_is_not_predicted"]


def test_the_sign_really_is_convention_dependent_and_not_merely_declared_so():
    """The reason the sign is withheld, measured. If both conventions
    pushed Mn the same way, withholding the sign would be caution rather
    than a fact about the estimator."""
    from instrument.calibration import NARROW_POLYSTYRENE
    from instrument.chromatogram import (AT_SLICE_END, AT_SLICE_MIDPOINT, EqualAreaSlicing,
                                         EqualVolumeSlicing, IntegrationParameters,
                                         slice_area_moments, true_chromatogram)
    from instrument.distributions import flory

    chromatogram = true_chromatogram(flory(1e5), NARROW_POLYSTYRENE, 8001)
    parameters = IntegrationParameters()
    fine = slice_area_moments(chromatogram, NARROW_POLYSTYRENE, parameters, EqualVolumeSlicing())
    midpoint = slice_area_moments(chromatogram, NARROW_POLYSTYRENE, parameters,
                                  EqualAreaSlicing(100, AT_SLICE_MIDPOINT))
    endpoint = slice_area_moments(chromatogram, NARROW_POLYSTYRENE, parameters,
                                  EqualAreaSlicing(100, AT_SLICE_END))
    assert midpoint.mn > fine.mn > endpoint.mn, (
        "the two conventions must straddle the fine value, or the sign is predictable and "
        "withholding it is false modesty"
    )


def test_the_second_anchor_predictions_are_the_ones_that_were_stated():
    second = RECORD["predictions_for_a_second_anchor"]
    assert set(second) == {
        "p1_equal_area_slicing_again",
        "p2_a_per_slice_validity_flag_that_tracks_the_elution_window",
        "p3_integration_parameters_absent_again",
        "p4_the_calibration_range_is_stated_in_prose_only",
    }
    p2 = second["p2_a_per_slice_validity_flag_that_tracks_the_elution_window"]
    assert "PRESENT in the document and structurally unreachable" in p2["why_it_is_the_sharpest_of_the_four"]


def test_the_record_says_what_it_did_not_take_from_the_anchor():
    header = header_prose()
    assert "Not taken: any value" in header
    assert "No fixture has been transcribed" in header
    needed = RECORD["what_is_still_needed_and_from_whom"]
    assert "Not this session's to fabricate" in needed["a_verified_transcription"]
    assert "cannot answer them" in needed["a_second_anchor_with_replicates"]


def test_no_prediction_here_is_a_verdict_about_anchor_one():
    """The artifact must not become a description of what the anchor
    contained. Every entry under the second-anchor section is about a
    report that does not exist yet, and the anchor-one section is about
    two tables that did not extract."""
    for name, body in RECORD["predictions_for_a_second_anchor"].items():
        assert "second anchor" in body["prediction"], (
            f"{name} states something about an anchor already read rather than a prediction"
        )
    assert "not a retrofit" in RECORD["what_this_document_must_not_become"] or \
        "retrofit of Anchor 1's findings into predictions" in \
        RECORD["what_this_document_must_not_become"]
