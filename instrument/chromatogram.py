"""The chromatogram, its broadening, and the estimator the software runs.

THREE STAGES, AND THE DISCREPANCY LIVES IN THE LAST TWO.

    truth  ->  c(V)            exact, via the calibration's Jacobian
           ->  broadened c(V)  the column has finite efficiency
           ->  reported Mn, Mw the slice-area estimator over chosen limits

BROADENING IS NOT A FITTED KNOB. A Gaussian whose width you choose is a
knob and proves nothing; a Gaussian whose width follows from a stated
plate count is a physical claim that can be wrong in an informative way.
The width here is sigma_V = V_peak / sqrt(N), the standard plate-count
relation, applied uniformly across the peak. That uniformity IS an
approximation -- a general rate model would give a width varying with
retention -- and it is stated rather than hidden, because the acceptance
test is about the SIGN and the DEPENDENCE of the discrepancy, not its
exact magnitude.

THE ESTIMATOR IS NOT THE MOMENTS. Conventional GPC computes Mn and Mw
from concentration and slice area, because molecule counts are not
measurable that way:

    Mn = sum(c_i) / sum(c_i / M_i)        Mw = sum(c_i * M_i) / sum(c_i)

with M_i read off the calibration at slice i. So the generating
distribution and the software's estimator are different mathematical
objects and the report is not the truth even when everything works.

THE INTEGRATION LIMITS ARE ANALYST INPUTS AND THE REPORT WILL NOT CARRY
THEM. Baseline and peak intervals change the reported moments. Real
reports omit them. That is `no_context_free_property`'s argument made
executable rather than asserted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from instrument.calibration import Calibration
from instrument.distributions import ChainLengthDistribution, Moments


@dataclass(frozen=True)
class Column:
    """The physical parameters the band width is derived FROM.

    Stated as column properties rather than as a width, so that a wrong
    width is a wrong claim about a column rather than a badly chosen
    number.
    """

    identifier: str
    plate_count: int
    length_mm: float
    particle_size_um: float
    #: Exponential tailing constant as a multiple of the Gaussian width.
    #: Zero is a symmetric Gaussian; real SEC peaks tail toward LATER
    #: elution volume, which is LOWER molar mass. Expressed as a ratio so
    #: the asymmetry is a property of the column rather than a second
    #: absolute width to choose independently of the plate count.
    tailing_tau_over_sigma: float = 0.0

    def __post_init__(self) -> None:
        if self.plate_count <= 0:
            raise ValueError(f"plate_count must be positive, got {self.plate_count}")
        if self.tailing_tau_over_sigma < 0.0:
            raise ValueError(
                f"tailing_tau_over_sigma must be non-negative, got {self.tailing_tau_over_sigma}")

    def band_sigma(self, peak_volume: float) -> float:
        """sigma_V = V / sqrt(N). The uniform-broadening approximation,
        named as one."""
        return peak_volume / math.sqrt(self.plate_count)


@dataclass(frozen=True)
class Chromatogram:
    """Concentration against elution volume, on a uniform grid."""

    volumes: Tuple[float, ...]
    concentrations: Tuple[float, ...]

    @property
    def step(self) -> float:
        return self.volumes[1] - self.volumes[0]

    def peak_volume(self) -> float:
        peak = max(range(len(self.concentrations)), key=lambda i: self.concentrations[i])
        return self.volumes[peak]


def true_chromatogram(distribution: ChainLengthDistribution, calibration: Calibration,
                      points: int = 4001) -> Chromatogram:
    """The chromatogram an infinitely efficient column would produce.

    c(V) = dW/dlogM(logM(V)) * |dlogM/dV| -- the density transformed by
    the calibration's own Jacobian, analytic rather than differenced.
    """
    low, high = calibration.valid_volume_range
    step = (high - low) / (points - 1)
    volumes, concentrations = [], []
    for index in range(points):
        volume = low + index * step
        jacobian = abs(calibration.d_log10_mass_d_volume(volume))
        concentrations.append(distribution.dw_dlogm(calibration.log10_mass(volume)) * jacobian)
        volumes.append(volume)
    return Chromatogram(tuple(volumes), tuple(concentrations))


def _convolve(values: Sequence[float], kernel: Sequence[float], origin: int) -> Tuple[float, ...]:
    n = len(values)
    out: List[float] = []
    for index in range(n):
        accumulated = 0.0
        for position, weight in enumerate(kernel):
            source = index + position - origin
            if 0 <= source < n:
                accumulated += values[source] * weight
        out.append(accumulated)
    return tuple(out)


def broaden(chromatogram: Chromatogram, column: Column) -> Chromatogram:
    """Band broadening with a width derived from the plate count.

    A symmetric Gaussian when the column declares no tailing; an
    EXPONENTIALLY MODIFIED GAUSSIAN when it does, built as the Gaussian
    convolved with a one-sided exponential -- which is what an EMG is,
    rather than a separate closed form to get subtly wrong.

    The exponential runs toward LATER elution volume, which is LOWER
    molar mass. That direction matters: a symmetric kernel UNDERSTATES
    the low-M side, biasing the report the same way the column's
    permeation limit does.
    """
    sigma = column.band_sigma(chromatogram.peak_volume())
    step = chromatogram.step
    reach = max(1, int(math.ceil(4.0 * sigma / step)))

    gaussian = [math.exp(-0.5 * (offset * step / sigma) ** 2)
                for offset in range(-reach, reach + 1)]
    total = sum(gaussian)
    gaussian = [value / total for value in gaussian]
    smeared = _convolve(chromatogram.concentrations, gaussian, origin=reach)

    if column.tailing_tau_over_sigma > 0.0:
        tau = column.tailing_tau_over_sigma * sigma
        span = max(1, int(math.ceil(6.0 * tau / step)))
        # One-sided, toward later volume: origin 0 so the kernel only
        # moves mass forward in elution.
        # Indexed so that _convolve's `source = index + position - origin`
        # with origin = span puts the LARGEST weight at source == index
        # and decaying weights at EARLIER sources -- which spreads mass
        # FORWARD in elution, leaving the mode where it was.
        #
        # The first draft indexed this the other way round. The direction
        # test still passed, because a reversed exponential also shifts
        # mass to later volume -- it TRANSLATES the peak instead of
        # tailing it. What caught it was the MAGNITUDE: a one-sided
        # exponential shifts the centroid by tau, and the reversed kernel
        # shifted it by span*step - tau, six times further. A sign check
        # was not a discriminating case here.
        tail = [math.exp(-((span - offset) * step) / tau) for offset in range(span + 1)]
        tail_total = sum(tail)
        tail = [value / tail_total for value in tail]
        smeared = _convolve(smeared, tail, origin=span)

    return Chromatogram(chromatogram.volumes, smeared)


@dataclass(frozen=True)
class IntegrationParameters:
    """The analyst's choices. THE EMITTED REPORT WILL NOT CARRY THESE.

    peak_start_volume / peak_end_volume bound the integrated peak;
    baseline_threshold discards slices below a fraction of the maximum.
    All three change the reported moments and none appears in a typical
    vendor report.
    """

    peak_start_volume: Optional[float] = None
    peak_end_volume: Optional[float] = None
    baseline_threshold: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.baseline_threshold < 1.0:
            raise ValueError(
                f"baseline_threshold must be in [0, 1), got {self.baseline_threshold}")


def slice_area_moments(chromatogram: Chromatogram, calibration: Calibration,
                       parameters: IntegrationParameters) -> Moments:
    """What the software computes -- not what is true."""
    peak = max(chromatogram.concentrations)
    cutoff = peak * parameters.baseline_threshold

    sum_c = sum_c_over_m = sum_cm = sum_cm2 = 0.0
    used = 0
    for volume, concentration in zip(chromatogram.volumes, chromatogram.concentrations):
        if parameters.peak_start_volume is not None and volume < parameters.peak_start_volume:
            continue
        if parameters.peak_end_volume is not None and volume > parameters.peak_end_volume:
            continue
        if concentration <= cutoff:
            continue
        mass = calibration.mass(volume)
        sum_c += concentration
        sum_c_over_m += concentration / mass
        sum_cm += concentration * mass
        sum_cm2 += concentration * mass * mass
        used += 1

    if used < 2 or sum_c <= 0.0:
        raise ValueError(
            "the integration limits admit fewer than two slices; the report would be a moment "
            "over a point rather than over a peak"
        )
    return Moments(mn=sum_c / sum_c_over_m, mw=sum_cm / sum_c, mz=sum_cm2 / sum_cm)


def report_moments(distribution: ChainLengthDistribution, calibration: Calibration,
                   column: Column, parameters: IntegrationParameters,
                   points: int = 4001) -> Moments:
    """The whole forward path, truth to reported."""
    return slice_area_moments(
        broaden(true_chromatogram(distribution, calibration, points), column),
        calibration, parameters)
