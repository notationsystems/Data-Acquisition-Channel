"""Lane memory — the residuals that make the fiftieth load teach you
something the first one did not.

A market index tells you what a lane costs. Your record tells you what it
costs YOU, with this carrier, in February, including the detention that
was not in the quote. The second is proprietary, it compounds, and nobody
else can compute it.

WHAT THIS REFUSES, AND WHY EACH REFUSAL IS HERE.

MIN-TRIALS FLOOR. A mean over two loads is a number and not an estimate.
Every group below reports its own n, and a group under the floor returns
`None` with the count rather than a figure a reader will treat as a rate.
This account has already paid for the alternative: a precision computed
over a denominator of one.

THE PARTITION IS DECLARED, NOT INFERRED. `by_carrier` and `by_lane` answer
different questions and can disagree, which is the point: a gap that
appears on one lane and not another is a lane fact, and the same gap
following a carrier across lanes is a carrier fact. Reporting one without
naming the partition is how the two get confused.

SEASON IS A PARTITION, NOT A COVARIATE. A lane whose transit runs long in
three months of the year and on time in nine has a bimodal residual, and
its annual mean describes neither mode. `by_lane_season` exists because
the annual figure is the one that looks fine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from commerce.events import (PICKUP_ACTUAL, PICKUP_PROMISED, RATE_INVOICED, RATE_QUOTED,
                             SETTLES, TRANSIT_ESTIMATED, TRANSIT_REALIZED, LoadEvent)

#: Below this, a group reports its count and no estimate.
MIN_TRIALS = 5

#: Seasons, as a declared partition rather than a derived one.
WINTER = "winter"
NON_WINTER = "non_winter"
WINTER_MONTHS = frozenset({12, 1, 2})

INSUFFICIENT_OBSERVATIONS = "INSUFFICIENT_OBSERVATIONS"
NO_GROUPS_BECAUSE_NO_LOADS_SETTLED = "NO_GROUPS_BECAUSE_NO_LOADS_SETTLED"
NO_GROUPS_BECAUSE_EVERY_GROUP_IS_BELOW_THE_FLOOR = (
    "NO_GROUPS_BECAUSE_EVERY_GROUP_IS_BELOW_THE_FLOOR")


def season_of(month: int) -> str:
    return WINTER if month in WINTER_MONTHS else NON_WINTER


@dataclass(frozen=True)
class Residual:
    """One group's residual, with the population it was computed over."""

    key: str
    partition: str
    basis: str
    unit: str
    n: int
    mean: Optional[float]
    spread: Optional[float]
    refusal: Optional[str] = None

    @property
    def estimated(self) -> bool:
        return self.mean is not None


def _summarise(key: str, partition: str, basis: str, unit: str,
               values: Sequence[float]) -> Residual:
    n = len(values)
    if n < MIN_TRIALS:
        return Residual(key, partition, basis, unit, n, None, None,
                        refusal=(f"{INSUFFICIENT_OBSERVATIONS}: {n} settled load(s) against a "
                                 f"floor of {MIN_TRIALS}. A mean over {n} is a number and not an "
                                 "estimate, and reported as one it would be read as a rate."))
    mean = math.fsum(values) / n
    spread = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / n) if n > 1 else 0.0
    return Residual(key, partition, basis, unit, n, mean, spread)


@dataclass(frozen=True)
class ResidualSet:
    partition: str
    residuals: Tuple[Residual, ...]
    empty_because: Optional[str] = None

    @property
    def estimated(self) -> Tuple[Residual, ...]:
        return tuple(r for r in self.residuals if r.estimated)

    @property
    def below_floor(self) -> Tuple[Residual, ...]:
        return tuple(r for r in self.residuals if not r.estimated)

    def get(self, key: str) -> Optional[Residual]:
        for residual in self.residuals:
            if residual.key == key:
                return residual
        return None


def _paired(events: Sequence[LoadEvent], promise: str) -> Dict[str, Tuple[float, float]]:
    """Loads with BOTH the promise and its settlement, keyed by load.

    A load carrying only one half is not a small residual; it is not a
    residual at all, and including it as zero would pull every mean toward
    nothing.
    """
    settlement = SETTLES[promise]
    promised: Dict[str, float] = {}
    realized: Dict[str, float] = {}
    for event in events:
        if event.kind == promise:
            promised[event.load] = event.value
        elif event.kind == settlement:
            realized[event.load] = event.value
    return {load: (promised[load], realized[load])
            for load in promised if load in realized}


def _build(groups: Mapping[str, List[float]], partition: str, basis: str,
           unit: str) -> ResidualSet:
    residuals = tuple(_summarise(key, partition, basis, unit, values)
                      for key, values in sorted(groups.items()))
    empty_because = None
    if not residuals:
        empty_because = (f"{NO_GROUPS_BECAUSE_NO_LOADS_SETTLED}: no load carries both halves of "
                         "the pair, so there is nothing to difference. This is not a residual of "
                         "zero.")
    elif not any(r.estimated for r in residuals):
        empty_because = (f"{NO_GROUPS_BECAUSE_EVERY_GROUP_IS_BELOW_THE_FLOOR}: "
                         f"{len(residuals)} group(s) exist and every one is under {MIN_TRIALS} "
                         "settled loads. The book is real and too thin to estimate from, which is "
                         "a different state from an empty book.")
    return ResidualSet(partition, residuals, empty_because)


def by_carrier(events: Sequence[LoadEvent], carrier_of: Mapping[str, str], *,
               promise: str = RATE_QUOTED) -> ResidualSet:
    """Realized minus promised, grouped by the carrier that was tendered.

    A persistent positive residual on one carrier across lanes is a
    carrier fact. The same residual on one lane across carriers is not.
    """
    groups: Dict[str, List[float]] = {}
    for load, (promised, realized) in _paired(events, promise).items():
        carrier = carrier_of.get(load)
        if carrier is None:
            continue
        groups.setdefault(carrier, []).append(realized - promised)
    unit = "CAD" if promise in (RATE_QUOTED,) else "days"
    return _build(groups, "carrier", f"realized_minus_{promise}", unit)


def by_lane(events: Sequence[LoadEvent], lane_of: Mapping[str, Tuple[str, str]], *,
            promise: str = TRANSIT_ESTIMATED) -> ResidualSet:
    groups: Dict[str, List[float]] = {}
    for load, (promised, realized) in _paired(events, promise).items():
        lane = lane_of.get(load)
        if lane is None:
            continue
        groups.setdefault(f"{lane[0]}->{lane[1]}", []).append(realized - promised)
    return _build(groups, "lane", f"realized_minus_{promise}", "days")


def by_lane_season(events: Sequence[LoadEvent], lane_of: Mapping[str, Tuple[str, str]],
                   month_of: Mapping[str, int], *,
                   promise: str = TRANSIT_ESTIMATED) -> ResidualSet:
    """The partition the annual figure hides.

    A lane running one day long in three months and on time in nine has an
    annual mean of a quarter-day, which describes neither mode and would
    price every load the same.
    """
    groups: Dict[str, List[float]] = {}
    for load, (promised, realized) in _paired(events, promise).items():
        lane = lane_of.get(load)
        month = month_of.get(load)
        if lane is None or month is None:
            continue
        key = f"{lane[0]}->{lane[1]}:{season_of(month)}"
        groups.setdefault(key, []).append(realized - promised)
    return _build(groups, "lane_season", f"realized_minus_{promise}", "days")


def appointment_slippage(events: Sequence[LoadEvent],
                         receiver_of: Mapping[str, str]) -> ResidualSet:
    """Promised pickup against actual, grouped by the receiver.

    Modelled on the RECEIVER rather than on the driver deliberately: it
    generalises across carriers, has more observations per group, and
    carries none of the exposure of a person-level score.
    """
    groups: Dict[str, List[float]] = {}
    for load, (promised, actual) in _paired(events, PICKUP_PROMISED).items():
        receiver = receiver_of.get(load)
        if receiver is None:
            continue
        groups.setdefault(receiver, []).append(actual - promised)
    return _build(groups, "receiver", "actual_minus_promised_pickup", "days")


def render(result: ResidualSet) -> str:
    lines = [f"RESIDUALS by {result.partition}"]
    if result.empty_because:
        lines.append(f"  (nothing estimated) {result.empty_because}")
    for residual in result.residuals:
        if residual.estimated:
            assert residual.mean is not None and residual.spread is not None
            lines.append(f"  {residual.key:<34} n={residual.n:<3} "
                         f"mean {residual.mean:>+9.2f} sd {residual.spread:>7.2f} "
                         f"{residual.unit}  [{residual.basis}]")
        else:
            lines.append(f"  {residual.key:<34} n={residual.n:<3} NO ESTIMATE — "
                         f"{residual.refusal}")
    return "\n".join(lines)
