"""The drift-anchor acceptance criteria, and the arithmetic behind the
one threshold that is a number rather than a judgement."""

from __future__ import annotations

import pathlib
import sys
from collections import Counter

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402
from instrument import anchor_one, anchor_two  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "drift_anchor_criteria.yaml"
RECORD = loads(ARTIFACT.read_text())


def test_the_five_pair_threshold_is_the_sign_test_and_not_a_round_number():
    """p = 0.031 is 2 to the minus 5. Four pairs give 0.0625, which is
    not significant at the conventional level, which is why the threshold
    is five and not four."""
    assert 0.5 ** 5 < 0.05 <= 0.5 ** 4
    text = RECORD["a_candidate_must_contain"]["at_least_five_duplicate_pairs"]
    assert "0.031" in text and "one-tailed sign test" in text
    assert "must be reported as insufficient rather than argued up" in text


def test_the_record_separates_the_two_questions_that_shared_one_word():
    """ANCHOR 2 WAS OBTAINED AS THE REPLICATE ANCHOR AND ANSWERS THE
    OTHER QUESTION. Measured here rather than asserted: its ten standards
    are ten distinct masses, so it carries no duplicate pair at all."""
    two = Counter(row[1] for row in anchor_two.CALIBRATION_STANDARDS)
    assert len(two) == 10 and max(two.values()) == 1, (
        "if Anchor 2 did carry duplicate pairs, it would bear on the drift question and this "
        "record's central distinction would be wrong"
    )
    one = Counter(row[0] for row in anchor_one.CALIBRATION_STANDARDS)
    assert len([n for n, c in one.items() if c > 1]) == 11

    assert len(anchor_two.INJECTIONS) == 2, "and it does answer B.2.4"
    header = " ".join(line.lstrip("#").strip()
                      for line in ARTIFACT.read_text().split("extends:")[0].splitlines())
    assert "ANCHOR 2 HAS NONE" in header
    assert "answers one of them and is silent on the other" in header


def test_all_three_outcomes_carry_a_prediction_and_one_is_named_most_likely():
    outcomes = RECORD["predictions_by_outcome"]
    assert set(outcomes) == {"it_reproduces_as_an_instrument_property",
                             "it_is_session_specific",
                             "the_third_case_sign_reproduces_and_magnitude_does_not"}
    for name, body in outcomes.items():
        assert "then" in body, f"{name} states no consequence"
    third = outcomes["the_third_case_sign_reproduces_and_magnitude_does_not"]
    assert "most likely" in third["why_it_is_the_likely_one"] or \
        "most probable" in third["why_it_is_the_likely_one"]
    assert "if one of the other two happens" in third["and_it_is_named_as_most_likely_here"], (
        "the naming must say what being WRONG would look like, not merely that a naming "
        "happened -- an assertion the key already implies proves nothing"
    )
    assert "factor of three" in third["prediction"], "the magnitude claim must be falsifiable"


def test_the_session_specific_outcome_withdraws_rather_than_softens():
    """A record whose losing branch says `narrows somewhat` has no losing
    branch."""
    body = RECORD["predictions_by_outcome"]["it_is_session_specific"]["then"]
    assert "withdrawn rather than softened" in body
    assert "says nothing about the practice" in body


def test_the_criteria_state_what_disqualifies_and_not_only_what_qualifies():
    disqualifying = RECORD["what_disqualifies_a_candidate"]
    assert set(disqualifying) == {"the_same_sequence", "order_absent",
                                  "averaged_duplicates", "moments_only"}
    assert "adds nothing" in disqualifying["the_same_sequence"]
    assert "the reason the search is hard" in disqualifying["moments_only"]


def test_the_order_requirement_cites_the_measured_reason_it_is_not_a_row_label():
    """Anchor 2 carries three identifiers for two runs and the
    instrument's own disagrees with the other two, which is why sequence
    order has to come from a timestamp."""
    text = RECORD["a_candidate_must_contain"]["recorded_sequence_order"]
    assert "three identifiers for two runs" in text
    by_time = sorted(anchor_two.INJECTION_REPORTS, key=lambda r: r["date_acquired"])
    assert by_time[0]["instrument_injection_number"] == 1
    assert by_time[0]["figure_caption"] == "injection #2"
