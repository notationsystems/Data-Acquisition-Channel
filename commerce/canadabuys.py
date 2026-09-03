"""PC-2 — the CanadaBuys adapter, built only against what recon proved
parseable (architecture/canadabuys_recon.yaml).

THE DEGRADATION LADDER. Every retrieval lands on exactly one rung and the
rung is carried on the result rather than inferred from whether the list
is empty. The rungs are DISTINCT states, not severities:

    LIVE                  bytes arrived and parsed, rows present
    PUBLISHED_NO_ROWS     bytes arrived and parsed, header only, zero rows
    UNPARSEABLE           bytes arrived and are not the format claimed
    UNREACHABLE           no bytes

PUBLISHED_NO_ROWS is the rung recon met on its first successful probe: a
2904-byte file, HTTP 200, a well-formed 67-field header, and nothing
under it. An adapter that returned `[]` for that would be
indistinguishable from one that succeeded and found nothing worth
reporting -- and from one whose parser broke. Which nothing it is, is the
whole question, so it is a rung.

ROW ACCOUNTING. Every notice in the bytes leaves this module in exactly
one of three buckets: admitted, rejected with a reason, or filtered with
the predicate that filtered it NAMED. The three conserve against the row
count, asserted. A filter whose predicate is not printed is a silent
filter, which is defect class 1.

WHAT THIS ADAPTER WILL NOT CARRY. Thirteen of the source's sixty-seven
columns are `contactInfo*` -- a person's name, email, phone, fax and
address, populated on essentially every notice. The projection below has
no field for any of them. This is not a filter applied on the way out; it
is the absence of a place to put the value, which is the only version of
the rule that survives a second reader being added later.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

#: The rungs. Carried on the result, never inferred from list length.
LIVE = "LIVE"
PUBLISHED_NO_ROWS = "PUBLISHED_NO_ROWS"
UNPARSEABLE = "UNPARSEABLE"
UNREACHABLE = "UNREACHABLE"

#: The feed answered and had nothing in it. Distinct from both failures
#: below and from a filter that rejected everything.
FEED_PUBLISHED_NO_ROWS = "FEED_PUBLISHED_NO_ROWS"
#: Bytes arrived that are not the format the source claims.
FEED_IS_NOT_THE_FORMAT_IT_CLAIMS = "FEED_IS_NOT_THE_FORMAT_IT_CLAIMS"
#: The header does not carry the columns this adapter was built against.
#: The source changed shape; refusing beats parsing by position.
FEED_HEADER_LACKS_EXPECTED_COLUMNS = "FEED_HEADER_LACKS_EXPECTED_COLUMNS"
#: A row with no reference number. It cannot be addressed, amended or
#: de-duplicated, so it is rejected rather than given a synthetic id.
NOTICE_CARRIES_NO_REFERENCE_NUMBER = "NOTICE_CARRIES_NO_REFERENCE_NUMBER"
#: A row with no publication date. `known_at` would have to be invented,
#: and an invented known_at silently defeats every as-known-then query.
NOTICE_CARRIES_NO_PUBLICATION_DATE = "NOTICE_CARRIES_NO_PUBLICATION_DATE"

#: Class 7, applied to the admitted set.
NONE_ADMITTED_BECAUSE_THE_FEED_WAS_EMPTY = "NONE_ADMITTED_BECAUSE_THE_FEED_WAS_EMPTY"
NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED = "NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED"
NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_FILTERED = "NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_FILTERED"
NONE_ADMITTED_BECAUSE_THE_FEED_COULD_NOT_BE_READ = "NONE_ADMITTED_BECAUSE_THE_FEED_COULD_NOT_BE_READ"

#: Columns this adapter refuses to carry. Matched by prefix so a column
#: added upstream (`contactInfoMobile`) is excluded on arrival rather than
#: on the day someone notices it.
PERSON_COLUMN_PREFIX = "contactInfo"

#: The columns the adapter was built against, all measured 979/979 by
#: recon. If the header stops carrying these, the source changed shape.
REQUIRED_COLUMNS = (
    "title-titre-eng",
    "referenceNumber-numeroReference",
    "solicitationNumber-numeroSollicitation",
    "publicationDate-datePublication",
    "tenderClosingDate-appelOffresDateCloture",
    "procurementCategory-categorieApprovisionnement",
    "procurementMethod-methodeApprovisionnement-eng",
    "contractingEntityName-nomEntitContractante-eng",
)


def _multi(cell: Optional[str]) -> FrozenSet[str]:
    """Parse a newline-delimited, asterisk-prefixed cell into a SET.

    Recon measured this shape on `procurementCategory` and
    `regionsOfDelivery`. Read as a scalar, `*GD\\n*SRV` becomes its own
    category and a frequency table grows a seventh procurement category
    beside the six real ones. The value would not be wrong; the basis of
    the count would be.
    """
    if not cell:
        return frozenset()
    parts = (piece.strip().lstrip("*").strip() for piece in cell.replace("\r", "").split("\n"))
    return frozenset(piece for piece in parts if piece)


@dataclass(frozen=True)
class Notice:
    """The projection. There is no field here for a person."""

    reference_number: str
    solicitation_number: str
    title: str
    #: The notice's OWN publication date, carried as known_at. Not the
    #: retrieval time: the world could have known this when it was
    #: published, and a bid post-mortem asks the first question.
    known_at: str
    closing_at: str
    buyer: str
    categories: FrozenSet[str]
    delivery_regions: FrozenSet[str]
    procurement_method: str
    description: Optional[str] = None
    unspsc: Optional[str] = None
    expected_start: Optional[str] = None
    expected_end: Optional[str] = None
    notice_url: Optional[str] = None
    attachments: Tuple[str, ...] = ()
    #: A CLOSED vocabulary, measured at 7 distinct values over 979 notices
    #: -- not free text. An earlier draft of the extractor refused this as
    #: prose and under-reported what the source answers.
    selection_criteria: Optional[str] = None
    #: Multi-valued, measured at 17 distinct atoms over 407 distinct cells.
    trade_agreements: FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class Rejection:
    reference: str
    code: str
    reason: str


@dataclass(frozen=True)
class Filtered:
    reference: str
    #: The PREDICATE, printed. A filter whose rule is not stated is a
    #: silent filter, and the reader cannot tell it from an empty source.
    predicate: str


@dataclass(frozen=True)
class Retrieval:
    """One retrieval, accounted for.

    `rung` is authoritative. A caller must never infer success from
    `len(notices)`, because three different rungs can produce zero.
    """

    rung: str
    source_url: str
    retrieved_at: str
    notices: Tuple[Notice, ...] = ()
    rejected: Tuple[Rejection, ...] = ()
    filtered: Tuple[Filtered, ...] = ()
    rows_in_feed: int = 0
    last_modified: Optional[str] = None
    empty_because: Optional[str] = None
    refusal: Optional[str] = None

    @property
    def accounted(self) -> int:
        return len(self.notices) + len(self.rejected) + len(self.filtered)

    @property
    def conserves(self) -> bool:
        return self.accounted == self.rows_in_feed


def parse_feed(
    raw: str,
    *,
    source_url: str,
    retrieved_at: str,
    last_modified: Optional[str] = None,
    keep: Optional[Callable[[Notice], bool]] = None,
    predicate_name: str = "",
) -> Retrieval:
    """Parse captured bytes into an accounted retrieval.

    `keep` is optional and `predicate_name` is REQUIRED alongside it: a
    filter that cannot say what it filtered on is refused at the call
    site rather than producing an unattributable short list.
    """
    if keep is not None and not predicate_name.strip():
        raise ValueError(
            "a filter must name its predicate. An unnamed filter produces a short list that "
            "the reader cannot distinguish from a short source."
        )

    def _empty(rung: str, refusal: str, because: str) -> Retrieval:
        return Retrieval(rung=rung, source_url=source_url, retrieved_at=retrieved_at,
                         last_modified=last_modified, refusal=refusal, empty_because=because)

    try:
        reader = csv.DictReader(io.StringIO(raw))
        fieldnames = reader.fieldnames
    except csv.Error as exc:  # pragma: no cover - defensive
        return _empty(UNPARSEABLE, f"{FEED_IS_NOT_THE_FORMAT_IT_CLAIMS}: {exc}",
                      f"{NONE_ADMITTED_BECAUSE_THE_FEED_COULD_NOT_BE_READ}: the bytes are not CSV.")

    if not fieldnames:
        return _empty(UNPARSEABLE,
                      f"{FEED_IS_NOT_THE_FORMAT_IT_CLAIMS}: no header row.",
                      f"{NONE_ADMITTED_BECAUSE_THE_FEED_COULD_NOT_BE_READ}: the bytes carry no "
                      "header, so not even the shape could be confirmed.")

    # The BOM the source ships is stripped by utf-8-sig at read time; if a
    # caller hands us bytes decoded as plain utf-8 it survives into the
    # first field name, so it is removed here too rather than causing a
    # spurious "the source changed shape".
    header = {name.lstrip("﻿") for name in fieldnames}
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        return _empty(
            UNPARSEABLE,
            f"{FEED_HEADER_LACKS_EXPECTED_COLUMNS}: {missing}. Recon measured every one of these "
            "on 979 of 979 notices, so their absence means the source changed shape. Parsing by "
            "position from here would produce rows that look right and are not.",
            f"{NONE_ADMITTED_BECAUSE_THE_FEED_COULD_NOT_BE_READ}: the header is not the one this "
            "adapter was built against.",
        )

    rows = list(reader)
    if not rows:
        return _empty(
            PUBLISHED_NO_ROWS,
            f"{FEED_PUBLISHED_NO_ROWS}: a well-formed {len(fieldnames)}-field header and zero "
            "rows. The feed answered; it had nothing in it.",
            f"{NONE_ADMITTED_BECAUSE_THE_FEED_WAS_EMPTY}: the source published a header and no "
            "notices. This is NOT a transport failure and NOT a filter rejecting everything; "
            "which of those it looks like from a bare empty list is the reason it is a rung.",
        )

    admitted: List[Notice] = []
    rejected: List[Rejection] = []
    filtered: List[Filtered] = []

    def cell(row: Dict[str, Optional[str]], key: str) -> str:
        return (row.get(key) or "").strip()

    for position, row in enumerate(rows):
        # The BOM again: DictReader keys the first column with it attached
        # when the caller decoded as plain utf-8.
        row = {(k or "").lstrip("﻿"): v for k, v in row.items()}
        reference = cell(row, "referenceNumber-numeroReference")
        if not reference:
            rejected.append(Rejection(
                reference=f"<row {position}>", code=NOTICE_CARRIES_NO_REFERENCE_NUMBER,
                reason="the notice cannot be addressed, amended or de-duplicated. A synthetic id "
                       "would make the next amendment arrive as a second notice."))
            continue
        published = cell(row, "publicationDate-datePublication")
        if not published:
            rejected.append(Rejection(
                reference=reference, code=NOTICE_CARRIES_NO_PUBLICATION_DATE,
                reason="known_at would have to be invented. An invented known_at defeats every "
                       "as-known-then query silently, which is the one query a bid post-mortem asks."))
            continue

        attachments = tuple(
            url.strip() for url in cell(row, "attachment-piecesJointes-eng").split(",")
            if url.strip())

        notice = Notice(
            reference_number=reference,
            solicitation_number=cell(row, "solicitationNumber-numeroSollicitation"),
            title=cell(row, "title-titre-eng"),
            known_at=published,
            closing_at=cell(row, "tenderClosingDate-appelOffresDateCloture"),
            buyer=cell(row, "contractingEntityName-nomEntitContractante-eng"),
            categories=_multi(row.get("procurementCategory-categorieApprovisionnement")),
            delivery_regions=_multi(row.get("regionsOfDelivery-regionsLivraison-eng")),
            procurement_method=cell(row, "procurementMethod-methodeApprovisionnement-eng"),
            description=cell(row, "tenderDescription-descriptionAppelOffres-eng") or None,
            unspsc=cell(row, "unspsc") or None,
            expected_start=cell(row, "expectedContractStartDate-dateDebutContratPrevue") or None,
            expected_end=cell(row, "expectedContractEndDate-dateFinContratPrevue") or None,
            notice_url=cell(row, "noticeURL-URLavis-eng") or None,
            attachments=attachments,
            selection_criteria=cell(row, "selectionCriteria-criteresSelection-eng") or None,
            trade_agreements=_multi(row.get("tradeAgreements-accordsCommerciaux-eng")),
        )
        if keep is not None and not keep(notice):
            filtered.append(Filtered(reference=reference, predicate=predicate_name))
            continue
        admitted.append(notice)

    empty_because: Optional[str] = None
    if not admitted:
        if rejected and not filtered:
            empty_because = (f"{NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED}: {len(rejected)} "
                             "row(s) arrived and none could be admitted. The feed is healthy and "
                             "this adapter cannot read it.")
        elif filtered and not rejected:
            empty_because = (f"{NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_FILTERED}: {len(filtered)} "
                             f"row(s) arrived and every one failed {predicate_name!r}. The source "
                             "has notices; none of them are the ones asked for.")
        else:
            empty_because = (f"{NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED}: {len(rejected)} "
                             f"rejected and {len(filtered)} filtered by {predicate_name!r}, "
                             "leaving nothing.")

    return Retrieval(
        rung=LIVE, source_url=source_url, retrieved_at=retrieved_at,
        last_modified=last_modified, notices=tuple(admitted), rejected=tuple(rejected),
        filtered=tuple(filtered), rows_in_feed=len(rows), empty_because=empty_because)


def unreachable(source_url: str, retrieved_at: str, detail: str) -> Retrieval:
    """The bottom rung. Named so a caller cannot reach it by accident.

    `detail` is the transport's own words and is usually a fragment
    ("connection reset"). It is composed INTO a sentence rather than used
    as one: a warrant that reads `connection reset` tells the operator the
    transport failed and not what that means for the reading, which is the
    status-word-instead-of-a-sentence failure the vacuity guards exist to
    catch. This one was caught by that guard, on this module.
    """
    return Retrieval(
        rung=UNREACHABLE, source_url=source_url, retrieved_at=retrieved_at,
        refusal=f"{UNREACHABLE}: {detail}",
        empty_because=(
            f"{NONE_ADMITTED_BECAUSE_THE_FEED_COULD_NOT_BE_READ}: no bytes arrived from "
            f"{source_url} ({detail}). Nothing is known about what the source holds right now — "
            "this is not evidence that it published nothing."))


def render(retrieval: Retrieval) -> str:
    """The retrieval as an operator reads it.

    Rejections and filters print WITH the count. A notice that is not in
    the list and not visibly accounted for will be assumed to have been
    admitted.
    """
    lines = [f"CANADABUYS {retrieval.rung} — {retrieval.source_url}",
             f"  retrieved {retrieval.retrieved_at}"
             + (f", source last modified {retrieval.last_modified}" if retrieval.last_modified else ""),
             f"  rows in feed {retrieval.rows_in_feed}; admitted {len(retrieval.notices)}, "
             f"rejected {len(retrieval.rejected)}, filtered {len(retrieval.filtered)}"]
    if not retrieval.conserves:
        lines.append(f"  ! ACCOUNTING DOES NOT CONSERVE: {retrieval.accounted} accounted for "
                     f"{retrieval.rows_in_feed} rows")
    if retrieval.refusal:
        lines.append(f"  REFUSED: {retrieval.refusal}")
    if retrieval.empty_because:
        lines.append(f"  (none admitted) {retrieval.empty_because}")
    for rejection in retrieval.rejected:
        lines.append(f"  REJECTED {rejection.reference} ({rejection.code}): {rejection.reason}")
    for drop in retrieval.filtered:
        lines.append(f"  FILTERED {drop.reference} by predicate {drop.predicate!r}")
    return "\n".join(lines)


def person_columns(fieldnames: Sequence[str]) -> Tuple[str, ...]:
    """The columns this adapter refuses to carry, from a real header.

    Exposed so the guard test derives its list from the source rather than
    from a list someone typed -- the coverage-by-enumeration defect this
    account has already filed once.
    """
    return tuple(name for name in fieldnames
                 if name.lstrip("﻿").startswith(PERSON_COLUMN_PREFIX))
