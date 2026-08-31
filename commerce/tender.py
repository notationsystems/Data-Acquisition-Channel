"""PC-3 — a notice becomes a structured opportunity, or says why it cannot.

WHAT RECON CHANGED ABOUT THIS ITEM. The founding order asks for ten
fields: buyer, commodity, quantity, origin, destination, delivery windows,
incoterms, compliance requirements, equipment, evaluation criteria and
duration. Measured against the source (architecture/canadabuys_recon.yaml),
FIVE of them have NO COLUMN AT ALL -- quantity, incoterms, origin,
equipment, and contract value. Not sparse: absent.

So the honest extractor's majority output on this source is refusals, and
that is the finding rather than a shortfall. A tender notice tells a
bidder WHO is buying, UNDER WHAT PROCESS, and BY WHEN. It does not tell
them HOW MUCH. The quantity is in an attachment, and only 411 of 979
notices carry one.

THE THREE KINDS OF ABSENCE, which an extractor that returned None for all
of them would collapse into one:

    NO_COLUMN_IN_THIS_SOURCE   the source never carries this field. No
                               notice will ever have it. The remedy is a
                               different document, or none.
    EMPTY_IN_THIS_NOTICE       the column exists and this row is blank.
                               Another notice may well have it.

WHAT IS NEVER DONE. No field is inferred from another. A delivery region
is not an origin; a UNSPSC code is not a quantity; a contract end date
minus a start date is a duration only when BOTH are present, and 411 of
979 notices are missing at least one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Mapping, Optional, Tuple

from commerce.canadabuys import Notice

#: The field is not in this source's schema at all.
NO_COLUMN_IN_THIS_SOURCE = "NO_COLUMN_IN_THIS_SOURCE"
#: The column exists; this notice left it blank.
EMPTY_IN_THIS_NOTICE = "EMPTY_IN_THIS_NOTICE"
# A third code, PROSE_NOT_A_VALUE, was defined here and REMOVED after
# measurement. It was applied to `compliance` and `evaluation_criteria` on
# the assumption that evaluation rules arrive as paragraphs; over the 979
# open notices both are closed vocabularies (7 values and 17 atoms). With
# both corrected, no field could emit the code, and a refusal nothing can
# reach is a branch that passes every test by never running. It will
# return when a genuinely free-text field is extracted -- the
# past-performance requirement is one, and it is named in the founding
# record as unextractable rather than given a code that never fires.

#: The ten fields the founding order names, so the accounting is against
#: the ORDER's list rather than against whatever the source happened to
#: supply. An extractor graded on its own output always scores full marks.
REQUESTED_FIELDS: Tuple[str, ...] = (
    "buyer", "commodity", "quantity", "origin", "destination", "delivery_window",
    "incoterms", "compliance", "equipment", "evaluation_criteria", "duration",
)


@dataclass(frozen=True)
class Extracted:
    """One field: a value with the column it came from, or a refusal with
    a remedy. Never a bare None -- a None is three different absences
    wearing one face."""

    field: str
    value: Optional[object] = None
    from_column: Optional[str] = None
    code: Optional[str] = None
    remedy: Optional[str] = None

    @property
    def present(self) -> bool:
        return self.code is None


@dataclass(frozen=True)
class Opportunity:
    reference: str
    known_at: str
    fields: Mapping[str, Extracted]

    @property
    def present(self) -> Tuple[str, ...]:
        return tuple(k for k, v in self.fields.items() if v.present)

    @property
    def refused(self) -> Tuple[str, ...]:
        return tuple(k for k, v in self.fields.items() if not v.present)

    @property
    def accounted(self) -> bool:
        """Every requested field is in exactly one of the two lists."""
        return (len(self.present) + len(self.refused) == len(REQUESTED_FIELDS)
                and set(self.fields) == set(REQUESTED_FIELDS))

    def value(self, field: str) -> Optional[object]:
        entry = self.fields.get(field)
        return entry.value if entry is not None and entry.present else None


def _attachment_remedy(notice: Notice, what: str) -> str:
    """The remedy names a document when one exists, and says so plainly
    when none does. `unavailable` is not a remedy."""
    if notice.attachments:
        return (f"{what} is not in the notice feed. This notice links "
                f"{len(notice.attachments)} document(s); the first is {notice.attachments[0]}. "
                "Reading it is a separate acquisition this system has not built.")
    return (f"{what} is not in the notice feed and this notice links no document. There is no "
            "remedy within this source: it would have to be asked of the buyer.")


def extract(notice: Notice) -> Opportunity:
    """Project one notice onto the order's ten fields, accounting for
    every one."""
    fields: Dict[str, Extracted] = {}

    def present(name: str, value: object, column: str) -> None:
        fields[name] = Extracted(field=name, value=value, from_column=column)

    def refuse(name: str, code: str, remedy: str) -> None:
        fields[name] = Extracted(field=name, code=code, remedy=remedy)

    present("buyer", notice.buyer, "contractingEntityName")

    if notice.unspsc:
        present("commodity", notice.unspsc, "unspsc")
    else:
        refuse("commodity", EMPTY_IN_THIS_NOTICE,
               "the UNSPSC column exists and this notice left it blank. 826 of 979 notices carry "
               "one, so another notice from the same buyer may. The title is prose and naming a "
               "commodity from it would be inference.")

    # The five with no column. The refusal says the SOURCE cannot carry
    # it, which is a different fact from this notice not having it, and
    # the difference decides whether looking at more notices would help.
    refuse("quantity", NO_COLUMN_IN_THIS_SOURCE, _attachment_remedy(notice, "quantity"))
    refuse("origin", NO_COLUMN_IN_THIS_SOURCE,
           "the feed has no origin concept at all: a notice states where delivery is required, "
           "never where goods come from. Origin is the bidder's decision, not the buyer's fact.")
    refuse("incoterms", NO_COLUMN_IN_THIS_SOURCE, _attachment_remedy(notice, "the delivery term"))
    refuse("equipment", NO_COLUMN_IN_THIS_SOURCE, _attachment_remedy(notice, "equipment"))

    if notice.delivery_regions:
        # A SET of named regions, not a place. `*Canada` and a list of ten
        # provinces are both legitimate values and neither is an address.
        present("destination", notice.delivery_regions, "regionsOfDelivery")
    else:
        refuse("destination", EMPTY_IN_THIS_NOTICE,
               "the regionsOfDelivery column exists and this notice left it blank (843 of 979 "
               "carry it). The buyer's own address is in the feed and is NOT the destination.")

    if notice.expected_start and notice.expected_end:
        present("delivery_window", (notice.expected_start, notice.expected_end),
                "expectedContractStartDate + expectedContractEndDate")
        present("duration", (notice.expected_start, notice.expected_end),
                "expectedContractStartDate + expectedContractEndDate")
    else:
        missing = ("expectedContractStartDate" if not notice.expected_start
                   else "expectedContractEndDate")
        detail = (f"{missing} is blank. Start is present on 568 of 979 notices and end on 512, so "
                  "this is common rather than exceptional. The tender CLOSING date is in the feed "
                  "and is when bids are due, not when goods are wanted — substituting it would be "
                  "inference from a different field.")
        refuse("delivery_window", EMPTY_IN_THIS_NOTICE, detail)
        refuse("duration", EMPTY_IN_THIS_NOTICE,
               "a duration needs both endpoints. " + detail)

    # CORRECTED AFTER MEASUREMENT. An earlier draft refused both of these
    # as PROSE_NOT_A_VALUE on the assumption that evaluation rules arrive
    # as paragraphs. Measured over the 979 open notices, selectionCriteria
    # takes SEVEN distinct values and tradeAgreements resolves to
    # SEVENTEEN atoms in the same multi-valued cell shape as the delivery
    # regions. Both are closed vocabularies. Refusing them was the mirror
    # of the defect this module guards against: it under-reported what the
    # source can answer, and a reader would have concluded the feed cannot
    # say how bids are evaluated when it says so on 800 of 979 notices.
    if notice.trade_agreements:
        present("compliance", notice.trade_agreements, "tradeAgreements")
    else:
        refuse("compliance", EMPTY_IN_THIS_NOTICE,
               "the tradeAgreements column exists and this notice left it blank (977 of 979 carry "
               "it). The set names which agreements govern; it does not name the clauses, which "
               "are in the solicitation document.")

    if notice.selection_criteria:
        present("evaluation_criteria", notice.selection_criteria, "selectionCriteria")
    else:
        refuse("evaluation_criteria", EMPTY_IN_THIS_NOTICE,
               "the selectionCriteria column exists and this notice left it blank (800 of 979 "
               "carry one of seven values). `Not applicable` is itself one of the seven and is a "
               "stated criterion, not an absence — the two must not be collapsed.")

    return Opportunity(reference=notice.reference_number, known_at=notice.known_at, fields=fields)


@dataclass(frozen=True)
class ExtractionCensus:
    """What a whole feed's worth of extraction actually yielded.

    Reported per FIELD rather than per notice, because the useful question
    is not `how complete was this notice` but `which of the order's ten
    fields can this source ever answer`. Measured over the feed, four of
    them are answered never.
    """

    notices: int
    present_by_field: Mapping[str, int]
    refused_by_field: Mapping[str, Mapping[str, int]]
    never_answered: Tuple[str, ...]
    empty_because: Optional[str] = None


def census(opportunities: Tuple[Opportunity, ...]) -> ExtractionCensus:
    present: Dict[str, int] = {name: 0 for name in REQUESTED_FIELDS}
    refused: Dict[str, Dict[str, int]] = {name: {} for name in REQUESTED_FIELDS}
    for opportunity in opportunities:
        for name in REQUESTED_FIELDS:
            entry = opportunity.fields[name]
            if entry.present:
                present[name] += 1
            else:
                code = entry.code or "UNCODED"
                refused[name][code] = refused[name].get(code, 0) + 1
    empty_because = None
    if not opportunities:
        empty_because = ("NO_NOTICES_TO_EXTRACT_FROM: the census ran over an empty set, so it "
                         "reports nothing about the source's coverage. This is not a finding that "
                         "the source answers no fields.")
    return ExtractionCensus(
        notices=len(opportunities),
        present_by_field=present,
        refused_by_field={k: dict(v) for k, v in refused.items()},
        never_answered=tuple(name for name in REQUESTED_FIELDS
                             if opportunities and present[name] == 0),
        empty_because=empty_because,
    )


def render(opportunity: Opportunity) -> str:
    lines = [f"OPPORTUNITY {opportunity.reference} (known at {opportunity.known_at})"]
    for name in REQUESTED_FIELDS:
        entry = opportunity.fields[name]
        if entry.present:
            lines.append(f"  {name:<20} {entry.value}   [{entry.from_column}]")
        else:
            lines.append(f"  {name:<20} REFUSED {entry.code}")
            lines.append(f"  {'':<20} remedy: {entry.remedy}")
    return "\n".join(lines)
