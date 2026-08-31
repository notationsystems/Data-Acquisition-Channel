"""The operator surface for one load. `python3 -m commerce`.

WHY THIS EXISTS, AND WHY IT IS THE PHASE 0 BLOCKER. Walking one real
transaction end to end through the tree showed steps 1 to 7 working and
step 8 stopping: there was no way to reach any of it without writing
Python. That is the same defect this account already named and fixed for
the session instrument -- a mechanism reachable only through an import
statement is reached by nobody -- recurring at the shortest possible
distance from the class that names it.

The first transaction is recorded by a person under time pressure who is
not going to open an editor. So:

    python3 -m commerce form                     print a blank form
    python3 -m commerce sheet                    print a blank sheet header
    python3 -m commerce record <events.json>     grade one load
    python3 -m commerce read <sheet.csv>         read a sheet AND grade it
    python3 -m commerce morning <opps.json>      the three-list morning view
    python3 -m commerce outbound <drafts.json>   what is waiting for a person

THE THIRD INSTANCE OF THE SAME CLASS. `record` and `form` were added when
walking a transaction showed step 8 stopping. The morning view, the sheet
reader and the outbound queue were then built and left reachable only by
import -- in the same session, by the same author, after naming the
defect. It is recorded that way rather than presented as a feature.

EXIT CODES ARE THE SIGNAL. 2 for an input this reader cannot use, 1 for a
record that carries refusals, 0 only when the record can be graded. A
record that cannot be graded must not exit 0, because the operator's next
action is decided by whether the shell said it was fine.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from commerce.events import SETTLES, EventRefusal, LoadEvent, pair_events
from commerce.manual import blank_form, load_entries
from commerce.stores import (Authority, Commitment, CommitmentStore, Evidence, Outcome,
                             OutcomeStore, Provenance, Quantity, StoreRefusal, diverge, pair)

USAGE = """usage:
  python3 -m commerce form                          print a blank event form
  python3 -m commerce sheet                         print a blank sheet header
  python3 -m commerce record <events.json>          record and grade one load
  python3 -m commerce read <sheet.csv> <auth.json>  read a sheet AND grade it
  python3 -m commerce morning <opportunities.json>  the three-list morning view
  python3 -m commerce outbound <drafts.json>        what is waiting for a person

An events file is a JSON object with an `authority` and an `events` array.
Every promise you record (rate_quoted, pickup_promised, transit_estimated)
is a COMMITMENT; every world-fact (rate_invoiced, pickup_actual,
transit_realized) is an OUTCOME. They are kept apart on purpose: the gap
between them is the only thing here that compounds.

`read` takes the sheet you typed into and the authority you book under,
because a CSV cannot carry an authority object and a load recorded under
none is a commitment the record cannot say who was entitled to make."""

#: The authority a manually recorded load is booked under. Passed in
#: rather than assumed, because an authority resolved by this module would
#: be this module's claim about who may bind the firm.
AUTHORITY_KEY = "authority"


def _authority(payload: Mapping[str, Any]) -> Authority:
    body = payload.get(AUTHORITY_KEY) or {}
    return Authority(holder=str(body.get("holder", "")),
                     instrument=str(body.get("instrument", "")),
                     valid_from=str(body.get("valid_from", "")),
                     valid_until=str(body.get("valid_until", "")))


def record(events: Sequence[LoadEvent], authority: Authority) -> Tuple[int, str]:
    """Grade one load. Returns (exit code, printed record)."""
    lines: List[str] = []
    refusals: List[str] = []

    by_load: Dict[str, List[LoadEvent]] = {}
    for event in events:
        by_load.setdefault(event.load, []).append(event)

    if not by_load:
        return 1, ("NO EVENTS — the file parsed and is empty. That is a file with nothing in it, "
                   "not a load with nothing to say about it, and an empty record would read as "
                   "the second.")

    for load, group in sorted(by_load.items()):
        lines.append(f"LOAD {load}")
        commitments = CommitmentStore()
        outcomes = OutcomeStore(commitments)
        paired = pair_events(tuple(group))

        for key, (promise, settlement) in sorted(paired.items()):
            if promise is None:
                continue
            idempotency = f"{load}:{promise.kind}"
            try:
                commitment = commitments.issue(Commitment(
                    subject=idempotency,
                    quantity=Quantity(promise.value, promise.unit, promise.basis),
                    issuer=promise.source.recorded_by or "",
                    authority=authority,
                    idempotency_key=idempotency,
                    issued_at=promise.source.known_at))
            except StoreRefusal as exc:
                refusals.append(f"{idempotency}: {exc.code}")
                lines.append(f"  REFUSED {promise.kind}: {exc.code}")
                lines.append(f"          {exc.detail}")
                continue

            if settlement is None:
                lines.append(f"  {promise.kind:<22} {promise.value:>12,.2f} {promise.unit}"
                             f"   [{promise.basis}]  — NOT YET SETTLED "
                             f"(awaiting {SETTLES[promise.kind]})")
                continue

            outcome = outcomes.record(Outcome(idempotency, Evidence(
                subject=idempotency,
                quantity=Quantity(settlement.value, settlement.unit, settlement.basis),
                provenance=Provenance(source_id=settlement.source.source_id,
                                      retrieved_at=settlement.source.known_at,
                                      known_at=settlement.source.known_at,
                                      locator=settlement.source.artifact),
                evidence_class=settlement.source.source_class)))
            result = diverge(commitment, outcome)
            if result.refusal:
                refusals.append(f"{idempotency}: basis")
                lines.append(f"  {promise.kind:<22} REFUSED — {result.refusal}")
            else:
                assert result.residual is not None
                lines.append(
                    f"  {promise.kind:<22} promised {promise.value:>10,.2f} "
                    f"realized {settlement.value:>10,.2f} {settlement.unit}"
                    f"   residual {result.residual:>+10,.2f}")

        accounting = pair(commitments, outcomes)
        lines.append(f"  accounted {accounting.accounted} of {len(commitments)} commitment(s); "
                     f"settled {len(accounting.divergences)}, "
                     f"unsettled {len(accounting.unsettled)}, "
                     f"revoked {len(accounting.revoked)}, "
                     f"basis-refused {len(accounting.basis_refused)}")
        if accounting.accounted != len(commitments):
            lines.append(f"  ! ACCOUNTING DOES NOT CONSERVE: {accounting.accounted} accounted "
                         f"for {len(commitments)} commitment(s). A promise in no bucket is one "
                         "the firm has forgotten it made.")
        if accounting.empty_because:
            lines.append(f"  (no residuals) {accounting.empty_because}")

    if refusals:
        lines.append("")
        lines.append(f"NOT GRADEABLE — {len(refusals)} refusal(s) above. The record stands; it "
                     "is the reading of it that is withheld.")
        return 1, "\n".join(lines)
    return 0, "\n".join(lines)


COMMANDS = {"form", "sheet", "record", "read", "morning", "outbound"}


def _read_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        print(f"cannot read {path}: {exc}")
        return None


def _sheet_then_grade(raw: str, authority: Authority) -> Tuple[int, str]:
    """Read a sheet and grade what it yielded, in one pass.

    This is the directive's workflow end to end: type into a sheet, export
    it, see the residuals. A refused row is printed WITH the grading rather
    than in a separate step, because an operator who does not see the
    refusal will read the shorter list as the whole day.
    """
    from commerce.sheet import read_sheet, render as render_sheet
    read = read_sheet(raw)
    lines = [render_sheet(read)]
    if not read.events:
        return 1, "\n".join(lines)
    code, graded = record(read.events, authority)
    lines.append("")
    lines.append(graded)
    if read.refused:
        lines.append("")
        lines.append(f"NOT THE WHOLE DAY — {len(read.refused)} row(s) above were refused and are "
                     "not in the grading.")
        return 1, "\n".join(lines)
    return code, "\n".join(lines)


def _morning(raw: str) -> Tuple[int, str]:
    """The three-list view. The middle list is the product."""
    from commerce.gate import Authorisations, morning_view, render as render_view
    from commerce.opportunity_intake import from_manual_form
    payload = json.loads(raw)
    authorisations = Authorisations(
        frozenset(payload.get("activity_classes", [])),
        payload.get("credentials", {}))
    opportunities = [from_manual_form(entry) for entry in payload.get("opportunities", [])]
    view = morning_view(opportunities, authorisations, payload.get("pricing", {}),
                        asof=str(payload["asof"]))
    return (0 if view.conserves else 1), render_view(
        view, sustainable_loads_per_week=payload.get("sustainable_loads_per_week"))


def _outbound(raw: str) -> Tuple[int, str]:
    """What is waiting for a person, and why each item needs their hand."""
    from commerce.authority import Actor
    from commerce.outbound import Draft, OutboundQueue, render as render_queue
    payload = json.loads(raw)
    queue = OutboundQueue()
    for entry in payload.get("drafts", []):
        queue.draft(Draft(kind=str(entry["kind"]), counterparty=str(entry["counterparty"]),
                          body=str(entry.get("body", "")),
                          drafted_by=Actor(str(entry.get("drafted_by", "agent")), True)))
    return 0, render_queue(queue)


def main(argv: Sequence[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(USAGE)
        return 2
    if argv[0] == "form":
        print(json.dumps([blank_form()], indent=2))
        return 0
    if argv[0] == "sheet":
        from commerce.sheet import blank_sheet
        print(blank_sheet(), end="")
        return 0
    if len(argv) < 2:
        print(f"{argv[0]} needs a file: python3 -m commerce {argv[0]} <file>")
        return 2
    raw = _read_file(argv[1])
    if raw is None:
        return 2

    if argv[0] == "read":
        if len(argv) < 3:
            print("read needs a sheet and an authority: "
                  "python3 -m commerce read <sheet.csv> <authority.json>")
            return 2
        auth_raw = _read_file(argv[2])
        if auth_raw is None:
            return 2
        try:
            authority = _authority(json.loads(auth_raw))
        except json.JSONDecodeError as exc:
            print(f"the authority file is not JSON ({exc.msg}).")
            return 2
        if not authority.holder or not authority.instrument:
            print("NO_AUTHORITY_STATED: the authority file must carry holder, instrument, "
                  "valid_from and valid_until.")
            return 2
        try:
            code, text = _sheet_then_grade(raw, authority)
        except EventRefusal as exc:
            print(f"{exc.code}: {exc.detail}")
            return 2
        print(text)
        return code

    if argv[0] in {"morning", "outbound"}:
        handler = _morning if argv[0] == "morning" else _outbound
        try:
            code, text = handler(raw)
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            print(f"{type(exc).__name__}: {exc}")
            return 2
        print(text)
        return code

    payload: Mapping[str, Any] = {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            payload = parsed
            raw = json.dumps(parsed.get("events", []))
    except json.JSONDecodeError:
        pass

    authority = _authority(payload)
    if not authority.holder or not authority.instrument:
        print("NO_AUTHORITY_STATED: the file must carry an `authority` object with holder, "
              "instrument, valid_from and valid_until. A load recorded under no authority is a "
              "commitment the record cannot say who was entitled to make.")
        return 2

    try:
        events = load_entries(raw)
    except EventRefusal as exc:
        print(f"{exc.code}: {exc.detail}")
        return 2

    code, text = record(events, authority)
    print(text)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
