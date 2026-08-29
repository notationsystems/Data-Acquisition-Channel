"""The operator surface: a queue on paper becomes a work order, and a
capture sheet becomes a graded session record.

WHY THIS EXISTS. The instrument enforced its invariants and could only be
reached by writing Python. The preconditions it waits on -- a date, a
time-box, the researcher's own questions, a stopping rule -- are supplied
by a person on the morning of a session, and a mechanism reachable only
through an import statement will be reached by nobody. Part of the
blocked precondition was a missing FORM.

WHAT IT REFUSES, and why each refusal is at THIS layer rather than the
ranker's. A field the operator misspelled cannot be caught downstream:
`minutes_` is not `minutes`, so the item silently loses its box and
arrives at the ranker looking like an item that never had one. The
distinction between `the operator wrote nothing here` and `the operator
wrote something this reader does not understand` is exactly the
which-nothing question, moved to the file boundary.

WHY JSON. `session/` may not import `epistemics`, which owns this
repository's YAML subset parser, and writing a second parser here would
be the duplicate-vocabulary problem in a new place. `json` is stdlib and
is not a layer. The cost is real -- the operator writes JSON rather than
YAML -- and it is the honest one: a parser this package maintains itself
would drift from the one the rest of the repository trusts.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from session.work_order import (Abandonment, Finding, QueueItem, Session, WorkOrder,
                                ABANDONED_AT_ITS_BOX, NOT_REACHED, WORKED)

#: The file is not the format it claims. DISTINCT from an empty queue:
#: `unparseable` and `nothing asked` are different states, and returning
#: an empty list for both is the class this instrument exists to refuse.
MALFORMED_INTAKE = "MALFORMED_INTAKE"
#: A required field is absent from an item. Named with the field AND the
#: item, so the operator is sent to one line rather than to the file.
QUEUE_FIELD_MISSING = "QUEUE_FIELD_MISSING"
#: A field this reader does not understand. Refused rather than ignored:
#: a silently dropped key is a value the operator believes they set.
UNKNOWN_QUEUE_FIELD = "UNKNOWN_QUEUE_FIELD"

_REQUIRED = ("identifier", "question", "decision_it_could_change", "acceptance_test",
             "expected_yield", "minutes")
_OPTIONAL = ("acceptance_test_at", "worked_at")
_KNOWN = set(_REQUIRED) | set(_OPTIONAL)


def _parse(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{MALFORMED_INTAKE}: the intake is not JSON ({exc.msg} at line {exc.lineno}). "
            "An unreadable file and an empty queue are different states; this reader will not "
            "return the second for the first."
        ) from None


def load_queue(raw: str) -> Tuple[int, List[QueueItem]]:
    """Parse an intake file into (box_minutes, items).

    Nothing is defaulted. A missing required field is refused with the
    field and the item named; an unknown field is refused rather than
    dropped. The items are returned UNRANKED -- ordering is the ranker's
    job and doing it here would put the discrimination rule in two
    places.
    """
    payload = _parse(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"{MALFORMED_INTAKE}: the intake must be a JSON object with "
                         "`box_minutes` and `items`.")
    if "box_minutes" not in payload:
        raise ValueError(f"{QUEUE_FIELD_MISSING}: `box_minutes` — the session's own box. "
                         "A session with no box cannot overrun, so it can only end by "
                         "exhaustion.")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError(f"{QUEUE_FIELD_MISSING}: `items` must be a list (it may be empty; an "
                         "empty queue is a state the order will name).")

    items: List[QueueItem] = []
    for position, entry in enumerate(raw_items):
        if not isinstance(entry, dict):
            raise ValueError(f"{MALFORMED_INTAKE}: item at position {position} is not an object.")
        identifier = entry.get("identifier", f"<item {position}>")
        unknown = sorted(set(entry) - _KNOWN)
        if unknown:
            raise ValueError(
                f"{UNKNOWN_QUEUE_FIELD}: item {identifier!r} carries {unknown}, which this "
                f"reader does not understand. Known fields: {sorted(_KNOWN)}. Refused rather "
                "than ignored — a dropped key is a value you believe you set."
            )
        for field in _REQUIRED:
            if field not in entry:
                raise ValueError(
                    f"{QUEUE_FIELD_MISSING}: item {identifier!r} has no {field!r}. Nothing is "
                    "defaulted here: a value invented at load would reach the ranker wearing "
                    "the operator's authority."
                )
        items.append(QueueItem(
            identifier=str(entry["identifier"]),
            question=str(entry["question"]),
            decision_it_could_change=entry["decision_it_could_change"],
            acceptance_test=entry["acceptance_test"],
            expected_yield=float(entry["expected_yield"]),
            minutes=entry["minutes"],
            acceptance_test_at=entry.get("acceptance_test_at"),
            worked_at=entry.get("worked_at"),
        ))
    return int(payload["box_minutes"]), items


def load_capture(raw: str) -> Dict[str, Any]:
    """Parse a capture sheet into the keyword arguments `close_session`
    takes.

    `residue` is passed through as None when the key is ABSENT and as a
    list when it is present-but-empty, because those are the two states
    the session distinguishes and collapsing them here would undo the
    distinction one layer down.
    """
    payload = _parse(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"{MALFORMED_INTAKE}: the capture must be a JSON object.")
    findings = [
        Finding(
            item_id=str(entry.get("item_id", "")),
            statement=str(entry.get("statement", "")),
            sources=tuple(entry.get("sources", ()) or ()),
            evidence_class=entry.get("evidence_class"),
        )
        for entry in payload.get("findings", []) or []
    ]
    abandoned = [
        Abandonment(
            identifier=str(entry.get("identifier", "")),
            reason=str(entry.get("reason", "")),
            minutes_spent=int(entry.get("minutes_spent", 0)),
        )
        for entry in payload.get("abandoned", []) or []
    ]
    return {
        "findings": findings,
        "abandoned": abandoned,
        "residue": payload["residue"] if "residue" in payload else None,
        "stopping_rule_met": bool(payload.get("stopping_rule_met")),
    }


def render_order(order: WorkOrder) -> str:
    """The work order, as an operator reads it before the session.

    Drops and refusals are printed WITH the order rather than in a log
    somewhere: an item that is not on the printed list and not visibly
    dropped will be assumed to have been ranked.
    """
    lines = [f"WORK ORDER — {order.box_minutes} minute box, "
             f"{order.planned_minutes} minutes planned"]
    if order.overruns_the_box:
        lines.append(f"  ! THE PLAN OVERRUNS THE BOX by {order.planned_minutes - order.box_minutes}"
                     " minutes. Nothing was trimmed: which items to cut is yours.")
    if order.empty_because:
        lines.append(f"  (no items) {order.empty_because}")
    for position, item in enumerate(order.items, start=1):
        lines.append(f"  {position}. [{item.minutes:>3} min] {item.identifier} — {item.question}")
        lines.append(f"        decides: {item.decision_it_could_change}")
        lines.append(f"        accepted when: {item.acceptance_test}")
    for drop in order.drops:
        lines.append(f"  DROPPED {drop.identifier} ({drop.code}): {drop.reason}")
    for code, identifier in order.refusals:
        lines.append(f"  REFUSED {identifier}: {code}")
    return "\n".join(lines)


def render_session(session: Session) -> str:
    """The session record, as it is read after.

    Every ranked item appears in exactly one bucket, the residue appears
    even when empty, and a session that cannot be graded says so at the
    end rather than looking finished.
    """
    lines = ["SESSION RECORD"]
    for bucket in (WORKED, ABANDONED_AT_ITS_BOX, NOT_REACHED):
        members = session.accounting.get(bucket, ())
        lines.append(f"  {bucket.upper():<22} {len(members)}"
                     + (f"  {', '.join(members)}" if members else ""))
    for finding in session.findings:
        lines.append(f"  FINDING {finding.item_id} [{finding.evidence_class}]: "
                     f"{finding.statement}")
        lines.append(f"        sources: {', '.join(finding.sources) or '(none)'}")
    for record in session.abandoned:
        lines.append(f"  ABANDONED {record.identifier} after {record.minutes_spent} min: "
                     f"{record.reason}")
    if session.findings_empty_because:
        lines.append(f"  NO FINDINGS — {session.findings_empty_because}")
    lines.append(f"  RESIDUE ({len(session.residue)})"
                 + ("" if session.residue_was_stated else " — NOT STATED"))
    for question in session.residue:
        lines.append(f"        {question}")
    for code, subject in session.refusals:
        lines.append(f"  REFUSED {subject}: {code}")
    lines.append("  COMPLETE" if session.complete else "  NOT COMPLETE — see the refusals above")
    return "\n".join(lines)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def main(argv: Sequence[str]) -> int:
    """`python3 -m session plan <queue>` / `close <queue> <capture>`.

    Returns 2 for an unusable input and 1 for a session whose record
    carries refusals -- the exit code is the operator's signal, and a
    record that cannot be graded must not exit 0.
    """
    from session.work_order import close_session, plan

    if len(argv) < 2 or argv[0] not in {"plan", "close"}:
        print("usage: python3 -m session plan <queue.json>\n"
              "       python3 -m session close <queue.json> <capture.json>")
        return 2
    try:
        box_minutes, items = load_queue(_read(argv[1]))
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 2

    order = plan(items, box_minutes=box_minutes)
    if argv[0] == "plan":
        print(render_order(order))
        return 0

    if len(argv) < 3:
        print("close needs a capture file: python3 -m session close <queue> <capture>")
        return 2
    try:
        captured: Mapping[str, Any] = load_capture(_read(argv[2]))
    except (ValueError, OSError) as exc:
        print(str(exc))
        return 2

    session = close_session(order, **captured)
    print(render_order(order))
    print()
    print(render_session(session))
    return 0 if session.complete else 1
