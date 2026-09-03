"""The outbound channel — the only way anything leaves the firm.

WHY THE BOUNDARY IS HERE AND NOT ON THE RECORD TYPE. PC-5 already stops an
agent constructing a Commitment. That is necessary and it is not
sufficient, because a dispatcher who receives

    "can you cover Toronto-Detroit Thursday at $2,400"

treats it as an offer regardless of what our schema calls it. The
recipient cannot see the type system. So the boundary that matters is the
one at the wire, and it is drawn here.

    Agents may:     read inbound mail, parse, draft, rank, propose,
                    refuse, run check-ins, update tracking, prepare
                    documents
    Agents may not: send to a counterparty, quote a rate, tender a load,
                    issue a rate confirmation, or confirm on a call

The first row is most of the time saving. The second is where the
liability lives, and a person presses send until measurement earns
otherwise.

INBOUND CHECK-INS ARE THE SAFE CASE and are deliberately not gated: a
status request carries no offer and no acceptance, so `check_in` exists as
a separate constructor that `send` accepts from an agent.

OFFER-SHAPED CONTENT IS FLAGGED, NOT BLOCKED BY ITS SHAPE. A draft that
names a price and a lane is an offer whatever it is labelled, so the
reviewer is told WHY their hand is required rather than being asked to
notice. The detector reports a candidate; it does not decide, because a
detector that decided would be committing class 8 one level up -- acting
confidently on a rule it measured loosely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import FrozenSet, Optional, Sequence, Tuple

from commerce.authority import Actor

#: A message an agent tried to put on the wire.
AN_AGENT_MAY_NOT_SEND_TO_A_COUNTERPARTY = "AN_AGENT_MAY_NOT_SEND_TO_A_COUNTERPARTY"
#: A draft with no reviewer recorded.
SENT_WITHOUT_A_NAMED_SENDER = "SENT_WITHOUT_A_NAMED_SENDER"
#: A draft with no counterparty.
DRAFT_NAMES_NO_COUNTERPARTY = "DRAFT_NAMES_NO_COUNTERPARTY"
#: A binding kind that was never reviewed.
BINDING_DRAFT_WAS_NOT_REVIEWED = "BINDING_DRAFT_WAS_NOT_REVIEWED"

#: Class 7 on the queue.
QUEUE_EMPTY_BECAUSE_NOTHING_WAS_DRAFTED = "QUEUE_EMPTY_BECAUSE_NOTHING_WAS_DRAFTED"
QUEUE_EMPTY_BECAUSE_EVERYTHING_WAS_SENT = "QUEUE_EMPTY_BECAUSE_EVERYTHING_WAS_SENT"

#: Acts that bind the firm. Named so the list is checkable rather than a
#: sentence a reader must interpret.
BINDING_KINDS: FrozenSet[str] = frozenset({
    "quote", "tender", "rate_confirmation", "booking", "customs_filing",
})
#: Acts that carry no offer and no acceptance.
NON_BINDING_KINDS: FrozenSet[str] = frozenset({
    "check_in", "status_request", "document_request", "acknowledgement",
})

#: A price beside a lane or a date reads as an offer to a dispatcher.
_PRICE = re.compile(r"(\$\s?\d[\d,]*(?:\.\d{2})?|\b\d[\d,]{2,}\s?(?:CAD|USD)\b)")
_COMMITTING_VERB = re.compile(
    r"\b(can you cover|we can do|we'll take|book it|confirmed at|rate is|"
    r"our rate|we are offering|tender(?:ing)? (?:you|this))\b", re.IGNORECASE)


class OutboundRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Draft:
    """What an agent may produce. It is not a message until a person sends it."""

    kind: str
    counterparty: str
    body: str
    drafted_by: Actor
    reviewed_by: Optional[Actor] = None

    def __post_init__(self) -> None:
        if not self.counterparty.strip():
            raise OutboundRefusal(
                DRAFT_NAMES_NO_COUNTERPARTY,
                "a draft with no counterparty cannot be reviewed, because the reviewer cannot "
                "tell who would receive it.")

    @property
    def binding(self) -> bool:
        return self.kind in BINDING_KINDS

    @property
    def offer_shaped(self) -> Tuple[str, ...]:
        """Why a reviewer's hand is required, in the draft's own words.

        Reports candidates. A price in a sentence explaining last month's
        invoice is not an offer, and this cannot tell the difference.
        """
        found = []
        price = _PRICE.search(self.body)
        if price:
            found.append(f"names a price ({price.group(0)!r})")
        verb = _COMMITTING_VERB.search(self.body)
        if verb:
            found.append(f"uses committing language ({verb.group(0)!r})")
        return tuple(found)


@dataclass(frozen=True)
class Sent:
    draft: Draft
    sender: Actor
    sent_at: str


def send(draft: Draft, sender: Actor, *, at: str) -> Sent:
    """The ONLY egress. A person presses send.

    Checked in this order deliberately: an agent sender is refused before
    anything about the draft's content is considered, because whether the
    content looks binding is a judgement and whether the sender is an
    agent is a fact.
    """
    if sender.is_agent:
        raise OutboundRefusal(
            AN_AGENT_MAY_NOT_SEND_TO_A_COUNTERPARTY,
            f"{sender.identifier!r} is an agent identity. The boundary is the WIRE, not the "
            f"record type: a dispatcher reading {draft.body[:60]!r} treats it as an offer "
            "whatever our schema calls it, and cannot see the type system that made it a draft.")
    if not sender.identifier.strip():
        raise OutboundRefusal(SENT_WITHOUT_A_NAMED_SENDER,
                              "the record would not say who put this on the wire.")
    if draft.binding and draft.reviewed_by is None:
        raise OutboundRefusal(
            BINDING_DRAFT_WAS_NOT_REVIEWED,
            f"a {draft.kind} binds the firm and carries no reviewer. Sending is a person's act "
            "and the record must say which person.")
    return Sent(draft=draft, sender=sender, sent_at=at)


def check_in(counterparty: str, body: str, drafted_by: Actor) -> Draft:
    """The safe case, constructed separately so it is reachable by name.

    An inbound status request carries no offer and no acceptance, so it is
    the one outbound an agent may originate. It still goes through `send`,
    which still refuses an agent SENDER -- automating the drafting is not
    automating the wire.
    """
    return Draft(kind="check_in", counterparty=counterparty, body=body, drafted_by=drafted_by)


@dataclass
class OutboundQueue:
    """Drafts waiting for a person."""

    _pending: list
    _sent: list

    def __init__(self) -> None:
        self._pending = []
        self._sent = []

    def draft(self, draft: Draft) -> None:
        self._pending.append(draft)

    def release(self, draft: Draft, sender: Actor, *, at: str) -> Sent:
        sent = send(draft, sender, at=at)
        self._pending = [d for d in self._pending if d is not draft]
        self._sent.append(sent)
        return sent

    @property
    def pending(self) -> Tuple[Draft, ...]:
        return tuple(self._pending)

    @property
    def empty_because(self) -> Optional[str]:
        if self._pending:
            return None
        if not self._sent:
            return (f"{QUEUE_EMPTY_BECAUSE_NOTHING_WAS_DRAFTED}: no agent has drafted anything. "
                    "An empty outbound queue and an agent layer that never ran look identical "
                    "from here.")
        return (f"{QUEUE_EMPTY_BECAUSE_EVERYTHING_WAS_SENT}: {len(self._sent)} draft(s) "
                "released by a person; the queue is clear because the work was done.")


def render(queue: OutboundQueue) -> str:
    lines = [f"OUTBOUND — {len(queue.pending)} awaiting a person"]
    if queue.empty_because:
        lines.append(f"  (empty) {queue.empty_because}")
    for draft in queue.pending:
        flags = draft.offer_shaped
        lines.append(f"  {draft.kind:<18} -> {draft.counterparty}"
                     + ("  [BINDING]" if draft.binding else ""))
        for flag in flags:
            lines.append(f"  {'':<18}    ! {flag} — reads as an offer to the recipient")
    return "\n".join(lines)
