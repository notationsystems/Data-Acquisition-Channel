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

AND WHAT A SLICE IS WAS ASSUMED HERE AND ASSUMED WRONG. This module took
"slice" to mean one acquisition point -- equal WIDTH in volume. A real
Waters Empower report shows one hundred slices of equal AREA: the same
`Slice Area` on every row, a cumulative-percent column running 1 to 100,
and elution steps that narrow through the peak and widen in the tails.
Both conventions are now built and neither has a default, because a
default is how the wrong one stayed invisible.

THE INTEGRATION LIMITS ARE ANALYST INPUTS AND THE REPORT WILL NOT CARRY
THEM. Baseline and peak intervals change the reported moments. Real
reports omit them. That is `no_context_free_property`'s argument made
executable rather than asserted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

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


class SlicingError(ValueError):
    """Raised when the admitted region cannot be sliced as asked."""


@dataclass(frozen=True)
class AdmittedRegion:
    """What the integration limits left, and whether it is one piece.

    Contiguity is carried rather than assumed because equal-area slicing
    integrates a running total across it: a baseline threshold that
    splits a shoulder off the main peak leaves a gap, and a cumulative
    sum that steps over the gap silently attributes the missing area to
    the slice that spans it.
    """

    volumes: Tuple[float, ...]
    concentrations: Tuple[float, ...]
    contiguous: bool


#: Where inside a slice the molar mass is read. The anchor report pins
#: the slice COUNT and the cumulative-percent column; it does not pin
#: this, and it moves the answer, so it is an argument rather than a
#: convention chosen here.
AT_SLICE_START = "at_slice_start"
AT_SLICE_MIDPOINT = "at_slice_midpoint"
AT_SLICE_END = "at_slice_end"
REPRESENTATIVE_POINTS = (AT_SLICE_START, AT_SLICE_MIDPOINT, AT_SLICE_END)

_CUMULATIVE_OFFSET = {AT_SLICE_START: 0.0, AT_SLICE_MIDPOINT: 0.5, AT_SLICE_END: 1.0}


@dataclass(frozen=True)
class Slice:
    """One row of the software's slice table: an area and the mass the
    calibration returns for the volume that row reports."""

    area: float
    mass: float


@dataclass(frozen=True)
class EqualVolumeSlicing:
    """One slice per acquisition point, of equal WIDTH in volume.

    This was the only estimator here until a real Waters Empower report
    showed it is not what that software does. It is kept because it is a
    real convention -- fixed-interval integration -- and because the
    equal-volume and equal-area numbers differ, which is the point.
    """

    def slices(self, admitted: AdmittedRegion,
               calibration: Calibration) -> Tuple[Slice, ...]:
        step = 1.0
        if len(admitted.volumes) > 1:
            step = admitted.volumes[1] - admitted.volumes[0]
        return tuple(
            Slice(area=concentration * step, mass=calibration.mass(volume))
            for volume, concentration in zip(admitted.volumes, admitted.concentrations)
        )


@dataclass(frozen=True)
class EqualAreaSlicing:
    """Equal AREA per slice, with the elution volume as the free variable.

    WHAT THE ANCHOR SHOWED. A real Waters Empower GPC report carries one
    hundred slices whose `Slice Area` column reads the same value on
    every row, a `Cumulative %` column running 1 to 100, and elution
    steps that narrow through the peak and widen in the tails. That is
    equal-area slicing, and the estimator here assumed equal-volume.

    IT IS NOT A COSMETIC DIFFERENCE. With equal area the slice weights
    are all identical, so the moments become plain means over the slice
    masses -- Mw the arithmetic mean, Mn the harmonic mean -- and the
    distribution's shape is carried entirely by WHERE the boundaries
    fall. The two conventions converge as the slice count grows, so what
    survives at a real count of one hundred is a discretisation error
    concentrated in the tails, where one slice spans a wide volume range
    and a single mass has to stand for all of it.

    `representative` is required because the anchor does not pin it. A
    cumulative column reading 1 to 100 is consistent with the reported
    volume being each slice's END, and the endpoint rule reads every
    slice at its low-mass edge; a midpoint rule does not. The choice is
    the vendor's, the report does not carry it, and it moves the answer.
    """

    slice_count: int
    representative: str

    def __post_init__(self) -> None:
        if self.slice_count < 2:
            raise SlicingError(
                f"slice_count must be at least 2, got {self.slice_count}")
        if self.representative not in REPRESENTATIVE_POINTS:
            raise SlicingError(
                f"representative must be one of {REPRESENTATIVE_POINTS}, "
                f"got {self.representative!r}")

    def slices(self, admitted: AdmittedRegion,
               calibration: Calibration) -> Tuple[Slice, ...]:
        if not admitted.contiguous:
            raise SlicingError(
                "the admitted region is not contiguous, so a running area total would step "
                "across the gap and attribute the missing area to the slice that spans it"
            )
        if len(admitted.volumes) < 2:
            raise SlicingError("equal-area slicing needs at least two acquisition points")

        cumulative = [0.0]
        for index in range(1, len(admitted.volumes)):
            width = admitted.volumes[index] - admitted.volumes[index - 1]
            mean_height = 0.5 * (admitted.concentrations[index]
                                 + admitted.concentrations[index - 1])
            cumulative.append(cumulative[-1] + mean_height * width)
        total = cumulative[-1]
        if total <= 0.0:
            raise SlicingError("the admitted region has no area to divide")

        area = total / self.slice_count
        offset = _CUMULATIVE_OFFSET[self.representative]
        return tuple(
            Slice(area=area,
                  mass=calibration.mass(
                      _volume_at_cumulative(admitted.volumes, cumulative,
                                            (index + offset) * area)))
            for index in range(self.slice_count)
        )


Slicing = Union[EqualVolumeSlicing, EqualAreaSlicing]


def _volume_at_cumulative(volumes: Sequence[float], cumulative: Sequence[float],
                          target: float) -> float:
    """The volume at which the running area reaches `target`, linearly
    interpolated. Bisection rather than a scan, because a hundred slices
    over eight thousand points is otherwise quadratic for no reason."""
    if target <= cumulative[0]:
        return volumes[0]
    if target >= cumulative[-1]:
        return volumes[-1]
    low, high = 0, len(cumulative) - 1
    while high - low > 1:
        middle = (low + high) // 2
        if cumulative[middle] <= target:
            low = middle
        else:
            high = middle
    span = cumulative[high] - cumulative[low]
    if span <= 0.0:
        return volumes[low]
    fraction = (target - cumulative[low]) / span
    return volumes[low] + fraction * (volumes[high] - volumes[low])


def admitted_region(chromatogram: Chromatogram,
                    parameters: IntegrationParameters) -> AdmittedRegion:
    """Apply the analyst's limits, and report whether what is left is one
    piece."""
    peak = max(chromatogram.concentrations)
    cutoff = peak * parameters.baseline_threshold

    volumes: List[float] = []
    concentrations: List[float] = []
    indices: List[int] = []
    for index, (volume, concentration) in enumerate(
            zip(chromatogram.volumes, chromatogram.concentrations)):
        if parameters.peak_start_volume is not None and volume < parameters.peak_start_volume:
            continue
        if parameters.peak_end_volume is not None and volume > parameters.peak_end_volume:
            continue
        if concentration <= cutoff:
            continue
        volumes.append(volume)
        concentrations.append(concentration)
        indices.append(index)

    contiguous = not indices or indices[-1] - indices[0] == len(indices) - 1
    return AdmittedRegion(tuple(volumes), tuple(concentrations), contiguous)


def slice_area_moments(chromatogram: Chromatogram, calibration: Calibration,
                       parameters: IntegrationParameters, slicing: Slicing) -> Moments:
    """What the software computes -- not what is true.

    `slicing` is a required argument for the same reason `parameters` is.
    It carried a default of equal-volume for exactly as long as it took a
    real report to show that Empower does not slice that way, and a
    default is how a wrong convention stays invisible.
    """
    pieces = slicing.slices(admitted_region(chromatogram, parameters), calibration)

    sum_c = sum_c_over_m = sum_cm = sum_cm2 = 0.0
    for piece in pieces:
        sum_c += piece.area
        sum_c_over_m += piece.area / piece.mass
        sum_cm += piece.area * piece.mass
        sum_cm2 += piece.area * piece.mass * piece.mass

    if len(pieces) < 2 or sum_c <= 0.0:
        raise ValueError(
            "the integration limits admit fewer than two slices; the report would be a moment "
            "over a point rather than over a peak"
        )
    return Moments(mn=sum_c / sum_c_over_m, mw=sum_cm / sum_c, mz=sum_cm2 / sum_cm)


def report_moments(distribution: ChainLengthDistribution, calibration: Calibration,
                   column: Column, parameters: IntegrationParameters,
                   slicing: Slicing, points: int = 4001) -> Moments:
    """The whole forward path, truth to reported."""
    return slice_area_moments(
        broaden(true_chromatogram(distribution, calibration, points), column),
        calibration, parameters, slicing)
