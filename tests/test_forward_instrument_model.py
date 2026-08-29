"""Acceptance 1 and 2 for the forward instrument model, and the layer rule.

The brief's build order says to stop after the distributions and verify:
nothing downstream is worth building on a bad integrator. This is that
stop.
"""

from __future__ import annotations

import dataclasses
import math
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402
from instrument.distributions import (LogNormal, SchulzZimm,  # noqa: E402
                                      flory, integrated_moments)

RECORD = loads((REPO_ROOT / "architecture" / "forward_instrument_model.yaml").read_text())

FAMILIES = [
    ("flory_1e3", flory(1e3)),
    ("flory_1e5", flory(1e5)),
    ("flory_1e6", flory(1e6)),
    ("schulz_zimm_z_0p5", SchulzZimm(1e5, 0.5)),
    ("schulz_zimm_z_3", SchulzZimm(1e5, 3.0)),
    ("schulz_zimm_z_19", SchulzZimm(1e5, 19.0)),
    ("log_normal_1p05", LogNormal(1e5, 1.05)),
    ("log_normal_1p5", LogNormal(1e5, 1.5)),
    ("log_normal_3p0", LogNormal(1e5, 3.0)),
]


# =====================================================================
# ACCEPTANCE 1 -- if this fails, everything downstream measures the integrator
# =====================================================================

@pytest.mark.parametrize("name,distribution", FAMILIES, ids=[n for n, _ in FAMILIES])
def test_analytic_moments_equal_numerically_integrated_moments(name, distribution):
    """The oracle is closed form and the check is numerical, so a
    disagreement indicts one side rather than passing. A test that
    computed the expectation the same way as the value would prove only
    that the code agrees with itself."""
    analytic = distribution.analytic_moments()
    integrated = integrated_moments(distribution)
    for moment in ("mn", "mw", "mz"):
        expected = getattr(analytic, moment)
        actual = getattr(integrated, moment)
        assert abs(actual / expected - 1.0) < 1e-10, (
            f"{name}.{moment}: analytic {expected!r} vs integrated {actual!r}"
        )


# =====================================================================
# ACCEPTANCE 2 -- the anchor that does not depend on this implementation
# =====================================================================

@pytest.mark.parametrize("mn", [1e3, 1e4, 1e5, 1e6, 1e7])
def test_flory_dispersity_is_exactly_two_at_every_scale(mn):
    """Mz : Mw : Mn = 3 : 2 : 1 is a property of the most-probable
    distribution, not of this code. It holds for every parameter, which
    is what makes it a regression anchor rather than a recorded
    expectation."""
    integrated = integrated_moments(flory(mn))
    assert integrated.dispersity == pytest.approx(2.0, abs=1e-9)
    ratio_wn, ratio_zw = integrated.as_ratios()
    assert ratio_wn == pytest.approx(2.0, abs=1e-9)
    assert ratio_zw == pytest.approx(1.5, abs=1e-9)


def test_the_moment_ratios_tell_the_two_shape_families_apart():
    """THE DISCRIMINATING CASE. `close to its own analytic moments` passes
    for a log-normal implemented as a Gamma and vice versa -- each would
    agree with whatever closed form it was given. The SIGNATURE separates
    them: a log-normal has Mw/Mn == Mz/Mw exactly (the moments are
    geometric), and a Schulz-Zimm does not unless it is degenerate."""
    log_normal = integrated_moments(LogNormal(1e5, 1.5))
    ratio_wn, ratio_zw = log_normal.as_ratios()
    assert ratio_wn == pytest.approx(ratio_zw, rel=1e-9), (
        "a log-normal's moments must be geometric"
    )

    gamma = integrated_moments(SchulzZimm(1e5, 3.0))
    gamma_wn, gamma_zw = gamma.as_ratios()
    assert gamma_wn != pytest.approx(gamma_zw, rel=1e-3), (
        "a Schulz-Zimm must NOT have geometric moments, or this check cannot separate the "
        "families and both tests above would pass on one implementation"
    )


def test_the_integration_range_is_derived_and_a_fixed_one_fails_at_z_zero():
    """DETECTOR PROOF for the range derivation, on the case that found it.

    A fixed six-decade lower bound was measured wrong at 1.0e-06 for
    Flory while the z > 0 families agreed to 1e-14, because the number
    density goes as M^z and is FLAT at z = 0. Planted here so the
    derivation cannot silently revert to a constant."""
    distribution = flory(1e5)
    low, high = distribution.log10_range()
    assert low < high

    @dataclasses.dataclass(frozen=True)
    class _FixedRange(SchulzZimm):
        def log10_range(self):
            import math
            return (math.log10(self.scale) - 6.0, high)

    broken = integrated_moments(_FixedRange(mn=1e5, z=0.0))
    analytic = distribution.analytic_moments()
    error = abs(broken.mn / analytic.mn - 1.0)
    assert error > 1e-8, (
        f"a fixed six-decade lower bound now gives {error:.2e} error, so this no longer "
        "demonstrates why the range is derived -- re-measure rather than delete"
    )
    assert error == pytest.approx(1e-6, rel=0.5), (
        "the error should be about the missing number-integral tail, L/b = 1e-6"
    )


# =====================================================================
# The layer rule -- ground truth must not be reachable from the product
# =====================================================================

def test_nothing_in_the_product_imports_the_instrument_package():
    """A product path that can reach the forward model is ground truth
    leaking into the measurement, and every result after it is worthless.
    Derived over every authored package rather than a named list."""
    import ast

    offenders = []
    for package in ("daf", "science", "epistemics", "boundary", "bridge", "assertion"):
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for module in modules:
                    if module.split(".")[0] == "instrument":
                        offenders.append(f"{path.relative_to(REPO_ROOT)}: {module}")
    assert offenders == [], (
        f"the product imports the forward model: {offenders}. Everything it emits is a fixture, "
        "and a product that can reach the truth record is measuring its own answer key."
    )


def test_the_instrument_package_imports_nothing_from_the_product():
    """The other direction. A fixture generator that depends on the code
    under test cannot be an independent oracle."""
    import ast

    offenders = []
    for path in sorted((REPO_ROOT / "instrument").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                if module.split(".")[0] in ("daf", "science", "evidence", "scout",
                                            "materials", "boundary", "bridge", "assertion"):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {module}")
    assert offenders == [], f"the forward model depends on the code it is meant to test: {offenders}"


# =====================================================================
# ACCEPTANCE 3-6 -- the forward path
# =====================================================================

from instrument.calibration import (NARROW_PMMA, NARROW_POLYSTYRENE,  # noqa: E402
                                    Calibration, POLYSTYRENE)
from instrument.chromatogram import (AT_SLICE_END, AT_SLICE_MIDPOINT,  # noqa: E402
                                     AT_SLICE_START, Column, EqualAreaSlicing,
                                     EqualVolumeSlicing, IntegrationParameters,
                                     SlicingError, admitted_region, broaden,
                                     report_moments, slice_area_moments,
                                     true_chromatogram)

#: Every measurement recorded before the Empower anchor was taken under
#: equal-volume slicing. Named here rather than defaulted, so that the
#: numbers below are convention-stamped rather than convention-blind.
EQUAL_VOLUME = EqualVolumeSlicing()

WIDE = Calibration("cal:wide", POLYSTYRENE, (12.0, -0.60, 0.010, -0.00012), (4.0, 26.0), 0.9997)
FLORY = flory(1e5)


def test_a_calibration_that_turns_round_inside_its_own_range_is_refused():
    """A cubic that is not monotonic maps two volumes to one mass, and
    the estimator would read one slice as two."""
    from instrument.calibration import CalibrationError

    bent = Calibration("cal:bent", POLYSTYRENE, (12.0, -0.60, 0.10, -0.00012), (6.0, 18.0), 0.99)
    assert not bent.is_monotonic_over_range()
    with pytest.raises(CalibrationError, match="not monotonic"):
        bent.volume_for_mass(1e5)
    assert NARROW_POLYSTYRENE.is_monotonic_over_range()


def test_acceptance_3_broadening_broadens_and_the_excess_grows_as_plates_fall():
    """THE DISCRIMINATING FORM. `the reported value is close to the truth`
    passes under a broken broadening model and a correct one. The
    property is the SIGN of the discrepancy and its DEPENDENCE on plate
    count, measured against the same calibration and the same limits so
    that only N varies."""
    parameters = IntegrationParameters()
    unbroadened = slice_area_moments(true_chromatogram(FLORY, WIDE, 8001), WIDE, parameters, EQUAL_VOLUME)

    excesses = []
    for plates in (300000, 100000, 30000, 10000, 3000, 1000, 300):
        chromatogram = broaden(true_chromatogram(FLORY, WIDE, 8001),
                               Column("c", plates, 300.0, 5.0))
        reported = slice_area_moments(chromatogram, WIDE, parameters, EQUAL_VOLUME)
        assert reported.dispersity > unbroadened.dispersity, (
            f"broadening did not broaden at N={plates}"
        )
        excesses.append(reported.dispersity - unbroadened.dispersity)

    assert excesses == sorted(excesses), (
        f"the excess must grow strictly as plate count falls; got {excesses}"
    )


def test_the_permeation_limit_biases_the_report_with_a_perfect_column():
    """THE FINDING THE BRIEF DID NOT ANTICIPATE, and the reason
    acceptance 3 is false as originally stated.

    A real calibration spans a finite mass range -- the column cannot see
    chains below its permeation limit. Truncating the low-M tail biases
    Mn UP and dispersity DOWN, with NO broadening involved: measured at
    D = 1.899 against a true 2.000, on an unbroadened chromatogram.
    Widening the range recovers the truth, which is what identifies
    truncation as the cause rather than the estimator."""
    parameters = IntegrationParameters()
    narrow = slice_area_moments(true_chromatogram(FLORY, NARROW_POLYSTYRENE, 8001),
                                NARROW_POLYSTYRENE, parameters, EQUAL_VOLUME)
    wide = slice_area_moments(true_chromatogram(FLORY, WIDE, 8001), WIDE, parameters, EQUAL_VOLUME)

    assert narrow.dispersity < 1.95, "the narrow range must bias dispersity DOWN"
    assert narrow.mn > 1.04e5, "and Mn UP"
    assert wide.dispersity == pytest.approx(2.0, abs=1e-3), (
        "a wide enough range must recover the truth, or the bias is the estimator rather than "
        "the truncation and this test names the wrong cause"
    )


def test_two_real_effects_push_dispersity_in_opposite_directions():
    """Which is why `reported PDI > true PDI, always` does not hold."""
    parameters = IntegrationParameters()
    column = Column("c", 10000, 300.0, 5.0)
    narrow = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, EQUAL_VOLUME, 8001)
    wide = report_moments(FLORY, WIDE, column, parameters, EQUAL_VOLUME, 8001)
    assert narrow.dispersity < 2.0 < wide.dispersity


def test_two_large_errors_cancel_into_a_correct_looking_dispersity():
    """THE SHARPEST RESULT. At a plate count where truncation and
    broadening happen to balance, the report states a dispersity of 2.00
    -- indistinguishable from a correct measurement -- while Mn is wrong
    by more than three percent. The cancellation is in the RATIO and not
    in the SCALE, and no consumer reading the report can tell."""
    reported = report_moments(FLORY, NARROW_POLYSTYRENE, Column("c", 2500, 300.0, 5.0),
                              IntegrationParameters(), EQUAL_VOLUME, 8001)
    assert reported.dispersity == pytest.approx(2.0, abs=0.01), (
        "this test exists because the dispersity looks RIGHT here"
    )
    assert abs(reported.mn / 1e5 - 1.0) > 0.02, (
        "and Mn is wrong. If both were right the cancellation would not be a finding."
    )


def test_acceptance_4_the_discrepancy_is_reproducible_and_its_magnitude_is_stated():
    parameters = IntegrationParameters()
    column = Column("c", 10000, 300.0, 5.0)
    first = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, EQUAL_VOLUME, 4001)
    second = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, EQUAL_VOLUME, 4001)
    assert (first.mn, first.mw, first.mz) == (second.mn, second.mw, second.mz)
    assert first.mn / 1e5 - 1.0 == pytest.approx(0.0505, abs=0.002)


def test_acceptance_5_two_calibrations_over_one_truth_disagree_attributably():
    """Two labs, one material, two standard chemistries -- a
    contradiction with a known cause, which is unreachable any other
    way."""
    column = Column("c", 10000, 300.0, 5.0)
    parameters = IntegrationParameters()
    ps = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, EQUAL_VOLUME, 8001)
    pmma = report_moments(FLORY, NARROW_PMMA, column, parameters, EQUAL_VOLUME, 8001)

    assert ps.mn != pmma.mn
    assert abs(pmma.mn / ps.mn - 1.0) > 0.005
    assert NARROW_POLYSTYRENE.standard_chemistry != NARROW_PMMA.standard_chemistry, (
        "the difference must be attributable to a stated property, not merely observed"
    )


def test_acceptance_6_integration_limits_change_the_reported_moments():
    """THE DELIVERABLE. The analyst's integration choices move Mn by more
    than sixty percent, and no vendor report carries them. That is
    no_context_free_property's argument executable rather than
    asserted."""
    column = Column("c", 10000, 300.0, 5.0)
    full = report_moments(FLORY, NARROW_POLYSTYRENE, column, IntegrationParameters(), EQUAL_VOLUME, 8001)
    thresholded = report_moments(FLORY, NARROW_POLYSTYRENE, column,
                                 IntegrationParameters(baseline_threshold=0.05), EQUAL_VOLUME, 8001)
    windowed = report_moments(FLORY, NARROW_POLYSTYRENE, column,
                              IntegrationParameters(peak_start_volume=10.0,
                                                    peak_end_volume=15.0), EQUAL_VOLUME, 8001)

    assert thresholded.mn > full.mn * 1.05
    assert windowed.mn > full.mn * 1.5, (
        f"a peak window moved Mn from {full.mn:.6g} to {windowed.mn:.6g}"
    )
    assert len({round(m.dispersity, 6) for m in (full, thresholded, windowed)}) == 3


def test_the_integration_parameters_are_an_explicit_input_and_not_a_default():
    """They must be passed. A default that silently applies is the
    information the report omits, omitted here too."""
    import inspect

    signature = inspect.signature(slice_area_moments)
    assert signature.parameters["parameters"].default is inspect.Parameter.empty


# =====================================================================
# The record's own claims, re-measured rather than restated
# =====================================================================

def test_the_record_states_acceptance_three_as_false_and_says_why():
    """A record claiming all six acceptances passed would be the more
    comfortable artifact and the wrong one."""
    three = RECORD["acceptance"]["three_reported_pdi_exceeds_true_pdi"]
    assert three["verdict"].startswith("FALSE AS STATED")
    assert "PERMEATION LIMIT" in three["the_effect_that_was_missing"]
    assert "broadening is RIGHT" in three["what_was_measured"]


def test_the_records_numbers_are_the_numbers_this_module_produces():
    """Every figure quoted in the record is re-derived here. A record
    whose numbers are typed in is prose with digits."""
    parameters = IntegrationParameters()
    column = Column("c", 10000, 300.0, 5.0)

    unbroadened_narrow = slice_area_moments(
        true_chromatogram(FLORY, NARROW_POLYSTYRENE, 8001), NARROW_POLYSTYRENE, parameters, EQUAL_VOLUME)
    assert f"{unbroadened_narrow.dispersity:.3f}" == "1.899"

    unbroadened_wide = slice_area_moments(
        true_chromatogram(FLORY, WIDE, 8001), WIDE, parameters, EQUAL_VOLUME)
    assert f"{unbroadened_wide.dispersity:.6f}" == "1.999775"

    cancelling = report_moments(FLORY, NARROW_POLYSTYRENE, Column("c", 2500, 300.0, 5.0),
                                parameters, EQUAL_VOLUME, 8001)
    assert f"{cancelling.dispersity:.3f}" == "2.004"
    assert f"{cancelling.mn / 1e5 - 1.0:+.4f}" == "+0.0328"

    windowed = report_moments(FLORY, NARROW_POLYSTYRENE, column,
                              IntegrationParameters(peak_start_volume=10.0,
                                                    peak_end_volume=15.0), EQUAL_VOLUME, 8001)
    full = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, EQUAL_VOLUME, 8001)
    assert f"{windowed.mn / full.mn - 1.0:.0%}" == "62%"


def test_the_record_says_what_is_not_built_and_why():
    not_built = RECORD["what_is_not_built_and_why"]
    assert "B.1 has not run" in not_built["report_emission"]
    assert "third fixture" in not_built["report_emission"]
    assert "waits on the anchors" in not_built["extractor_against_emitted_reports"]

    limits = RECORD["known_limits_of_the_model"]
    assert "NOT transcribed from any instrument" in limits["fabricated_calibration_coefficients"]
    emg = limits["gaussian_not_emg_MEASURED_AND_THE_LIMIT_WAS_UNDERSTATED"]
    assert "gets its SIGN wrong" in emg
    assert "strengthened by its own stated limit" in emg
    assert "agreed with the negation" in limits["a_direction_test_was_not_a_discriminating_case"]


# =====================================================================
# Tailing: the limit that made the cancellation LOOK SMALLER than it is
# =====================================================================

def test_the_tail_kernel_shifts_the_centroid_by_its_discrete_mean_not_merely_later():
    """DIRECTION WAS NOT A DISCRIMINATING CASE.

    A reversed exponential also moves mass to later volume -- it
    TRANSLATES the peak instead of tailing it -- so a sign check passed
    on a kernel indexed backwards. What caught it was the MAGNITUDE: the
    shift must equal the kernel's own discrete mean, r/(1-r) steps with
    r = exp(-step/tau), and the reversed kernel shifted six times
    further."""
    from instrument.chromatogram import Chromatogram

    step, peak_index, n = 0.06, 100, 401
    volumes = tuple(6.0 + step * i for i in range(n))
    delta = Chromatogram(volumes, tuple(1.0 if i == peak_index else 0.0 for i in range(n)))

    def centroid(chromatogram):
        total = sum(chromatogram.concentrations)
        return sum(v * c for v, c in zip(chromatogram.volumes, chromatogram.concentrations)) / total

    gaussian = broaden(delta, Column("g", 10000, 300.0, 5.0))
    sigma = volumes[peak_index] / math.sqrt(10000)

    for ratio in (1.0, 2.0):
        tau = ratio * sigma
        tailed = broaden(delta, Column("e", 10000, 300.0, 5.0, tailing_tau_over_sigma=ratio))
        r = math.exp(-step / tau)
        expected = (r / (1.0 - r)) * step
        assert centroid(tailed) - centroid(gaussian) == pytest.approx(expected, rel=0.02), (
            "the centroid shift must be the kernel's discrete mean; a reversed kernel gives "
            "span*step - tau instead, which is also 'later' and is wrong"
        )


def test_tailing_makes_the_cancellation_worse_and_flips_the_sign_of_the_residual():
    """THE LIMIT, MEASURED RATHER THAN CONCEDED.

    The Gaussian was recorded as understating the low-M side, biasing the
    same way as truncation. Measured, it understates the CONSEQUENCE by
    about six-fold and gets the residual's SIGN wrong:

        tau/sigma = 0    cancels near N=2600   Mn error  +3.4%
        tau/sigma = 2    cancels near N=8250   Mn error -20.3%

    So a consumer calibrating against the symmetric model would correct
    Mn in the wrong direction. The cancellation finding is strengthened
    by its own stated limit, not weakened."""
    parameters = IntegrationParameters()

    symmetric = report_moments(FLORY, NARROW_POLYSTYRENE,
                               Column("c", 2600, 300.0, 5.0), parameters, EQUAL_VOLUME, 4001)
    assert symmetric.dispersity == pytest.approx(2.0, abs=0.01)
    assert symmetric.mn > 1e5, "the symmetric model puts Mn ABOVE the truth"

    tailed = report_moments(FLORY, NARROW_POLYSTYRENE,
                            Column("c", 8250, 300.0, 5.0, tailing_tau_over_sigma=2.0),
                            parameters, EQUAL_VOLUME, 4001)
    assert tailed.dispersity == pytest.approx(2.0, abs=0.01), (
        "the report still reads a correct-looking dispersity with realistic tailing"
    )
    assert tailed.mn < 1e5, "and with tailing Mn falls BELOW the truth -- the sign flips"
    assert abs(tailed.mn / 1e5 - 1.0) > 4.0 * abs(symmetric.mn / 1e5 - 1.0), (
        "the tailed residual must be several times the symmetric one, or the recorded limit "
        "overstates its own effect"
    )


def test_tailing_alone_raises_dispersity_and_lowers_mn():
    """Isolated against the wide calibration, so truncation is absent and
    only the kernel shape acts."""
    parameters = IntegrationParameters()
    previous_dispersity, previous_mn = None, None
    for ratio in (0.0, 0.5, 1.0, 2.0):
        reported = report_moments(FLORY, WIDE, Column("c", 10000, 300.0, 5.0,
                                                      tailing_tau_over_sigma=ratio),
                                  parameters, EQUAL_VOLUME, 4001)
        if previous_dispersity is not None:
            assert reported.dispersity > previous_dispersity
            assert reported.mn < previous_mn
        previous_dispersity, previous_mn = reported.dispersity, reported.mn


# =====================================================================
# EQUAL-AREA SLICING -- the correction a real report forced
#
# Everything above was measured with one slice per acquisition point:
# equal WIDTH in volume. A Waters Empower contract-lab report shows the
# software slices by equal AREA. The estimator was not wrong about the
# formula; it was wrong about what a slice is, and that assumption was
# invisible because it was a default.
# =====================================================================

EQUAL_AREA_END = EqualAreaSlicing(100, AT_SLICE_END)
EQUAL_AREA_MID = EqualAreaSlicing(100, AT_SLICE_MIDPOINT)


def _slice_edges(chromatogram, parameters, count):
    """The volume boundaries an equal-area slicer would print."""
    from instrument.chromatogram import _volume_at_cumulative

    admitted = admitted_region(chromatogram, parameters)
    cumulative = [0.0]
    for index in range(1, len(admitted.volumes)):
        width = admitted.volumes[index] - admitted.volumes[index - 1]
        mean_height = 0.5 * (admitted.concentrations[index]
                             + admitted.concentrations[index - 1])
        cumulative.append(cumulative[-1] + mean_height * width)
    total = cumulative[-1]
    return [_volume_at_cumulative(admitted.volumes, cumulative, k * total / count)
            for k in range(count + 1)]


def test_the_slice_table_reproduces_the_anchors_structural_signature():
    """THE DISCRIMINATING CASE, and it is the anchor's own columns.

    A real report's slice table shows a constant `Slice Area` on every
    row, a cumulative-percent column running 1 to 100, and elution steps
    that narrow through the peak and widen in the tails. An equal-volume
    slicer produces the exact opposite signature -- constant step,
    varying area -- so this separates the two conventions rather than
    merely confirming one runs."""
    chromatogram = broaden(true_chromatogram(FLORY, NARROW_POLYSTYRENE, 8001),
                           Column("c", 10000, 300.0, 5.0))
    parameters = IntegrationParameters()

    pieces = EQUAL_AREA_END.slices(admitted_region(chromatogram, parameters),
                                   NARROW_POLYSTYRENE)
    assert len(pieces) == 100
    assert len({round(piece.area, 9) for piece in pieces}) == 1, (
        "every row of the anchor's slice table reads the same Slice Area"
    )

    edges = _slice_edges(chromatogram, parameters, 100)
    widths = [edges[k + 1] - edges[k] for k in range(100)]
    peak_volume = chromatogram.peak_volume()
    containing_peak = max(k for k in range(100) if edges[k] <= peak_volume)
    assert widths.index(min(widths)) == containing_peak, (
        "the narrowest slice must be the one holding the peak; that is what 'the steps narrow "
        "through the peak' means, and it is what an equal-volume slicer cannot do"
    )
    assert widths[-1] > 50.0 * min(widths), "and the tail slices must be far wider"

    volume_pieces = EqualVolumeSlicing().slices(
        admitted_region(chromatogram, parameters), NARROW_POLYSTYRENE)
    assert len({round(piece.area, 9) for piece in volume_pieces}) > 1, (
        "if the equal-volume slicer also produced a constant area, this test would pass on "
        "either convention and separate nothing"
    )


def test_equal_area_and_equal_volume_converge_as_the_slice_count_grows():
    """Equal area is a change of variable, not a different integral, so
    the two must agree in the limit. That is what makes the disagreement
    at a hundred slices a DISCRETISATION error attributable to the real
    slice count, rather than a second defect in the estimator."""
    chromatogram = true_chromatogram(FLORY, NARROW_POLYSTYRENE, 8001)
    parameters = IntegrationParameters()
    reference = slice_area_moments(chromatogram, NARROW_POLYSTYRENE, parameters, EQUAL_VOLUME)

    errors = []
    for count in (100, 1000, 10000):
        equal_area = slice_area_moments(chromatogram, NARROW_POLYSTYRENE, parameters,
                                        EqualAreaSlicing(count, AT_SLICE_MIDPOINT))
        errors.append(abs(equal_area.mn / reference.mn - 1.0))
    assert errors == sorted(errors, reverse=True), f"must converge; got {errors}"
    assert errors[0] > 1e-2, "and must NOT already agree at the real slice count of one hundred"
    assert errors[-1] < 1e-4


def test_the_slicing_convention_alone_flips_the_sign_of_the_mn_error():
    """THE CORRECTION'S OWN FINDING.

    One chromatogram, one column, one calibration, one set of integration
    limits. Only what the software calls a slice differs -- and the
    report's Mn goes from five percent ABOVE the truth to seven percent
    BELOW it. The convention is the vendor's, not the analyst's, and the
    report carries it nowhere."""
    column = Column("c", 10000, 300.0, 5.0)
    parameters = IntegrationParameters()

    by_volume = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, EQUAL_VOLUME, 8001)
    by_area_end = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters,
                                 EQUAL_AREA_END, 8001)
    by_area_mid = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters,
                                 EQUAL_AREA_MID, 8001)

    assert by_volume.mn > 1e5 > by_area_end.mn, "the sign of the Mn residual must flip"
    assert f"{by_volume.mn / 1e5 - 1.0:+.4f}" == "+0.0505"
    assert f"{by_area_end.mn / 1e5 - 1.0:+.4f}" == "-0.0684"
    assert f"{by_area_mid.mn / 1e5 - 1.0:+.4f}" == "+0.0616"
    assert by_area_mid.mn - by_area_end.mn > 0.11 * 1e5, (
        "and the two equal-area conventions -- which differ only in WHERE inside a slice the "
        "mass is read, something the anchor does not pin -- differ by more than eleven percent "
        "of the true Mn"
    )


def test_the_cancellation_does_not_survive_the_convention_the_anchor_indicates():
    """THE RESULT THIS CORRECTION CHANGES.

    Under equal-volume slicing, truncation and broadening cancel at
    N = 2600 into a report reading D = 2.00 while Mn is 3.4% wrong. Under
    equal-area slicing read at the slice END -- which is what a
    cumulative column running 1 to 100 indicates -- there is NO plate
    count at which the report reads 2.00: the endpoint rule's own bias
    exceeds truncation's and pushes dispersity the other way, so the
    reported D stays above 2.09 however good the column is.

    The cancellation is therefore a property of an estimator convention
    and not of the instrument. It is still a real failure mode -- a
    consumer cannot tell a correct dispersity from two cancelling errors
    -- but the plate count at which it happens, and whether it happens at
    all, is not knowable from a report that omits the convention."""
    parameters = IntegrationParameters()
    dispersities = [
        report_moments(FLORY, NARROW_POLYSTYRENE, Column("c", plates, 300.0, 5.0),
                       parameters, EQUAL_AREA_END, 8001).dispersity
        for plates in (500, 1000, 2000, 5000, 20000, 100000, 1000000)
    ]
    assert min(dispersities) > 2.09, (
        f"the endpoint rule must never reach a correct-looking dispersity; got {dispersities}"
    )

    cancelling = report_moments(FLORY, NARROW_POLYSTYRENE, Column("c", 2600, 300.0, 5.0),
                                parameters, EQUAL_VOLUME, 8001)
    assert cancelling.dispersity == pytest.approx(2.0, abs=0.01), (
        "and equal-volume must still cancel, or this test is comparing two broken estimators "
        "rather than one convention against another"
    )


def test_one_slice_in_a_hundred_carries_a_sixth_of_the_denominator_that_sets_mn():
    """THE MECHANISM, so the sign flip above is attributable rather than
    observed. Mn is a harmonic mean, the last equal-area slice spans the
    widest volume range of any row, and the endpoint rule reads it at its
    lowest-mass edge -- which is the column's permeation limit."""
    chromatogram = broaden(true_chromatogram(FLORY, NARROW_POLYSTYRENE, 8001),
                           Column("c", 2500, 300.0, 5.0))
    pieces = EQUAL_AREA_END.slices(admitted_region(chromatogram, IntegrationParameters()),
                                   NARROW_POLYSTYRENE)
    inverse_total = sum(piece.area / piece.mass for piece in pieces)
    last = pieces[-1]
    assert (last.area / last.mass) / inverse_total > 0.15, (
        "one row in a hundred, holding one percent of the area, must carry more than a sixth "
        "of the sum that sets Mn"
    )
    assert last.mass == pytest.approx(NARROW_POLYSTYRENE.mass(
        NARROW_POLYSTYRENE.valid_volume_range[1]), rel=1e-6), (
        "and the mass it is read at is the permeation limit itself"
    )


def test_the_conventions_blast_radius_depends_on_the_limits_the_report_also_omits():
    """TWO OMISSIONS THAT INTERACT.

    The integration limits are the analyst's and absent from the report;
    the slicing convention is the vendor's and also absent. They are not
    independent: integrated to the calibration's own edges the three
    conventions spread Mn across twelve points and disagree on its SIGN,
    while under a tight analyst window they agree to three points and on
    the sign. So how much the missing convention matters cannot be
    bounded without the missing limits."""
    column = Column("c", 10000, 300.0, 5.0)

    def spread(parameters):
        values = [report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, slicing,
                                 8001).mn / 1e5 - 1.0
                  for slicing in (EQUAL_VOLUME, EQUAL_AREA_END, EQUAL_AREA_MID)]
        return values

    unwindowed = spread(IntegrationParameters())
    windowed = spread(IntegrationParameters(peak_start_volume=8.0, peak_end_volume=16.0))

    assert max(unwindowed) - min(unwindowed) > 0.11
    assert min(unwindowed) < 0.0 < max(unwindowed), "unwindowed, they disagree on the sign"
    assert max(windowed) - min(windowed) < 0.03
    assert min(windowed) > 0.0, "windowed, they agree on the sign and nearly on the value"


def test_the_slicing_convention_is_a_required_argument_like_the_integration_parameters():
    """It carried a default of equal-volume, and that default is exactly
    why nothing here noticed the convention was wrong until a real report
    showed it. The representative point is required for the same reason:
    the anchor pins the slice count and the cumulative column, and does
    not pin where inside a slice the mass is read."""
    import inspect

    signature = inspect.signature(slice_area_moments)
    assert signature.parameters["slicing"].default is inspect.Parameter.empty
    assert signature.parameters["parameters"].default is inspect.Parameter.empty
    assert inspect.signature(report_moments).parameters["slicing"].default is \
        inspect.Parameter.empty

    fields = {field.name: field for field in dataclasses.fields(EqualAreaSlicing)}
    for name in ("slice_count", "representative"):
        assert fields[name].default is dataclasses.MISSING, (
            f"{name} must be stated, not defaulted"
        )


def test_equal_area_slicing_refuses_a_split_peak_rather_than_stepping_over_the_gap():
    """DETECTOR PROOF for the contiguity carried on the admitted region.

    A running area total across a gap attributes the missing area to the
    slice that spans it. Equal-volume slicing has no running total and is
    unaffected, which is why the check lives on the one convention that
    needs it rather than on the limits."""
    from instrument.chromatogram import Chromatogram

    volumes = tuple(8.0 + 0.01 * index for index in range(601))
    concentrations = tuple(
        1.0 if index < 200 else (0.0 if index < 400 else 1.0) for index in range(601))
    split = Chromatogram(volumes, concentrations)
    parameters = IntegrationParameters(baseline_threshold=0.5)

    assert not admitted_region(split, parameters).contiguous
    with pytest.raises(SlicingError, match="not contiguous"):
        slice_area_moments(split, NARROW_POLYSTYRENE, parameters, EQUAL_AREA_MID)

    unsplit = Chromatogram(volumes, tuple(1.0 for _ in volumes))
    assert admitted_region(unsplit, parameters).contiguous
    assert slice_area_moments(unsplit, NARROW_POLYSTYRENE, parameters, EQUAL_AREA_MID).mn > 0.0
    assert slice_area_moments(split, NARROW_POLYSTYRENE, parameters, EQUAL_VOLUME).mn > 0.0, (
        "equal-volume must still compute, or the check is refusing the limits rather than the "
        "convention that cannot survive them"
    )


def test_a_slicing_that_could_not_be_a_slice_table_is_refused_at_construction():
    with pytest.raises(SlicingError, match="at least 2"):
        EqualAreaSlicing(1, AT_SLICE_MIDPOINT)
    with pytest.raises(SlicingError, match="representative must be one of"):
        EqualAreaSlicing(100, "wherever")
    assert EqualAreaSlicing(100, AT_SLICE_START).representative == AT_SLICE_START


def test_the_record_carries_the_correction_rather_than_a_restated_result():
    """A record that quietly re-derived its numbers under the new
    convention would hide that the old ones were taken under a wrong
    one."""
    correction = RECORD["corrections"]["slicing_was_assumed_equal_volume_and_empower_is_equal_area"]
    assert correction["source"].startswith("ANCHOR 1")
    assert "no plate count" in correction["what_it_changes"]
    assert "was a default" in correction["why_it_was_invisible"]
    assert RECORD["acceptance"]["the_sharpest_result"]["superseded_scope"]
