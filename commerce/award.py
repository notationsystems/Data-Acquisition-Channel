"""The award feed — the outcome side of a bid, and the reason a contract
value is not a number.

WHY THIS IS THE HIGHEST-VALUE INPUT IN THE PROGRAMME. An award notice is
an outcome the firm did not choose, produced by the world, arriving
whether or not anyone was watching. Paired with a bid it makes
`curation: independent` true by construction -- which is the thing
forty-five phases of instrument-building could not produce for itself.
The join is `solicitationNumber`, populated on 3056 of 3056.

THE MEASUREMENT THAT SHAPES THIS MODULE. Over the 3056 awards in the
2026-2027 file:

    amount == 0 while total > 0        831   27.2%
    total == 0 while amount > 0         62    2.0%
    both zero                          807   26.4%
    the two columns DISAGREE          1008   33.0%

So 893 rows -- 29.2% -- are misread as a contract worth nothing by
WHICHEVER SINGLE COLUMN YOU PICK. Read `contractAmount` alone and 831
real contracts vanish; read `totalContractValue` alone and 62 do. There
is no safe default and no column that is right more of the time in a way
that helps, because the failure is not noise: the two columns are
measured on DIFFERENT BASES. One is the value of this amendment, the
other the cumulative contract.

THEREFORE `Award.value` DOES NOT EXIST. There is no scalar to ask for.
A caller wanting a number must name the basis it wants -- and a bid
post-mortem must therefore state which basis it bid on before it can be
scored, which is the correct thing to force it to do.

THE SUPPLIER NAME IS A COMPANY, WITH ONE HAZARD NAMED. `supplierLegalName`
is a business identity in a public procurement record and is carried. The
hazard is that a sole proprietor's legal name IS a person's name, and
this module cannot tell those apart. It is carried because the winning
bidder's identity is the point of an award notice, and the hazard is
recorded rather than solved by dropping the field.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from commerce.canadabuys import (LIVE, PUBLISHED_NO_ROWS, UNPARSEABLE, Filtered, Rejection,
                                 _multi)
from commerce.stores import Evidence, Provenance, Quantity

#: The two bases the feed reports money on. Named, because the whole
#: module exists to stop them being added together.
AMENDMENT = "this_amendment"
CUMULATIVE = "cumulative_contract"
BASES: FrozenSet[str] = frozenset({AMENDMENT, CUMULATIVE})

AWARD_CARRIES_NO_SOLICITATION = "AWARD_CARRIES_NO_SOLICITATION"
AWARD_CARRIES_NO_AWARD_DATE = "AWARD_CARRIES_NO_AWARD_DATE"
FEED_HEADER_LACKS_EXPECTED_COLUMNS = "FEED_HEADER_LACKS_EXPECTED_COLUMNS"
VALUE_REQUESTED_WITHOUT_A_BASIS = "VALUE_REQUESTED_WITHOUT_A_BASIS"
VALUE_IS_ZERO_ON_THIS_BASIS_AND_NOT_THE_OTHER = "VALUE_IS_ZERO_ON_THIS_BASIS_AND_NOT_THE_OTHER"
VALUE_ABSENT_ON_THIS_BASIS = "VALUE_ABSENT_ON_THIS_BASIS"
AMOUNT_WITHOUT_A_CURRENCY = "AMOUNT_WITHOUT_A_CURRENCY"

NONE_ADMITTED_BECAUSE_THE_FEED_WAS_EMPTY = "NONE_ADMITTED_BECAUSE_THE_FEED_WAS_EMPTY"
NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED = "NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED"
NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_FILTERED = "NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_FILTERED"

PERSON_COLUMN_PREFIX = "contactInfo"

REQUIRED_COLUMNS: Tuple[str, ...] = (
    "solicitationNumber-numeroSollicitation",
    "publicationDate-datePublication",
    "contractAwardDate-dateAttributionContrat",
    "contractAmount-montantContrat",
    "totalContractValue-valeurTotaleContrat",
    "contractCurrency-contratMonnaie",
    "supplierLegalName-nomLegalFournisseur-eng",
    "awardStatus-attributionStatut-eng",
)

#: The measurement, pinned so a change to the feed that moves it is loud.
MEASURED_MISREAD_AS_ZERO = 893
MEASURED_ROWS = 3056


class AwardRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class AwardValue:
    """The two money columns, kept apart.

    Deliberately has no `.value`, no `.amount`, and no `__float__`. Every
    convenience that would let a caller get one number out of this without
    naming a basis is the defect this class exists to prevent.
    """

    amendment: Optional[float]
    cumulative: Optional[float]
    currency: Optional[str]

    def on(self, basis: str) -> float:
        """The figure on ONE named basis, or a refusal.

        `basis` is required and has no default. A default here would be a
        column chosen by this module on behalf of every caller, which is
        exactly the choice that misreads 29.2% of awards.
        """
        if basis not in BASES:
            raise AwardRefusal(
                VALUE_REQUESTED_WITHOUT_A_BASIS,
                f"{basis!r} is not a basis. An award reports money on two: {sorted(BASES)}. "
                f"Measured, {MEASURED_MISREAD_AS_ZERO} of {MEASURED_ROWS} awards are misread as "
                "worth nothing by whichever single column is picked, so there is no default to "
                "fall back on.",
            )
        figure = self.amendment if basis == AMENDMENT else self.cumulative
        other = self.cumulative if basis == AMENDMENT else self.amendment
        if figure is None:
            raise AwardRefusal(
                VALUE_ABSENT_ON_THIS_BASIS,
                f"this award states no figure on the {basis} basis.",
            )
        if not self.currency:
            raise AwardRefusal(
                AMOUNT_WITHOUT_A_CURRENCY,
                f"{figure} of what? The currency column is blank on this award, and a figure "
                "without one sums correctly and means nothing.",
            )
        if figure == 0.0 and other not in (None, 0.0):
            raise AwardRefusal(
                VALUE_IS_ZERO_ON_THIS_BASIS_AND_NOT_THE_OTHER,
                f"the {basis} basis reports 0.00 while the other reports {other}. This is the "
                f"measured case: {MEASURED_MISREAD_AS_ZERO} of {MEASURED_ROWS} awards read as "
                "worthless on one basis and not the other. Taking the zero would record a real "
                "contract as nothing.",
            )
        return figure

    @property
    def bases_disagree(self) -> bool:
        return (self.amendment is not None and self.cumulative is not None
                and self.amendment != self.cumulative)

    @property
    def zero_on_exactly_one_basis(self) -> bool:
        pair = (self.amendment, self.cumulative)
        return (0.0 in pair and any(v not in (None, 0.0) for v in pair))


@dataclass(frozen=True)
class Award:
    solicitation: str
    reference: str
    known_at: str
    awarded_at: str
    supplier: str
    status: str
    value: AwardValue
    contract_number: Optional[str] = None
    categories: FrozenSet[str] = frozenset()
    delivery_regions: FrozenSet[str] = frozenset()

    @property
    def supplier_may_be_a_natural_person(self) -> bool:
        """A sole proprietor's legal name IS a person's name.

        This module cannot tell a company from a person by inspecting a
        string, so it does not try. The flag says the hazard exists on
        every row rather than pretending some rows are safe.
        """
        return True


@dataclass(frozen=True)
class AwardRetrieval:
    rung: str
    source_url: str
    retrieved_at: str
    awards: Tuple[Award, ...] = ()
    rejected: Tuple[Rejection, ...] = ()
    filtered: Tuple[Filtered, ...] = ()
    rows_in_feed: int = 0
    empty_because: Optional[str] = None
    refusal: Optional[str] = None

    @property
    def accounted(self) -> int:
        return len(self.awards) + len(self.rejected) + len(self.filtered)

    @property
    def conserves(self) -> bool:
        return self.accounted == self.rows_in_feed


def _number(cell: str) -> Optional[float]:
    cell = (cell or "").strip()
    if not cell:
        return None
    try:
        return float(cell)
    except ValueError:
        return None


def parse_awards(raw: str, *, source_url: str, retrieved_at: str,
                 keep: Optional[Callable[[Award], bool]] = None,
                 predicate_name: str = "") -> AwardRetrieval:
    """Parse captured award bytes into an accounted retrieval."""
    if keep is not None and not predicate_name.strip():
        raise ValueError("a filter must name its predicate.")

    reader = csv.DictReader(io.StringIO(raw))
    fieldnames = reader.fieldnames
    if not fieldnames:
        return AwardRetrieval(UNPARSEABLE, source_url, retrieved_at,
                              refusal=f"{FEED_HEADER_LACKS_EXPECTED_COLUMNS}: no header.",
                              empty_because="NONE_ADMITTED_BECAUSE_THE_FEED_COULD_NOT_BE_READ: "
                                            "the bytes carry no header.")
    header = {name.lstrip("﻿") for name in fieldnames}
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        return AwardRetrieval(
            UNPARSEABLE, source_url, retrieved_at,
            refusal=f"{FEED_HEADER_LACKS_EXPECTED_COLUMNS}: {missing}.",
            empty_because="NONE_ADMITTED_BECAUSE_THE_FEED_COULD_NOT_BE_READ: the header is not "
                          "the one this adapter was built against.")

    rows = list(reader)
    if not rows:
        return AwardRetrieval(
            PUBLISHED_NO_ROWS, source_url, retrieved_at,
            empty_because=f"{NONE_ADMITTED_BECAUSE_THE_FEED_WAS_EMPTY}: a well-formed "
                          f"{len(fieldnames)}-field header and zero rows. No award was published "
                          "in this window; that is not a transport failure and not a filter.")

    admitted: List[Award] = []
    rejected: List[Rejection] = []
    filtered: List[Filtered] = []

    def cell(row: Mapping[str, Optional[str]], key: str) -> str:
        return (row.get(key) or "").strip()

    for position, row in enumerate(rows):
        row = {(k or "").lstrip("﻿"): v for k, v in row.items()}
        solicitation = cell(row, "solicitationNumber-numeroSollicitation")
        if not solicitation:
            rejected.append(Rejection(
                f"<row {position}>", AWARD_CARRIES_NO_SOLICITATION,
                "the award cannot be joined to the tender it settles, which is the only reason "
                "this feed is worth reading."))
            continue
        awarded = cell(row, "contractAwardDate-dateAttributionContrat")
        if not awarded:
            rejected.append(Rejection(
                solicitation, AWARD_CARRIES_NO_AWARD_DATE,
                "an outcome with no date cannot take part in an as-known-then question."))
            continue

        award = Award(
            solicitation=solicitation,
            reference=cell(row, "referenceNumber-numeroReference"),
            known_at=cell(row, "publicationDate-datePublication"),
            awarded_at=awarded,
            supplier=cell(row, "supplierLegalName-nomLegalFournisseur-eng"),
            status=cell(row, "awardStatus-attributionStatut-eng"),
            contract_number=cell(row, "contractNumber-numeroContrat") or None,
            value=AwardValue(
                amendment=_number(cell(row, "contractAmount-montantContrat")),
                cumulative=_number(cell(row, "totalContractValue-valeurTotaleContrat")),
                currency=cell(row, "contractCurrency-contratMonnaie") or None,
            ),
            categories=_multi(row.get("procurementCategory-categorieApprovisionnement")),
            delivery_regions=_multi(row.get("regionsOfDelivery-regionsLivraison-eng")),
        )
        if keep is not None and not keep(award):
            filtered.append(Filtered(solicitation, predicate_name))
            continue
        admitted.append(award)

    empty_because: Optional[str] = None
    if not admitted:
        if rejected and not filtered:
            empty_because = (f"{NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED}: {len(rejected)} "
                             "row(s) arrived and none could be admitted.")
        elif filtered:
            empty_because = (f"{NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_FILTERED}: {len(filtered)} "
                             f"row(s) arrived and every one failed {predicate_name!r}.")

    return AwardRetrieval(LIVE, source_url, retrieved_at, tuple(admitted), tuple(rejected),
                          tuple(filtered), len(rows), empty_because)


# ---------------------------------------------------------------------
# The bid post-mortem. This is what the whole feed is for.
# ---------------------------------------------------------------------

BID_HAS_NO_AWARD_YET = "BID_HAS_NO_AWARD_YET"
BID_STATED_NO_BASIS = "BID_STATED_NO_BASIS"

#: Class 7 on the post-mortem set.
NO_POSTMORTEMS_BECAUSE_NO_BIDS_WERE_SUBMITTED = "NO_POSTMORTEMS_BECAUSE_NO_BIDS_WERE_SUBMITTED"
NO_POSTMORTEMS_BECAUSE_NO_AWARD_HAS_PUBLISHED_YET = (
    "NO_POSTMORTEMS_BECAUSE_NO_AWARD_HAS_PUBLISHED_YET")


def outcome_for(award: Award, *, basis: str, subject: str,
                retrieved_at: str) -> Evidence:
    """An award as PC-1 evidence, on a NAMED basis.

    The basis is a required keyword and has no default, so a bid
    post-mortem must state which basis it bid on before it can be scored.
    That is the correct thing to force: a firm that cannot say whether it
    bid the amendment or the cumulative value does not have a comparable
    number either.

    `known_at` is the award's PUBLICATION date, not the award date. The
    contract was awarded before the world could read about it, and a
    post-mortem asking what we knew must use the second.
    """
    figure = award.value.on(basis)
    return Evidence(
        subject=subject,
        quantity=Quantity(figure, award.value.currency or "", f"award:{basis}"),
        provenance=Provenance(source_id="canadabuys:awards", retrieved_at=retrieved_at,
                              known_at=award.known_at,
                              locator=award.contract_number),
        evidence_class="measured",
        period=award.awarded_at,
    )


@dataclass(frozen=True)
class PostMortemSet:
    matched: Tuple[Tuple[str, Award], ...]
    unawarded: Tuple[str, ...]
    empty_because: Optional[str] = None


def match_bids(bid_solicitations: Sequence[str],
               awards: Sequence[Award]) -> PostMortemSet:
    """Join submitted bids to published awards on solicitation number.

    An unmatched bid is UNAWARDED and stays visible. Measured on the live
    feeds, 966 open solicitations intersect 2118 awarded ones at only 38 --
    which is the right answer and not a broken join, because an open
    tender is by definition mostly not yet awarded. The ground truth
    arrives with a lag, and dropping the unmatched would hide it.
    """
    by_solicitation: Dict[str, Award] = {a.solicitation: a for a in awards}
    matched = [(b, by_solicitation[b]) for b in bid_solicitations if b in by_solicitation]
    unawarded = tuple(b for b in bid_solicitations if b not in by_solicitation)
    empty_because = None
    if not matched:
        if not bid_solicitations:
            empty_because = (f"{NO_POSTMORTEMS_BECAUSE_NO_BIDS_WERE_SUBMITTED}: nothing was bid, "
                             "so there is nothing to score. This is not a record of losing.")
        else:
            empty_because = (f"{NO_POSTMORTEMS_BECAUSE_NO_AWARD_HAS_PUBLISHED_YET}: "
                             f"{len(unawarded)} bid(s) submitted and none has a published award. "
                             "The outcome arrives with a lag; this is a wait, not a loss.")
    return PostMortemSet(tuple(matched), unawarded, empty_because)


def render(retrieval: AwardRetrieval) -> str:
    lines = [f"AWARDS {retrieval.rung} — {retrieval.source_url}",
             f"  rows {retrieval.rows_in_feed}; admitted {len(retrieval.awards)}, "
             f"rejected {len(retrieval.rejected)}, filtered {len(retrieval.filtered)}"]
    if not retrieval.conserves:
        lines.append(f"  ! ACCOUNTING DOES NOT CONSERVE: {retrieval.accounted}")
    if retrieval.empty_because:
        lines.append(f"  (none admitted) {retrieval.empty_because}")
    for award in retrieval.awards:
        value = award.value
        both = f"{value.amendment} / {value.cumulative} {value.currency or '(no currency)'}"
        flag = "  ! ZERO ON ONE BASIS ONLY" if value.zero_on_exactly_one_basis else ""
        lines.append(f"  {award.solicitation}  {award.supplier[:38]:<38} {both}{flag}")
    for rejection in retrieval.rejected:
        lines.append(f"  REJECTED {rejection.reference} ({rejection.code})")
    return "\n".join(lines)
