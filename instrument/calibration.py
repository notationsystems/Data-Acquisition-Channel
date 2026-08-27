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
