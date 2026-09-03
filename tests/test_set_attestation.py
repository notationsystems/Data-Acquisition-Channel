"""The attestation, checked against a real laboratory's published figures.

Every number here is printed in Table 8 or section 13.7.2 of the WIL
Research report the third and fourth anchors came from. Synthetic values
would test the arithmetic; these test whether the shape holds a real
document's claims about its own sets.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from science.admissibility import UNCERTAINTY_KINDS  # noqa: E402
from science.set_attestation import (AGREED, COEFFICIENT_OF_VARIATION,  # noqa: E402
                                     CORRELATION_COEFFICIENT, DISAGREED,
                                     MAXIMUM_DIFFERENCE, MEAN,
                                     NO_COUNTERPART_COMPUTABLE,
                                     POPULATION_DISAGREES_WITH_THE_ATTESTED_N,
                                     POPULATION_EMPTY, UNCHECKED,
                                     SetAttestation, SetAttestationError,
                                     check_attestation)
from science.table import ABSENCE_REASONS  # noqa: E402

#: Table 8, page 34, as printed.
FLOW_24 = (9.43, 9.61, 9.66, 9.70, 9.69, 9.68, 9.71, 9.71, 9.70, 9.72)
FLOW_12 = (9.70, 9.72, 9.73, 9.74, 9.76, 9.74, 9.75, 9.80, 9.73, 9.74)
SOURCE = "WIL Research Europe project 505902, Table 8"


def _cv(value, n, population):
    return SetAttestation(statistic=COEFFICIENT_OF_VARIATION, value=value, unit="percent",
                          n=n, variable="eluate_concentration", population=population,
                          source=SOURCE)


# =====================================================================
# The four real instances
# =====================================================================

def test_the_published_cv_agrees_with_the_recomputed_one_at_both_flow_rates():
    """The check that existed only as a hardcoded assertion in one
    anchor's test module, now a property of the substrate.

    The laboratory prints 0.91 and 0.28; recomputation gives 0.903 and
    0.271, because it computed from concentrations it printed rounded to
    two decimals. Within a tolerance the reader chooses, they agree.
    """
    for attested, values in ((0.91, FLOW_24), (0.28, FLOW_12)):
        check = check_attestation(_cv(attested, 10, "24 or 12 ml/h series"),
                                  values, tolerance=0.01)
        assert check.verdict == AGREED, (check.attestation.value, check.computed)
        assert check.checked
        assert check.difference is not None and check.difference < 0.01


def test_the_published_maximum_difference_does_not_follow_from_the_reports_own_formula():
    """THE CAPABILITY EARNING ITS KEEP ON ITS FIRST REAL DOCUMENT.

    Page 33 states the formula: (highest - lowest) / mean value x 100,
    where "'mean value' is the mean of the highest and lowest value".
    Applied to the report's own two flow-rate means that gives 0.824657,
    which prints as 0.82. Table 8 prints 0.83.

    Every denominator tested reproduces 0.82 except one -- the LOWEST
    mean, which gives 0.828072 -> 0.83 and is not the denominator the
    report's formula names. Which of those the laboratory did is not
    determined here and is not guessed.

    Fails in the state where the printed figure DOES follow, at which
    point this finding is wrong and the record must be re-measured.
    """
    means = (sum(FLOW_24) / 10, sum(FLOW_12) / 10)
    attestation = SetAttestation(statistic=MAXIMUM_DIFFERENCE, value=0.83, unit="percent",
                                 n=2, variable="eluate_concentration",
                                 population="the two flow-rate means", source=SOURCE)

    # Tolerance tight enough to separate 0.82 from 0.83. An earlier check
    # of this same figure used 0.01 and passed -- a tolerance wide enough
    # to absorb the discrepancy it existed to find.
    check = check_attestation(attestation, means, tolerance=0.005)
    assert check.verdict == DISAGREED
    assert abs(check.computed - 0.824657251829709) < 1e-12
    assert round(check.computed, 2) == 0.82

    high, low = max(means), min(means)
    by_lowest = 100 * (high - low) / low
    assert round(by_lowest, 2) == 0.83, (
        "the one denominator that reproduces the printed figure is the lowest value"
    )


def test_the_reported_water_solubility_is_the_mean_of_the_two_means():
    means = (sum(FLOW_24) / 10, sum(FLOW_12) / 10)
    attestation = SetAttestation(statistic=MEAN, value=9.70, unit="mg/L", n=2,
                                 variable="eluate_concentration",
                                 population="the two flow-rate means", source=SOURCE)
    check = check_attestation(attestation, means, tolerance=0.005)
    assert check.verdict == AGREED
    assert abs(check.computed - 9.7010) < 1e-9


def test_the_regression_r_is_carried_and_reported_unchecked_not_agreed():
    """P2's half that matters. Section 13.7.2 prints
    `log k' = 0.474 x log Pow - 0.706 (r = 0.9998, n = 12)`. That is a fit
    against SEVEN reference substances' guideline log Pow values -- an
    external table this substrate does not hold -- so no counterpart is
    computable and the verdict must say so.

    Fails in the state where an uncheckable attestation reports AGREED,
    which would be a capability-level vacuous pass.
    """
    attestation = SetAttestation(statistic=CORRELATION_COEFFICIENT, value=0.9998,
                                 unit="dimensionless", n=12, variable="log_k_prime",
                                 population="six reference substances, two injections each",
                                 source="WIL Research Europe project 505902, section 13.7.2")
    check = check_attestation(attestation, [0.1, 0.2, 0.3], tolerance=0.0001)
    assert check.verdict == UNCHECKED
    assert not check.checked
    assert NO_COUNTERPART_COMPUTABLE in check.reasons
    assert check.computed is None and check.difference is None


# =====================================================================
# The refusals
# =====================================================================

def test_a_transcription_error_in_one_replicate_is_caught():
    """The reason the capability is worth having. One digit moved, and
    the published CV no longer reconciles."""
    corrupted = (9.43, 9.61, 9.66, 9.70, 9.69, 9.68, 9.71, 9.71, 9.70, 9.20)
    check = check_attestation(_cv(0.91, 10, "24 ml/h series"), corrupted, tolerance=0.01)
    assert check.verdict == DISAGREED
    assert check.checked and check.difference > 0.01


def test_a_statistic_with_no_denominator_is_refused():
    with pytest.raises(SetAttestationError, match="population it was computed over"):
        _cv(0.91, 0, "a series")


def test_a_kind_nothing_can_interpret_is_refused_rather_than_carried():
    with pytest.raises(SetAttestationError, match="not a statistic kind"):
        SetAttestation(statistic="repeatability_index", value=1.0, unit="percent", n=10,
                       variable="x", population="p", source="s")


def test_a_population_of_the_wrong_size_is_unchecked_and_never_disagreed():
    """Handing over nine values for a statistic the source computed over
    ten makes the comparison meaningless. Reporting DISAGREED would blame
    the source for the caller's error."""
    check = check_attestation(_cv(0.91, 10, "24 ml/h"), FLOW_24[:9], tolerance=0.01)
    assert check.verdict == UNCHECKED
    assert POPULATION_DISAGREES_WITH_THE_ATTESTED_N in check.reasons
    assert check.computed is not None, "it still reports what it computed"
    assert check.difference is None, "but not a difference, which would imply a comparison"


def test_an_empty_population_says_which_kind_of_nothing_it_is():
    check = check_attestation(_cv(0.91, 10, "24 ml/h"), [], tolerance=0.01)
    assert check.verdict == UNCHECKED
    assert POPULATION_EMPTY in check.reasons


def test_the_tolerance_has_no_default():
    """A default would be this layer deciding how close counts as
    agreement -- a judgement about the source's rounding."""
    with pytest.raises(TypeError):
        check_attestation(_cv(0.91, 10, "x"), FLOW_24)  # type: ignore[call-arg]


def test_the_cv_convention_is_the_sample_deviation_and_is_stated():
    """The two conventions differ by 1 - sqrt((n-1)/n). A check whose
    tolerance absorbs that difference is not checking a transcription."""
    import inspect

    import science.set_attestation as module
    source = inspect.getsource(module._cv)
    assert "SAMPLE deviation" in source
    # And it is the sample one in fact, not only in the comment.
    import statistics as st
    computed = module._cv(FLOW_24)
    assert abs(computed - 100 * st.stdev(FLOW_24) / st.mean(FLOW_24)) < 1e-12


# =====================================================================
# P5, the stop condition
# =====================================================================

def test_neither_per_cell_vocabulary_was_touched():
    """The pre-registration's stop condition. If building this had needed
    a fifth uncertainty kind or a sixth absence reason, the design was
    wrong."""
    assert UNCERTAINTY_KINDS == ("stated", "estimated", "propagated", "absent")
    assert set(ABSENCE_REASONS) == {"not_measured", "below_detection", "above_range",
                                    "withheld", "lost_in_acquisition"}


def test_the_module_does_not_reach_into_the_acquisition_layer():
    """science/ may not import daf/. The attestation is a scientific
    object and the layer rule is not relaxed for a new one."""
    source = (REPO_ROOT / "science" / "set_attestation.py").read_text()
    for forbidden in ("import daf", "from daf", "import evidence", "from evidence"):
        assert forbidden not in source


# =====================================================================
# The record, bound to what the code and the document actually do
# =====================================================================

def test_the_result_record_states_the_arithmetic_that_produced_the_finding():
    import pathlib as _p

    from epistemics._yaml import loads as _loads
    record = _loads((REPO_ROOT / "architecture"
                     / "set_level_attestation_result.yaml").read_text())
    finding = record["the_finding"]

    means = (sum(FLOW_24) / 10, sum(FLOW_12) / 10)
    high, low = max(means), min(means)
    by_formula = 100 * (high - low) / ((high + low) / 2)
    assert f"{by_formula:.6f}" in finding["the_arithmetic"]
    assert f"{100 * (high - low) / low:.6f}" in finding["what_was_tested_before_saying_so"]
    # `" ".join(a_dict)` joins the KEYS. That construction is the eighth
    # instance of a class this repository already tracks, and it was
    # written here in a test about a check whose tolerance hid a finding.
    # The assertion that matters reads the VALUE.
    assert "one hypothesis" in finding["what_is_NOT_claimed"]
    assert "that the laboratory divided by the lowest value" in finding["what_is_NOT_claimed"]

    # And the tolerance that hid it, named as this repository's own miss.
    missed = record["it_was_missed_twice_and_both_misses_are_this_repositorys"]
    assert "0.0053" in missed["the_second_and_worse"]
    assert "wide enough to absorb" in missed["the_second_and_worse"]


def test_every_verdict_the_module_can_return_is_reachable():
    """Coverage asserted as a property rather than hoped for: a verdict
    no input produces is a branch nobody has evidence about."""
    means = (sum(FLOW_24) / 10, sum(FLOW_12) / 10)
    reached = {
        check_attestation(_cv(0.91, 10, "p"), FLOW_24, tolerance=0.01).verdict,
        check_attestation(_cv(0.91, 10, "p"), FLOW_12, tolerance=0.0001).verdict,
        check_attestation(_cv(0.91, 10, "p"), [], tolerance=0.01).verdict,
    }
    assert reached == {AGREED, DISAGREED, UNCHECKED}
    assert len(means) == 2
