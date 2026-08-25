"""`ClassifiedPool` -- where `class_assigned_at_ingest` actually lands.

    run_scout  -->  pool.put_source/document/record/observation/...
                        |
                        +-- ClassifiedPool override: assign the class,
                        |   persist it, then delegate to DurablePool
                        v
                    DurablePool.put_*  (unchanged)

WHY THIS IS THE INGEST GATE AND NOT A LABELLING PASS.
`scout.pipeline.run_scout` is the only evidence write path in this
repository (AST-asserted in `tests/test_epistemic_boundary.py`), and it
writes exclusively through `pool.put_*`. `DurablePool` already overrides
all eight. Adding the assignment inside those same overrides means an
object cannot enter the pool by the supported path without its class
being fixed in the same call -- no separate pass to forget, no window in
which a classified and an unclassified copy both exist.

The vendored `scout/pipeline.py` is not touched, and does not need to be:
it accepts any `EvidencePool`, and a `ClassifiedPool` is one.

WHAT THE POLICY IS, AND WHY IT IS DECLARED RATHER THAN INFERRED.
`SourceClassPolicy` maps a declared source kind to a class. An
undeclared source kind yields no assignment at all, so its evidence is
`UNCLASSIFIED` and inadmissible for canonical assertion -- it is not
guessed at, and there is no bypass argument to make it admissible. This
is §22's migration state made live rather than hypothetical: a source
nobody has classified is exactly a source whose evidence nobody may
assert.

Derived objects are never classified from the source policy. A
`DerivedValue` or `DerivedGrounding` is a computation, so it takes
`derived` regardless of what produced it, and `make_class_assignment`
refuses `measured`/`asserted` for those kinds outright. That is
`proposals_are_not_evidence` expressed where a mistake would actually be
made.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from evidence.types import (
    ClaimedRelationship,
    DerivedGrounding,
    DerivedValue,
    Document,
    Observation,
    Record,
    Source,
)

from daf.storage.class_store import ClassAssignmentStore
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics.evidence_class import (
    DERIVED,
    ClassRegister,
    make_class_assignment,
)


@dataclass(frozen=True)
class SourceClassPolicy:
    """Declared source kind -> ingest class.

    `id` names the declaration in every assignment it produces, so two
    different policies classifying the same evidence produce two
    assignments and the disagreement surfaces as a `ClassReassignment`
    instead of one silently winning."""

    id: str
    by_source_kind: Mapping[str, str]

    def class_for(self, source_kind: str) -> Optional[str]:
        return self.by_source_kind.get(source_kind)


class ClassifiedPool(DurablePool):
    def __init__(
        self,
        store: FilesystemEvidenceStore,
        policy: SourceClassPolicy,
        *,
        register: Optional[ClassRegister] = None,
    ) -> None:
        super().__init__(store)
        self.policy = policy
        self.classes = ClassAssignmentStore(store.root)
        self.register = register if register is not None else self.classes.restore()
        # source id -> class, so a Document/Record/Observation can inherit
        # the class of the Source it came from without re-deriving it.
        self._class_by_source: dict = {}
        self._source_of_document: dict = {}
        self._document_of_record: dict = {}

    def _assign(self, evidence_id: str, evidence_kind: str, evidence_class: str) -> None:
        assignment = make_class_assignment(
            evidence_id=evidence_id,
            evidence_kind=evidence_kind,
            evidence_class=evidence_class,
            assigned_by=self.policy.id,
        )
        self.register.assign(assignment)
        self.classes.put(assignment)

    def _class_for_source_id(self, source_id: str) -> Optional[str]:
        declared = self._class_by_source.get(source_id)
        if declared is not None:
            return declared
        assignment = self.register.assignment_for(source_id)
        return assignment.evidence_class if assignment else None

    # -- put overrides: classify, then delegate unchanged --

    def put_source(self, source: Source) -> None:
        declared = self.policy.class_for(source.kind)
        if declared is not None:
            self._class_by_source[source.id] = declared
            self._assign(source.id, "source", declared)
        super().put_source(source)

    def put_document(self, document: Document) -> None:
        self._source_of_document[document.id] = document.source_id
        declared = self._class_for_source_id(document.source_id)
        if declared is not None:
            self._assign(document.id, "document", declared)
        super().put_document(document)

    def put_record(self, record: Record) -> None:
        self._document_of_record[record.id] = record.document_id
        source_id = self._source_of_document.get(record.document_id)
        declared = self._class_for_source_id(source_id) if source_id else None
        if declared is not None:
            self._assign(record.id, "record", declared)
        super().put_record(record)

    def put_observation(self, observation: Observation) -> None:
        declared = None
        for record_id in observation.record_ids:
            document_id = self._document_of_record.get(record_id)
            source_id = self._source_of_document.get(document_id) if document_id else None
            candidate = self._class_for_source_id(source_id) if source_id else None
            if candidate is None:
                # One unclassified input is enough: an observation is no
                # better classified than the least-classified record it
                # rests on.
                declared = None
                break
            if declared is not None and candidate != declared:
                declared = None
                break
            declared = candidate
        if declared is not None:
            self._assign(observation.id, "observation", declared)
        super().put_observation(observation)

    # `Referent` is deliberately NOT classified. It is an identity anchor
    # -- `(natural_key, kind)` -- and asserts nothing about the world, so
    # there is no fact about it that could be measured, asserted, computed
    # or derived. Classifying it would make the class mean "the class of
    # whatever mentioned it", which is a different and weaker claim.
    # It is therefore inherited from DurablePool unchanged.

    def put_claimed_relationship(self, relationship: ClaimedRelationship) -> None:
        assignment = self.register.assignment_for(relationship.observation_id)
        if assignment is not None:
            self._assign(relationship.id, "claimed_relationship", assignment.evidence_class)
        super().put_claimed_relationship(relationship)

    def put_derived_value(self, derived_value: DerivedValue) -> None:
        self._assign(derived_value.id, "derived_value", DERIVED)
        super().put_derived_value(derived_value)

    def put_derived_grounding(self, grounding: DerivedGrounding) -> None:
        self._assign(grounding.id, "derived_grounding", DERIVED)
        super().put_derived_grounding(grounding)
