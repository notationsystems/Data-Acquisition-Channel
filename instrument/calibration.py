"""The log M against elution volume calibration, as an object.

WHY AN OBJECT AND NOT A FUNCTION. A calibration is a claim about a
particular column, a particular standard chemistry and a particular fit,
and two reports of the same material disagree when those differ. A bare
polynomial cannot carry the disagreement's cause; this carries the
coefficients, the standard chemistry, the fit order, the reported R-squared
and the calibrated range, so a difference between two reports is
attributable rather than merely observed.

THIRD ORDER, because that is what real instruments fit. The valid range
is the span of the standards used, and OUTSIDE IT THE MAPPING IS
EXTRAPOLATION. Real reports do not flag that, which is itself worth
reproducing: this model knows when it extrapolated, and the report it
will eventually emit does not say.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

#: Standard chemistries a calibration can be built against. A closed
#: vocabulary because there are only so many, and because a polystyrene
#: calibration read as a PMMA one is exactly the disagreement this object
#: exists to make attributable.
POLYSTYRENE = "polystyrene"
PMMA = "pmma"
STANDARD_CHEMISTRIES = (POLYSTYRENE, PMMA)


class CalibrationError(ValueError):
    """The calibration cannot describe what was asked of it."""


@dataclass(frozen=True)
class Calibration:
    """log10(M) = a + b*V + c*V^2 + d*V^3, over a stated volume range."""

    identifier: str
    standard_chemistry: str
    coefficients: Tuple[float, float, float, float]
    valid_volume_range: Tuple[float, float]
    r_squared: float

    def __post_init__(self) -> None:
        if self.standard_chemistry not in STANDARD_CHEMISTRIES:
            raise CalibrationError(
                f"{self.standard_chemistry!r} is not one of {list(STANDARD_CHEMISTRIES)}. A "
                "calibration whose standard chemistry is unstated cannot be compared with another."
            )
        low, high = self.valid_volume_range
        if not low < high:
            raise CalibrationError(f"valid_volume_range must be increasing, got {(low, high)}")
        if not 0.0 <= self.r_squared <= 1.0:
            raise CalibrationError(f"r_squared must be in [0, 1], got {self.r_squared}")

    @property
    def fit_order(self) -> int:
        return len(self.coefficients) - 1

    def log10_mass(self, volume: float) -> float:
        a, b, c, d = self.coefficients
        return a + b * volume + c * volume ** 2 + d * volume ** 3

    def mass(self, volume: float) -> float:
        return 10.0 ** self.log10_mass(volume)

    def d_log10_mass_d_volume(self, volume: float) -> float:
        """Analytic derivative. Needed to convert a density in log M into
        a density in V, and analytic rather than finite-difference so the
        Jacobian is not a second source of numerical error on top of the
        integrator the moment-agreement test just qualified."""
        _, b, c, d = self.coefficients
        return b + 2.0 * c * volume + 3.0 * d * volume ** 2

    def is_extrapolation(self, volume: float) -> bool:
        low, high = self.valid_volume_range
        return not (low <= volume <= high)

    def is_monotonic_over_range(self, samples: int = 2001) -> bool:
        """SEC elutes large chains first, so log M must DECREASE with
        volume across the whole calibrated range. A cubic that turns
        round inside its own range maps two volumes to one mass, and the
        estimator would then read one slice as two."""
        low, high = self.valid_volume_range
        step = (high - low) / (samples - 1)
        return all(self.d_log10_mass_d_volume(low + index * step) < 0.0
                   for index in range(samples))

    def volume_for_mass(self, mass: float, tolerance: float = 1e-12) -> float:
        """Invert by bisection over the calibrated range.

        Bisection rather than a root formula because the range is bounded
        and monotonic there, and because a closed-form cubic root would
        return branches outside the calibration that this object has no
        business claiming.
        """
        if not self.is_monotonic_over_range():
            raise CalibrationError(
                f"calibration {self.identifier!r} is not monotonic over its own valid range; "
                "two volumes map to one mass and the inverse is not a function"
            )
        target = math.log10(mass)
        low, high = self.valid_volume_range
        if not self.log10_mass(high) <= target <= self.log10_mass(low):
            raise CalibrationError(
                f"mass {mass!r} lies outside calibration {self.identifier!r}'s range "
                f"[{self.mass(high):.4g}, {self.mass(low):.4g}]"
            )
        for _ in range(200):
            middle = 0.5 * (low + high)
            if self.log10_mass(middle) > target:
                low = middle
            else:
                high = middle
            if high - low < tolerance:
                break
        return 0.5 * (low + high)


#: Two calibrations over the same column, differing in a way that is
#: attributable. Both are FABRICATED coefficients chosen to be monotonic
#: and physically ordered over the range; they are not transcribed from
#: any instrument, and nothing here claims otherwise.
NARROW_POLYSTYRENE = Calibration(
    identifier="cal:ps-narrow-3rd-order",
    standard_chemistry=POLYSTYRENE,
    coefficients=(12.0, -0.60, 0.010, -0.00012),
    valid_volume_range=(6.0, 18.0),
    r_squared=0.9997,
)

#: The same column calibrated against PMMA standards. A material measured
#: against both should report DIFFERENT moments, and the difference is
#: the standard chemistry rather than the material.
NARROW_PMMA = Calibration(
    identifier="cal:pmma-narrow-3rd-order",
    standard_chemistry=PMMA,
    coefficients=(11.82, -0.58, 0.0096, -0.000115),
    valid_volume_range=(6.0, 18.0),
    r_squared=0.9994,
)


# ----------------------------------------------------------------------
# A REAL CALIBRATION, from a real instrument. The two above are not.
# ----------------------------------------------------------------------

#: Waters Alliance 2695, two Styragel HR1 and one HR2, stabilized THF at
#: 40 C and 1.0 mL/min, calibrated against eleven American Polymer
#: Standards polystyrene standards from 162 to 14000 Da, each injected
#: twice. Transcribed in `instrument.anchor_one`; the coefficients here
#: are a third-order fit to that table, and the tests re-derive them.
#:
#: THERE ARE TWO CUBICS AND THEY ARE DIFFERENT OBJECTS. Fitting log10 M
#: against retention time reads on the report's `Calculated Weight`
#: column or on its nominal `Mol Wt` column, and the two fits do not
#: agree in the fourth significant figure:
#:
#:   vs Calculated Weight  (18.3712133214, -1.590686219, 0.0565734153, -0.0007300652)
#:   vs nominal Mol Wt     (18.3606691906, -1.589070073, 0.0564910669, -0.0007286686)
#:
#: TEN DECIMAL PLACES, and that is not decoration. Rounded to six the
#: same fit reproduces the report's column to 0.38% instead of 0.135% and
#: the slice table to 0.22% instead of 0.080% -- a factor of three thrown
#: away by a display convention. The precision needed was measured, not
#: chosen.
#:
#: The FIRST is the instrument's own function: the calculated column IS
#: that function evaluated at each standard's retention time, so
#: recovering it is a transcription check rather than a model fit, and it
#: reproduces the column to 0.135%. The SECOND measures calibration
#: QUALITY -- how far the standards sit from the curve -- and gives the
#: R^2 of 0.9987 recorded below.
#:
#: The confirmation that settles the transcription is a CROSS-TABLE one:
#: the first cubic, fitted only to the raster-read calibration table,
#: reproduces the TEXT-LAYER slice table's mass column to 0.080% across
#: all one hundred rows. Two tables read by two different routes, one
#: function, no free parameters.
#:
#: `valid_volume_range` is the span of the STANDARDS, which is what the
#: calibration is valid over -- not the span the report evaluates it
#: across. Nineteen of the anchor's hundred slices elute before the
#: highest standard, so `is_extrapolation` is True for them. That is the
#: report's own stated limit made mechanical.
WATERS_STYRAGEL_HR1_HR2_PS = Calibration(
    identifier="cal:anchor-1-waters-styragel-hr1-hr2-polystyrene",
    standard_chemistry=POLYSTYRENE,
    coefficients=(18.3712133214, -1.590686219, 0.0565734153, -0.0007300652),
    valid_volume_range=(16.858, 27.631),
    r_squared=0.9987,
)

#: The other fit, kept because the distinction above is only checkable if
#: both are present. NOT the instrument's function.
ANCHOR_1_QUALITY_FIT_COEFFICIENTS = (18.3606691906, -1.589070073,
                                    0.0564910669, -0.0007286686)
