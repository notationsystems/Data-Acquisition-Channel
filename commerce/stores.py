"""PC-1 — three stores, decided in the first schema.

    EVIDENCE      what was observed          — sourced, never written by us
    COMMITMENTS   what we instructed or promised
    OUTCOMES      what actually happened     — observed, therefore evidence again

WHY THE SPLIT IS STRUCTURAL RATHER THAN A CONVENTION. A commitment is an
act upon the world, not an observation about it. It has no source, because
nothing observed it: the firm produced it. A store that accepts both ends
up holding "we promised Tuesday" alongside "the vessel sailed Tuesday"
with the same standing, and a system that cannot tell those apart starts
believing its own intentions. Retrofitting the split after commitments
have been written into a state store costs a reconciliation subsystem, so
it is taken here, first, before there is anything to reconcile.

WHAT EACH STORE KEEPS FROM THE EARLIER PROGRAMME. Provenance on evidence;
`known_at` separated from the period the value describes; refusal rather
than default; typed identity. Commitments additionally need what evidence
never did, because evidence is not an act: an ISSUER, an AUTHORITY under
which the firm was bound, IDEMPOTENCY so a retried send does not bind
twice, and a REVOCATION path.

THE PAIRING IS THE POINT. A commitment and the outcome for the same
subject are two claims about one quantity, which is what the divergence
machinery already handles: quoted versus invoiced, promised transit versus
actual, bid landed cost versus realized. `diverge()` below is that reuse,
and it carries the one guard the freight domain needs more than the
commodity domain did -- see DIVERGENCE_ACROSS_UNLIKE_BASIS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------
# Refusal codes. Each names an OBSERVABLE, never a cause it cannot
# establish -- the rule this account already applies to
# EVERY_RUN_DIFFERS_IN. `COMMITMENT_NAMES_NO_AUTHORITY` says the field is
# empty; it does not say the issuer lacked authority, which is a fact
# about the world no store can see.
# ---------------------------------------------------------------------

#: Evidence arrived with nothing saying where it came from.
EVIDENCE_CARRIES_NO_PROVENANCE = "EVIDENCE_CARRIES_NO_PROVENANCE"
#: Evidence arrived declaring no class. The vocabulary is owned elsewhere;
#: this layer asserts only that a declaration was made.
EVIDENCE_DECLARES_NO_CLASS = "EVIDENCE_DECLARES_NO_CLASS"
#: `known_at` precedes the period it describes -- the record claims the
#: world knew a thing before the thing had happened.
EVIDENCE_KNOWN_BEFORE_ITS_PERIOD = "EVIDENCE_KNOWN_BEFORE_ITS_PERIOD"

#: A commitment with no issuer. Someone bound the firm and the record does
#: not say who.
COMMITMENT_NAMES_NO_ISSUER = "COMMITMENT_NAMES_NO_ISSUER"
#: A commitment with no authority. NOT a claim that the issuer lacked
#: authority: the field is empty, which is the observable.
COMMITMENT_NAMES_NO_AUTHORITY = "COMMITMENT_NAMES_NO_AUTHORITY"
#: The authority's own validity window does not contain the issue date.
COMMITMENT_ISSUED_OUTSIDE_ITS_AUTHORITY_WINDOW = "COMMITMENT_ISSUED_OUTSIDE_ITS_AUTHORITY_WINDOW"
#: A commitment with no idempotency key. A retried send binds twice.
COMMITMENT_CARRIES_NO_IDEMPOTENCY_KEY = "COMMITMENT_CARRIES_NO_IDEMPOTENCY_KEY"
#: The same key already admitted DIFFERENT content. The observable is that
#: two bodies share one key, not which of them is correct.
COMMITMENT_KEY_REUSED_WITH_DIFFERENT_CONTENT = "COMMITMENT_KEY_REUSED_WITH_DIFFERENT_CONTENT"
#: Revoked before it was issued.
COMMITMENT_REVOKED_BEFORE_IT_WAS_ISSUED = "COMMITMENT_REVOKED_BEFORE_IT_WAS_ISSUED"

#: An outcome that references no commitment. An outcome is only an outcome
#: OF something; unreferenced, it is plain evidence and belongs in that store.
OUTCOME_REFERENCES_NO_COMMITMENT = "OUTCOME_REFERENCES_NO_COMMITMENT"
#: It references a commitment this store has never admitted.
OUTCOME_REFERENCES_AN_ABSENT_COMMITMENT = "OUTCOME_REFERENCES_AN_ABSENT_COMMITMENT"

#: A type offered to a store that does not hold it. The three stores
#: reject each other's types, as CanonicalState already rejects derived values.
WRONG_TYPE_FOR_THIS_STORE = "WRONG_TYPE_FOR_THIS_STORE"

#: Two claims about one quantity measured on DIFFERENT bases. The gap
#: between them is not a divergence, it is a unit error, and subtracting
#: them produces a number with no referent. The freight domain has this
#: worse than commodities did: gross vs net vs chargeable weight, TEU vs
#: tonnes vs cubic, all-in vs linehaul-plus-accessorials, spot vs
#: contract, DDP vs FOB, CAD vs USD at which date's rate.
DIVERGENCE_ACROSS_UNLIKE_BASIS = "DIVERGENCE_ACROSS_UNLIKE_BASIS"

# Class 7 applied to the pairing: an empty pairing is a claim and needs a
# warrant. These are three different afternoons and an empty list states none.
NO_PAIRS_BECAUSE_NO_COMMITMENTS_WERE_ISSUED = "NO_PAIRS_BECAUSE_NO_COMMITMENTS_WERE_ISSUED"
NO_PAIRS_BECAUSE_NO_OUTCOME_HAS_ARRIVED_YET = "NO_PAIRS_BECAUSE_NO_OUTCOME_HAS_ARRIVED_YET"
NO_PAIRS_BECAUSE_EVERY_COMMITMENT_WAS_REVOKED = "NO_PAIRS_BECAUSE_EVERY_COMMITMENT_WAS_REVOKED"
NO_PAIRS_BECAUSE_EVERY_PAIR_DIFFERED_IN_BASIS = "NO_PAIRS_BECAUSE_EVERY_PAIR_DIFFERED_IN_BASIS"


class StoreRefusal(ValueError):
    """Refused at a store boundary. Carries the code so a caller can act
    on the kind rather than parse the sentence."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------
# The quantity, and its basis. Every number in this system carries the
# basis it was measured on, because the only alternative is that the
# basis lives in a column name somewhere and is lost on the first join.
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Quantity:
    """A number that knows what it is measured on.

    `basis` is deliberately an open string rather than an enum. This layer
    does not own the freight vocabulary and inventing a closed one here
    would be the duplicate-vocabulary problem in a new place; what it
    enforces is that two numbers may only be compared when their bases
    agree EXACTLY. An unknown basis therefore fails safe -- it agrees with
    nothing, including itself when spelled differently.
    """

    value: float
    unit: str
    basis: str

    def comparable_with(self, other: "Quantity") -> bool:
        return self.unit == other.unit and self.basis == other.basis


@dataclass(frozen=True)
class Provenance:
    """Where a value came from, and when the world could have known it.

    `known_at` is separated from the period the value describes. That
    separation is what makes a bid post-mortem answer *what did we know
    when we bid* rather than *what do we know now*, and it is the single
    most valuable thing carried forward from the earlier programme.
    """

    source_id: str
    retrieved_at: str
    known_at: str
    #: Verbatim locator for the bytes this was read from, when one exists.
    locator: Optional[str] = None


@dataclass(frozen=True)
class Evidence:
    """Observed. Never written by us."""

    subject: str
    quantity: Quantity
    provenance: Provenance
    #: Declared, not validated here. The admissible set is owned by
    #: `epistemics.evidence_class`, which this layer may not import.
    evidence_class: str
    #: The period the value describes, distinct from `provenance.known_at`.
    period: Optional[str] = None


@dataclass(frozen=True)
class Authority:
    """The right under which the firm may bind itself.

    Recorded ON the commitment rather than looked up at read time: the
    question a post-mortem asks is *under what authority was this issued*,
    and an authority resolved later answers *what authority exists now*.
    """

    holder: str
    instrument: str
    valid_from: str
    valid_until: str

    def covers(self, when: str) -> bool:
        return self.valid_from <= when <= self.valid_until


@dataclass(frozen=True)
class Commitment:
    """An act upon the world. It has no source; the firm produced it."""

    subject: str
    quantity: Quantity
    issuer: str
    authority: Optional[Authority]
    idempotency_key: str
    issued_at: str
    counterparty: Optional[str] = None
    revoked_at: Optional[str] = None

    @property
    def is_live(self) -> bool:
        return self.revoked_at is None


@dataclass(frozen=True)
class Outcome:
    """What actually happened. Observed, and therefore evidence again --
    which is why it CARRIES evidence rather than restating its fields."""

    commitment_key: str
    observed: Evidence


@dataclass(frozen=True)
class Divergence:
    """Two claims about one quantity, and the gap between them.

    `residual` is None when the bases disagree. It is not zero and it is
    not the raw difference: subtracting a chargeable weight from a gross
    weight produces a number that looks like a finding and is a unit
    error. Which nothing this is, is in `refusal`.
    """

    subject: str
    committed: Quantity
    realized: Quantity
    residual: Optional[float]
    refusal: Optional[str] = None


def diverge(commitment: Commitment, outcome: Outcome) -> Divergence:
    """Pair one commitment with its outcome.

    The whole reuse argument of this programme lands on this function: it
    is the divergence machinery, and it needed no new analytics to reach a
    new domain -- only the basis guard, which the commodity domain also
    had and needed less.
    """
    committed = commitment.quantity
    realized = outcome.observed.quantity
    if not committed.comparable_with(realized):
        return Divergence(
            subject=commitment.subject,
            committed=committed,
            realized=realized,
            residual=None,
            refusal=(
                f"{DIVERGENCE_ACROSS_UNLIKE_BASIS}: committed in "
                f"{committed.value} {committed.unit} on basis {committed.basis!r}, realized in "
                f"{realized.value} {realized.unit} on basis {realized.basis!r}. The difference "
                "of two unlike bases is a unit error wearing a finding's clothes."
            ),
        )
    return Divergence(
        subject=commitment.subject,
        committed=committed,
        realized=realized,
        residual=realized.value - committed.value,
    )


# ---------------------------------------------------------------------
# The three stores. Each admits exactly one type and refuses the other
# two BY TYPE, not by a field check -- a store that inspected fields
# would admit a commitment that happened to look like evidence.
# ---------------------------------------------------------------------

@dataclass
class EvidenceStore:
    _rows: List[Evidence] = field(default_factory=list)

    def admit(self, item: object) -> Evidence:
        if not isinstance(item, Evidence):
            raise StoreRefusal(
                WRONG_TYPE_FOR_THIS_STORE,
                f"the evidence store was offered {type(item).__name__}. A commitment is an act "
                "upon the world, not an observation about it; admitting one here is how a system "
                "starts believing its own intentions.",
            )
        if not item.provenance.source_id.strip():
            raise StoreRefusal(EVIDENCE_CARRIES_NO_PROVENANCE,
                               f"{item.subject!r} names no source.")
        if not item.evidence_class.strip():
            raise StoreRefusal(
                EVIDENCE_DECLARES_NO_CLASS,
                f"{item.subject!r} declares no evidence class. This layer requires the "
                "declaration and does not make it: the admissible set is owned elsewhere.",
            )
        if item.period is not None and item.provenance.known_at < item.period:
            raise StoreRefusal(
                EVIDENCE_KNOWN_BEFORE_ITS_PERIOD,
                f"{item.subject!r} is known_at {item.provenance.known_at} for period "
                f"{item.period}. A value cannot have been knowable before the period it describes.",
            )
        self._rows.append(item)
        return item

    def __len__(self) -> int:
        return len(self._rows)

    @property
    def rows(self) -> Tuple[Evidence, ...]:
        return tuple(self._rows)


@dataclass
class CommitmentStore:
    _rows: Dict[str, Commitment] = field(default_factory=dict)

    def issue(self, item: object) -> Commitment:
        if not isinstance(item, Commitment):
            raise StoreRefusal(
                WRONG_TYPE_FOR_THIS_STORE,
                f"the commitment store was offered {type(item).__name__}. Only an act belongs "
                "here; an observation has a source and this store has no place to put one.",
            )
        if not item.issuer.strip():
            raise StoreRefusal(COMMITMENT_NAMES_NO_ISSUER,
                               f"{item.subject!r} binds the firm and does not say who did it.")
        if item.authority is None:
            raise StoreRefusal(
                COMMITMENT_NAMES_NO_AUTHORITY,
                f"{item.subject!r} names no authority. This says the FIELD is empty; it does not "
                "claim the issuer lacked authority, which is a fact about the world no store can see.",
            )
        if not item.idempotency_key.strip():
            raise StoreRefusal(
                COMMITMENT_CARRIES_NO_IDEMPOTENCY_KEY,
                f"{item.subject!r} carries no idempotency key, so a retried send binds the firm twice.",
            )
        if not item.authority.covers(item.issued_at):
            raise StoreRefusal(
                COMMITMENT_ISSUED_OUTSIDE_ITS_AUTHORITY_WINDOW,
                f"{item.subject!r} was issued {item.issued_at} under {item.authority.instrument!r}, "
                f"valid {item.authority.valid_from}..{item.authority.valid_until}.",
            )
        if item.revoked_at is not None and item.revoked_at < item.issued_at:
            raise StoreRefusal(COMMITMENT_REVOKED_BEFORE_IT_WAS_ISSUED,
                               f"{item.subject!r} revoked {item.revoked_at}, issued {item.issued_at}.")
        seen = self._rows.get(item.idempotency_key)
        if seen is not None:
            if seen != item:
                raise StoreRefusal(
                    COMMITMENT_KEY_REUSED_WITH_DIFFERENT_CONTENT,
                    f"key {item.idempotency_key!r} already admitted different content. The "
                    "observable is that two bodies share one key, not which of them is right.",
                )
            return seen  # idempotent: the retry binds nothing new
        self._rows[item.idempotency_key] = item
        return item

    def __len__(self) -> int:
        return len(self._rows)

    def get(self, key: str) -> Optional[Commitment]:
        return self._rows.get(key)

    @property
    def rows(self) -> Tuple[Commitment, ...]:
        return tuple(self._rows.values())


@dataclass
class OutcomeStore:
    commitments: CommitmentStore
    _rows: List[Outcome] = field(default_factory=list)

    def record(self, item: object) -> Outcome:
        if not isinstance(item, Outcome):
            raise StoreRefusal(
                WRONG_TYPE_FOR_THIS_STORE,
                f"the outcome store was offered {type(item).__name__}.",
            )
        if not item.commitment_key.strip():
            raise StoreRefusal(
                OUTCOME_REFERENCES_NO_COMMITMENT,
                "an outcome is an outcome OF something. Unreferenced, it is plain evidence and "
                "belongs in the evidence store, where it will be read as an observation rather "
                "than as the settlement of a promise.",
            )
        if self.commitments.get(item.commitment_key) is None:
            raise StoreRefusal(
                OUTCOME_REFERENCES_AN_ABSENT_COMMITMENT,
                f"no commitment with key {item.commitment_key!r} has been issued.",
            )
        self._rows.append(item)
        return item

    def __len__(self) -> int:
        return len(self._rows)

    @property
    def rows(self) -> Tuple[Outcome, ...]:
        return tuple(self._rows)


@dataclass(frozen=True)
class Pairing:
    """Every commitment in exactly one bucket, and the three conserve.

    Row accounting applied to the pairing: a commitment that produced no
    divergence must say WHICH nothing -- not yet settled, revoked, or
    settled on a basis that cannot be compared. An empty `divergences`
    states none of those, so `empty_because` carries the warrant.
    """

    divergences: Tuple[Divergence, ...]
    unsettled: Tuple[str, ...]
    revoked: Tuple[str, ...]
    basis_refused: Tuple[Divergence, ...]
    empty_because: Optional[str] = None

    @property
    def accounted(self) -> int:
        return (len(self.divergences) + len(self.unsettled)
                + len(self.revoked) + len(self.basis_refused))


def pair(commitments: CommitmentStore, outcomes: OutcomeStore) -> Pairing:
    """Pair every issued commitment against its outcome, accounting for
    every one of them."""
    by_key: Dict[str, Outcome] = {o.commitment_key: o for o in outcomes.rows}
    matched: List[Divergence] = []
    refused: List[Divergence] = []
    unsettled: List[str] = []
    revoked: List[str] = []

    for commitment in commitments.rows:
        if not commitment.is_live:
            revoked.append(commitment.idempotency_key)
            continue
        outcome = by_key.get(commitment.idempotency_key)
        if outcome is None:
            unsettled.append(commitment.idempotency_key)
            continue
        result = diverge(commitment, outcome)
        (refused if result.refusal else matched).append(result)

    empty_because: Optional[str] = None
    if not matched:
        if len(commitments) == 0:
            empty_because = (f"{NO_PAIRS_BECAUSE_NO_COMMITMENTS_WERE_ISSUED}: nothing has been "
                             "promised, so there is nothing to settle.")
        elif revoked and not unsettled and not refused:
            empty_because = (f"{NO_PAIRS_BECAUSE_EVERY_COMMITMENT_WAS_REVOKED}: "
                             f"{len(revoked)} issued, all withdrawn before settlement.")
        elif refused and not unsettled:
            empty_because = (f"{NO_PAIRS_BECAUSE_EVERY_PAIR_DIFFERED_IN_BASIS}: {len(refused)} "
                             "commitment(s) settled on a basis their outcome does not share. This "
                             "is a measurement fault in the pipeline, not a quiet quarter.")
        else:
            empty_because = (f"{NO_PAIRS_BECAUSE_NO_OUTCOME_HAS_ARRIVED_YET}: {len(unsettled)} "
                             "commitment(s) live and awaiting settlement.")

    return Pairing(
        divergences=tuple(matched),
        unsettled=tuple(unsettled),
        revoked=tuple(revoked),
        basis_refused=tuple(refused),
        empty_because=empty_because,
    )
