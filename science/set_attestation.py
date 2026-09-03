"""What a source says about a SET of runs, and whether it agrees.

WHY THIS IS NOT A FIFTH UNCERTAINTY KIND. `uncertainty_kind` is per
cell -- it describes the number in one row of one column. A coefficient
of variation over ten samples is not a property of any one of them, and
putting it on each would be the shape science/structured_uncertainty.py
already refuses when a 2x2 covariance is attached to a scalar value. The
level is the whole difference, so this is a different object rather than
a widened vocabulary.

WHAT IT IS FOR, measured rather than imagined. A GLP water-solubility
determination publishes `CV = 0.91%, n = 10` beside the ten
concentrations it was computed from. Before this module the ten entered
the evidence pool and the 0.91 did not -- so the substrate held the
inputs of a published statistic and no way to say the statistic had been
published, let alone whether its own arithmetic agreed. The check that
compares them existed once, hardcoded in one anchor's test module for one
document.

THE THREE VERDICTS, AND WHY THE THIRD IS NOT THE SECOND. An attestation
is AGREED when a counterpart was computed and matches within a stated
tolerance, DISAGREED when one was computed and does not, and UNCHECKED
when no counterpart could be computed at all. A shape with only two
verdicts reports `uncheckable` as `fine`, which is this repository's
vacuous-evidence shape at the level of a whole capability.

WHAT IT DELIBERATELY DOES NOT DO. It does not resolve a disagreement. A
laboratory's 0.91 and a recomputed 0.903 differ because the laboratory
computed from concentrations it printed rounded to two decimals; that is
a fact a reader needs and not one this layer settles. And it does not
hold a WITHHELD set-level statistic -- a report stating that a
correlation coefficient was obtained and archived rather than released
has made a set-level ABSENCE claim, which has no value to attest and no
home here. Named in architecture/set_level_attestation_result.yaml as
the remainder rather than smuggled in as a None.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Sequence, Tuple

#: Statistic kinds this module can compute a counterpart for. A kind
#: outside it is carried and reported UNCHECKED -- never silently passed.
MEAN = "mean"
STANDARD_DEVIATION_POPULATION = "standard_deviation_population"
STANDARD_DEVIATION_SAMPLE = "standard_deviation_sample"
COEFFICIENT_OF_VARIATION = "coefficient_of_variation"
MAXIMUM_DIFFERENCE = "maximum_difference"

#: Kinds a source may state that this module cannot recompute. Carried
#: with an explicit verdict rather than dropped: a fit quality against an
#: external reference table is a real published fact.
CORRELATION_COEFFICIENT = "correlation_coefficient"

STATISTIC_KINDS = (MEAN, STANDARD_DEVIATION_POPULATION, STANDARD_DEVIATION_SAMPLE,
                   COEFFICIENT_OF_VARIATION, MAXIMUM_DIFFERENCE, CORRELATION_COEFFICIENT)

AGREED = "AGREED"
DISAGREED = "DISAGREED"
UNCHECKED = "UNCHECKED"

UNKNOWN_STATISTIC_KIND = "UNKNOWN_STATISTIC_KIND"
NO_COUNTERPART_COMPUTABLE = "NO_COUNTERPART_COMPUTABLE"
POPULATION_EMPTY = "POPULATION_EMPTY"
POPULATION_DISAGREES_WITH_THE_ATTESTED_N = "POPULATION_DISAGREES_WITH_THE_ATTESTED_N"
NON_FINITE_ATTESTED_VALUE = "NON_FINITE_ATTESTED_VALUE"


class SetAttestationError(ValueError):
    """The attestation cannot be described honestly as given."""


@dataclass(frozen=True)
class SetAttestation:
    """A statistic a SOURCE stated about a set of runs.

    `n` is the population the source says it computed over, and it is
    required. A statistic without its denominator cannot be compared with
    anything: `CV = 0.91` over ten samples and over two are different
    claims, and a shape that let the denominator be omitted would make
    them the same object.
    """

    statistic: str
    value: float
    unit: str
    n: int
    #: The variable the statistic is about -- the column of the replicate
    #: set, never the set as a whole. Two columns can each carry one.
    variable: str
    #: Free text, from the source, saying which runs. Opaque here on
    #: purpose: matching it to a comparison context is the caller's act
    #: and inventing the match would be the fabrication this refuses.
    population: str
    source: str

    def __post_init__(self) -> None:
        if self.statistic not in STATISTIC_KINDS:
            raise SetAttestationError(
                f"{self.statistic!r} is not a statistic kind this module names "
                f"({list(STATISTIC_KINDS)}). It is refused rather than carried as an "
                "unknown: a kind nothing can interpret is a number with no meaning attached."
            )
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise SetAttestationError(f"a non-numeric attested value: {self.value!r}")
        if not math.isfinite(float(self.value)):
            raise SetAttestationError(
                f"{NON_FINITE_ATTESTED_VALUE}: {self.value!r}. An infinity is not a statistic."
            )
        if not isinstance(self.n, int) or isinstance(self.n, bool) or self.n < 1:
            raise SetAttestationError(
                f"an attested statistic must state the population it was computed over; "
                f"got n={self.n!r}. `CV = 0.91` over ten and over two are different claims."
            )
        for name in ("unit", "variable", "population", "source"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise SetAttestationError(f"{name!r} must be a non-empty string")


@dataclass(frozen=True)
class AttestationCheck:
    """What happened when the attestation met the values."""

    attestation: SetAttestation
    verdict: str
    computed: Optional[float]
    #: |attested - computed|, absolute. None when nothing was computed.
    difference: Optional[float]
    tolerance: Optional[float]
    reasons: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(self.reasons)))

    @property
    def checked(self) -> bool:
        return self.verdict in (AGREED, DISAGREED)


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _sd_population(values: Sequence[float]) -> float:
    mean = _mean(values)
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / len(values))


def _sd_sample(values: Sequence[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    mean = _mean(values)
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _cv(values: Sequence[float]) -> Optional[float]:
    """Percent, on the SAMPLE deviation.

    Stated rather than assumed, because the two conventions differ by
    1 - sqrt((n-1)/n) -- 10.56% at n = 5 -- and a comparison against a
    laboratory's figure is only as good as knowing which one it used. A
    check whose tolerance has to absorb the difference between two
    estimators is not checking the transcription.
    """
    sd = _sd_sample(values)
    mean = _mean(values)
    if sd is None or mean == 0:
        return None
    return 100.0 * sd / mean


def _maximum_difference(values: Sequence[float]) -> Optional[float]:
    """Percent, over the mean of the extremes -- the guideline definition:
    (highest - lowest) / mean(highest, lowest) x 100."""
    if len(values) < 2:
        return None
    high, low = max(values), min(values)
    midpoint = (high + low) / 2
    if midpoint == 0:
        return None
    return 100.0 * (high - low) / midpoint


_COMPUTABLE: Mapping[str, Callable[[Sequence[float]], Optional[float]]] = {
    MEAN: _mean,
    STANDARD_DEVIATION_POPULATION: _sd_population,
    STANDARD_DEVIATION_SAMPLE: _sd_sample,
    COEFFICIENT_OF_VARIATION: _cv,
    MAXIMUM_DIFFERENCE: _maximum_difference,
}


def check_attestation(attestation: SetAttestation, values: Sequence[float],
                      tolerance: float) -> AttestationCheck:
    """Compare a source's stated statistic with one computed from values.

    `tolerance` is REQUIRED and has no default. A default would be this
    layer deciding how close counts as agreement, which is a judgement
    about the source's rounding and belongs to whoever read the document.
    """
    if tolerance < 0:
        raise SetAttestationError("a negative tolerance is not a tolerance")

    reasons = []
    if not values:
        return AttestationCheck(attestation, UNCHECKED, None, None, tolerance,
                                (POPULATION_EMPTY,))
    if len(values) != attestation.n:
        # NOT an error and NOT agreement. The source says it computed over
        # n and it was handed a different number of values, so whatever is
        # computed here is a statistic over a different population.
        reasons.append(POPULATION_DISAGREES_WITH_THE_ATTESTED_N)

    compute = _COMPUTABLE.get(attestation.statistic)
    if compute is None:
        reasons.append(NO_COUNTERPART_COMPUTABLE)
        return AttestationCheck(attestation, UNCHECKED, None, None, tolerance,
                                tuple(reasons))

    computed = compute(values)
    if computed is None:
        reasons.append(NO_COUNTERPART_COMPUTABLE)
        return AttestationCheck(attestation, UNCHECKED, None, None, tolerance,
                                tuple(reasons))

    if reasons:
        # A population mismatch makes the comparison meaningless rather
        # than failed: reporting DISAGREED would blame the source for the
        # caller handing over the wrong set.
        return AttestationCheck(attestation, UNCHECKED, computed, None, tolerance,
                                tuple(reasons))

    difference = abs(float(attestation.value) - computed)
    verdict = AGREED if difference <= tolerance else DISAGREED
    return AttestationCheck(attestation, verdict, computed, difference, tolerance,
                            tuple(reasons))
