"""The sheet as an intake surface, never as the system of record.

A spreadsheet is the correct store for the first twenty loads. Building a
database before there is a load is the error this programme has already
paid for once, and a sheet costs nothing and migrates nothing on day three.

THE DISTINCTION THAT DOES THE WORK. Type into the sheet; the adapter reads
it and writes canonical events; commitments and outcomes land in separate
stores rather than adjacent columns. Without that, a year of this produces
a spreadsheet and an inbox. With it, the same year produces a lane model.

NOTHING DOWNSTREAM READS THE SHEET. A number computed from canonical state
is never written back into it, because a sheet that is both the input and
the report becomes the record by accident -- and then the residual history
is whatever someone last typed over. `refuse_computed_column` below is the
structural half of that rule: a sheet carrying a column this system
computes is refused at read time rather than silently trusted.

WHY THIS IS A SEPARATE MODULE FROM `manual`. The sheet is a TRANSPORT.
`commerce.manual` owns what a valid event is, and this module owns only
turning rows into the entries that module already grades. Putting the
validation here would be a second copy of the rules, which is the
duplicate-vocabulary problem in a new place.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from commerce.events import EVENT_KINDS, EventRefusal, LoadEvent
from commerce.manual import from_entry

SHEET_IS_NOT_A_SHEET = "SHEET_IS_NOT_A_SHEET"
SHEET_LACKS_A_REQUIRED_COLUMN = "SHEET_LACKS_A_REQUIRED_COLUMN"
SHEET_CARRIES_A_COMPUTED_COLUMN = "SHEET_CARRIES_A_COMPUTED_COLUMN"
ROW_REFUSED = "ROW_REFUSED"

#: Columns this system COMPUTES. Their presence in an intake sheet means
#: something downstream has been written back, and the sheet has started
#: becoming the record.
COMPUTED_COLUMNS: FrozenSet[str] = frozenset({
    "residual", "contribution", "realized_contribution", "margin", "variance",
    "days_outstanding", "sustainable_loads", "landed_cost", "total",
})

REQUIRED_COLUMNS: Tuple[str, ...] = ("load", "kind", "value", "unit", "known_at",
                                     "method", "recorded_by")
OPTIONAL_COLUMNS: Tuple[str, ...] = ("recorded_at", "artifact", "period_start", "period_end",
                                     "supersedes")
#: Columns describing what a load IS rather than what happened to it.
#: They are not events -- they do not settle and carry no promise -- so
#: they are split off here and land in the load register instead.
REGISTER_COLUMNS: Tuple[str, ...] = ("carrier", "origin", "destination", "month",
                                     "bill_of_lading_carrier")


@dataclass(frozen=True)
class RowRefusal:
    row: int
    load: str
    code: str
    detail: str


@dataclass(frozen=True)
class SheetRead:
    """Every row accepted or refused with a reason. The two conserve."""

    events: Tuple[LoadEvent, ...]
    refused: Tuple[RowRefusal, ...]
    rows_in_sheet: int
    empty_because: Optional[str] = None
    #: The raw rows, so load attributes can be registered without this
    #: module needing to know what a register is.
    rows: Tuple[Mapping[str, str], ...] = ()

    @property
    def accounted(self) -> int:
        return len(self.events) + len(self.refused)

    @property
    def conserves(self) -> bool:
        return self.accounted == self.rows_in_sheet


def read_sheet(raw: str) -> SheetRead:
    """Read a sheet export into canonical events.

    A refused row does NOT stop the read. An operator who typed twenty
    loads and made one mistake needs the other nineteen and a named
    reason for the twentieth, not a stack trace and nothing.
    """
    try:
        reader = csv.DictReader(io.StringIO(raw))
        fieldnames = reader.fieldnames
    except csv.Error as exc:  # pragma: no cover - defensive
        raise EventRefusal(SHEET_IS_NOT_A_SHEET, str(exc)) from None
    if not fieldnames:
        raise EventRefusal(
            SHEET_IS_NOT_A_SHEET,
            "the export has no header row. An unreadable sheet and an empty one are different "
            "states and this reader will not return the second for the first.")

    header = {name.strip().lstrip("﻿") for name in fieldnames}
    computed = sorted(header & COMPUTED_COLUMNS)
    if computed:
        raise EventRefusal(
            SHEET_CARRIES_A_COMPUTED_COLUMN,
            f"the sheet carries {computed}, which this system computes. Their presence means a "
            "number has been written back into the intake surface, and a sheet that is both the "
            "input and the report becomes the record by accident — after which the residual "
            "history is whatever someone last typed over. Remove the column; read the value from "
            "canonical state instead.")
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise EventRefusal(
            SHEET_LACKS_A_REQUIRED_COLUMN,
            f"the sheet has no {missing} column(s). Known columns: "
            f"{sorted(set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS) | set(REGISTER_COLUMNS))}.")

    rows = list(reader)
    events: List[LoadEvent] = []
    refused: List[RowRefusal] = []
    raw_rows: List[Mapping[str, str]] = []
    for position, row in enumerate(rows, start=2):  # row 1 is the header, as the operator sees it
        cleaned = {(k or "").strip().lstrip("﻿"): (v or "").strip()
                   for k, v in row.items() if k}
        entry = {k: v for k, v in cleaned.items() if v != ""}
        if not entry:
            continue  # a blank spacer row is not a row
        raw_rows.append(cleaned)
        entry = {k: v for k, v in entry.items() if k not in REGISTER_COLUMNS}
        try:
            entry["value"] = float(entry["value"])
        except (KeyError, ValueError):
            refused.append(RowRefusal(position, cleaned.get("load", ""), ROW_REFUSED,
                                      f"`value` is {cleaned.get('value','')!r}, which is not a "
                                      "number. Nothing is coerced here."))
            continue
        try:
            events.append(from_entry(entry))
        except EventRefusal as exc:
            refused.append(RowRefusal(position, cleaned.get("load", ""), exc.code, exc.detail))

    counted = sum(1 for row in rows
                  if any((v or "").strip() for k, v in row.items() if k))
    empty_because = None
    if not events:
        if not counted:
            empty_because = ("SHEET_HAS_NO_ROWS: the export parsed and carries only a header. "
                             "That is a sheet nobody has typed into, not a day with no loads.")
        else:
            empty_because = (f"EVERY_ROW_WAS_REFUSED: {len(refused)} row(s) were typed and none "
                             "could be read. The sheet is being used and this reader cannot read "
                             "it, which is a different problem from an empty one.")
    return SheetRead(tuple(events), tuple(refused), counted, empty_because, tuple(raw_rows))


def blank_sheet() -> str:
    """The header an operator pastes into a new sheet.

    Ships with the columns and nothing else. A template with an example
    row in it becomes the example, and the first real load gets typed
    underneath a fiction that then reaches the record.
    """
    return ",".join(REQUIRED_COLUMNS + OPTIONAL_COLUMNS + REGISTER_COLUMNS) + "\n"


def render(read: SheetRead) -> str:
    lines = [f"SHEET — {read.rows_in_sheet} row(s); read {len(read.events)}, "
             f"refused {len(read.refused)}"]
    if not read.conserves:
        lines.append(f"  ! ACCOUNTING DOES NOT CONSERVE: {read.accounted}")
    if read.empty_because:
        lines.append(f"  (nothing read) {read.empty_because}")
    for refusal in read.refused:
        lines.append(f"  ROW {refusal.row} ({refusal.load or 'no load'}): {refusal.code}")
        lines.append(f"      {refusal.detail}")
    return "\n".join(lines)
