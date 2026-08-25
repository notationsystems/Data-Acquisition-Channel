"""Durable storage for `EvidenceClassAssignment`, beside the evidence.

Same discipline as `FilesystemEvidenceStore`: one JSON file per object,
filename IS the object's content-addressed id, append-only, no delete
method. Written as its own directory (`<root>/evidence_classes/`) rather
than as a ninth `FilesystemEvidenceStore._CATEGORIES` entry, because a
class assignment is not an `evidence.types` object and giving it a
category there would put it in `fingerprint()`'s corpus, changing the
meaning of an already-verified pool fingerprint.

Reads go through `assignment_from_dict`, so an altered `evidence_class`
on disk is refused on load rather than trusted -- see
`epistemics/evidence_class.py` for exactly what that does and does not
prove.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from epistemics.evidence_class import (
    ClassRegister,
    EvidenceClassAssignment,
    assignment_from_dict,
    assignment_to_dict,
)

_DIRECTORY = "evidence_classes"


class ClassAssignmentStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / _DIRECTORY
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, assignment: EvidenceClassAssignment) -> None:
        path = self.root / f"{assignment.id}.json"
        payload = assignment_to_dict(assignment)
        path.write_text(json.dumps(payload, sort_keys=True, indent=2))

    def all_assignments(self) -> Tuple[EvidenceClassAssignment, ...]:
        found = []
        for path in sorted(self.root.glob("*.json")):
            payload = json.loads(path.read_text())
            assignment = assignment_from_dict(payload)
            if path.stem != assignment.id:
                raise ValueError(
                    f"assignment stored as {path.stem!r} identifies as {assignment.id!r}"
                )
            found.append(assignment)
        return tuple(found)

    def restore(self) -> ClassRegister:
        """Rebuilds the in-memory register. A second assignment for the
        same evidence id with a different class raises `ClassReassignment`
        HERE, at load -- which is the mechanism that catches an assignment
        rewritten wholesale under a new id rather than edited in place."""
        register = ClassRegister()
        for assignment in self.all_assignments():
            register.assign(assignment)
        return register
