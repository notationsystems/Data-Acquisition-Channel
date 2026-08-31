"""Truck-legal routing as a priced input, and the measurement that decides
how to validate one.

WHAT WAS MEASURED, on 2026-08-31, against a public Valhalla instance.

  Toronto -> Montreal, a 400-series trunk haul:
      auto   544.93 km / 5.49 h
      truck  545.96 km / 5.54 h        <- 0.19% apart

  A short Toronto urban lane, truck costing, sweeping vehicle height:
      3.00 m   18.261 km / 1102 s
      4.11 m   18.261 km / 1102 s
      4.60 m   18.202 km / 1851 s      <- the threshold
      5.20 m   18.202 km / 1851 s

THE FINDING, AND IT INVERTS THE OBVIOUS METRIC. Crossing the restriction
threshold moved DISTANCE by -0.3% and moved TIME by +68%. The over-height
vehicle is pushed off a fast restricted road onto surface streets: it
travels very slightly less far and takes half an hour instead of eighteen
minutes.

So mileage is close to the worst quantity available for validating a truck
profile. An economics stage estimating carrier cost from distance alone
would see a legal and an illegal route as the same number, on both the
trunk haul and the urban lane. The restriction shows up in DURATION.

Two consequences, both structural below:

  1. A route estimate carries distance AND duration, and a caller cannot
     take one without the other. Distance agreement between two engines is
     not evidence that they routed the same way.

  2. LEGALITY IS A PROPERTY OF THE PROFILE SUPPLIED, NOT OF THE ENDPOINT
     CALLED. Valhalla's truck costing with no height is a consumer route
     wearing a truck label -- the sweep above shows the model does nothing
     until a dimension actually binds. So a route with no vehicle profile
     is classed `consumer` regardless of which engine produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

#: Restrictions were inputs to the cost function.
TRUCK_LEGAL = "truck_legal"
#: Restrictions were not considered. A claim, not a route.
CONSUMER = "consumer"
#: Which of the two this is has not been established.
LEGALITY_UNKNOWN = "legality_unknown"

ROUTE_CARRIES_NO_VEHICLE_PROFILE = "ROUTE_CARRIES_NO_VEHICLE_PROFILE"
ROUTE_CARRIES_NO_DURATION = "ROUTE_CARRIES_NO_DURATION"
CANNOT_PRICE_ON_AN_UNKNOWN_LEGALITY = "CANNOT_PRICE_ON_AN_UNKNOWN_LEGALITY"
CANNOT_PRICE_ON_A_CONSUMER_ROUTE = "CANNOT_PRICE_ON_A_CONSUMER_ROUTE"
COMPARISON_ACROSS_UNLIKE_LEGALITY = "COMPARISON_ACROSS_UNLIKE_LEGALITY"

#: The dimensions that must be supplied for a route to be truck-legal.
#: Absent any one of them the engine has nothing to bind on.
REQUIRED_DIMENSIONS: Tuple[str, ...] = ("height_m", "width_m", "length_m",
                                        "weight_t", "axle_load_t")


class RouteRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class VehicleProfile:
    """What binds. All five dimensions or none: a profile missing one is a
    profile the engine cannot refuse a road for."""

    height_m: float
    width_m: float
    length_m: float
    weight_t: float
    axle_load_t: float
    hazmat: bool = False


@dataclass(frozen=True)
class RouteEstimate:
    """Distance AND duration, with the legality of the routing that
    produced them.

    `duration_s` is required. It is the quantity the restriction actually
    moves, and an estimate carrying only distance lets a caller compare a
    legal and an illegal route and find them equal.
    """

    origin: str
    destination: str
    distance_km: float
    duration_s: float
    engine: str
    profile: Optional[VehicleProfile]
    retrieved_at: str

    def __post_init__(self) -> None:
        if self.duration_s is None:
            raise RouteRefusal(
                ROUTE_CARRIES_NO_DURATION,
                "an estimate with distance and no duration cannot distinguish a legal route from "
                "an illegal one: measured, a binding height moved distance by 0.3% and duration "
                "by 68%.",
            )

    @property
    def legality(self) -> str:
        """Derived from whether a profile was supplied, never from the
        engine's name or the endpoint that was called."""
        if self.profile is None:
            return CONSUMER
        return TRUCK_LEGAL

    @property
    def basis(self) -> str:
        return f"{self.legality}:{self.engine}"

    @property
    def average_speed_kph(self) -> float:
        return self.distance_km / (self.duration_s / 3600.0)


def truck_legal(origin: str, destination: str, *, distance_km: float, duration_s: float,
                engine: str, profile: VehicleProfile, retrieved_at: str) -> RouteEstimate:
    """A route computed with the vehicle's dimensions in the cost function."""
    for dimension in REQUIRED_DIMENSIONS:
        if getattr(profile, dimension) is None:
            raise RouteRefusal(
                ROUTE_CARRIES_NO_VEHICLE_PROFILE,
                f"{dimension} is absent. A truck costing model with a dimension missing has "
                "nothing to refuse a road for, and the measured sweep shows it returns the "
                "consumer route unchanged until a dimension binds.",
            )
    return RouteEstimate(origin, destination, distance_km, duration_s, engine, profile,
                         retrieved_at)


def consumer(origin: str, destination: str, *, distance_km: float, duration_s: float,
             engine: str, retrieved_at: str) -> RouteEstimate:
    """A route with no restrictions applied. Usable for a distance matrix
    where legality does not bind; never for the route a driver is sent on,
    and never as the basis of a quote."""
    return RouteEstimate(origin, destination, distance_km, duration_s, engine, None,
                         retrieved_at)


@dataclass(frozen=True)
class RouteComparison:
    """Two estimates of one lane.

    `distance_delta_pct` is reported and explicitly NOT sufficient: the
    measurement this module is built on is that distance is nearly
    insensitive to the thing that matters.
    """

    lane: str
    distance_delta_pct: float
    duration_delta_pct: float
    same_legality: bool
    refusal: Optional[str] = None
    finding: Optional[str] = None


def compare(a: RouteEstimate, b: RouteEstimate) -> RouteComparison:
    """Compare two estimates of the same lane.

    Comparing across unlike legality is refused for the reason every
    cross-basis comparison is refused here: the difference is not a
    finding about the road, it is a difference in what was being computed.
    """
    lane = f"{a.origin}->{a.destination}"
    distance_delta = 100.0 * (b.distance_km - a.distance_km) / a.distance_km
    duration_delta = 100.0 * (b.duration_s - a.duration_s) / a.duration_s
    if a.legality != b.legality:
        return RouteComparison(
            lane, distance_delta, duration_delta, same_legality=False,
            refusal=(f"{COMPARISON_ACROSS_UNLIKE_LEGALITY}: {a.legality} against {b.legality}. "
                     "The gap is not a fact about the road; it is the difference between "
                     "computing a legal route and computing any route."),
            finding=("measured on this pair: distance differs by "
                     f"{distance_delta:+.2f}% and duration by {duration_delta:+.2f}%. Distance "
                     "agreement is NOT evidence the two engines routed the same way."))
    return RouteComparison(lane, distance_delta, duration_delta, same_legality=True)


def validation_lane_is_discriminating(comparison: RouteComparison,
                                      *, minimum_duration_delta_pct: float = 5.0) -> bool:
    """Is this lane worth validating a truck profile on?

    A trunk haul is not. Measured, Toronto-Montreal moved 0.19% between
    auto and truck costing, so a validation suite built from long highway
    lanes would report agreement and prove nothing. A lane earns its place
    in the suite by making the profile MOVE.
    """
    return abs(comparison.duration_delta_pct) >= minimum_duration_delta_pct


def mileage_for_pricing(estimate: RouteEstimate) -> RouteEstimate:
    """The gate between a route and a quote.

    A quote priced off a consumer route is a quote against a road the
    truck may not legally travel, and the carrier will discover that
    before the firm does.
    """
    if estimate.legality == LEGALITY_UNKNOWN:
        raise RouteRefusal(
            CANNOT_PRICE_ON_AN_UNKNOWN_LEGALITY,
            f"{estimate.origin}->{estimate.destination} carries no established legality.",
        )
    if estimate.legality == CONSUMER:
        raise RouteRefusal(
            CANNOT_PRICE_ON_A_CONSUMER_ROUTE,
            f"{estimate.origin}->{estimate.destination} was routed without a vehicle profile, so "
            "restrictions were never in the cost function. Measured, that is worth 0.3% of "
            "distance and 68% of duration on a lane with a binding height — the quote would look "
            "almost right and the driver would be sent under a bridge.",
        )
    return estimate
