"""Generate the representative freight fixture: deterministic, at scale,
inadmissible by construction.

    python3 tools/make_fixture.py --out /tmp/payload

Writes `book.jsonl` and `register.jsonl` in the same format the operator
CLI reads, so every command in `python3 -m commerce` runs over it
unchanged. That is the point: the fixture exercises the SHIPPING code
path, not a parallel one.

DETERMINISTIC. Seeded PRNG, no clock, no randomness that varies between
runs. A fixture that differs run to run cannot support a regression pin,
and a residual that moves when nothing changed is indistinguishable from
one that moved because something did.

INADMISSIBLE BY CONSTRUCTION. Every event's source carries
`representative_fixture`, and `commerce.admissibility` refuses to mark any
result derived from it admissible. When a real load arrives the same code
runs and the flag flips for that record only.

THE SIX PLANTED SIGNALS SURVIVE AT SCALE. They are placed on named
carriers, lanes and facilities rather than sprinkled, so a test can assert
each is found and the surrounding four hundred loads are the noise it has
to be found in.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List, Sequence, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "vendor"
                       / "scout-retrieval-agent"))

from commerce.events import (PICKUP_ACTUAL, PICKUP_PROMISED, RATE_INVOICED,  # noqa: E402
                             RATE_QUOTED, TRANSIT_ESTIMATED, TRANSIT_REALIZED, LoadEvent, Source)
from commerce.register import LoadRecord  # noqa: E402
from commerce.register import append as append_register  # noqa: E402
from commerce.ledger import append as append_ledger  # noqa: E402

PROVENANCE = "representative_fixture"
SEED = 20260831

N_CARRIERS = 40
N_SHIPPERS = 25
N_FACILITIES = 60
N_LANES = 120
N_LOADS = 400
MONTHS = 18

#: The planted signals, on named actors so a test can assert each.
PLANT_OVERBILLING_CARRIER = "carrier-07"
PLANT_LAPSING_CARRIER = "carrier-13"
PLANT_SLIPPING_RECEIVER = "fac-19"
PLANT_SEASONAL_LANE = ("fac-02", "fac-19")
PLANT_DOUBLE_BROKERED_LOAD = "L-0333"
PLANT_UNEXPECTED_CARRIER = "carrier-38"
PLANT_DUPLICATE_FACILITY = ("fac-04", "fac-04-dup")

FACILITY_ADDRESSES: Dict[str, str] = {}


class Rng:
    """A tiny deterministic PRNG. `random` is avoided so the stream cannot
    be perturbed by anything else importing it and reseeding."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF

    def next(self) -> int:
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return self.state

    def below(self, n: int) -> int:
        return self.next() % n

    def pick(self, items: Sequence):
        return items[self.below(len(items))]

    def chance(self, numerator: int, denominator: int) -> bool:
        return self.below(denominator) < numerator


def _facilities() -> Dict[str, str]:
    cities = ["Mississauga ON", "Brampton ON", "Vaughan ON", "Windsor ON", "London ON",
              "Lachine QC", "Laval QC", "Boucherville QC", "Detroit MI", "Buffalo NY"]
    streets = ["Industrial Dr", "Airport Rd", "Commerce Blvd", "Rue Notre-Dame",
               "Logistics Way", "Dixie Rd", "Steeles Ave", "Chemin Saint-Francois"]
    rng = Rng(SEED ^ 0xFAC)
    out: Dict[str, str] = {}
    for index in range(N_FACILITIES):
        number = 100 + rng.below(900)
        out[f"fac-{index:02d}"] = f"{number} {rng.pick(streets)}, {rng.pick(cities)}"
    # PLANT — the same warehouse under a second address.
    base = out[PLANT_DUPLICATE_FACILITY[0]]
    house, _, rest = base.partition(" ")
    street, _, city = rest.partition(", ")
    out[PLANT_DUPLICATE_FACILITY[1]] = f"{house} {street.upper()} UNIT 4, {city}"
    return out


def _source(known_at: str, method: str) -> Source:
    return Source(source_id=f"{PROVENANCE}:{method}", source_class="asserted", method=method,
                  known_at=known_at, recorded_by="op-fixture", artifact=PROVENANCE,
                  rung="manual")


def _date(month_index: int, day: int) -> str:
    year = 2025 + (month_index + 6) // 12
    month = ((month_index + 6) % 12) + 1
    return f"{year}-{month:02d}-{min(day, 28):02d}"


def generate() -> Tuple[List[LoadEvent], List[LoadRecord]]:
    rng = Rng(SEED)
    facilities = _facilities()
    FACILITY_ADDRESSES.update(facilities)
    facility_ids = [f for f in facilities if not f.endswith("-dup")]
    carriers = [f"carrier-{i:02d}" for i in range(N_CARRIERS)]
    shippers = [f"shipper-{i:02d}" for i in range(N_SHIPPERS)]

    lanes: List[Tuple[str, str]] = [PLANT_SEASONAL_LANE]
    while len(lanes) < N_LANES:
        origin, destination = rng.pick(facility_ids), rng.pick(facility_ids)
        if origin != destination and (origin, destination) not in lanes:
            lanes.append((origin, destination))

    events: List[LoadEvent] = []
    records: List[LoadRecord] = []

    for index in range(N_LOADS):
        load = f"L-{index:04d}"
        # The planted lane gets a third of the book so its seasons clear
        # the min-trials floor; everything else is spread.
        lane = PLANT_SEASONAL_LANE if index % 3 == 0 else rng.pick(lanes)
        origin, destination = lane
        month_index = rng.below(MONTHS)
        calendar_month = ((month_index + 6) % 12) + 1
        winter = calendar_month in (12, 1, 2)

        carrier = rng.pick(carriers)
        if index % 17 == 0:
            carrier = PLANT_OVERBILLING_CARRIER          # PLANT: over-invoicing
        if index % 53 == 0:
            carrier = PLANT_LAPSING_CARRIER              # PLANT: insurance lapse
        bol = carrier
        if load == PLANT_DOUBLE_BROKERED_LOAD:
            bol = PLANT_UNEXPECTED_CARRIER               # PLANT: double-brokering

        quoted = 1400.0 + rng.below(1800)
        # PLANT: one carrier invoices consistently above its quote.
        invoiced = quoted + (110.0 + rng.below(40)) if carrier == PLANT_OVERBILLING_CARRIER \
            else quoted
        transit_est = 2.0 + rng.below(3)
        # PLANT: the named lane runs long in winter only.
        transit_real = transit_est + (1.0 if (lane == PLANT_SEASONAL_LANE and winter) else 0.0)
        promised_day = 1000 + index
        # PLANT: one receiver slips its appointment on most loads.
        slips = destination == PLANT_SLIPPING_RECEIVER and rng.chance(3, 4)
        actual_day = promised_day + (1 if slips else 0)

        quoted_at = _date(month_index, 5)
        settled_at = _date(month_index, 24)
        live = rng.chance(1, 12)   # some loads are still open, as a real book is

        events.append(LoadEvent(load, RATE_QUOTED, quoted, "CAD", _source(quoted_at, "phone")))
        events.append(LoadEvent(load, TRANSIT_ESTIMATED, transit_est, "days",
                                _source(quoted_at, "phone")))
        events.append(LoadEvent(load, PICKUP_PROMISED, float(promised_day), "epoch_day",
                                _source(quoted_at, "phone")))
        if not live:
            events.append(LoadEvent(load, RATE_INVOICED, invoiced, "CAD",
                                    _source(settled_at, "document")))
            events.append(LoadEvent(load, TRANSIT_REALIZED, transit_real, "days",
                                    _source(settled_at, "observed")))
            events.append(LoadEvent(load, PICKUP_ACTUAL, float(actual_day), "epoch_day",
                                    _source(settled_at, "observed")))

        records.append(LoadRecord(load=load, carrier=carrier, origin=origin,
                                  destination=destination, month=calendar_month,
                                  bill_of_lading_carrier=bol, recorded_at=quoted_at))
    return events, records


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="directory for book.jsonl and register.jsonl")
    args = parser.parse_args(list(argv))
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    book, register = out / "book.jsonl", out / "register.jsonl"
    for path in (book, register):
        if path.exists():
            path.unlink()

    events, records = generate()
    append_ledger(events, path=book)
    append_register(records, path=register)
    (out / "facilities.json").write_text(json.dumps(FACILITY_ADDRESSES, indent=2, sort_keys=True))

    settled = sum(1 for e in events if e.kind == RATE_INVOICED)
    print(f"wrote {len(events)} events over {len(records)} loads to {book}")
    print(f"  {len(records) - settled} load(s) still open, {settled} settled")
    print(f"  {len(FACILITY_ADDRESSES)} facilities, {N_CARRIERS} carriers, {N_LANES} lanes, "
          f"{MONTHS} months")
    print(f"  every event stamped {PROVENANCE!r}")
    print(f"  plants: overbilling={PLANT_OVERBILLING_CARRIER} lapsing={PLANT_LAPSING_CARRIER} "
          f"slipping={PLANT_SLIPPING_RECEIVER}")
    print(f"          seasonal={PLANT_SEASONAL_LANE} dup={PLANT_DUPLICATE_FACILITY} "
          f"double-brokered={PLANT_DOUBLE_BROKERED_LOAD}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
