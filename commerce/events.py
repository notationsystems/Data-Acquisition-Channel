"""The canonical load events, written identically by a person and by an API.

WHY THIS FILE IS THE CHEAPEST THING IN THE PROGRAMME. The first fifty loads
have no integrations; they are phone calls and emails. If manual entry
writes the SAME events a future API adapter will write, the residual
history starts at load one rather than at whenever the integrations land.
A commitment/outcome pair recorded by a person is `curation: independent`
by exactly the same construction as one recorded by an API, because the
outcome came from the world either way. It costs a form.

THE VOCABULARY IS PAIRED, AND THE PAIRING IS TOTAL. Every event is either
something the firm PROMISED or something the world DID, and every promise
has exactly one counterpart. That is asserted, not documented: a promise
with no counterpart can never be scored, so it would sit in the record
looking like data and never reach a residual.

    rate_quoted          <->  rate_invoiced
    rate_accepted        <->  rate_invoiced
    pickup_promised      <->  pickup_actual
    transit_estimated    <->  transit_realized
    accessorial_claimed  <->  accessorial_paid
    contribution_expected<->  contribution_realized

WHERE THEY LAND. Promises are COMMITMENTS and world-facts are OUTCOMES, in
the PC-1 sense -- which means `commerce.stores.diverge()` already scores
them and no new analytics are needed to get a residual out of a phone
call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

RATE_QUOTED = "rate_quoted"
RATE_ACCEPTED = "rate_accepted"
RATE_INVOICED = "rate_invoiced"
PICKUP_PROMISED = "pickup_promised"
PICKUP_ACTUAL = "pickup_actual"
TRANSIT_ESTIMATED = "transit_estimated"
TRANSIT_REALIZED = "transit_realized"
ACCESSORIAL_CLAIMED = "accessorial_claimed"
ACCESSORIAL_PAID = "accessorial_paid"
CONTRIBUTION_EXPECTED = "contribution_expected"
CONTRIBUTION_REALIZED = "contribution_realized"

#: Promise -> the world-fact that settles it. Total over PROMISES by
#: construction, asserted by a test: an unpaired promise is a number that
#: can never be scored.
SETTLES: Mapping[str, str] = {
    RATE_QUOTED: RATE_INVOICED,
    RATE_ACCEPTED: RATE_INVOICED,
    PICKUP_PROMISED: PICKUP_ACTUAL,
    TRANSIT_ESTIMATED: TRANSIT_REALIZED,
    ACCESSORIAL_CLAIMED: ACCESSORIAL_PAID,
    CONTRIBUTION_EXPECTED: CONTRIBUTION_REALIZED,
}

PROMISES: FrozenSet[str] = frozenset(SETTLES)
WORLD_FACTS: FrozenSet[str] = frozenset(SETTLES.values())
EVENT_KINDS: FrozenSet[str] = PROMISES | WORLD_FACTS

#: The basis each event kind is measured on. Carried here rather than at
#: the call site so a manual entry and an API adapter cannot disagree
#: about it -- two adapters writing the same event on different bases is
#: the mud-tonnage error arriving through the back door.
BASIS_OF: Mapping[str, str] = {
    RATE_QUOTED: "all_in_to_shipper",
    RATE_ACCEPTED: "all_in_to_shipper",
    RATE_INVOICED: "all_in_to_shipper",
    PICKUP_PROMISED: "local_date_at_origin",
    PICKUP_ACTUAL: "local_date_at_origin",
    TRANSIT_ESTIMATED: "door_to_door",
    TRANSIT_REALIZED: "door_to_door",
    ACCESSORIAL_CLAIMED: "line_item",
    ACCESSORIAL_PAID: "line_item",
    CONTRIBUTION_EXPECTED: "gross_margin",
    CONTRIBUTION_REALIZED: "gross_margin",
}

UNKNOWN_EVENT_KIND = "UNKNOWN_EVENT_KIND"
EVENT_CARRIES_NO_LOAD = "EVENT_CARRIES_NO_LOAD"
EVENT_CARRIES_NO_SOURCE = "EVENT_CARRIES_NO_SOURCE"
EVENT_CARRIES_NO_KNOWN_AT = "EVENT_CARRIES_NO_KNOWN_AT"
#: A world-fact that references no promise. It is an observation, and it
#: belongs in the evidence store rather than settling something.
WORLD_FACT_SETTLES_NOTHING = "WORLD_FACT_SETTLES_NOTHING"


class EventRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Source:
    """Where an event came from. A phone call is a source.

    `recorded_by` is an OPAQUE PERSON IDENTIFIER and never a name: this
    package carries no natural-person data, and the rule is enforced by
    there being no field to put one in rather than by a filter someone
    remembers to apply.
    """

    source_id: str
    source_class: str
    method: str
    known_at: str
    recorded_by: Optional[str] = None
    artifact: Optional[str] = None
    #: Which rung of an acquisition ladder served this. Manual entry is
    #: its own rung and says so rather than passing as an integration.
    rung: str = "manual"


@dataclass(frozen=True)
class LoadEvent:
    """One canonical event. THE shape both adapters must produce.

    There is deliberately no `notes` or `raw` field. A free-text escape
    hatch is where two adapters stop agreeing: the manual form would put
    the number in the note and the API adapter would put it in the value,
    and both would look like they were writing the same events.
    """

    load: str
    kind: str
    value: float
    unit: str
    source: Source
    #: What the value describes, distinct from when it became knowable.
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    #: The event this one revises, if any.
    supersedes: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise EventRefusal(
                UNKNOWN_EVENT_KIND,
                f"{self.kind!r} is not a canonical event. The vocabulary is closed on purpose: an "
                "adapter that can invent a kind is an adapter whose events another adapter will "
                f"not write. Known: {sorted(EVENT_KINDS)}",
            )
        if not self.load.strip():
            raise EventRefusal(EVENT_CARRIES_NO_LOAD,
                               f"a {self.kind} event belonging to no load cannot be paired.")
        if not self.source.source_id.strip():
            raise EventRefusal(
                EVENT_CARRIES_NO_SOURCE,
                f"a {self.kind} event on load {self.load!r} names no source. A phone call IS a "
                "source; an event with none is an event nobody can go back and check.",
            )
        if not self.source.known_at.strip():
            raise EventRefusal(
                EVENT_CARRIES_NO_KNOWN_AT,
                f"a {self.kind} event on load {self.load!r} has no known_at, so it cannot take "
                "part in an as-known-then question -- which is the only question a post-mortem asks.",
            )

    @property
    def basis(self) -> str:
        return BASIS_OF[self.kind]

    @property
    def is_promise(self) -> bool:
        return self.kind in PROMISES

    @property
    def settled_by(self) -> Optional[str]:
        return SETTLES.get(self.kind)

    def canonical(self) -> Tuple[object, ...]:
        """The comparable shape.

        Two adapters agree when this tuple matches. It deliberately
        EXCLUDES the source, because the whole point is that a phone call
        and an API produce the same event about the world differing only
        in how it was learned.
        """
        return (self.load, self.kind, self.value, self.unit, self.basis,
                self.period_start, self.period_end)


def pair_events(events: Tuple[LoadEvent, ...]) -> Dict[str, Tuple[Optional[LoadEvent],
                                                                  Optional[LoadEvent]]]:
    """Group events into (promise, settlement) per load and promise kind.

    A promise with no settlement is `(promise, None)` and stays visible.
    Dropping it would make an unsettled load look like a load with nothing
    outstanding, which is the same error as an empty list with no warrant.
    """
    paired: Dict[str, Tuple[Optional[LoadEvent], Optional[LoadEvent]]] = {}
    by_kind: Dict[Tuple[str, str], LoadEvent] = {}
    for event in events:
        by_kind[(event.load, event.kind)] = event
    for (load, kind), event in by_kind.items():
        if kind not in PROMISES:
            continue
        settlement = by_kind.get((load, SETTLES[kind]))
        paired[f"{load}:{kind}"] = (event, settlement)
    return paired
