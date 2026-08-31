"""The Opportunity record — one type, many channels, wildly different
completeness.

THE MIDDLE LIST IS THE PRODUCT. An opportunity you cannot price is not a
low-ranked opportunity; it is an UN-RANKED one with a named gap, and the
gap is usually one phone call. So `Field` does not merely record that
something is missing -- it records WHO KNOWS IT, which is what turns the
blocked list from a backlog into a call sheet. A missing weight on a
shipper-direct load is one email; a missing quantity on a tender is an
attachment already in hand.

An engine that silently drops the unpriceable and shows four clean items
has thrown away most of the day's work. That is why `missing` is a status
with structure rather than a `None`, and why nothing in this module has a
default.

THREE FIELD STATES, NOT TWO. `missing` and `unparsed` are different
situations with different remedies: nobody told us, versus somebody told
us and this reader could not read it. Collapsing them sends an operator to
make a phone call that has already been made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Generic, Mapping, Optional, Sequence, Tuple, TypeVar

T = TypeVar("T")

PRESENT = "present"
MISSING = "missing"
UNPARSED = "unparsed"

# Channels. Each arrives with predictable holes, which is why the record
# is one type: the holes differ, the shape does not.
LOAD_BOARD = "load_board"
SHIPPER_DIRECT = "shipper_direct"
THREEPL_OVERFLOW = "threepl_overflow"
TENDER = "tender"
INBOUND_EMAIL = "inbound_email"
MANUAL = "manual"

CHANNELS: FrozenSet[str] = frozenset({
    LOAD_BOARD, SHIPPER_DIRECT, THREEPL_OVERFLOW, TENDER, INBOUND_EMAIL, MANUAL,
})

# Activity classes. "Registered and compliant" is PER ACTIVITY, so the
# compliance gate keys on this rather than on the firm as a whole.
DOMESTIC_BROKERAGE = "domestic_brokerage"
CROSS_BORDER_BROKERAGE = "cross_border_brokerage"
EXPEDITE = "expedite"
FORWARDING = "forwarding"
CUSTOMS_CLEARANCE = "customs_clearance"
DANGEROUS_GOODS = "dangerous_goods"
WAREHOUSING = "warehousing"
GOVERNMENT_SUPPLY = "government_supply"

ACTIVITY_CLASSES: FrozenSet[str] = frozenset({
    DOMESTIC_BROKERAGE, CROSS_BORDER_BROKERAGE, EXPEDITE, FORWARDING,
    CUSTOMS_CLEARANCE, DANGEROUS_GOODS, WAREHOUSING, GOVERNMENT_SUPPLY,
})

#: The fields a price cannot be computed without. Named here so
#: `completeness` is measured against what PRICING needs rather than
#: against how many fields the record happens to have -- a record that
#: grew a new optional field would otherwise appear to get less complete.
PRICING_RELEVANT: Tuple[str, ...] = (
    "origin", "destination", "commodity", "weight", "equipment",
    "pickup_window", "delivery_req", "revenue",
)

UNKNOWN_CHANNEL = "UNKNOWN_CHANNEL"
UNKNOWN_ACTIVITY_CLASS = "UNKNOWN_ACTIVITY_CLASS"
MISSING_FIELD_NAMES_NOBODY = "MISSING_FIELD_NAMES_NOBODY"


class OpportunityRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Field(Generic[T]):
    """A value, or a structured absence.

    `who_knows` is required on a missing field and is the whole point: it
    is what makes the blocked list actionable this morning rather than a
    list of things that are regrettably unknown.
    """

    status: str
    value: Optional[T] = None
    source: Optional[str] = None
    #: Can this be obtained by asking? A market rate is missing and not
    #: askable; a weight is missing and one email away.
    askable: bool = False
    who_knows: str = ""
    reason: str = ""

    @property
    def present(self) -> bool:
        return self.status == PRESENT


def present(value: T, source: str) -> "Field[T]":
    return Field(status=PRESENT, value=value, source=source)


def missing(who_knows: str, *, askable: bool = True) -> "Field[T]":
    """Absent, and here is who to ask.

    A missing field naming nobody is refused. `unknown` is not a state
    this engine can act on, and a blocked list of them is a backlog --
    which is exactly what the middle list exists not to be.
    """
    if not who_knows.strip():
        raise OpportunityRefusal(
            MISSING_FIELD_NAMES_NOBODY,
            "a missing field must name who knows it. Without that the blocked list is a backlog "
            "rather than a call sheet, and the engine's most valuable output becomes a list of "
            "regrets.",
        )
    return Field(status=MISSING, askable=askable, who_knows=who_knows)


def unparsed(reason: str) -> "Field[T]":
    """Somebody told us and this reader could not read it.

    Distinct from missing: the remedy is to improve the reader or open the
    document, not to make a phone call that has already been made.
    """
    return Field(status=UNPARSED, reason=reason)


@dataclass(frozen=True)
class Opportunity:
    """One opportunity, from any channel.

    Every pricing-relevant field is explicitly present, missing or
    unparsed. There is no `Optional[Money]` anywhere: an absent revenue
    and a revenue of zero are different facts and a nullable field renders
    them identically.
    """

    identifier: str
    channel: str
    activity_class: str
    received_at: str
    fields: Mapping[str, Field[object]]
    expires_at: Optional[str] = None

    def __post_init__(self) -> None:
        if self.channel not in CHANNELS:
            raise OpportunityRefusal(UNKNOWN_CHANNEL,
                                     f"{self.channel!r}; known: {sorted(CHANNELS)}")
        if self.activity_class not in ACTIVITY_CLASSES:
            raise OpportunityRefusal(
                UNKNOWN_ACTIVITY_CLASS,
                f"{self.activity_class!r}; known: {sorted(ACTIVITY_CLASSES)}. The compliance gate "
                "keys on this, so an unrecognised class would be evaluated against no requirement "
                "at all and pass.",
            )
        for name in PRICING_RELEVANT:
            if name not in self.fields:
                raise OpportunityRefusal(
                    MISSING_FIELD_NAMES_NOBODY,
                    f"{name!r} is not on this opportunity at all. Every pricing-relevant field "
                    "must be explicitly present, missing or unparsed: a field that is simply "
                    "absent from the record is one nobody will ever be asked about.",
                )

    @property
    def completeness(self) -> float:
        """Fraction of PRICING-RELEVANT fields present.

        Measured against what pricing needs, not against the record's own
        field count -- otherwise adding an optional field would make every
        opportunity appear less complete overnight.
        """
        have = sum(1 for name in PRICING_RELEVANT if self.fields[name].present)
        return have / len(PRICING_RELEVANT)

    @property
    def gaps(self) -> Tuple[str, ...]:
        return tuple(name for name in PRICING_RELEVANT if not self.fields[name].present)

    @property
    def blocking_field(self) -> Optional[str]:
        """The ONE thing needed next.

        Askable gaps come first: the point of the list is the call to make
        this morning, and an unaskable gap cannot be closed by making one.
        """
        gaps = self.gaps
        if not gaps:
            return None
        askable = [name for name in gaps if self.fields[name].askable]
        return (askable or list(gaps))[0]

    @property
    def call_to_make(self) -> Optional[str]:
        blocking = self.blocking_field
        if blocking is None:
            return None
        field = self.fields[blocking]
        if not field.askable:
            return None
        return f"{blocking}: ask {field.who_knows}"

    def expired_at(self, asof: str) -> bool:
        """A spot load expires in hours and a tender in weeks. The clock is
        always passed in, never read, so a morning view can be replayed."""
        return self.expires_at is not None and asof > self.expires_at
