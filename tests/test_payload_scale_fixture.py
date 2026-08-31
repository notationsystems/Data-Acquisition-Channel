"""The six plants, found in four hundred loads rather than thirty.

At small scale a plant is next to the assertion that checks it. At scale
it has to be FOUND — the over-invoicing carrier is one of forty, the
slipping receiver one of sixty, the double-brokered load one of four
hundred. That is what the noise is for.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

import tools.make_fixture as make  # noqa: E402
from commerce import residuals as R  # noqa: E402
from commerce.admissibility import derived_from  # noqa: E402
from commerce.facility import AMBIGUOUS, Facility, available_normalizer, resolve  # noqa: E402
from commerce.register import LoadRecord  # noqa: E402

EVENTS, RECORDS = make.generate()
CARRIER_OF = {r.load: r.carrier for r in RECORDS if r.carrier}
LANE_OF = {r.load: r.lane for r in RECORDS if r.lane}
MONTH_OF = {r.load: r.month for r in RECORDS if r.month is not None}
RECEIVER_OF = {r.load: r.destination for r in RECORDS if r.destination}


def test_the_generator_is_deterministic():
    """A fixture that differs run to run cannot support a regression pin."""
    again_events, again_records = make.generate()
    assert [e.canonical() for e in again_events] == [e.canonical() for e in EVENTS]
    assert again_records == tuple(RECORDS) or list(again_records) == list(RECORDS)


def test_everything_derived_from_it_is_inadmissible():
    assert not derived_from(EVENTS).admissible


def test_the_overbilling_carrier_is_the_unique_outlier_among_forty():
    result = R.by_carrier(EVENTS, CARRIER_OF)
    outliers = [r for r in result.estimated if r.mean is not None and abs(r.mean) > 50.0]
    assert [r.key for r in outliers] == [make.PLANT_OVERBILLING_CARRIER], (
        f"exactly one carrier should stand out; got {[r.key for r in outliers]}"
    )
    assert outliers[0].n >= R.MIN_TRIALS
    clean = [r for r in result.estimated if r.key != make.PLANT_OVERBILLING_CARRIER]
    assert clean and all(r.mean == 0.0 for r in clean), (
        "every other estimated carrier must be clean, or the plant is found by luck"
    )


def test_the_seasonal_lane_shows_two_modes_and_the_annual_figure_shows_neither():
    lane_key = f"{make.PLANT_SEASONAL_LANE[0]}->{make.PLANT_SEASONAL_LANE[1]}"
    seasonal = R.by_lane_season(EVENTS, LANE_OF, MONTH_OF)
    winter = seasonal.get(f"{lane_key}:winter")
    summer = seasonal.get(f"{lane_key}:non_winter")
    assert winter is not None and winter.estimated and winter.mean == 1.0
    assert summer is not None and summer.estimated and summer.mean == 0.0
    annual = R.by_lane(EVENTS, LANE_OF).get(lane_key)
    assert annual is not None and annual.mean is not None
    assert 0.0 < annual.mean < 1.0


def test_the_slipping_receiver_is_found_among_sixty_facilities():
    result = R.appointment_slippage(EVENTS, RECEIVER_OF)
    slipping = result.get(make.PLANT_SLIPPING_RECEIVER)
    assert slipping is not None and slipping.estimated
    assert slipping.mean is not None and slipping.mean > 0.5
    clean = [r for r in result.estimated
             if r.key != make.PLANT_SLIPPING_RECEIVER and r.mean == 0.0]
    assert len(clean) >= 5, "the signal must be found against clean receivers, not alone"


def test_the_duplicate_facility_resolves_ambiguous_never_merged():
    make.generate()  # populate the address table
    addresses = make.FACILITY_ADDRESSES
    original, duplicate = make.PLANT_DUPLICATE_FACILITY
    name, normalize = available_normalizer()
    register = [Facility(fid, addr, normalize(addr), name)
                for fid, addr in addresses.items() if fid != duplicate]
    result = resolve(addresses[duplicate], register)
    assert result.status == AMBIGUOUS
    assert result.facility is None
    assert original in [c.facility_id for c in result.candidates]


def test_the_double_brokered_load_is_the_only_divergence_in_four_hundred():
    """Last entry wins, exactly as the register read applies it: the
    quote-time entry carries no BOL and the settlement entry does."""
    latest = {r.load: r for r in RECORDS}
    diverging = [r.load for r in latest.values() if r.double_brokered]
    assert diverging == [make.PLANT_DOUBLE_BROKERED_LOAD]
    unknown = sorted(r.load for r in latest.values() if r.double_brokered is None)
    live = sorted({e.load for e in EVENTS if e.kind == R.RATE_QUOTED}
                  - {e.load for e in EVENTS if e.kind == R.RATE_INVOICED})
    assert unknown == live, (
        "exactly the open loads lack a bill of lading — it arrives with the proof of delivery, "
        "so a live load's BOL is honestly uncaptured and a settled load's is on file"
    )


def test_open_loads_are_excluded_from_residuals_not_counted_as_zero():
    """The book carries live loads, as a real one does. Each is a promise
    with no settlement and must not appear in any mean."""
    settled = {e.load for e in EVENTS if e.kind == R.SETTLES[R.RATE_QUOTED]}
    quoted = {e.load for e in EVENTS if e.kind == R.RATE_QUOTED}
    live = quoted - settled
    assert live, "the fixture must carry open loads or this test is vacuous"
    result = R.by_carrier(EVENTS, CARRIER_OF)
    total_in_groups = sum(r.n for r in result.residuals)
    assert total_in_groups == len(settled), (
        f"{total_in_groups} loads grouped but {len(settled)} settled — a live load leaked in"
    )
