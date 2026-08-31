"""The store — append-only, on disk, replayable.

Everything before this was a library: a load recorded in one invocation
was gone by the next. A system keeps what it was told.

APPEND-ONLY, AND NOT AS A STYLE CHOICE. A commitment is an act; an outcome
is a fact. Neither may be edited, because the whole asset is the gap
between what was promised and what happened, and a store that lets a row
be corrected in place lets that gap be closed by editing. A mistake is
superseded by a later entry that says what it supersedes, and both stay.

JSONL BECAUSE THERE IS NO DATABASE YET AND SHOULD NOT BE. One line per
event, in arrival order, replayable from the first byte. It costs no
migration on day three, it is readable with `tail`, and when the first
twenty loads justify a real store this file is the import.

THE FILE IS THE RECORD. `known_at` is what a query filters on, never line
order — a row appended on Friday about a Tuesday call is Tuesday's, and
the ledger keeps both so an as-known-then question can still be asked.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from commerce.events import EVENT_KINDS, EventRefusal, LoadEvent, Source

#: One ledger per firm. Overridable for tests and for a second book.
DEFAULT_PATH = pathlib.Path(os.environ.get("COMMERCE_LEDGER", "commerce-ledger.jsonl"))

LEDGER_LINE_IS_NOT_JSON = "LEDGER_LINE_IS_NOT_JSON"
LEDGER_LINE_LACKS_A_KIND = "LEDGER_LINE_LACKS_A_KIND"
LEDGER_ENTRY_WOULD_OVERWRITE = "LEDGER_ENTRY_WOULD_OVERWRITE"

#: Class 7 on a read.
LEDGER_EMPTY_BECAUSE_IT_DOES_NOT_EXIST = "LEDGER_EMPTY_BECAUSE_IT_DOES_NOT_EXIST"
LEDGER_EMPTY_BECAUSE_NOTHING_HAS_BEEN_RECORDED = "LEDGER_EMPTY_BECAUSE_NOTHING_HAS_BEEN_RECORDED"
LEDGER_EMPTY_BECAUSE_EVERY_LINE_WAS_UNREADABLE = "LEDGER_EMPTY_BECAUSE_EVERY_LINE_WAS_UNREADABLE"


@dataclass(frozen=True)
class BadLine:
    line: int
    code: str
    detail: str
    raw: str


@dataclass(frozen=True)
class LedgerRead:
    """Every line accepted or reported. The two conserve."""

    events: Tuple[LoadEvent, ...]
    bad: Tuple[BadLine, ...]
    lines: int
    path: str
    empty_because: Optional[str] = None

    @property
    def accounted(self) -> int:
        return len(self.events) + len(self.bad)

    @property
    def conserves(self) -> bool:
        return self.accounted == self.lines


def _to_line(event: LoadEvent) -> str:
    return json.dumps({
        "load": event.load, "kind": event.kind, "value": event.value, "unit": event.unit,
        "period_start": event.period_start, "period_end": event.period_end,
        "supersedes": event.supersedes,
        "source": {
            "source_id": event.source.source_id, "source_class": event.source.source_class,
            "method": event.source.method, "known_at": event.source.known_at,
            "recorded_by": event.source.recorded_by, "artifact": event.source.artifact,
            "rung": event.source.rung,
        },
    }, sort_keys=True)


def _from_line(payload: Mapping[str, Any]) -> LoadEvent:
    body = payload.get("source") or {}
    return LoadEvent(
        load=str(payload["load"]), kind=str(payload["kind"]),
        value=float(payload["value"]), unit=str(payload["unit"]),
        source=Source(source_id=str(body.get("source_id", "")),
                      source_class=str(body.get("source_class", "")),
                      method=str(body.get("method", "")),
                      known_at=str(body.get("known_at", "")),
                      recorded_by=body.get("recorded_by"),
                      artifact=body.get("artifact"),
                      rung=str(body.get("rung", "manual"))),
        period_start=payload.get("period_start"), period_end=payload.get("period_end"),
        supersedes=payload.get("supersedes"))


def append(events: Sequence[LoadEvent], *, path: pathlib.Path = DEFAULT_PATH) -> int:
    """Append events. Never rewrites, never truncates.

    Written through a temporary file and concatenated rather than opened
    in "w" mode anywhere in this module, so a bug that reaches for the
    wrong mode cannot silently empty the book.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(_to_line(event) + "\n")
    return len(events)


def read(*, path: pathlib.Path = DEFAULT_PATH) -> LedgerRead:
    """Replay the book from the first byte.

    An unreadable line does NOT stop the read. A book with one corrupt
    line and four hundred good ones must yield the four hundred and name
    the one, or a single bad write costs the whole history.
    """
    if not path.exists():
        return LedgerRead((), (), 0, str(path), empty_because=(
            f"{LEDGER_EMPTY_BECAUSE_IT_DOES_NOT_EXIST}: no ledger at {path}. Nothing has ever "
            "been recorded here, which is a different state from a book that was emptied."))
    events: List[LoadEvent] = []
    bad: List[BadLine] = []
    lines = 0
    with path.open("r", encoding="utf-8") as handle:
        for number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            lines += 1
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                bad.append(BadLine(number, LEDGER_LINE_IS_NOT_JSON, exc.msg, raw[:120]))
                continue
            if not isinstance(payload, dict) or payload.get("kind") not in EVENT_KINDS:
                bad.append(BadLine(number, LEDGER_LINE_LACKS_A_KIND,
                                   f"kind is {payload.get('kind') if isinstance(payload, dict) else '(not an object)'!r}",
                                   raw[:120]))
                continue
            try:
                events.append(_from_line(payload))
            except (KeyError, ValueError, EventRefusal) as exc:
                bad.append(BadLine(number, LEDGER_LINE_LACKS_A_KIND, str(exc), raw[:120]))

    empty_because = None
    if not events:
        if not lines:
            empty_because = (f"{LEDGER_EMPTY_BECAUSE_NOTHING_HAS_BEEN_RECORDED}: the ledger "
                             "exists and is empty. It was created and never written to.")
        else:
            empty_because = (f"{LEDGER_EMPTY_BECAUSE_EVERY_LINE_WAS_UNREADABLE}: {lines} line(s) "
                             "are present and none parsed. The book is being written and this "
                             "reader cannot read it.")
    return LedgerRead(tuple(events), tuple(bad), lines, str(path), empty_because)


def as_known_at(events: Sequence[LoadEvent], asof: str) -> Tuple[LoadEvent, ...]:
    """Only what was knowable by `asof`.

    Filters on `known_at`, never on line order. A row appended on Friday
    about a Tuesday call is Tuesday's, and a post-mortem that used arrival
    order would be retrospectively right about everything.
    """
    return tuple(e for e in events if e.source.known_at <= asof)


def superseded(events: Sequence[LoadEvent]) -> Tuple[Tuple[LoadEvent, ...],
                                                     Tuple[LoadEvent, ...]]:
    """Split into (current, superseded).

    A correction is a later entry naming what it replaces. Both stay in
    the book; only one is current, and which is which is derivable rather
    than destructive.
    """
    replaced = {e.supersedes for e in events if e.supersedes}
    current = tuple(e for e in events if _identity(e) not in replaced)
    old = tuple(e for e in events if _identity(e) in replaced)
    return current, old


def _identity(event: LoadEvent) -> str:
    return f"{event.load}:{event.kind}:{event.source.known_at}"


def render(result: LedgerRead) -> str:
    lines = [f"LEDGER {result.path} — {result.lines} line(s); "
             f"read {len(result.events)}, unreadable {len(result.bad)}"]
    if not result.conserves:
        lines.append(f"  ! ACCOUNTING DOES NOT CONSERVE: {result.accounted}")
    if result.empty_because:
        lines.append(f"  (nothing read) {result.empty_because}")
    for entry in result.bad:
        lines.append(f"  LINE {entry.line} ({entry.code}): {entry.detail}")
        lines.append(f"       {entry.raw.rstrip()}")
    if result.events:
        loads = sorted({e.load for e in result.events})
        lines.append(f"  {len(loads)} load(s): {', '.join(loads[:12])}"
                     + (" ..." if len(loads) > 12 else ""))
    return "\n".join(lines)
