"""ANCHOR 1, verified rather than trusted.

The transcription in `instrument/anchor_one.py` was read off rendered
pages for the raster tables and out of the text layer for the slice
table. This module is what stands behind it: every claim is re-derived,
and the two independently-read tables are made to check each other.

NOTHING HERE IS A FIXTURE. `instrument` is unreachable from the product
by a rule asserted in tests/test_forward_instrument_model.py, so these
values cannot enter an adapter, an extractor or the pool. B.1 still has
no fixture and this module does not give it one.
"""

from __future__ import annotations

import math
import pathlib
import statistics
import sys
from collections import defaultdict

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402
from instrument import anchor_one as A  # noqa: E402
from instrument.calibration import (ANCHOR_1_QUALITY_FIT_COEFFICIENTS,  # noqa: E402
                                    WATERS_STYRAGEL_HR1_HR2_PS as CAL, POLYSTYRENE)

RECORD = loads((REPO_ROOT / "architecture" / "anchor_one_result.yaml").read_text())

MASSES = [mass for _, mass, _ in A.SLICE_TABLE]
LOG_MASSES = [math.log10(mass) for mass in MASSES]


def _fit(degree, target):
    """Least squares of log10(target) against retention time, by normal
    equations. Written out rather than imported so the check does not
    depend on a library the repository does not declare."""
    size = degree + 1
    matrix = [[sum(row[1] ** (i + j) for row in A.CALIBRATION_STANDARDS)
               for j in range(size)] for i in range(size)]
    vector = [sum(math.log10(target(row)) * row[1] ** i for row in A.CALIBRATION_STANDARDS)
              for i in range(size)]
    augmented = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(augmented[r][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        for row in range(size):
            if row != column:
                factor = augmented[row][column] / augmented[column][column]
                for c in range(column, size + 1):
                    augmented[row][c] -= factor * augmented[column][c]
    return tuple(augmented[i][size] / augmented[i][i] for i in range(size))


# =====================================================================
# The transcription checks itself
# =====================================================================

def test_the_slice_table_is_complete_and_equal_area():
    assert len(A.SLICE_TABLE) == 100
    times = [rt for rt, _, _ in A.SLICE_TABLE]
    assert times == sorted(times), "the rows must be in elution order"
    assert len(A.SLICE_TABLE) * A.SLICE_AREA == 12232100
    assert abs(len(A.SLICE_TABLE) * A.SLICE_AREA / A.REPORTED["area"] - 1) < 1e-6, (
        "constant slice area times row count must reproduce the reported total area, or "
        "`equal-area slicing` is an inference rather than a measurement"
    )


def test_the_calibration_transcription_is_confirmed_by_a_table_it_was_not_fitted_to():
    """THE CHECK THAT MATTERS, because the two tables were read by
    different routes. The calibration table is a raster image read off a
    rendered page; the slice table came out of the PDF's text layer. A
    cubic fitted ONLY to the raster table predicts the text-layer table's
    mass column across all hundred rows, with no free parameters. A
    transcription error in either would break it."""
    worst_own = max(abs(CAL.mass(row[1]) / row[2] - 1) for row in A.CALIBRATION_STANDARDS)
    assert worst_own < 0.002, f"does not reproduce the report's own column: {worst_own:.4%}"

    worst_cross = max(abs(CAL.mass(rt) / mass - 1) for rt, mass, _ in A.SLICE_TABLE)
    assert worst_cross < 0.001, (
        f"the calibration fitted to page 3 does not predict page 5-7's masses: {worst_cross:.4%}"
    )
    assert CAL.is_monotonic_over_range()
    assert CAL.standard_chemistry == POLYSTYRENE


def test_there_are_two_cubics_and_the_stated_one_is_the_instruments():
    """A DISCRIMINATING CASE FOR THE COEFFICIENTS. Fitting against the
    report's `Calculated Weight` column and against its nominal `Mol Wt`
    column give different cubics, and only the first is the instrument's
    function. Reading the wrong one costs a factor of three in accuracy
    and it is not visible from either fit's own residuals."""
    against_calculated = _fit(3, lambda row: row[2])
    against_nominal = _fit(3, lambda row: row[0])
    assert against_calculated != against_nominal

    for derived, stated in zip(against_calculated, CAL.coefficients):
        assert abs(derived - stated) < 5e-10, (
            "the constant must be the fit against the CALCULATED column"
        )
    for derived, stated in zip(against_nominal, ANCHOR_1_QUALITY_FIT_COEFFICIENTS):
        assert abs(derived - stated) < 5e-10

    def worst(coefficients):
        return max(abs(10 ** sum(c * row[1] ** i for i, c in enumerate(coefficients)) / row[2] - 1)
                   for row in A.CALIBRATION_STANDARDS)
    assert worst(against_calculated) < 0.0015
    assert worst(against_nominal) > 2.0 * worst(against_calculated), (
        f"the quality fit reproduces the instrument's own column to "
        f"{worst(against_nominal):.4%} against {worst(against_calculated):.4%}; if the two were "
        "comparable the distinction this test names would not matter"
    )


def test_six_decimal_places_would_throw_away_a_factor_of_three():
    """Why the coefficients carry ten. Measured rather than chosen."""
    full = _fit(3, lambda row: row[2])

    def worst(coefficients):
        return max(abs(10 ** sum(c * row[1] ** i for i, c in enumerate(coefficients)) / row[2] - 1)
                   for row in A.CALIBRATION_STANDARDS)
    assert worst(tuple(round(c, 10) for c in full)) < 0.0015
    assert worst(tuple(round(c, 6) for c in full)) > 0.0035


def test_the_residual_column_is_relative_to_the_calculated_weight():
    """Recovered by arithmetic. `/nominal` and `/calculated` differ by
    enough to tell apart, which is what makes this a measurement."""
    assert A.RESIDUAL_IS_RELATIVE_TO == "calculated"

    # THE `Calculated Weight` COLUMN IS ROUNDED TO WHOLE NUMBERS, which
    # is why comparing percentages directly does not settle it -- at 162
    # Da an integer is a 0.3% quantisation. Inverting instead: the
    # residual and the nominal weight together recover an unrounded
    # calculated weight, and under the right definition it must land
    # within half a unit of the printed integer on EVERY row.
    worst_calculated = max(abs(nominal / (1 + stated / 100.0) - calculated)
                           for nominal, _, calculated, stated in A.CALIBRATION_STANDARDS)
    worst_nominal = max(abs(nominal * (1 - stated / 100.0) - calculated)
                        for nominal, _, calculated, stated in A.CALIBRATION_STANDARDS)
    assert worst_calculated < 0.5, (
        f"/calculated must recover every printed integer to within half a unit: {worst_calculated}"
    )
    assert worst_nominal > 5.0, (
        "and /nominal must NOT, or the two definitions are indistinguishable here and this "
        "recovers nothing"
    )


# =====================================================================
# The duplicate injections are a drift, not scatter
# =====================================================================

def test_the_duplicate_spread_is_systematic_and_is_a_stretch_not_an_offset():
    """ELEVEN OF ELEVEN, which is 1 in 2048 under a random sign.

    Every standard's second injection elutes LATER, and the shift scales
    with retention time: a proportional stretch fits with half the
    coefficient of variation of a constant offset. That is a flow or
    equilibration drift across the calibration run, and it applies to the
    sample too."""
    pairs = defaultdict(list)
    for nominal, time, calculated, _ in A.CALIBRATION_STANDARDS:
        pairs[nominal].append((time, calculated))
    assert len(pairs) == 11 and all(len(v) == 2 for v in pairs.values())

    offsets, stretches, spreads = [], [], []
    for entries in pairs.values():
        (first, first_mass), (second, second_mass) = sorted(entries)
        assert second > first, "a pair whose second injection is EARLIER breaks the claim"
        offsets.append(second - first)
        stretches.append(second / first - 1.0)
        spreads.append(max(first_mass, second_mass) / min(first_mass, second_mass) - 1.0)

    offset_cv = statistics.stdev(offsets) / statistics.mean(offsets)
    stretch_cv = statistics.stdev(stretches) / statistics.mean(stretches)
    assert stretch_cv < 0.6 * offset_cv, (
        f"a stretch ({stretch_cv:.1%}) must fit better than an offset ({offset_cv:.1%}), or the "
        "drift is not proportional and the consequence below is derived from the wrong model"
    )
    assert 0.001 < statistics.mean(stretches) < 0.002
    assert all(0.010 < spread < 0.019 for spread in spreads), (
        "the calibrated-mass spread must be present on EVERY standard; one large pair would be "
        "an outlier rather than a drift"
    )


def test_the_drift_does_not_cancel_in_a_ratio_so_averaging_will_not_remove_it():
    """WHY IT MATTERS. A random error on a calibrant averages out and
    leaves a ratio alone. This one is mass-dependent, so it moves Mn and
    Mw by different amounts and changes the dispersity."""
    pairs = defaultdict(list)
    for nominal, time, _, _ in A.CALIBRATION_STANDARDS:
        pairs[nominal].append(time)
    stretch = statistics.mean(max(v) / min(v) - 1.0 for v in pairs.values())

    shifts = [CAL.mass(rt * (1 + stretch)) / CAL.mass(rt) - 1.0 for rt in (16.5, 20.0, 25.0)]
    assert all(shift < 0 for shift in shifts), "a later elution must read a LOWER mass"
    assert abs(shifts[0]) > 1.3 * abs(shifts[-1]), (
        "the shift must be larger at high mass than at low, or it cancels in a ratio and this "
        "test names a consequence that does not follow"
    )


# =====================================================================
# The printed rows are slice BOUNDARIES, and the moments do not reproduce
# =====================================================================

def _trapezoids():
    densities = [d for _, _, d in A.SLICE_TABLE]
    return [0.5 * (densities[k] + densities[k + 1]) * (LOG_MASSES[k] - LOG_MASSES[k + 1])
            for k in range(len(A.SLICE_TABLE) - 1)]


def test_the_printed_rows_are_slice_boundaries_not_slice_representatives():
    """THE GEOMETRY, settled by the report's own density column.

    If each printed row were a representative carrying one percent of the
    area, the density at that row times the interval width would be
    uniform. It is not. The TRAPEZOID between consecutive rows is uniform
    -- an order of magnitude more so than either endpoint reading -- and
    the ninety-nine of them sum to the whole distribution. So the rows
    bound equal-weight intervals."""
    densities = [d for _, _, d in A.SLICE_TABLE]
    widths = [LOG_MASSES[k] - LOG_MASSES[k + 1] for k in range(99)]
    trapezoid = _trapezoids()
    earlier = [densities[k] * widths[k] for k in range(99)]
    later = [densities[k + 1] * widths[k] for k in range(99)]

    def cv(values):
        return statistics.stdev(values) / statistics.mean(values)

    assert cv(trapezoid) < 0.02
    assert cv(earlier) > 0.10 and cv(later) > 0.10
    assert cv(trapezoid) < 0.2 * min(cv(earlier), cv(later)), (
        "the trapezoid must be dramatically more uniform, or the boundary reading is a "
        "preference rather than a measurement"
    )
    assert abs(sum(trapezoid) - 1.0) < 1e-3, (
        f"the ninety-nine intervals must span the whole distribution; they sum to {sum(trapezoid)}"
    )


def _moments_at(fraction):
    """Interval masses interpolated in log M between their bounds."""
    masses = [10 ** (LOG_MASSES[k] + fraction * (LOG_MASSES[k + 1] - LOG_MASSES[k]))
              for k in range(99)]
    count = float(len(masses))
    mn = count / sum(1.0 / m for m in masses)
    mw = sum(masses) / count
    mz = sum(m * m for m in masses) / sum(masses)
    return mn, mw, mz


def test_no_representative_point_reproduces_both_reported_moments():
    """THE FINDING, and it is stronger than `the numbers disagree`.

    If the reported moments came from these hundred rows under some
    convention nobody has guessed, ONE interpolation fraction would
    reproduce them all. Scanned across the whole family: Mn is matched
    near f = 0.39 and Mw near f = 0.02, and those do not overlap. The
    best simultaneous fit still leaves about two percent."""
    reported = A.REPORTED
    matches_mn, matches_mw, worst_by_fraction = [], [], []
    for step in range(1001):
        fraction = step / 1000.0
        mn, mw, mz = _moments_at(fraction)
        if abs(mn / reported["mn"] - 1) < 0.002:
            matches_mn.append(fraction)
        if abs(mw / reported["mw"] - 1) < 0.002:
            matches_mw.append(fraction)
        worst_by_fraction.append(max(abs(mn / reported["mn"] - 1),
                                     abs(mw / reported["mw"] - 1),
                                     abs(mz / reported["mz"] - 1)))

    assert matches_mn and matches_mw, "each moment alone must be reachable, or the scan is broken"
    assert max(matches_mw) < min(matches_mn), (
        f"Mw is matched at {matches_mw[0]:.3f}-{matches_mw[-1]:.3f} and Mn at "
        f"{matches_mn[0]:.3f}-{matches_mn[-1]:.3f}; if these overlapped the reported moments "
        "WOULD be computable from the printed table and this finding would be wrong"
    )
    assert min(worst_by_fraction) > 0.015, (
        "and no fraction gets every moment inside one and a half percent"
    )


def test_reading_the_rows_as_representatives_inflates_the_mn_gap_six_fold():
    """THE SELF-CORRECTION, kept executable. Reading the hundred rows as
    representatives each carrying one percent of area gives Mn off by
    6.2%; reading them as boundaries gives 0.9%. Most of the gap first
    reported was the reading, not the report."""
    reported = A.REPORTED
    as_representatives = len(MASSES) / sum(1.0 / m for m in MASSES)
    naive_error = abs(as_representatives / reported["mn"] - 1)
    boundary_error = abs(_moments_at(0.5)[0] / reported["mn"] - 1)

    assert f"{naive_error:.4f}" == "0.0619"
    assert boundary_error < 0.02
    assert naive_error > 4.0 * boundary_error, (
        "the correction must be large, or it was not worth making"
    )


def test_the_gap_is_real_under_the_corrected_reading_too():
    """The prediction this resolves said the printed table would NOT
    reproduce the printed moments, and would differ by of order one
    percent rather than zero. Under the corrected geometry it does differ,
    by of order one percent, on every moment."""
    reported = A.REPORTED
    mn, mw, mz = _moments_at(0.5)
    errors = [abs(mn / reported["mn"] - 1), abs(mw / reported["mw"] - 1),
              abs(mz / reported["mz"] - 1)]
    assert all(error > 0.005 for error in errors), "none may be zero"
    assert all(error < 0.05 for error in errors), "and none is a different order of magnitude"


# =====================================================================
# The validity contradiction, on the report's own numbers
# =====================================================================

def test_the_report_states_a_limit_and_reports_two_moments_above_it():
    reported = A.REPORTED
    assert A.STATED_VALIDITY_LIMIT_DA == 14000
    above = {name: reported[name] for name in ("mp", "mz_plus_1", "mz", "mw", "mn")
             if reported[name] > A.STATED_VALIDITY_LIMIT_DA}
    assert set(above) == {"mp", "mz_plus_1"}, (
        f"exactly Mp and Mz+1 must exceed the stated limit; got {sorted(above)}"
    )
    assert len([m for m in MASSES if m > A.STATED_VALIDITY_LIMIT_DA]) == 20
    assert len([m for m in MASSES if m > A.COLUMN_EXCLUSION_LIMIT_DA]) == 4


def test_the_only_machine_readable_boundary_is_the_one_that_did_not_fire():
    """Twenty-one slices are extrapolations of the calibration, twenty
    exceed the stated validity limit, four exceed the column's exclusion
    limit -- and the per-slice flag reads benign on every row of both
    distribution tables."""
    extrapolating = [rt for rt, _, _ in A.SLICE_TABLE if CAL.is_extrapolation(rt)]
    assert len(extrapolating) == 21
    assert A.THE_SENTENCE in RECORD["the_validity_contradiction"]["the_documents_own_words"]


def test_dropping_the_invalid_slices_moves_the_moments_by_tens_of_percent():
    kept = [m for m in MASSES if m <= A.STATED_VALIDITY_LIMIT_DA]
    assert len(kept) == 80
    full_mn = len(MASSES) / sum(1.0 / m for m in MASSES)
    kept_mn = len(kept) / sum(1.0 / m for m in kept)
    full_mw = sum(MASSES) / len(MASSES)
    kept_mw = sum(kept) / len(kept)
    assert kept_mn / full_mn - 1 < -0.15
    assert kept_mw / full_mw - 1 < -0.25, (
        "a fifth of the area, outside the calibrated range, must carry a disproportionate share "
        "of Mw or the contradiction is arithmetically minor"
    )


# =====================================================================
# The record
# =====================================================================

def test_the_record_carries_the_correction_rather_than_the_first_reading():
    correction = RECORD["the_correction"]
    assert "6.19" in correction["what_was_first_reported"]
    assert "BOUNDARIES" in correction["what_the_density_column_shows"]
    assert "the reading, not the report" in correction["what_it_means"]


def test_the_record_marks_the_transcription_as_read_rather_than_certified():
    header = " ".join(line.lstrip("#").strip() for line
                      in (REPO_ROOT / "architecture" / "anchor_one_result.yaml")
                      .read_text().split("extends:")[0].splitlines())
    assert "not verified by a second party" in header
    assert "zero characters" in header


def test_the_new_predictions_are_pinned_separately_from_the_resolved_ones():
    """A prediction recorded after the anchor was fully read is weaker
    still than one recorded after a partial reading, and the artifact
    must not let the three generations blur."""
    assert set(RECORD["further_predictions_for_a_second_anchor"]) >= {"p4_moments_do_not_reproduce",
                                                                     "p5_headline_results_raster"}
    for name, body in RECORD["further_predictions_for_a_second_anchor"].items():
        assert "prediction" in body, f"{name} states no prediction"
        assert any(word in body.get("basis", "") for word in ("OPEN", "MEASURED")), (
            f"{name} does not say whether it rests on measured behaviour"
        )


def test_the_cross_table_check_refuses_the_fit_that_looks_better_on_its_own_column():
    """THE ARBITER EARNING ITS NAME.

    The `Calculated Weight` column is integer-rounded, so an unrounded
    version can be recovered through the residual column and fitted
    instead. That fit reproduces its OWN column three times better -- and
    predicts the independent slice table WORSE. A fit that improves where
    it was trained and degrades where it was not is fitting the rounding,
    and the cross-table check is the only test here not contaminated by
    the table being fitted."""
    rounded = [row[2] for row in A.CALIBRATION_STANDARDS]
    unrounded = [row[0] / (1 + row[3] / 100.0) for row in A.CALIBRATION_STANDARDS]

    def scores(values):
        coefficients = _fit(3, lambda row: values[A.CALIBRATION_STANDARDS.index(row)])
        mass = lambda rt: 10 ** sum(c * rt ** i for i, c in enumerate(coefficients))
        own = max(abs(mass(row[1]) / value - 1)
                  for row, value in zip(A.CALIBRATION_STANDARDS, values))
        cross = max(abs(mass(rt) / m - 1) for rt, m, _ in A.SLICE_TABLE)
        return own, cross

    rounded_own, rounded_cross = scores(rounded)
    unrounded_own, unrounded_cross = scores(unrounded)

    assert unrounded_own < 0.5 * rounded_own, "the unrounded fit must look better on its own column"
    assert unrounded_cross > rounded_cross, (
        "and worse on the table it was not fitted to. If it were better on both, the constant in "
        "instrument/calibration.py is the wrong one and must be changed."
    )
    assert tuple(round(c, 10) for c in _fit(3, lambda row: row[2])) == CAL.coefficients
