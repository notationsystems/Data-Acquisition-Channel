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
    python3 -m commerce record <events.json>     grade one load

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
  python3 -m commerce form                    print a blank event form
  python3 -m commerce record <events.json>    record and grade one load

An events file is a JSON array of form entries. Every promise you record
(rate_quoted, pickup_promised, transit_estimated, ...) is a COMMITMENT;
every world-fact (rate_invoiced, pickup_actual, transit_realized, ...) is
an OUTCOME. They are kept apart on purpose: the gap between them is the
only thing here that compounds."""

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


def main(argv: Sequence[str]) -> int:
    if not argv or argv[0] not in {"form", "record"}:
        print(USAGE)
        return 2
    if argv[0] == "form":
        print(json.dumps([blank_form()], indent=2))
        return 0
    if len(argv) < 2:
        print("record needs an events file: python3 -m commerce record <events.json>")
        return 2
    try:
        with open(argv[1], "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError as exc:
        print(f"cannot read {argv[1]}: {exc}")
        return 2

    payload: Mapping[str, Any] = {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            payload = parsed
            raw = json.dumps(parsed.get("events", []))
    except json.JSONDecodeError:
        pass

    try:
        events = load_entries(raw)
    except EventRefusal as exc:
        print(f"{exc.code}: {exc.detail}")
        return 2

    authority = _authority(payload)
    if not authority.holder or not authority.instrument:
        print("NO_AUTHORITY_STATED: the file must carry an `authority` object with holder, "
              "instrument, valid_from and valid_until. A load recorded under no authority is a "
              "commitment the record cannot say who was entitled to make.")
        return 2

    code, text = record(events, authority)
    print(text)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
