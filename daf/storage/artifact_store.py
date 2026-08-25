"""ArtifactStore: a Document-centric convenience facade over
FilesystemEvidenceStore, answering the artifact-identity /
version-identity / content-identity distinction explicitly.

THE IDENTIFIED GAP (see docs/DAF_DURABLE_STORAGE.md section 4 for the
full writeup): `evidence.types.Document` -- literally described in its
own docstring as "a retrieved artifact" -- already has a real identity
(`Document.id`) that is content-addressed, so it already serves as
*version identity* (it changes when the content changes) and, folded
into that same hash, *content identity* is already present too (`id`
is computed from `content_hash(raw_content)`, among other fields). What
the existing architecture does NOT have is a stable *artifact identity*
-- something that names "the same logical source artifact" across
multiple revisions. `Document` itself carries no such field.

This module does not add one as a new type or a new field on `Document`
(that would be exactly the "silently redefine artifact_id" the task
warned against). Instead it recognizes that `Document.source_id`
together with its associated `Record.locator` (locator is deliberately
present on `Record`, per that type's own docstring, precisely to name
"where within a source this came from") ALREADY jointly identify the
same thing "artifact identity" is asking for -- an arXiv paper's
`Record.locator` is its stable, revision-independent id, for example.
`artifact_id` here is a DERIVED, non-authoritative hash of that existing
pair, computed with the SAME `evidence.identity.content_hash` primitive
already used everywhere else -- exactly the same discipline
`EvidencePool.fingerprint()` already uses for its own derived,
non-authoritative view over already-existing ids. It is not stored
anywhere as a new identity; it is recomputed on demand from `store`.

Three distinct, individually inspectable identities per Document:

    content_hash  = evidence.identity.content_hash(document.raw_content)
                    (the bytes alone -- ignoring source_id/retrieval_method)
    version_id    = document.id
                    (the REAL, existing identity: source_id + content_hash
                     + retrieval_method -- changes on any revision)
    artifact_id   = content_hash({"source_id": ..., "locator": ...})
                    (DERIVED grouping key -- stable across revisions,
                     because it never includes raw_content)
"""

from __future__ import annotations

from typing import Optional, Tuple

from evidence.identity import content_hash
from evidence.types import Document, Record

from daf.storage.filesystem_store import FilesystemEvidenceStore


class ArtifactNotFoundError(KeyError):
    """Raised when `version_id` names no persisted Document, or names a
    Document that does not belong to `artifact_id`'s (source_id, locator)
    group."""


class ArtifactStore:
    def __init__(self, store: FilesystemEvidenceStore) -> None:
        self._store = store

    def put(self, document: Document, record: Record) -> str:
        """Persists one acquired Document together with the Record that
        carries its locator (the same pair `scout.pipeline.run_scout`
        already produces together for one `RawDocument`). Returns the
        artifact_id this (document, record) pair belongs to."""
        if record.document_id != document.id:
            raise ValueError(
                f"record.document_id {record.document_id!r} does not reference "
                f"document.id {document.id!r}"
            )
        self._store.put_document(document)
        self._store.put_record(record)
        return self.artifact_id(document.source_id, record.locator)

    @staticmethod
    def artifact_id(source_id: str, locator: str) -> str:
        return content_hash({"source_id": source_id, "locator": locator})

    @staticmethod
    def content_hash_of(document: Document) -> str:
        return content_hash(document.raw_content)

    def exists(self, artifact_id: str, version_id: str) -> bool:
        try:
            self.get(artifact_id, version_id)
            return True
        except ArtifactNotFoundError:
            return False

    def get(self, artifact_id: str, version_id: str) -> Document:
        if not self._store.has_document(version_id):
            raise ArtifactNotFoundError(f"no Document persisted under version_id {version_id!r}")
        document = self._store.get_document(version_id)
        locator = self._locator_for(document)
        if locator is None or self.artifact_id(document.source_id, locator) != artifact_id:
            raise ArtifactNotFoundError(
                f"Document {version_id!r} exists but is not a version of artifact {artifact_id!r}"
            )
        return document

    def list_versions(self, artifact_id: str) -> Tuple[str, ...]:
        """All Document ids (version_ids) sharing this artifact_id,
        ordered by (retrieved_at, id) -- deterministic and, since
        `retrieved_at` is always caller-supplied rather than wall-clock,
        reproducible acquisition-order, not directory-listing order."""
        matches = []
        for document in self._store.all_documents():
            locator = self._locator_for(document)
            if locator is not None and self.artifact_id(document.source_id, locator) == artifact_id:
                matches.append(document)
        matches.sort(key=lambda d: (d.retrieved_at, d.id))
        return tuple(document.id for document in matches)

    def _locator_for(self, document: Document) -> Optional[str]:
        """A Document has no locator of its own -- only a Record does.
        This resolves it by scanning persisted Records for one whose
        `document_id` references this Document, exactly the relationship
        `scout.pipeline.run_scout` establishes at admission time. Returns
        None if no Record exists yet for this Document (not expected in
        normal operation, since `put()` always persists both together)."""
        for record in self._store.all_records():
            if record.document_id == document.id:
                return record.locator
        return None
