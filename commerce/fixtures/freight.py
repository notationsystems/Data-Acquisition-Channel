"""A representative freight fixture — every row fabricated, every result
inadmissible by construction.

WHY THIS IS NOT A WORKAROUND. Copper ran for twenty-odd rounds on a
representative fixture with every result correctly marked inadmissible,
and the gate flipped the day a real source landed. Freight is the same
shape. A fixture does not license a claim about the world; it licenses
work on the machinery, and the admissibility machinery is what keeps the
two apart.

EVERY ROW DECLARES ITSELF. `PROVENANCE` is carried on every event and
observation this module emits, and a test asserts nothing from here can
reach a store without it. The convention is the one this account already
uses for the GPC fixture and the CanadaBuys worked example.

THE FIXTURE IS A SET OF PLANTED DEFECTS, NOT A SET OF ROWS. Each signal
below is something the machinery is supposed to catch, and the tests
assert it does. A fixture that merely filled tables would prove the tables
fill.

    1  repeated lanes with seasonal detention     -> lane residual model
    2  one carrier, persistent quote/invoice gap  -> divergence by carrier
    3  one receiver, chronic appointment slippage -> receiver reliability
    4  two facilities, same place, two addresses  -> resolution gate
    5  one carrier whose insurance lapses         -> validWhile predicate
       mid-window
    6  one double-brokering signature             -> tendered vs bill of
                                                     lading divergence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

from commerce.events import (PICKUP_ACTUAL, PICKUP_PROMISED, RATE_INVOICED, RATE_QUOTED,
                             TRANSIT_ESTIMATED, TRANSIT_REALIZED, LoadEvent, Source)

#: Stamped inside the content, not alongside it. A fixture whose label
#: lives in a filename is a fixture that loses its label on the first copy.
PROVENANCE = "fabricated_fixture"

#: What this fixture may and may not be used for, in its own words.
ADMISSIBILITY = (
    "INADMISSIBLE. Every row here is fabricated. It licenses work on the machinery and licenses "
    "NO claim about any carrier, lane, receiver or rate. A number computed from this fixture that "
    "reaches a report is the defect this label exists to prevent."
)

#: Carriers. One is clean, one over-invoices, one loses its insurance
#: mid-window, one appears on a bill of lading it was never tendered.
CARRIERS: Mapping[str, str] = {
    "carrier-clean": "Northbound Freight Ltd",
    "carrier-overbills": "Sunset Logistics Inc",
    "carrier-lapses": "Meridian Cartage Co",
    "carrier-unexpected": "Third Party Haulage Ltd",
}

#: PLANT 4 — the same warehouse under two addresses. Resolution must
#: surface these as candidates and must NOT merge them silently.
FACILITIES: Mapping[str, str] = {
    "fac-a": "123 Industrial Dr, Mississauga ON",
    "fac-a-dup": "123 INDUSTRIAL DRIVE UNIT 4, Mississauga, ON",
    "fac-b": "700 Rue Notre-Dame, Lachine QC",
    "fac-c": "45 Airport Rd, Windsor ON",
}

#: PLANT 3 — this receiver slips its appointment on most loads.
SLIPPING_RECEIVER = "fac-b"

LANES: Tuple[Tuple[str, str], ...] = (
    ("fac-a", "fac-b"),   # the repeated lane, run across seasons
    ("fac-a", "fac-c"),
)


def _source(known_at: str, method: str = "phone") -> Source:
    return Source(source_id=f"{PROVENANCE}:{method}", source_class="asserted",
                  method=method, known_at=known_at, recorded_by="op-fixture",
                  artifact=PROVENANCE, rung="manual")


@dataclass(frozen=True)
class FixtureLoad:
    """One fabricated load and the carrier that actually moved it."""

    load: str
    origin: str
    destination: str
    month: int
    tendered_to: str
    bill_of_lading_carrier: str
    events: Tuple[LoadEvent, ...]


def _load(load: str, origin: str, destination: str, *, month: int, carrier: str,
          quoted: float, invoiced: float, transit_est: float, transit_real: float,
          pickup_promised: int, pickup_actual: int,
          bill_of_lading: str = "") -> FixtureLoad:
    day = f"2026-{month:02d}-05"
    settle = f"2026-{month:02d}-20"
    events = (
        LoadEvent(load, RATE_QUOTED, quoted, "CAD", _source(day)),
        LoadEvent(load, RATE_INVOICED, invoiced, "CAD", _source(settle, "document")),
        LoadEvent(load, TRANSIT_ESTIMATED, transit_est, "days", _source(day)),
        LoadEvent(load, TRANSIT_REALIZED, transit_real, "days", _source(settle, "observed")),
        LoadEvent(load, PICKUP_PROMISED, float(pickup_promised), "epoch_day", _source(day)),
        LoadEvent(load, PICKUP_ACTUAL, float(pickup_actual), "epoch_day",
                  _source(settle, "observed")),
    )
    return FixtureLoad(load, origin, destination, month, carrier,
                       bill_of_lading or carrier, events)


def loads() -> Tuple[FixtureLoad, ...]:
    """Twenty-four fabricated loads carrying six planted signals."""
    out: List[FixtureLoad] = []
    a, b = LANES[0]
    a2, c = LANES[1]

    # PLANT 1 — the repeated lane, with detention concentrated in winter.
    # Transit runs one day long in months 12, 1 and 2 and on time otherwise,
    # so a model keyed on the lane ALONE sees a quarter-day that describes
    # neither mode, and a model keyed on lane-and-season sees both.
    #
    # THE MONTH LIST WAS WIDENED AFTER THE FIRST RUN. It was originally one
    # load per month across eight months, which put three loads in winter --
    # BELOW the min-trials floor the residual model correctly enforces. The
    # analytics refused to estimate, which was right, and the plant could
    # not fire, which made it prove nothing. A repeated lane runs more than
    # one load a month, so the fixture now does too.
    for index, month in enumerate((1, 1, 2, 2, 12, 12, 3, 4, 5, 6, 7, 8, 9, 10, 11)):
        winter = month in (1, 2, 12)
        out.append(_load(
            f"L-A{index:02d}", a, b, month=month, carrier="carrier-clean",
            quoted=2400.0, invoiced=2400.0,
            transit_est=3.0, transit_real=4.0 if winter else 3.0,
            # PLANT 3 — this receiver slips its appointment on most loads.
            pickup_promised=100 + index, pickup_actual=100 + index + (1 if index % 4 else 0)))

    # PLANT 2 — one carrier invoices consistently above its quote. The gap
    # is small per load and unmistakable across eight.
    for index, month in enumerate((1, 3, 4, 6, 8, 9, 10, 11)):
        out.append(_load(
            f"L-B{index:02d}", a2, c, month=month, carrier="carrier-overbills",
            quoted=1800.0, invoiced=1800.0 + 120.0 + index * 5,
            transit_est=2.0, transit_real=2.0,
            pickup_promised=200 + index, pickup_actual=200 + index))

    # A clean comparison set on the same lane, so plant 2 is attributable
    # to the CARRIER rather than to the lane.
    for index, month in enumerate((2, 5, 7, 10)):
        out.append(_load(
            f"L-C{index:02d}", a2, c, month=month, carrier="carrier-clean",
            quoted=1800.0, invoiced=1800.0, transit_est=2.0, transit_real=2.0,
            pickup_promised=300 + index, pickup_actual=300 + index))

    # PLANT 5 — a carrier whose insurance lapses BETWEEN PICKUP AND
    # DELIVERY (see insurance_window below), still tendered loads across
    # it. A check run at booking passes; the truck arrives uninsured.
    for index, month in enumerate((6, 7, 8)):
        out.append(_load(
            f"L-D{index:02d}", a, c, month=month, carrier="carrier-lapses",
            quoted=2100.0, invoiced=2100.0, transit_est=2.0, transit_real=2.0,
            pickup_promised=400 + index, pickup_actual=400 + index))

    # PLANT 7 — a LIVE load: quoted and promised, not yet invoiced. It is
    # not a residual of zero, it is not a residual at all, and counting it
    # as zero pulls every mean toward nothing.
    #
    # ADDED AFTER A PLANT WENT UNCAUGHT. `_paired` requires both halves and
    # that requirement had no discriminating case, because every other load
    # here settles. Disabling the requirement left the suite green — a real
    # guard with a fixture too clean to test it.
    day = "2026-09-05"
    out.append(FixtureLoad(
        "L-F00", a, b, 9, "carrier-clean", "carrier-clean",
        (LoadEvent("L-F00", RATE_QUOTED, 9999.0, "CAD", _source(day)),
         LoadEvent("L-F00", TRANSIT_ESTIMATED, 9.0, "days", _source(day)),
         LoadEvent("L-F00", PICKUP_PROMISED, 600.0, "epoch_day", _source(day)))))

    # PLANT 6 — one load tendered to one carrier and moved by another.
    out.append(_load(
        "L-E00", a, b, month=4, carrier="carrier-clean",
        quoted=2400.0, invoiced=2400.0, transit_est=3.0, transit_real=3.0,
        pickup_promised=500, pickup_actual=500,
        bill_of_lading="carrier-unexpected"))
    return tuple(out)


def events() -> Tuple[LoadEvent, ...]:
    return tuple(event for load in loads() for event in load.events)


def insurance_window() -> Mapping[str, Tuple[str, str]]:
    """PLANT 5, stated: the coverage period each carrier actually holds.

    `carrier-lapses` is covered to 2026-08-06 and was tendered a load
    booked 2026-08-05, picking up 2026-08-06 and delivering 2026-08-07.
    Coverage therefore survives the booking AND the pickup and expires
    before delivery — which is the case that matters and the one a
    point-in-time check at booking passes.

    THE DATE WAS MOVED AFTER THE FIRST RUN. It was originally 2026-07-15,
    three weeks before the booking, which made the predicate return
    COVERAGE_LAPSED_BEFORE_BOOKING — a real refusal and the EASY one. A
    plant that fires on the easy branch does not exercise the hard one,
    and the hard one is the whole reason `covers()` takes a period.
    """
    return {
        "carrier-clean": ("2026-01-01", "2026-12-31"),
        "carrier-overbills": ("2026-01-01", "2026-12-31"),
        "carrier-lapses": ("2026-01-01", "2026-08-06"),
        "carrier-unexpected": ("2026-01-01", "2026-12-31"),
    }


def label() -> Mapping[str, str]:
    """The fixture's own declaration, for a test to assert."""
    return {"provenance": PROVENANCE, "admissibility": ADMISSIBILITY,
            "what_this_is_not": "no carrier, lane, receiver or rate here corresponds to a real "
                                "one. No researcher, operator or counterparty supplied any of it."}
