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
import os
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

  python3 -m commerce commit <sheet.csv> <auth.json>   append a sheet to the ledger
  python3 -m commerce book                             replay the ledger
  python3 -m commerce residuals                        lane memory, from the book
  python3 -m commerce status                           one screen: book, residuals, gaps
  python3 -m commerce vet <carrier> <asof> [booking pickup delivery]
                                                       the three-state verdict, replayable
  python3 -m commerce exceptions                       loads where two claims disagree
  python3 -m commerce facilities <file.json>           duplicate scan: surfaced, never merged

`commit` is the only command that writes. The ledger is append-only: a
mistake is superseded by a later entry naming what it replaces, and both
stay, because the asset is the gap between promised and realized and a
store that allows an edit allows that gap to be closed by editing.

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


COMMANDS = {"form", "sheet", "record", "read", "morning", "outbound",
            "commit", "book", "residuals", "status", "vet", "exceptions", "facilities"}


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


def _commit(sheet_raw: str, authority: Authority, path) -> Tuple[int, str]:
    from commerce.ledger import append, read
    from commerce.sheet import read_sheet, render as render_sheet
    sheet = read_sheet(sheet_raw)
    lines = [render_sheet(sheet)]
    if not sheet.events:
        lines.append("NOTHING APPENDED — no readable row.")
        return 1, "\n".join(lines)
    from commerce.register import append as append_register, from_sheet_rows
    before = len(read(path=path).events)
    written = append(sheet.events, path=path)
    after = len(read(path=path).events)
    registered = append_register(from_sheet_rows(sheet.rows))
    if registered:
        lines.append(f"REGISTERED {registered} load description(s)")
    lines.append(f"APPENDED {written} event(s) to {path}; book went {before} -> {after}")
    if after - before != written:
        lines.append("  ! THE BOOK DID NOT GROW BY WHAT WAS WRITTEN")
        return 1, "\n".join(lines)
    # GRADE THE BOOK, NOT THE BATCH. A sheet of settlements carries no
    # promises, so grading the batch alone reported "nothing has been
    # promised" for a load quoted the day before — which is the whole
    # reason the book is persisted. Found by running two days rather than
    # by reading the code.
    code, graded = record(read(path=path).events, authority)
    lines.append("")
    lines.append(graded)
    if sheet.refused:
        lines.append("")
        lines.append(f"NOT THE WHOLE DAY — {len(sheet.refused)} row(s) refused and NOT appended.")
        return 1, "\n".join(lines)
    return code, "\n".join(lines)


def _book(path) -> Tuple[int, str]:
    from commerce.ledger import read, render as render_ledger, superseded
    result = read(path=path)
    lines = [render_ledger(result)]
    current, old = superseded(result.events)
    if old:
        lines.append(f"  {len(old)} superseded entry(ies) retained, {len(current)} current")
    return (0 if result.conserves and result.events else 1), "\n".join(lines)


def _residuals(path, asof: Optional[str]) -> Tuple[int, str]:
    from commerce import residuals as R
    from commerce.ledger import as_known_at, read
    book = read(path=path)
    if not book.events:
        return 1, f"NO RESIDUALS — {book.empty_because}"
    events = as_known_at(book.events, asof) if asof else book.events
    if not events:
        return 1, (f"NO RESIDUALS — the book holds {len(book.events)} event(s) and none was "
                   f"knowable by {asof}. That is a knowledge-state filter, not an empty book.")
    from commerce.register import read as read_register
    loads = sorted({e.load for e in events})
    register = read_register()
    from commerce.admissibility import derived_from
    standing = derived_from(events)
    lines = [f"LANE MEMORY — {len(events)} event(s) over {len(loads)} load(s)"
             + (f", as known at {asof}" if asof else ""),
             f"  {standing.sentence}"]
    if not register.records:
        lines.append("")
        lines.append("NO GROUPING — " + (register.empty_because or ""))
        lines.append("  Residuals are computed PER CARRIER, PER LANE and PER RECEIVER. Without a "
                     "register there is no partition to compute them over, and an ungrouped mean "
                     "over every load in the book is a number about nothing in particular.")
        lines.append("  Add carrier, origin, destination and month columns to the sheet and "
                     "re-commit; they are optional columns and land in the register.")
        return 1, "\n".join(lines)

    described = set(register.records) & set(loads)
    undescribed = sorted(set(loads) - set(register.records))
    lines.append(f"  {len(described)} of {len(loads)} load(s) described in the register")
    if undescribed:
        lines.append(f"  {len(undescribed)} not described and therefore not grouped: "
                     f"{undescribed[:8]}")
    for name, result in (
            ("carrier", R.by_carrier(events, register.carrier_of)),
            ("lane", R.by_lane(events, register.lane_of)),
            ("lane and season", R.by_lane_season(events, register.lane_of, register.month_of)),
            ("receiver", R.appointment_slippage(events, register.receiver_of))):
        lines.append("")
        lines.append(R.render(result))
    return 0, "\n".join(lines)


def _vet(argv: Sequence[str]) -> Tuple[int, str]:
    """The verdict as it stood at `asof`, from persisted observations.

    Exit codes carry the three states: 0 cleared, 1 blocked, 3
    undetermined — because a shell script that treats nonzero as `blocked`
    would collapse the third state, which is the collapse the gate exists
    to prevent.
    """
    from commerce.vetting import (authority_active, decide, insurance_current,
                                  no_recent_reincarnation, render as render_verdict, Carrier,
                                  CLEARED, BLOCKED)
    from commerce.vetting_store import read as read_vetting
    if len(argv) < 2:
        return 2, "vet needs: <carrier> <asof> [booking pickup delivery]"
    carrier_id, asof = argv[0], argv[1]
    store = read_vetting()
    observations = store.for_carrier(carrier_id)
    predicates = [authority_active(observations, asof=asof),
                  no_recent_reincarnation(observations, asof=asof)]
    if len(argv) >= 5:
        predicates.insert(0, insurance_current(
            observations, required=100_000.0, currency="CAD",
            booking_date=argv[2], pickup_date=argv[3], delivery_date=argv[4], asof=asof))
    verdict = decide(Carrier(carrier_id, carrier_id), predicates, asof=asof)
    text = render_verdict(verdict)
    if store.empty_because:
        text += "\n  " + store.empty_because
    return (0 if verdict.status == CLEARED else 1 if verdict.status == BLOCKED else 3), text


def _exceptions() -> Tuple[int, str]:
    """The queue of loads where two claims about one movement disagree.

    Exit codes carry the same three states as `vet`: 0 every load
    consistent and accounted, 1 at least one divergence to work, 3 the
    question cannot be fully answered (uncaptured bills of lading, bad
    lines, or no register at all). A queue that exited 0 over uncaptured
    BOLs would report a book nobody checked as a book with nothing wrong.
    """
    from commerce.register import partition, read as read_register
    register = read_register()
    split = partition(register)
    lines = [f"EXCEPTIONS — {split.described} load(s) in the register"]
    if register.empty_because:
        lines.append(f"  (nothing to examine) {register.empty_because}")
        return 3, "\n".join(lines)
    for number, detail in register.bad:
        lines.append(f"  LINE {number}: {detail}")
    for record in split.divergent:
        lines.append(f"  ! {record.load}: tendered to {record.carrier}, bill of lading names "
                     f"{record.bill_of_lading_carrier}. Two claims about one movement. A single "
                     "instance may be a legitimate interline; a persistent directional gap for "
                     "one carrier is the pattern worth ranking.")
    if split.unknowable:
        lines.append(f"  {len(split.unknowable)} load(s) with no bill of lading captured — the "
                     "carrier that actually moved each is unknown, which is not the same as "
                     "consistent.")
    lines.append(f"  {len(split.consistent)} consistent + {len(split.divergent)} divergent + "
                 f"{len(split.unknowable)} unknowable = {split.described}"
                 + ("" if split.conserves else "  ! DOES NOT CONSERVE"))
    if not split.conserves:
        return 2, "\n".join(lines)
    if split.divergent:
        return 1, "\n".join(lines)
    if split.unknowable or register.bad:
        return 3, "\n".join(lines)
    return 0, "\n".join(lines)


def _facilities(argv: Sequence[str]) -> Tuple[int, str]:
    """The facility register gate. Exit 1 when suspected duplicates are
    surfaced; 3 when the question cannot be answered to zero — which
    includes EVERY run under the conservative normalizer, because there
    `Dr` and `Drive` are distinct entries and the duplicate rate is
    unknown and not zero. 0 is reachable only with the statistical
    parser installed and no pair above the floor.
    """
    from commerce.facility import (STATISTICAL, Facility, FacilityRefusal,
                                   available_normalizer, duplicate_scan, register_health)
    source = argv[0] if argv else os.environ.get("COMMERCE_FACILITIES", "")
    if not source:
        return 2, "facilities needs a file: python3 -m commerce facilities <file.json>"
    raw_text = _read_file(source)
    if raw_text is None:
        return 3, (f"FACILITIES — no register at {source}. Nothing was scanned, which is not "
                   "the same as nothing being duplicated.")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return 2, f"FACILITIES — {source} is not JSON: {exc.msg}"
    if not isinstance(payload, dict):
        return 2, f"FACILITIES — {source} must be an object of id -> raw address"
    name, normalize = available_normalizer()
    register = []
    refused = []
    for facility_id in sorted(payload):
        raw_addr = str(payload[facility_id])
        try:
            register.append(Facility(facility_id=str(facility_id), raw=raw_addr,
                                     normalized=normalize(raw_addr), normalizer=name))
        except FacilityRefusal as exc:
            refused.append((str(facility_id), str(exc)))
    scan = duplicate_scan(register)
    health = register_health(register)
    lines = [f"FACILITIES {source} — {len(payload)} entr(ies): "
             f"{len(register)} scanned + {len(refused)} refused"]
    for facility_id, reason in refused:
        lines.append(f"  REFUSED {facility_id}: {reason}")
    if scan.empty_because:
        lines.append(f"  (nothing scanned) {scan.empty_because}")
        return 3, "\n".join(lines)
    for pair in scan.pairs:
        lines.append(f"  ? {pair.left.facility_id} ~ {pair.right.facility_id} "
                     f"(similarity {pair.similarity:.2f})")
        lines.append(f"      {pair.left.raw!r}")
        lines.append(f"      {pair.right.raw!r}")
        lines.append("      surfaced, not merged: confirm and merge deliberately, recording "
                     "which raw strings were judged the same and by whom.")
    if not scan.pairs:
        lines.append(f"  no suspect pair at or above {scan.floor:.2f} under {scan.normalizer}")
    if scan.distinct_by_number:
        sample = ", ".join(f"{pair.left.facility_id}~{pair.right.facility_id}"
                           for pair in scan.distinct_by_number[:5])
        lines.append(f"  {len(scan.distinct_by_number)} pair(s) above the floor differ in house "
                     f"number — a stated difference, so listed as distinct rather than dropped "
                     f"(e.g. {sample})")
    lines.append(f"  {len(scan.pairs)} suspect + {len(scan.distinct_by_number)} distinct-by-number "
                 f"= {scan.above_floor} pair(s) above the floor")
    lines.append(f"  health: {health.caveat}")
    if scan.pairs:
        return 1, "\n".join(lines)
    if scan.normalizer != STATISTICAL or refused:
        return 3, "\n".join(lines)
    return 0, "\n".join(lines)


def _status(path) -> Tuple[int, str]:
    from commerce.ledger import read
    from commerce.events import PROMISES, SETTLES
    result = read(path=path)
    lines = ["PAYLOAD — status"]
    lines.append(f"  ledger        {result.path}")
    lines.append(f"  lines         {result.lines}  (read {len(result.events)}, "
                 f"unreadable {len(result.bad)})")
    if result.empty_because:
        lines.append(f"  (empty)       {result.empty_because}")
        lines.append("")
        lines.append("  Next: python3 -m commerce sheet > loads.csv, type into it, then")
        lines.append("        python3 -m commerce commit loads.csv authority.json")
        return 1, "\n".join(lines)
    by_load: Dict[str, set] = {}
    for event in result.events:
        by_load.setdefault(event.load, set()).add(event.kind)
    unsettled = {load: sorted(k for k in kinds if k in PROMISES and SETTLES[k] not in kinds)
                 for load, kinds in by_load.items()}
    open_loads = {k: v for k, v in unsettled.items() if v}
    lines.append(f"  loads         {len(by_load)}  ({len(open_loads)} with an unsettled promise)")
    for load, kinds in sorted(open_loads.items())[:10]:
        lines.append(f"    {load:<10} awaiting {[SETTLES[k] for k in kinds]}")
    if not open_loads:
        lines.append("    every promise in the book has settled")
    return 0, "\n".join(lines)


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

    from commerce.ledger import DEFAULT_PATH
    if argv[0] == "book":
        code, text = _book(DEFAULT_PATH)
        print(text)
        return code
    if argv[0] == "residuals":
        code, text = _residuals(DEFAULT_PATH, argv[1] if len(argv) > 1 else None)
        print(text)
        return code
    if argv[0] == "status":
        code, text = _status(DEFAULT_PATH)
        print(text)
        return code
    if argv[0] == "vet":
        code, text = _vet(argv[1:])
        print(text)
        return code
    if argv[0] == "exceptions":
        code, text = _exceptions()
        print(text)
        return code
    if argv[0] == "facilities":
        code, text = _facilities(argv[1:])
        print(text)
        return code
    if len(argv) < 2:
        print(f"{argv[0]} needs a file: python3 -m commerce {argv[0]} <file>")
        return 2
    raw = _read_file(argv[1])
    if raw is None:
        return 2

    if argv[0] in {"read", "commit"}:
        if len(argv) < 3:
            print(f"{argv[0]} needs a sheet and an authority: "
                  f"python3 -m commerce {argv[0]} <sheet.csv> <authority.json>")
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
            if argv[0] == "commit":
                code, text = _commit(raw, authority, DEFAULT_PATH)
            else:
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
