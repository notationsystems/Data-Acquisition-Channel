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

THE PLANTED SIGNALS SURVIVE AT SCALE. They are placed on named
carriers, lanes and facilities rather than sprinkled, so a test can assert
each is found and the surrounding four hundred loads are the noise it has
to be found in.

THE VETTING STORE IS PART OF THE FIXTURE. `vetting.jsonl` carries the
observations the verdicts replay from: the lapsing carrier's certificate
with its real window, a carrier whose only word for its coverage is its
own, and grant dates served from the bulk rung that froze 2026-05-14 —
so `python3 -m commerce vet` over this fixture exercises all three
verdict states, and the exit codes 0/1/3 are all reachable from a shell.
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
from commerce.vetting import (AUTHORITY_GRANTED_AT, AUTHORITY_STATUS,  # noqa: E402
                              INSURANCE_COVERAGE, REPORTED, RUNG_BULK_HISTORY,
                              RUNG_COMMITTED_SNAPSHOT, SELF_REPORTED,
                              VettingObservation, VettingProvenance)
from commerce.vetting_store import append as append_vetting  # noqa: E402

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
#: The lapsing carrier's certificate: real coverage, real end. The same
#: certificate clears a same-day load on the 5th and blocks a multi-day
#: movement delivering the 8th — the pair only a period-based check tells
#: apart.
PLANT_INSURANCE_WINDOW = ("2026-01-01", "2026-08-06")
#: A carrier whose only insurance evidence is its own certificate. A
#: cloned identity forwards a real document, so this is undetermined
#: however fresh the paper is.
PLANT_SELF_INSURED_CARRIER = "carrier-21"

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


def _prov(method: str, source_class: str, rung: int, retrieved_at: str) -> VettingProvenance:
    return VettingProvenance(source_id=f"{PROVENANCE}:{method}", source_class=source_class,
                             rung=rung, retrieved_at=retrieved_at, artifact_id=PROVENANCE)


def vetting_observations() -> List[VettingObservation]:
    """The vetting side of the same forty carriers.

    Two confirmation sweeps — late April and early August — because the
    predicates carry refresh intervals, and a store with one vintage can
    only be fresh at one asof. Grant dates come from the bulk rung, whose
    freeze (2026-05-14) means every post-freeze reincarnation check is
    honestly UNDETERMINED; that is the measured world, not a fixture
    artefact, and the fixture must not be cleaner than the world.

    Insurance is recorded for exactly two carriers. The other
    thirty-eight have NO insurance observation — representative, because
    certificates are gathered per-tender rather than held for the base —
    and their verdict is undetermined, which is the correct kind of
    nothing and not the same as insured.
    """
    out: List[VettingObservation] = []
    for index in range(N_CARRIERS):
        carrier = f"carrier-{index:02d}"
        # Authority: confirmed active in both sweeps, from a dated
        # regulator printout committed to the record.
        for sweep in ("2026-04-29", "2026-08-04"):
            out.append(VettingObservation(
                subject=carrier, kind=AUTHORITY_STATUS, value=True, unit=None,
                period_start=sweep, period_end=None, known_at=sweep,
                provenance=_prov("regulator-printout", REPORTED,
                                 RUNG_COMMITTED_SNAPSHOT, sweep)))
        # Grant date: deterministic, all comfortably older than the
        # 180-day floor, served from the rung that actually answers it.
        granted = f"{2014 + index % 7}-{(index % 12) + 1:02d}-{((index * 7) % 28) + 1:02d}"
        out.append(VettingObservation(
            subject=carrier, kind=AUTHORITY_GRANTED_AT, value=granted, unit=None,
            period_start=granted, period_end=None, known_at="2026-04-20",
            provenance=_prov("bulk-census", REPORTED, RUNG_BULK_HISTORY, "2026-04-20")))

    # PLANT: the lapsing carrier's certificate, confirmed with the insurer
    # twice. Both confirmations report the SAME window — the second is a
    # fresh confirmation, not a renewal.
    start, end = PLANT_INSURANCE_WINDOW
    for confirmed in ("2026-04-28", "2026-08-05"):
        out.append(VettingObservation(
            subject=PLANT_LAPSING_CARRIER, kind=INSURANCE_COVERAGE, value=2_000_000.0,
            unit="CAD", period_start=start, period_end=end, known_at=confirmed,
            provenance=_prov("insurer-call", REPORTED, RUNG_COMMITTED_SNAPSHOT, confirmed)))

    # PLANT: a certificate supplied only by the carrier itself.
    out.append(VettingObservation(
        subject=PLANT_SELF_INSURED_CARRIER, kind=INSURANCE_COVERAGE, value=2_000_000.0,
        unit="CAD", period_start="2026-01-01", period_end="2027-01-01",
        known_at="2026-08-04",
        provenance=_prov("carrier-emailed-certificate", SELF_REPORTED,
                         RUNG_COMMITTED_SNAPSHOT, "2026-08-04")))
    return out


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
    vetting = out / "vetting.jsonl"
    for path in (book, register, vetting):
        if path.exists():
            path.unlink()

    events, records = generate()
    append_ledger(events, path=book)
    append_register(records, path=register)
    observations = vetting_observations()
    append_vetting(observations, path=vetting)
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
    print(f"  {len(observations)} vetting observation(s) to {vetting}: certificate window "
          f"{PLANT_INSURANCE_WINDOW[0]}..{PLANT_INSURANCE_WINDOW[1]} on "
          f"{PLANT_LAPSING_CARRIER}, self-attested cover on {PLANT_SELF_INSURED_CARRIER}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
