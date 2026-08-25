"""FilesystemEvidenceStore: local, durable, content-addressed persistence
for the 8 evidence.types categories EvidencePool already recognizes.

One JSON file per object, named by its own existing content-hash id, in a
per-category subdirectory -- mirrors EvidencePool's own internal
`Dict[str, T]` layout, just on disk instead of in memory. No new identity
scheme: the filename IS the object's real `evidence.identity.content_hash`
id, unchanged.

Writes are atomic (temp file + `os.replace`, which is atomic on POSIX)
so a crash mid-write can never leave a half-written file where a reader
would see it -- `all_*()` only ever globs `*.json`, never the `.tmp`
staging suffix.

Because every id is content-addressed via a `make_*` factory, two
LEGITIMATELY constructed objects that share an id are, by construction,
guaranteed to share every identity-relevant field -- the only fields
that can differ are exactly the epistemic/temporal ones identity
deliberately excludes (e.g. `Document.retrieved_at`). So "the same
content re-acquired at a different timestamp" and "genuinely conflicting
content under one id" are NOT the same situation, and must not be
detected the same way: the former is an ordinary, legitimate duplicate
(silent no-op); the latter can only arise from on-disk corruption or
tampering of the file ALREADY on disk, independent of whatever is being
written now. `_write` therefore does not compare payloads at all on a
duplicate write -- it re-verifies the EXISTING file's own identity (via
the category's `*_from_dict`, which recomputes and checks the id, per
`daf.storage.serialization`) and lets `ArtifactIdentityMismatch`
propagate if that file was corrupted. This is strictly more correct
than a payload-equality check, which would either reject legitimate
re-acquisitions (as an earlier version of this module did) or, if
weakened to ignore non-identity fields, still not verify the thing that
actually matters: whether the on-disk bytes are self-consistent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Tuple, TypeVar

from evidence.types import (
    ClaimedRelationship,
    DerivedGrounding,
    DerivedValue,
    Document,
    Observation,
    Record,
    Referent,
    Source,
)

from daf.storage import serialization

T = TypeVar("T")


class FilesystemEvidenceStore:
    _CATEGORIES = (
        "sources",
        "documents",
        "records",
        "observations",
        "referents",
        "claimed_relationships",
        "derived_values",
        "derived_groundings",
    )

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        for category in self._CATEGORIES:
            (self.root / category).mkdir(parents=True, exist_ok=True)

    # -- generic write/read machinery, shared by all 8 categories --

    def _write(self, category: str, artifact_id: str, payload: dict, from_dict: Callable[[dict], object]) -> None:
        directory = self.root / category
        final_path = directory / f"{artifact_id}.json"

        if final_path.exists():
            # Re-verify the EXISTING file's own identity rather than comparing
            # it to the incoming payload -- see module docstring for why a
            # payload-equality comparison would be wrong here. Propagates
            # serialization.ArtifactIdentityMismatch if the on-disk file was
            # corrupted or tampered with, independent of this write.
            from_dict(json.loads(final_path.read_text()))
            return  # existing file already validly represents this id -- nothing to do

        tmp_path = directory / f"{artifact_id}.json.tmp"
        tmp_path.write_text(json.dumps(payload, sort_keys=True, indent=2))
        tmp_path.replace(final_path)  # atomic on POSIX -- readers never see a partial file

    def _read_all(self, category: str) -> Tuple[dict, ...]:
        directory = self.root / category
        return tuple(
            json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))
        )

    def _read_one(self, category: str, artifact_id: str) -> dict:
        path = self.root / category / f"{artifact_id}.json"
        if not path.exists():
            raise KeyError(f"no {category[:-1]} persisted under id {artifact_id!r}")
        return json.loads(path.read_text())

    def _has(self, category: str, artifact_id: str) -> bool:
        return (self.root / category / f"{artifact_id}.json").exists()

    def _all_typed(self, category: str, from_dict: Callable[[dict], T]) -> Tuple[T, ...]:
        return tuple(from_dict(payload) for payload in self._read_all(category))

    # -- put: one per category --

    def put_source(self, source: Source) -> None:
        self._write("sources", source.id, serialization.source_to_dict(source), serialization.source_from_dict)

    def put_document(self, document: Document) -> None:
        self._write(
            "documents", document.id, serialization.document_to_dict(document), serialization.document_from_dict
        )

    def put_record(self, record: Record) -> None:
        self._write("records", record.id, serialization.record_to_dict(record), serialization.record_from_dict)

    def put_observation(self, observation: Observation) -> None:
        self._write(
            "observations",
            observation.id,
            serialization.observation_to_dict(observation),
            serialization.observation_from_dict,
        )

    def put_referent(self, referent: Referent) -> None:
        self._write(
            "referents", referent.id, serialization.referent_to_dict(referent), serialization.referent_from_dict
        )

    def put_claimed_relationship(self, relationship: ClaimedRelationship) -> None:
        self._write(
            "claimed_relationships",
            relationship.id,
            serialization.claimed_relationship_to_dict(relationship),
            serialization.claimed_relationship_from_dict,
        )

    def put_derived_value(self, derived_value: DerivedValue) -> None:
        self._write(
            "derived_values",
            derived_value.id,
            serialization.derived_value_to_dict(derived_value),
            serialization.derived_value_from_dict,
        )

    def put_derived_grounding(self, grounding: DerivedGrounding) -> None:
        self._write(
            "derived_groundings",
            grounding.id,
            serialization.derived_grounding_to_dict(grounding),
            serialization.derived_grounding_from_dict,
        )

    # -- get: one per category, raises KeyError if missing --

    def get_source(self, source_id: str) -> Source:
        return serialization.source_from_dict(self._read_one("sources", source_id))

    def get_document(self, document_id: str) -> Document:
        return serialization.document_from_dict(self._read_one("documents", document_id))

    def get_record(self, record_id: str) -> Record:
        return serialization.record_from_dict(self._read_one("records", record_id))

    def get_observation(self, observation_id: str) -> Observation:
        return serialization.observation_from_dict(self._read_one("observations", observation_id))

    # -- has: one per category --

    def has_document(self, document_id: str) -> bool:
        return self._has("documents", document_id)

    def has_record(self, record_id: str) -> bool:
        return self._has("records", record_id)

    # -- all: one per category, deterministic (sorted-by-filename) order --

    def all_sources(self) -> Tuple[Source, ...]:
        return self._all_typed("sources", serialization.source_from_dict)

    def all_documents(self) -> Tuple[Document, ...]:
        return self._all_typed("documents", serialization.document_from_dict)

    def all_records(self) -> Tuple[Record, ...]:
        return self._all_typed("records", serialization.record_from_dict)

    def all_observations(self) -> Tuple[Observation, ...]:
        return self._all_typed("observations", serialization.observation_from_dict)

    def all_referents(self) -> Tuple[Referent, ...]:
        return self._all_typed("referents", serialization.referent_from_dict)

    def all_claimed_relationships(self) -> Tuple[ClaimedRelationship, ...]:
        return self._all_typed("claimed_relationships", serialization.claimed_relationship_from_dict)

    def all_derived_values(self) -> Tuple[DerivedValue, ...]:
        return self._all_typed("derived_values", serialization.derived_value_from_dict)

    def all_derived_groundings(self) -> Tuple[DerivedGrounding, ...]:
        return self._all_typed("derived_groundings", serialization.derived_grounding_from_dict)
