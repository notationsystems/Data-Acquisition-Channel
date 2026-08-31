"""The load register — what a load IS, as distinct from what happened to it.

A load's carrier, origin, destination and month are not events. They do
not settle, they carry no promise, and forcing them into the event
vocabulary would open a closed set that exists precisely so two adapters
cannot disagree about what an event is.

So they live here, in their own append-only file, keyed by load. The event
ledger says what was promised and what happened; the register says which
lane and which carrier it happened on. Residuals need both, and neither
can be derived from the other.

DERIVING A CARRIER FROM A LOAD ID IS THE DEFECT THIS REPLACES. The first
version of `residuals` grouped by `load.split("-")[0]`, which produced
plausible groups from a naming convention and would have reported lane
memory computed over prefixes. It looked right on the fixture, which is
what made it dangerous.

APPEND-ONLY, SAME AS THE BOOK. A load reassigned to a different carrier is
a later entry, not an edit — because "who moved it" is exactly the field a
double-brokering check compares, and a register that allowed the edit
would let the answer be corrected into agreement.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

DEFAULT_PATH = pathlib.Path(os.environ.get(
    "COMMERCE_REGISTER",
    str(pathlib.Path(os.environ.get("COMMERCE_LEDGER", "commerce-ledger.jsonl")).parent
        / "commerce-register.jsonl")))

REGISTER_LINE_IS_NOT_JSON = "REGISTER_LINE_IS_NOT_JSON"
REGISTER_ENTRY_NAMES_NO_LOAD = "REGISTER_ENTRY_NAMES_NO_LOAD"
REGISTER_EMPTY_BECAUSE_IT_DOES_NOT_EXIST = "REGISTER_EMPTY_BECAUSE_IT_DOES_NOT_EXIST"
REGISTER_EMPTY_BECAUSE_NOTHING_WAS_REGISTERED = "REGISTER_EMPTY_BECAUSE_NOTHING_WAS_REGISTERED"

FIELDS: Tuple[str, ...] = ("carrier", "origin", "destination", "month",
                           "bill_of_lading_carrier", "recorded_at")


@dataclass(frozen=True)
class LoadRecord:
    load: str
    carrier: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    month: Optional[int] = None
    bill_of_lading_carrier: Optional[str] = None
    recorded_at: Optional[str] = None

    @property
    def lane(self) -> Optional[Tuple[str, str]]:
        if self.origin and self.destination:
            return (self.origin, self.destination)
        return None

    @property
    def double_brokered(self) -> Optional[bool]:
        """None when no bill of lading has been captured.

        Not False. A missing bill of lading is one claim about the
        movement, not agreement between two, and returning False would
        report every uncaptured load as clean.
        """
        if not self.bill_of_lading_carrier or not self.carrier:
            return None
        return self.bill_of_lading_carrier != self.carrier


@dataclass(frozen=True)
class RegisterRead:
    records: Mapping[str, LoadRecord]
    bad: Tuple[Tuple[int, str], ...]
    lines: int
    path: str
    empty_because: Optional[str] = None

    @property
    def carrier_of(self) -> Dict[str, str]:
        return {load: r.carrier for load, r in self.records.items() if r.carrier}

    @property
    def lane_of(self) -> Dict[str, Tuple[str, str]]:
        return {load: r.lane for load, r in self.records.items() if r.lane}

    @property
    def month_of(self) -> Dict[str, int]:
        return {load: r.month for load, r in self.records.items() if r.month is not None}

    @property
    def receiver_of(self) -> Dict[str, str]:
        return {load: r.destination for load, r in self.records.items() if r.destination}


def append(records: Sequence[LoadRecord], *, path: pathlib.Path = DEFAULT_PATH) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps({
                "load": record.load, "carrier": record.carrier, "origin": record.origin,
                "destination": record.destination, "month": record.month,
                "bill_of_lading_carrier": record.bill_of_lading_carrier,
                "recorded_at": record.recorded_at,
            }, sort_keys=True) + "\n")
    return len(records)


def read(*, path: pathlib.Path = DEFAULT_PATH) -> RegisterRead:
    """Replay the register. A later entry for a load supersedes an earlier
    one; both stay on disk and the last one wins on read."""
    if not path.exists():
        return RegisterRead({}, (), 0, str(path), empty_because=(
            f"{REGISTER_EMPTY_BECAUSE_IT_DOES_NOT_EXIST}: no register at {path}. No load has "
            "been given a carrier or a lane, so residuals cannot be grouped — which is not the "
            "same as a book with no loads in it."))
    records: Dict[str, LoadRecord] = {}
    bad: List[Tuple[int, str]] = []
    lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            lines += 1
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                bad.append((number, f"{REGISTER_LINE_IS_NOT_JSON}: {exc.msg}"))
                continue
            load = payload.get("load") if isinstance(payload, dict) else None
            if not load:
                bad.append((number, REGISTER_ENTRY_NAMES_NO_LOAD))
                continue
            month = payload.get("month")
            records[str(load)] = LoadRecord(
                load=str(load), carrier=payload.get("carrier"),
                origin=payload.get("origin"), destination=payload.get("destination"),
                month=int(month) if month not in (None, "") else None,
                bill_of_lading_carrier=payload.get("bill_of_lading_carrier"),
                recorded_at=payload.get("recorded_at"))
    empty_because = None
    if not records:
        empty_because = (f"{REGISTER_EMPTY_BECAUSE_NOTHING_WAS_REGISTERED}: {lines} line(s) "
                         "present and no load registered.")
    return RegisterRead(records, tuple(bad), lines, str(path), empty_because)


def from_sheet_rows(rows: Sequence[Mapping[str, str]]) -> Tuple[LoadRecord, ...]:
    """Pull load attributes out of sheet rows that carry them.

    A row with none of these columns registers nothing rather than
    registering a load with every attribute None, which would look like a
    load someone had described.
    """
    out: Dict[str, LoadRecord] = {}
    for row in rows:
        load = (row.get("load") or "").strip()
        if not load:
            continue
        stated = {f: (row.get(f) or "").strip() for f in FIELDS}
        if not any(stated.values()):
            continue
        month = stated["month"]
        out[load] = LoadRecord(
            load=load,
            carrier=stated["carrier"] or None,
            origin=stated["origin"] or None,
            destination=stated["destination"] or None,
            month=int(month) if month.isdigit() else None,
            bill_of_lading_carrier=stated["bill_of_lading_carrier"] or None,
            recorded_at=stated["recorded_at"] or None)
    return tuple(out.values())


def render(result: RegisterRead) -> str:
    lines = [f"REGISTER {result.path} — {result.lines} line(s); "
             f"{len(result.records)} load(s) described"]
    if result.empty_because:
        lines.append(f"  (nothing registered) {result.empty_because}")
    for number, detail in result.bad:
        lines.append(f"  LINE {number}: {detail}")
    unknown = [r.load for r in result.records.values() if r.double_brokered is None]
    if unknown:
        lines.append(f"  {len(unknown)} load(s) with no bill of lading captured — "
                     "one claim about the movement, not agreement between two")
    diverging = [r.load for r in result.records.values() if r.double_brokered]
    if diverging:
        lines.append(f"  ! {len(diverging)} load(s) moved by a carrier they were not tendered "
                     f"to: {diverging}")
    return "\n".join(lines)
