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

Because ids are content-addressed, writing the SAME id twice is only
ever legitimate if the payload is identical (that is what "duplicate
persistence" means here); if an existing file's payload differs from
what is being written under the same id, that is not a legitimate
duplicate -- it is on-disk corruption or tampering, and is reported as
such rather than silently overwritten or silently ignored.
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


class ArtifactConflictError(RuntimeError):
    """Raised when a write would place different content under an id
    that already exists on disk. Content-addressed identity means this
    can only happen if the existing file was corrupted or tampered with
    after being written -- a legitimate re-put of identical content is
    always a silent no-op, never this error."""


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

    def _write(self, category: str, artifact_id: str, payload: dict) -> None:
        directory = self.root / category
        final_path = directory / f"{artifact_id}.json"
        text = json.dumps(payload, sort_keys=True, indent=2)

        if final_path.exists():
            existing_text = final_path.read_text()
            if json.loads(existing_text) != json.loads(text):
                raise ArtifactConflictError(
                    f"{category}/{artifact_id}.json already exists with different content -- "
                    "this is only possible via on-disk corruption or tampering, since ids are "
                    "content-addressed"
                )
            return  # legitimate duplicate: identical content already durable, nothing to do

        tmp_path = directory / f"{artifact_id}.json.tmp"
        tmp_path.write_text(text)
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
        self._write("sources", source.id, serialization.source_to_dict(source))

    def put_document(self, document: Document) -> None:
        self._write("documents", document.id, serialization.document_to_dict(document))

    def put_record(self, record: Record) -> None:
        self._write("records", record.id, serialization.record_to_dict(record))

    def put_observation(self, observation: Observation) -> None:
        self._write("observations", observation.id, serialization.observation_to_dict(observation))

    def put_referent(self, referent: Referent) -> None:
        self._write("referents", referent.id, serialization.referent_to_dict(referent))

    def put_claimed_relationship(self, relationship: ClaimedRelationship) -> None:
        self._write(
            "claimed_relationships",
            relationship.id,
            serialization.claimed_relationship_to_dict(relationship),
        )

    def put_derived_value(self, derived_value: DerivedValue) -> None:
        self._write("derived_values", derived_value.id, serialization.derived_value_to_dict(derived_value))

    def put_derived_grounding(self, grounding: DerivedGrounding) -> None:
        self._write(
            "derived_groundings", grounding.id, serialization.derived_grounding_to_dict(grounding)
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
