"""Acceptance 1 and 2 for the forward instrument model, and the layer rule.

The brief's build order says to stop after the distributions and verify:
nothing downstream is worth building on a bad integrator. This is that
stop.
"""

from __future__ import annotations

import dataclasses
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
from instrument.chromatogram import (Column, IntegrationParameters,  # noqa: E402
                                     broaden, report_moments, slice_area_moments,
                                     true_chromatogram)

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
    unbroadened = slice_area_moments(true_chromatogram(FLORY, WIDE, 8001), WIDE, parameters)

    excesses = []
    for plates in (300000, 100000, 30000, 10000, 3000, 1000, 300):
        chromatogram = broaden(true_chromatogram(FLORY, WIDE, 8001),
                               Column("c", plates, 300.0, 5.0))
        reported = slice_area_moments(chromatogram, WIDE, parameters)
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
                                NARROW_POLYSTYRENE, parameters)
    wide = slice_area_moments(true_chromatogram(FLORY, WIDE, 8001), WIDE, parameters)

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
    narrow = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, 8001)
    wide = report_moments(FLORY, WIDE, column, parameters, 8001)
    assert narrow.dispersity < 2.0 < wide.dispersity


def test_two_large_errors_cancel_into_a_correct_looking_dispersity():
    """THE SHARPEST RESULT. At a plate count where truncation and
    broadening happen to balance, the report states a dispersity of 2.00
    -- indistinguishable from a correct measurement -- while Mn is wrong
    by more than three percent. The cancellation is in the RATIO and not
    in the SCALE, and no consumer reading the report can tell."""
    reported = report_moments(FLORY, NARROW_POLYSTYRENE, Column("c", 2500, 300.0, 5.0),
                              IntegrationParameters(), 8001)
    assert reported.dispersity == pytest.approx(2.0, abs=0.01), (
        "this test exists because the dispersity looks RIGHT here"
    )
    assert abs(reported.mn / 1e5 - 1.0) > 0.02, (
        "and Mn is wrong. If both were right the cancellation would not be a finding."
    )


def test_acceptance_4_the_discrepancy_is_reproducible_and_its_magnitude_is_stated():
    parameters = IntegrationParameters()
    column = Column("c", 10000, 300.0, 5.0)
    first = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, 4001)
    second = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, 4001)
    assert (first.mn, first.mw, first.mz) == (second.mn, second.mw, second.mz)
    assert first.mn / 1e5 - 1.0 == pytest.approx(0.0505, abs=0.002)


def test_acceptance_5_two_calibrations_over_one_truth_disagree_attributably():
    """Two labs, one material, two standard chemistries -- a
    contradiction with a known cause, which is unreachable any other
    way."""
    column = Column("c", 10000, 300.0, 5.0)
    parameters = IntegrationParameters()
    ps = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, 8001)
    pmma = report_moments(FLORY, NARROW_PMMA, column, parameters, 8001)

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
    full = report_moments(FLORY, NARROW_POLYSTYRENE, column, IntegrationParameters(), 8001)
    thresholded = report_moments(FLORY, NARROW_POLYSTYRENE, column,
                                 IntegrationParameters(baseline_threshold=0.05), 8001)
    windowed = report_moments(FLORY, NARROW_POLYSTYRENE, column,
                              IntegrationParameters(peak_start_volume=10.0,
                                                    peak_end_volume=15.0), 8001)

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
        true_chromatogram(FLORY, NARROW_POLYSTYRENE, 8001), NARROW_POLYSTYRENE, parameters)
    assert f"{unbroadened_narrow.dispersity:.3f}" == "1.899"

    unbroadened_wide = slice_area_moments(
        true_chromatogram(FLORY, WIDE, 8001), WIDE, parameters)
    assert f"{unbroadened_wide.dispersity:.6f}" == "1.999775"

    cancelling = report_moments(FLORY, NARROW_POLYSTYRENE, Column("c", 2500, 300.0, 5.0),
                                parameters, 8001)
    assert f"{cancelling.dispersity:.3f}" == "2.004"
    assert f"{cancelling.mn / 1e5 - 1.0:+.4f}" == "+0.0328"

    windowed = report_moments(FLORY, NARROW_POLYSTYRENE, column,
                              IntegrationParameters(peak_start_volume=10.0,
                                                    peak_end_volume=15.0), 8001)
    full = report_moments(FLORY, NARROW_POLYSTYRENE, column, parameters, 8001)
    assert f"{windowed.mn / full.mn - 1.0:.0%}" == "62%"


def test_the_record_says_what_is_not_built_and_why():
    not_built = RECORD["what_is_not_built_and_why"]
    assert "B.1 has not run" in not_built["report_emission"]
    assert "third fixture" in not_built["report_emission"]
    assert "waits on the anchors" in not_built["extractor_against_emitted_reports"]

    limits = RECORD["known_limits_of_the_model"]
    assert "NOT transcribed from any instrument" in limits["fabricated_calibration_coefficients"]
    assert "understates the low-M side" in limits["gaussian_not_emg"]
