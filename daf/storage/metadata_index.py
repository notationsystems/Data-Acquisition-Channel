"""MetadataIndex: the SQLite metadata index Phase J recommended and
Phase K implements -- an INDEX, never a second raw-content authority.

`FilesystemEvidenceStore` (the canonical, content-addressed store since
Phase B) remains the sole authority for what evidence exists; this index
only ever answers "which already-canonical ids satisfy this query"
faster than a full directory scan. Every table here stores ids and the
handful of columns Phase J's own reconnaissance found a real query
against (`artifact_id`/`source_id`/`content_hash`/`retrieved_at`/
`locator`) -- never raw content, and never a field no existing DAF code
actually queries by (see the module docstring in
`docs/DAF_STORAGE_ARCHITECTURE.md` section 6 for the query-pattern
evidence this schema is built from).

Only `sources`, `documents`, `records`, and `observations` are indexed:
these are the four evidence categories every real adapter built so far
(arXiv, EDGAR, USGS, NOAA) actually populates. `referents`,
`claimed_relationships`, `derived_values`, `derived_groundings` are never
constructed by any of them (every extractor in this codebase returns
`entities=()`, `relations=()`) -- indexing categories with zero real
population would be exactly the "index every field automatically"
Phase J's own report warned against. `DurablePool.fingerprint()`
(`daf/storage/durable_pool.py`) still answers correctly for those four
categories by falling back to a cheap filename-only listing (never a
JSON-body parse) rather than by omitting them.

Rebuildable by construction: `rebuild(store)` repopulates every table
from `store`'s own `all_*()` methods -- the filesystem remains the
authority, this index is always a *derived*, disposable projection of
it (Phase J's own stated invariant, reaffirmed here: delete this file
and `rebuild()` reproduces the identical logical index).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple

from evidence.identity import content_hash

from daf.storage.identity import compute_artifact_id

if TYPE_CHECKING:  # pragma: no cover -- avoids a runtime circular import with filesystem_store
    from daf.storage.evidence_store import EvidenceStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    retrieval_method TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    locator TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    content_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY
);
CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_retrieved_at ON documents(retrieved_at);
CREATE INDEX IF NOT EXISTS idx_records_artifact_id ON records(artifact_id);
CREATE INDEX IF NOT EXISTS idx_records_document_id ON records(document_id);
"""

_INDEXED_CATEGORIES = ("sources", "documents", "records", "observations")


class MetadataIndex:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        # A short-lived connection per call, opened/closed around each
        # operation rather than held for this object's whole lifetime --
        # deliberate, because this codebase's own restart tests construct
        # a SECOND FilesystemEvidenceStore (and therefore a second
        # MetadataIndex) against the SAME root while the first is only
        # `del`-eted, not explicitly closed (see e.g.
        # tests/test_*_integration.py's restart tests across Phases G-I).
        # A persistent connection would risk exactly the file-locking
        # surprise that pattern could trigger; a fresh connection per
        # call cannot.
        return sqlite3.connect(str(self.path))

    # -- write: called by FilesystemEvidenceStore's put_* methods, after
    #    the canonical JSON write has already succeeded (see that
    #    module's docstring for the crash-safety ordering this depends on) --

    def record_source(self, source_id: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO sources (id) VALUES (?)", (source_id,))

    def record_document(self, document_id: str, source_id: str, doc_content_hash: str,
                         retrieval_method: str, retrieved_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO documents (id, source_id, content_hash, retrieval_method, retrieved_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (document_id, source_id, doc_content_hash, retrieval_method, retrieved_at),
            )

    def record_record(self, record_id: str, document_id: str, locator: str, source_id: str,
                       rec_content_hash: str) -> None:
        artifact_id = compute_artifact_id(source_id, locator)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO records (id, document_id, locator, artifact_id, content_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (record_id, document_id, locator, artifact_id, rec_content_hash),
            )

    def record_observation(self, observation_id: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO observations (id) VALUES (?)", (observation_id,))

    # -- read: the actual queries Phase J's reconnaissance found no
    #    efficient path for --

    def list_versions(self, artifact_id: str) -> Tuple[str, ...]:
        """Version ids (Document ids) for `artifact_id`, ordered by
        (retrieved_at, id) -- the exact ordering
        `ArtifactStore.list_versions` has always used, now an indexed
        query instead of a full scan of every persisted document/record."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT d.id FROM records r JOIN documents d ON r.document_id = d.id "
                "WHERE r.artifact_id = ? ORDER BY d.retrieved_at, d.id",
                (artifact_id,),
            ).fetchall()
        return tuple(row[0] for row in rows)

    def find_by_content_hash(self, doc_content_hash: str) -> Tuple[str, ...]:
        """Document ids whose raw content hashes to `doc_content_hash`,
        ordered by (retrieved_at, id) -- e.g. "has this exact content
        ever appeared under a different locator" (dedup auditing,
        Phase J section 6)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM documents WHERE content_hash = ? ORDER BY retrieved_at, id",
                (doc_content_hash,),
            ).fetchall()
        return tuple(row[0] for row in rows)

    def list_source_artifacts(self, source_id: str) -> Tuple[str, ...]:
        """Distinct artifact_ids ever acquired from `source_id`, ordered
        by first-observed retrieved_at (operator inspection, Phase J
        section 6)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT r.artifact_id, MIN(d.retrieved_at) AS first_seen "
                "FROM records r JOIN documents d ON r.document_id = d.id "
                "WHERE d.source_id = ? GROUP BY r.artifact_id ORDER BY first_seen",
                (source_id,),
            ).fetchall()
        return tuple(row[0] for row in rows)

    def locator_for_document(self, document_id: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT locator FROM records WHERE document_id = ? LIMIT 1", (document_id,)
            ).fetchone()
        return row[0] if row is not None else None

    def all_ids(self, category: str) -> Tuple[str, ...]:
        """Every id in one indexed category, sorted -- used by
        `DurablePool.fingerprint()` to reproduce
        `evidence.pool.EvidencePool.fingerprint()`'s exact sorted-id-set
        hash without reading a single object's content (Phase J section
        8's explicit question). Only valid for `_INDEXED_CATEGORIES`."""
        if category not in _INDEXED_CATEGORIES:
            raise ValueError(f"{category!r} is not an indexed category: {_INDEXED_CATEGORIES}")
        with self._connect() as conn:
            # category is validated against _INDEXED_CATEGORIES above -- never user input.
            rows = conn.execute(f"SELECT id FROM {category} ORDER BY id").fetchall()
        return tuple(row[0] for row in rows)

    def is_empty(self) -> bool:
        """Cheap staleness check -- O(1), never a full scan -- used to
        decide whether `rebuild()` is needed on construction (Phase J
        section 9's invariant: an index that looks empty relative to a
        non-empty canonical store is stale, not genuinely empty)."""
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM documents LIMIT 1").fetchone()
        return row is None

    def rebuild(self, store: "EvidenceStore") -> None:
        # TYPED TO THE PROTOCOL, not the filesystem store. This read
        # `"FilesystemEvidenceStore"` -- a STRING forward reference, which
        # is how a coupling looks when the import sits under
        # TYPE_CHECKING, and which the first version of the seam guard
        # walked straight past because it only matched ast.Name. The body
        # calls all_sources, all_documents, all_records and
        # all_observations and nothing else, so the coupling was
        # incidental. It mattered: this index is the half the platform
        # directive gives to PostgreSQL, and it was typed to the half it
        # gives to object storage.
        """Repopulates every table from `store`'s own canonical `all_*()`
        methods -- the filesystem remains authoritative; this index is
        always reconstructible from it. Safe to call on a non-empty
        index too (every insert is `INSERT OR IGNORE`, idempotent on the
        primary key)."""
        for source in store.all_sources():
            self.record_source(source.id)

        source_id_by_document_id = {}
        for document in store.all_documents():
            source_id_by_document_id[document.id] = document.source_id
            self.record_document(
                document.id, document.source_id, content_hash(document.raw_content),
                document.retrieval_method, document.retrieved_at,
            )

        for record in store.all_records():
            source_id = source_id_by_document_id.get(record.document_id)
            if source_id is None:
                # A Record whose Document isn't (yet) persisted -- not
                # expected in normal operation (ArtifactStore.put always
                # writes both together), but rebuild must not crash on a
                # partially-written directory; skip it, exactly as
                # ArtifactStore._locator_for already tolerates a Record
                # with no matching Document.
                continue
            self.record_record(record.id, record.document_id, record.locator, source_id, content_hash(record.raw_content))

        for observation in store.all_observations():
            self.record_observation(observation.id)
