"""Closed-form chain-length distributions, and the moments that make them
oracles.

THE POINT OF CLOSED FORMS. An oracle whose expected value is computed the
same way as the thing under test proves only that the code agrees with
itself. Each family here exposes its moments ANALYTICALLY, and the
agreement test integrates the density numerically and compares -- so a
disagreement indicts one side or the other rather than passing.

FLORY IS THE STRONGEST ANCHOR. Its Mz : Mw : Mn is exactly 3 : 2 : 1, so
the dispersity is exactly 2 for every choice of parameter. That invariant
does not depend on this implementation, on the grid, or on the
integrator, which is what makes it a regression anchor rather than a
recorded expectation.

THE REPRESENTATION IS dW/dlogM. That is what GPC software plots and
integrates. Generating chain counts and hoping a later stage recovers the
shape puts the first error where it cannot be seen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

LN10 = math.log(10.0)


@dataclass(frozen=True)
class Moments:
    """The three power averages, plus the mode where a family has one.

    `mp` is the MODE of the weight distribution -- the molar mass at the
    peak of dW/dlogM -- and it is deliberately not called a moment. It is
    not a power average of the same family as Mn, Mw and Mz, and filing
    it beside them is the category error a consumer computing ratios
    would inherit.
    """

    mn: float
    mw: float
    mz: float

    @property
    def dispersity(self) -> float:
        return self.mw / self.mn

    def as_ratios(self) -> Tuple[float, float]:
        """(Mw/Mn, Mz/Mw) -- the shape-only signature, free of scale."""
        return (self.mw / self.mn, self.mz / self.mw)


class ChainLengthDistribution:
    """A true distribution. Never a measurement, never evidence."""

    def number_density(self, mass: float) -> float:
        """n(M), normalised so the integral over M is 1."""
        raise NotImplementedError

    def analytic_moments(self) -> Moments:
        raise NotImplementedError

    def log10_range(self) -> Tuple[float, float]:
        """The decades over which the density is worth integrating.

        Declared per family rather than assumed globally: a log-normal
        with a wide sigma has heavier tails than a Schulz-Zimm, and Mz
        weights the upper tail by M-squared, so a range adequate for Mn
        can be wrong for Mz without looking wrong.
        """
        raise NotImplementedError

    def dw_dlogm(self, log10_mass: float) -> float:
        """The GPC representation: dW/dlog10(M).

        w(M) = M n(M) / Mn is the weight density, normalised because the
        integral of M n(M) is Mn by definition. Then
        dW/dlog10(M) = w(M) * dM/dlog10(M) = ln(10) * M^2 * n(M) / Mn.
        """
        mass = 10.0 ** log10_mass
        return LN10 * mass * mass * self.number_density(mass) / self.analytic_moments().mn


@dataclass(frozen=True)
class SchulzZimm(ChainLengthDistribution):
    """n(M) proportional to M^z exp(-M/b): a Gamma number density.

    Mn = (z+1)b, Mw = (z+2)b, Mz = (z+3)b, so Mw/Mn = (z+2)/(z+1) and a
    target dispersity is directly specifiable. z = 0 is Flory.
    """

    mn: float
    z: float

    def __post_init__(self) -> None:
        if self.mn <= 0:
            raise ValueError(f"mn must be positive, got {self.mn}")
        if self.z < 0:
            raise ValueError(f"z must be non-negative, got {self.z}")

    @property
    def scale(self) -> float:
        return self.mn / (self.z + 1.0)

    def number_density(self, mass: float) -> float:
        if mass <= 0.0:
            return 0.0
        b, z = self.scale, self.z
        log_density = z * math.log(mass) - mass / b - math.lgamma(z + 1.0) - (z + 1.0) * math.log(b)
        return math.exp(log_density)

    def analytic_moments(self) -> Moments:
        b = self.scale
        return Moments(mn=(self.z + 1.0) * b, mw=(self.z + 2.0) * b, mz=(self.z + 3.0) * b)

    def log10_range(self) -> Tuple[float, float]:
        """Derived from the density's own tails, not chosen by trial.

        THE LOWER BOUND IS THE ONE THAT BITES, and a fixed six decades was
        wrong in a way only z = 0 revealed. Mn is computed as
        (integral of w) / (integral of w/M), and integral of w/M is
        integral of n, so the NUMBER integral's lower tail sets Mn's
        error. For small M the number density goes as M^z, so the mass
        missing below a cutoff L is about (L/b)^(z+1) / ((z+1) * Gamma(z+1)).
        At z = 0 that is simply L/b -- flat, not vanishing -- so six
        decades leaves 1e-6 of the number integral outside the grid and
        biases Mn by exactly that. Measured at 1.0e-06 before this was
        derived, against 1e-14 for the families with z > 0, which is why
        Flory being the strongest anchor is also what exposed it.

        Solving (L/b)^(z+1) = epsilon gives L/b = epsilon^(1/(z+1)), so
        the lower bound widens as z falls and is 12 decades at z = 0.

        The upper tail is exp(-M/b) weighted by M^(z+3) for Mz, peaking
        at (z+3)b and negligible well before the bound below.
        """
        b = self.scale
        decades_below = 12.0 / (self.z + 1.0)
        return (math.log10(b) - decades_below,
                math.log10(b) + math.log10(80.0 + 12.0 * self.z))


def flory(mn: float) -> SchulzZimm:
    """The most-probable distribution. Mz : Mw : Mn = 3 : 2 : 1 exactly."""
    return SchulzZimm(mn=mn, z=0.0)


@dataclass(frozen=True)
class LogNormal(ChainLengthDistribution):
    """A different shape family rather than another parameterisation:
    symmetric in log M, asymmetric in M.

    Mn = exp(mu + s^2/2), Mw = exp(mu + 3s^2/2), Mz = exp(mu + 5s^2/2),
    so Mw/Mn = Mz/Mw = exp(s^2) -- the moments are geometric, which is a
    signature no Gamma family has and which the agreement test uses to
    tell the two apart rather than merely checking both.
    """

    mn: float
    dispersity: float

    def __post_init__(self) -> None:
        if self.mn <= 0:
            raise ValueError(f"mn must be positive, got {self.mn}")
        if self.dispersity <= 1.0:
            raise ValueError(f"dispersity must exceed 1, got {self.dispersity}")

    @property
    def sigma(self) -> float:
        return math.sqrt(math.log(self.dispersity))

    @property
    def mu(self) -> float:
        return math.log(self.mn) - self.sigma ** 2 / 2.0

    def number_density(self, mass: float) -> float:
        if mass <= 0.0:
            return 0.0
        s = self.sigma
        z = (math.log(mass) - self.mu) / s
        return math.exp(-0.5 * z * z) / (mass * s * math.sqrt(2.0 * math.pi))

    def analytic_moments(self) -> Moments:
        s2 = self.sigma ** 2
        return Moments(mn=math.exp(self.mu + s2 / 2.0),
                       mw=math.exp(self.mu + 3.0 * s2 / 2.0),
                       mz=math.exp(self.mu + 5.0 * s2 / 2.0))

    def log10_range(self) -> Tuple[float, float]:
        # Mz weights by M^2 against a log-normal, which shifts the
        # effective centre up by 2*sigma^2 in ln M. Ten sigma either side
        # of the SHIFTED centre, converted to decades.
        centre = (self.mu + 2.0 * self.sigma ** 2) / LN10
        span = 10.0 * self.sigma / LN10
        return (centre - span - 1.0, centre + span + 1.0)


def integrated_moments(distribution: ChainLengthDistribution, points: int = 40001) -> Moments:
    """Moments by numerical integration of dW/dlogM -- the same shape the
    slice-area estimator uses, so agreement here is agreement about the
    method and not only about the algebra.

    Trapezoid over a uniform log10 M grid. The weight fraction of a slice
    is dW/dlogM times the slice width, which is exactly what a
    chromatogram slice carries.
    """
    if points < 3 or points % 2 == 0:
        raise ValueError("points must be odd and at least 3 for a symmetric trapezoid rule")

    low, high = distribution.log10_range()
    step = (high - low) / (points - 1)

    sum_w = sum_w_over_m = sum_wm = sum_wm2 = 0.0
    for index in range(points):
        log10_mass = low + index * step
        mass = 10.0 ** log10_mass
        weight = distribution.dw_dlogm(log10_mass) * step
        if index in (0, points - 1):
            weight *= 0.5
        sum_w += weight
        sum_w_over_m += weight / mass
        sum_wm += weight * mass
        sum_wm2 += weight * mass * mass

    return Moments(mn=sum_w / sum_w_over_m, mw=sum_wm / sum_w, mz=sum_wm2 / sum_wm)
