"""`class_assigned_at_ingest` -- the evidence class, and where it is fixed.

    acquisition  --run_scout-->  pool.put_*  --> evidence
                                     |
                                     +--> EvidenceClassAssignment  (here)

WHAT THE REPOSITORY HAD, INSPECTED. No evidence type carries a class
field. `evidence/types.py` has a de facto two-class split -- `Observation`
(admitted from a `Record`) versus `DerivedValue` (computed from other
evidence) -- and nothing more. Adding a field to `Observation` would mean
editing the vendored submodule, which this repository never does
(`daf/_vendor.py`). So the class is carried BESIDE the object in its own
content-addressed record, keyed by the evidence id.

WHY "AT INGEST" IS REAL HERE AND NOT A LABEL. `scout.pipeline.run_scout`
-- the single evidence write path in this repository, AST-asserted --
writes only through `pool.put_*`. `pool` is ours: `DurablePool` already
overrides all eight `put_*` methods. `daf.storage.classified_pool` adds
the assignment in that same override, so an object cannot enter the pool
by the supported path without its class being fixed in the same call.
Anything already in a pool without one is `UNCLASSIFIED`, which is not a
class but the absence of one, and is inadmissible for canonical
assertion and for training.

WHAT IMMUTABILITY MEANS, PRECISELY. Three separate mechanisms, none of
which is the same as the others:

  1. In memory: the assignment is a frozen dataclass, and `ClassRegister`
     raises `ClassReassignment` on a second, DIFFERENT class for the same
     evidence id. An identical re-assignment is a no-op, because
     re-running a deterministic acquisition must stay idempotent.
  2. On disk, in place: the id is `content_hash` over all four fields, so
     editing `evidence_class` in a persisted record makes it re-hash to
     something other than the id it is stored under. `assignment_from_dict`
     recomputes and refuses -- exactly the discipline
     `daf/storage/serialization.py` already applies to every evidence type.
  3. On disk, wholesale: rewriting the record under its NEW correct id
     leaves the original file in place (the store is append-only and
     content-addressed), so the pool now holds two assignments for one
     evidence id and mechanism 1 fires on load.

WHAT NONE OF THAT PROVES. An actor who can delete files can delete the
original assignment along with writing a new one, and nothing here would
notice; the store has no tombstone and no retraction path at all (this is
`architecture/_probes/generality.yaml`'s `revocable_record` finding,
recorded rather than papered over). These mechanisms detect alteration,
not an adversary with write access to the store.

BOUNDARY: this module imports `evidence.identity.content_hash` and the
standard library. Nothing else. No pool, no daf, no science, no network,
no clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from evidence.identity import content_hash

# The four ingest classes. Canonical; `architecture/evidence_class.yaml`
# is the source of truth and `tests/test_epistemic_boundary.py` asserts
# these agree with it rather than letting the two drift.
ASSERTED = "asserted"
COMPUTED = "computed"
DERIVED = "derived"
MEASURED = "measured"
INGEST_CLASSES: Tuple[str, ...] = (ASSERTED, COMPUTED, DERIVED, MEASURED)

# NOT a fifth class: the absence of one. §22's migration state.
UNCLASSIFIED = "unclassified"

# Presentation/query vocabulary. Maps ONTO the four; never competes.
VOCABULARY_MAP: Mapping[str, str] = {
    "computed": COMPUTED,
    "hypothesized": DERIVED,
    "inferred": DERIVED,
    "manufactured": MEASURED,
    "measured": MEASURED,
    "observed": MEASURED,
    "predicted": COMPUTED,
    "reported": ASSERTED,
    "simulated": COMPUTED,
}

# `validated` reads as a class and is a status on a claim. It is kept out
# of VOCABULARY_MAP deliberately: a promotion path from validation status
# to evidence class is exactly what `class_assigned_at_ingest` forbids.
STATUSES_NOT_CLASSES: Tuple[str, ...] = ("validated",)

# Classes a computation may produce. A derived or computed result is
# never `measured` or `asserted`, whatever produced it -- this is
# `proposals_are_not_evidence` expressed as a class constraint rather
# than as a naming convention.
COMPUTATION_CLASSES: Tuple[str, ...] = (COMPUTED, DERIVED)

# Admissibility by class. `unclassified` is inadmissible for both.
_CANONICAL_ADMISSIBLE = (ASSERTED, COMPUTED, DERIVED, MEASURED)
_TRAINING_ADMISSIBLE = (ASSERTED, MEASURED)

EVIDENCE_KINDS: Tuple[str, ...] = (
    "claimed_relationship",
    "derived_grounding",
    "derived_value",
    "document",
    "observation",
    "record",
    "referent",
    "source",
)

# Kinds a computation produces. Constrained to COMPUTATION_CLASSES.
_COMPUTED_KINDS: Tuple[str, ...] = ("derived_grounding", "derived_value")


class EvidenceClassError(ValueError):
    """Base for every refusal in this module."""


class UnknownEvidenceClass(EvidenceClassError):
    """A class outside the four ingest classes was offered."""


class UnknownEvidenceKind(EvidenceClassError):
    """An evidence kind outside `evidence/types.py`'s eight was offered."""


class ClassReassignment(EvidenceClassError):
    """A second, different class was offered for one evidence id. The
    class is fixed at ingest; there is no re-classification path and no
    bypass flag."""


class ProposalClassRefused(EvidenceClassError):
    """A computed object was offered a non-computation class. A
    derivation cannot be labelled `measured` or `asserted`."""


class ClassIdentityMismatch(EvidenceClassError):
    """A persisted assignment's own fields do not reproduce the id it was
    stored under -- the on-disk record was altered after being written."""


@dataclass(frozen=True)
class EvidenceClassAssignment:
    """One evidence object's class, fixed at ingest.

    `assigned_by` names the DECLARATION that produced the class (e.g.
    `"source_policy:noaa_water_level"`), never a person and never a
    timestamp. It participates in identity because "who declared this"
    is part of what the assignment asserts: the same evidence classified
    `measured` by two different declared policies is two claims, and
    collapsing them would hide a disagreement."""

    id: str
    evidence_id: str
    evidence_kind: str
    evidence_class: str
    assigned_by: str


def _validate(evidence_kind: str, evidence_class: str) -> None:
    if evidence_kind not in EVIDENCE_KINDS:
        raise UnknownEvidenceKind(
            f"{evidence_kind!r} is not one of evidence/types.py's kinds: {list(EVIDENCE_KINDS)}"
        )
    if evidence_class not in INGEST_CLASSES:
        if evidence_class in STATUSES_NOT_CLASSES:
            raise UnknownEvidenceClass(
                f"{evidence_class!r} is a claim-level status, not an evidence class -- "
                "validation status is never a promotion path into classification"
            )
        raise UnknownEvidenceClass(
            f"{evidence_class!r} is not one of the ingest classes {list(INGEST_CLASSES)}"
        )
    if evidence_kind in _COMPUTED_KINDS and evidence_class not in COMPUTATION_CLASSES:
        raise ProposalClassRefused(
            f"a {evidence_kind} is produced by computation and may only be classified "
            f"{list(COMPUTATION_CLASSES)}, not {evidence_class!r}"
        )


def make_class_assignment(
    evidence_id: str, evidence_kind: str, evidence_class: str, assigned_by: str
) -> EvidenceClassAssignment:
    """The only supported constructor -- the same discipline
    `evidence/types.py`'s `make_*` factories establish. The id is derived
    from content, never supplied, so an assignment's id can never
    disagree with its own class."""
    _validate(evidence_kind, evidence_class)
    assignment_id = content_hash(
        {
            "evidence_id": evidence_id,
            "evidence_kind": evidence_kind,
            "evidence_class": evidence_class,
            "assigned_by": assigned_by,
        }
    )
    return EvidenceClassAssignment(
        id=assignment_id,
        evidence_id=evidence_id,
        evidence_kind=evidence_kind,
        evidence_class=evidence_class,
        assigned_by=assigned_by,
    )


def assignment_to_dict(assignment: EvidenceClassAssignment) -> Dict[str, Any]:
    return {
        "id": assignment.id,
        "evidence_id": assignment.evidence_id,
        "evidence_kind": assignment.evidence_kind,
        "evidence_class": assignment.evidence_class,
        "assigned_by": assignment.assigned_by,
    }


def assignment_from_dict(payload: Mapping[str, Any]) -> EvidenceClassAssignment:
    """Reconstructs through `make_class_assignment` from the raw fields --
    never from the stored id -- then checks the recomputed id against the
    one it was stored under. An altered `evidence_class` cannot survive
    this: it re-hashes to a different id."""
    reconstructed = make_class_assignment(
        evidence_id=payload["evidence_id"],
        evidence_kind=payload["evidence_kind"],
        evidence_class=payload["evidence_class"],
        assigned_by=payload["assigned_by"],
    )
    if payload["id"] != reconstructed.id:
        raise ClassIdentityMismatch(
            f"EvidenceClassAssignment persisted under id {payload['id']!r} re-hashes to "
            f"{reconstructed.id!r} -- stored class no longer matches its own "
            "content-addressed identity"
        )
    return reconstructed


class ClassRegister:
    """Evidence id -> class, with no reassignment path.

    Not a pool and not a store: a pure in-memory index that
    `daf.storage.classified_pool` populates at ingest and reloads at
    restart. It has no `remove`, no `reclassify` and no bypass argument,
    because adding one is how `class_assigned_at_ingest` stops being
    true."""

    def __init__(self) -> None:
        self._by_evidence: Dict[str, EvidenceClassAssignment] = {}

    def assign(self, assignment: EvidenceClassAssignment) -> None:
        existing = self._by_evidence.get(assignment.evidence_id)
        if existing is None:
            self._by_evidence[assignment.evidence_id] = assignment
            return
        if existing.id == assignment.id:
            return  # Idempotent: re-running a deterministic acquisition.
        raise ClassReassignment(
            f"evidence {assignment.evidence_id!r} was classified {existing.evidence_class!r} "
            f"by {existing.assigned_by!r} at ingest; refusing to reclassify it "
            f"{assignment.evidence_class!r} by {assignment.assigned_by!r}"
        )

    def assignment_for(self, evidence_id: str) -> Optional[EvidenceClassAssignment]:
        return self._by_evidence.get(evidence_id)

    def class_of(self, evidence_id: str) -> str:
        """`UNCLASSIFIED` for anything with no assignment -- including
        every object admitted before this phase existed."""
        assignment = self._by_evidence.get(evidence_id)
        return assignment.evidence_class if assignment else UNCLASSIFIED

    def admissible_for_canonical_assertion(self, evidence_id: str) -> bool:
        return self.class_of(evidence_id) in _CANONICAL_ADMISSIBLE

    def admissible_for_training(self, evidence_id: str) -> bool:
        return self.class_of(evidence_id) in _TRAINING_ADMISSIBLE

    def unclassified(self, evidence_ids: Tuple[str, ...]) -> Tuple[str, ...]:
        """The migration backlog, as a metric rather than a warning."""
        return tuple(sorted(i for i in evidence_ids if i not in self._by_evidence))

    def all_assignments(self) -> Tuple[EvidenceClassAssignment, ...]:
        return tuple(sorted(self._by_evidence.values(), key=lambda a: a.id))

    def __len__(self) -> int:
        return len(self._by_evidence)


def canonical_class(term: str) -> str:
    """Presentation/query term -> ingest class.

    Raises for `validated` by name, because that is the term most likely
    to be handed to this function by someone expecting it to work."""
    if term in STATUSES_NOT_CLASSES:
        raise UnknownEvidenceClass(
            f"{term!r} is a claim-level status, not an evidence class"
        )
    if term in VOCABULARY_MAP:
        return VOCABULARY_MAP[term]
    if term in INGEST_CLASSES:
        return term
    raise UnknownEvidenceClass(f"{term!r} is not in the declared vocabulary")
