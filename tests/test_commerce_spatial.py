"""The two week-one spatial items, graded — and the measurement that
changed what "validating a truck profile" means.

MEASURED 2026-08-31 against a public Valhalla instance:

  Toronto -> Montreal (400-series trunk haul)
      auto  544.93 km / 5.49 h   truck  545.96 km / 5.54 h   -> 0.19% apart

  Toronto urban lane, truck costing, sweeping height:
      3.00 m  18.261 km / 1102 s
      4.11 m  18.261 km / 1102 s
      4.60 m  18.202 km / 1851 s
      5.20 m  18.202 km / 1851 s

Crossing the threshold moved DISTANCE by -0.3% and DURATION by +68%. The
brief proposed validating the truck profile on "a few known lanes" and
using truck-legal MILEAGE as the pricing input. Both are the wrong choice
on this evidence: a trunk haul barely moves, and mileage is the quantity
that barely moves even when the profile binds.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.facility import (AMBIGUOUS, CANONICAL_DUPLICATE_SIMILARITY,  # noqa: E402
                               CONSERVATIVE, NEAR_MATCH_FLOOR, RESOLVED, STATISTICAL,
                               UNRESOLVED, Facility, FacilityRefusal, _similarity,
                               available_normalizer, conservative_normalize, register_health,
                               resolve)
from commerce.mileage import (CANNOT_PRICE_ON_A_CONSUMER_ROUTE, CONSUMER,  # noqa: E402
                              COMPARISON_ACROSS_UNLIKE_LEGALITY, TRUCK_LEGAL, RouteRefusal,
                              VehicleProfile, compare, consumer, mileage_for_pricing,
                              truck_legal, validation_lane_is_discriminating)

PROFILE = VehicleProfile(height_m=4.11, width_m=2.6, length_m=21.0, weight_t=36.3,
                         axle_load_t=9.1)

# The measurements, as constants, so a test that stops matching them fails.
TRUNK_AUTO = (544.93, 5.49 * 3600)
TRUNK_TRUCK = (545.96, 5.54 * 3600)
URBAN_UNDER = (18.261, 1102.0)
URBAN_OVER = (18.202, 1851.0)


def _truck(dist, dur, engine="valhalla"):
    return truck_legal("YYZ", "YUL", distance_km=dist, duration_s=dur, engine=engine,
                       profile=PROFILE, retrieved_at="2026-08-31")


def _consumer(dist, dur, engine="valhalla"):
    return consumer("YYZ", "YUL", distance_km=dist, duration_s=dur, engine=engine,
                    retrieved_at="2026-08-31")


# =====================================================================
# The measurement, and what it implies about validation
# =====================================================================

def test_the_trunk_haul_barely_distinguishes_truck_from_consumer_routing():
    """So a validation suite built from long highway lanes would report
    agreement and prove nothing about the profile."""
    result = compare(_consumer(*TRUNK_AUTO), _truck(*TRUNK_TRUCK))
    assert abs(result.distance_delta_pct) < 0.5
    assert abs(result.duration_delta_pct) < 1.5
    assert not validation_lane_is_discriminating(result), (
        "Toronto-Montreal must NOT qualify as a validation lane; it is the lane that makes a "
        "truck profile look unnecessary"
    )


def test_the_urban_lane_with_a_binding_height_is_discriminating():
    under = _truck(*URBAN_UNDER)
    over = _truck(*URBAN_OVER)
    result = compare(under, over)
    assert abs(result.distance_delta_pct) < 1.0, "distance barely moves — that is the finding"
    assert result.duration_delta_pct > 60.0, "duration is where the restriction shows up"
    assert validation_lane_is_discriminating(result)


def test_distance_agreement_is_not_evidence_the_routes_agree():
    """The trap this module exists to close: two routes 0.3% apart in
    distance and 68% apart in time are not the same route."""
    result = compare(_truck(*URBAN_UNDER), _truck(*URBAN_OVER))
    assert abs(result.distance_delta_pct) < 1.0 and result.duration_delta_pct > 60.0


def test_an_estimate_cannot_be_built_without_a_duration():
    """A caller holding only distance can compare a legal and an illegal
    route and find them equal."""
    import inspect
    parameters = inspect.signature(truck_legal).parameters
    assert "duration_s" in parameters
    assert parameters["duration_s"].default is inspect.Parameter.empty


# =====================================================================
# Legality is a property of the profile, not of the endpoint called
# =====================================================================

def test_a_route_with_no_vehicle_profile_is_consumer_whatever_engine_produced_it():
    """Valhalla's truck costing with no height returns the consumer route
    unchanged — measured, 3.00 m and 4.11 m gave identical numbers. So an
    endpoint's name is not evidence about the route."""
    estimate = consumer("A", "B", distance_km=100.0, duration_s=3600.0,
                        engine="valhalla-truck-endpoint", retrieved_at="2026-08-31")
    assert estimate.legality == CONSUMER


def test_a_route_with_a_full_profile_is_truck_legal():
    assert _truck(*URBAN_UNDER).legality == TRUCK_LEGAL


def test_a_quote_cannot_be_priced_off_a_consumer_route():
    with pytest.raises(RouteRefusal) as caught:
        mileage_for_pricing(_consumer(*TRUNK_AUTO))
    assert caught.value.code == CANNOT_PRICE_ON_A_CONSUMER_ROUTE
    assert "sent under a bridge" in caught.value.detail


def test_a_truck_legal_route_passes_the_pricing_gate():
    assert mileage_for_pricing(_truck(*TRUNK_TRUCK)).legality == TRUCK_LEGAL


def test_comparing_across_unlike_legality_is_refused():
    result = compare(_consumer(*TRUNK_AUTO), _truck(*TRUNK_TRUCK))
    assert not result.same_legality
    assert result.refusal is not None and COMPARISON_ACROSS_UNLIKE_LEGALITY in result.refusal
    assert result.finding is not None
    assert "NOT evidence" in result.finding


def test_the_basis_carries_both_legality_and_engine():
    """Two truck-legal routes from different engines are still two claims,
    and the basis says so."""
    assert _truck(*TRUNK_TRUCK, engine="valhalla").basis != _truck(*TRUNK_TRUCK,
                                                                  engine="ors").basis


# =====================================================================
# Facility resolution: three states, and never a silent merge
# =====================================================================

def _register():
    name, normalize = available_normalizer()
    return [Facility("f-1", "123 Industrial Dr, Mississauga ON",
                     normalize("123 Industrial Dr, Mississauga ON"), name)]


def test_an_exact_normalized_match_resolves():
    result = resolve("123 INDUSTRIAL DR, MISSISSAUGA ON", _register())
    assert result.status == RESOLVED
    assert result.facility is not None and result.facility.facility_id == "f-1"


def test_a_near_match_is_surfaced_and_never_merged():
    """The state a similarity threshold quietly destroys. An automatic
    merge folds two real facilities into one and every lane statistic
    downstream inherits it."""
    result = resolve("123 Industrial Drive Unit 4, Mississauga ON", _register())
    assert result.status == AMBIGUOUS
    assert result.facility is None, "a near match must NOT be resolved to a facility"
    assert len(result.candidates) == 1
    assert "Surfaced, not merged" in result.detail
    assert result.remedy is not None and "confirm whether" in result.remedy


def test_no_match_preserves_the_raw_string_for_a_stronger_normalizer():
    result = resolve("500 Rue Sherbrooke, Montreal QC", _register())
    assert result.status == UNRESOLVED
    assert result.query == "500 Rue Sherbrooke, Montreal QC"
    assert "preserved so a stronger normalizer can re-read it" in result.detail


def test_the_three_resolution_states_are_distinguishable():
    register = _register()
    statuses = {
        resolve("123 INDUSTRIAL DR, MISSISSAUGA ON", register).status,
        resolve("123 Industrial Drive Unit 4, Mississauga ON", register).status,
        resolve("500 Rue Sherbrooke, Montreal QC", register).status,
    }
    assert statuses == {RESOLVED, AMBIGUOUS, UNRESOLVED}


def test_a_duplicate_already_in_the_register_is_reported_rather_than_picked():
    name, normalize = available_normalizer()
    raw = "123 Industrial Dr, Mississauga ON"
    register = [Facility("f-1", raw, normalize(raw), name),
                Facility("f-2", raw, normalize(raw), name)]
    result = resolve(raw, register)
    assert result.status == AMBIGUOUS
    assert len(result.candidates) == 2
    assert "already contains a duplicate" in result.detail


# =====================================================================
# The normalizer is part of the basis
# =====================================================================

def test_the_canonical_duplicate_scores_exactly_what_the_floor_was_set_against():
    """The measurement the floor is derived from, pinned. `123 Industrial
    Dr, Mississauga ON` and `123 Industrial Drive Unit 4, Mississauga ON`
    are the same warehouse and score 0.50 under the conservative
    normalizer -- `dr`/`drive` differ and `unit`/`4` are extra.

    A 0.6 floor (the first value tried here) misses it entirely and the
    register silently grows a duplicate. That is why the floor is a
    function of the normalizer rather than a constant, and why the
    conservative floor sits BELOW this number."""
    a = conservative_normalize("123 Industrial Dr, Mississauga ON")
    b = conservative_normalize("123 Industrial Drive Unit 4, Mississauga ON")
    assert abs(_similarity(a, b) - CANONICAL_DUPLICATE_SIMILARITY) < 0.01
    assert NEAR_MATCH_FLOOR[CONSERVATIVE] < CANONICAL_DUPLICATE_SIMILARITY, (
        "the conservative floor must sit below the canonical true duplicate, or the register "
        "silently accumulates the exact duplicates this module exists to prevent"
    )


def test_the_floor_rises_when_a_statistical_parser_is_installed():
    """A weaker normalizer needs a lower floor and produces more
    candidates. That trade is deliberate: a false candidate costs one
    glance, a missed one costs a lane statistic split forever."""
    assert NEAR_MATCH_FLOOR[STATISTICAL] > NEAR_MATCH_FLOOR[CONSERVATIVE]


def test_every_resolution_records_which_normalizer_made_it():
    result = resolve("123 INDUSTRIAL DR, MISSISSAUGA ON", _register())
    assert result.normalizer in (CONSERVATIVE, STATISTICAL)


def test_the_conservative_normalizer_does_not_guess_at_abbreviations():
    """`Dr` is Drive on a street line and Doctor in a name. A lookup table
    that guesses produces confident wrong merges — worse than the
    duplicates it set out to fix."""
    assert conservative_normalize("123 Industrial Dr") != conservative_normalize(
        "123 Industrial Drive")
    assert conservative_normalize("123 Industrial Dr") == conservative_normalize(
        "  123   INDUSTRIAL   dr.  ")


def test_the_register_health_states_what_the_normalizer_cannot_do():
    """Reporting a clean register under a weak normalizer is the
    confident-green problem."""
    health = register_health(_register())
    assert health.caveat
    if health.normalizer == CONSERVATIVE:
        assert "duplicate rate is unknown and is not zero" in health.caveat
        assert "123 Industrial Drive" in health.caveat


def test_a_facility_cannot_be_stored_without_its_raw_string():
    with pytest.raises(FacilityRefusal):
        Facility("f-9", "   ", "123 industrial dr", CONSERVATIVE)


def test_the_missing_statistical_parser_is_a_recorded_state_not_an_import_error():
    """The absence must be visible. A system that silently falls back and
    says nothing has defeated the point of recording the normalizer."""
    name, _ = available_normalizer()
    assert name in (CONSERVATIVE, STATISTICAL)
    health = register_health([])
    assert health.normalizer == name
