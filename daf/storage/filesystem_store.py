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

PHASE K -- BLOB SEPARATION AND METADATA INDEX:

Two things changed this phase, both purely at the storage layer --
`evidence.types.Document`/`Record` (vendored) are completely unchanged,
and every in-memory object this module hands back still carries a real
`raw_content` string exactly as before:

1. `documents/{id}.json` and `records/{id}.json` no longer each inline a
   full copy of `raw_content`. Phase A-J's `run_scout` (vendored,
   unmodified) always builds a Document and its one Record from the
   IDENTICAL raw string (`make_document(..., raw_content=raw_doc.content)`
   immediately followed by `make_record(..., raw_content=raw_doc.content)`
   -- see `scout/pipeline.py`), so every acquisition was writing that
   string to disk twice. Now the bytes live once, in `self.blobs`
   (`daf.storage.blob_store.BlobStore`), keyed by
   `content_hash(raw_content)`; the JSON metadata file stores that hash
   as a reference instead. `get_document`/`get_record`/`all_documents`/
   `all_records` resolve the reference back into a real, fully-populated
   `Document`/`Record` transparently -- every existing caller of this
   module's public API sees no difference.

   Directories written before this phase inlined `raw_content` directly
   and never wrote a `content_hash` key -- those files remain fully
   readable forever (`_resolve_raw_content` below checks for an inline
   `raw_content` first and only falls back to the blob store when it is
   absent), so no migration is required and no existing durable
   directory needs to be rewritten.

2. `self.index` (`daf.storage.metadata_index.MetadataIndex`, a small
   embedded SQLite database) is updated, after each successful write,
   with just the columns Phase J's reconnaissance found a real query
   against (`artifact_id`/`source_id`/`content_hash`/`retrieved_at`/
   `locator`). It is purely a derived index: `ArtifactStore` uses it to
   answer "what versions exist for this artifact"/"find by content
   hash"/"list this source's artifacts" without a full directory scan,
   and `DurablePool.fingerprint()` uses it to answer "what ids exist"
   without reading any object's content -- but the filesystem above
   remains the sole raw-content authority. If `index.sqlite` is deleted,
   `MetadataIndex.rebuild(store)` reconstructs an identical logical
   index purely from what's already durably on disk (`__init__` below
   does this automatically whenever it finds an empty index next to a
   non-empty store).

CRASH-SAFETY ORDERING (Phase J section 10): every `put_*` for `documents`/
`records` writes in this order -- (1) the blob (idempotent, atomic
temp+replace), (2) the metadata JSON (atomic temp+replace, referencing
the blob's hash), (3) the index row (`INSERT OR IGNORE`, cheap). A crash
between (1) and (2) leaves an orphaned-but-harmless blob (content-
addressed; a future write of the same content just finds it already
there). A crash between (2) and (3) leaves canonical storage fully
correct and self-verifiable, with the index merely stale -- exactly the
state `rebuild()` exists to repair, and the state `__init__` already
detects and repairs automatically. No ordering can produce a metadata
entry referencing a blob that was never written.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional, Tuple, TypeVar

from evidence.identity import content_hash as _content_hash
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
from daf.storage.blob_store import BlobStore
from daf.storage.metadata_index import MetadataIndex

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

    def __init__(self, root: Path, *, blobs: Optional[BlobStore] = None, index: Optional[MetadataIndex] = None) -> None:
        self.root = Path(root)
        for category in self._CATEGORIES:
            (self.root / category).mkdir(parents=True, exist_ok=True)
        self.blobs = blobs if blobs is not None else BlobStore(self.root / "blobs")
        self.index = index if index is not None else MetadataIndex(self.root / "index.sqlite")
        self._rebuild_index_if_stale()

    def _rebuild_index_if_stale(self) -> None:
        """An index with zero documents next to a store with at least
        one persisted document is stale (deleted, or a pre-Phase-K
        directory opened for the first time under this phase's code),
        not genuinely empty -- see the module docstring's "MIGRATION"
        note. Both checks are O(1): `is_empty()` is a single indexed
        query, and the glob below stops at the first match rather than
        enumerating the whole directory."""
        if not self.index.is_empty():
            return
        has_any_document = next((self.root / "documents").glob("*.json"), None) is not None
        if has_any_document:
            self.index.rebuild(self)

    # -- generic write/read machinery, shared by the 6 categories with
    #    no raw-content duplication concern (sources/observations/
    #    referents/claimed_relationships/derived_values/derived_groundings) --

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

    # -- blob-referenced serialization for documents/records only --

    def _resolve_raw_content(self, payload: dict) -> dict:
        """Backward-compatible with every directory this codebase has
        ever written: a pre-Phase-K file inlines `raw_content` directly
        (and has no `content_hash` key); a Phase-K-or-later file stores
        `raw_content: null` plus `content_hash`, resolved here via
        `self.blobs`. Either way the caller gets back a payload shaped
        exactly like `daf.storage.serialization` has always expected."""
        if payload.get("raw_content") is not None:
            return payload
        payload = dict(payload)
        payload["raw_content"] = self.blobs.get(payload["content_hash"])
        return payload

    def _document_from_dict(self, payload: dict) -> Document:
        return serialization.document_from_dict(self._resolve_raw_content(payload))

    def _record_from_dict(self, payload: dict) -> Record:
        return serialization.record_from_dict(self._resolve_raw_content(payload))

    # -- put: one per category --

    def put_source(self, source: Source) -> None:
        self._write("sources", source.id, serialization.source_to_dict(source), serialization.source_from_dict)
        self.index.record_source(source.id)

    def put_document(self, document: Document) -> None:
        doc_hash = _content_hash(document.raw_content)
        self.blobs.put(doc_hash, document.raw_content)  # (1) blob, before metadata -- see module docstring
        payload = {
            "id": document.id,
            "source_id": document.source_id,
            "raw_content": None,
            "content_hash": doc_hash,
            "retrieval_method": document.retrieval_method,
            "retrieved_at": document.retrieved_at,
        }
        self._write("documents", document.id, payload, self._document_from_dict)  # (2) metadata
        self.index.record_document(  # (3) index -- last, cheap, always rebuildable if skipped by a crash
            document.id, document.source_id, doc_hash, document.retrieval_method, document.retrieved_at
        )

    def put_record(self, record: Record) -> None:
        rec_hash = _content_hash(record.raw_content)
        self.blobs.put(rec_hash, record.raw_content)  # (1) blob
        payload = {
            "id": record.id,
            "document_id": record.document_id,
            "locator": record.locator,
            "raw_content": None,
            "content_hash": rec_hash,
        }
        self._write("records", record.id, payload, self._record_from_dict)  # (2) metadata
        if self.has_document(record.document_id):  # (3) index -- needs the document's source_id
            source_id = self.get_document(record.document_id).source_id
            self.index.record_record(record.id, record.document_id, record.locator, source_id, rec_hash)
        # else: the Document isn't persisted yet -- not expected via ArtifactStore.put/run_scout's
        # own ordering, but canonical storage above is still fully correct either way; a later
        # rebuild() picks this record up once its Document exists.

    def put_observation(self, observation: Observation) -> None:
        self._write(
            "observations",
            observation.id,
            serialization.observation_to_dict(observation),
            serialization.observation_from_dict,
        )
        self.index.record_observation(observation.id)

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
        return self._document_from_dict(self._read_one("documents", document_id))

    def get_record(self, record_id: str) -> Record:
        return self._record_from_dict(self._read_one("records", record_id))

    def get_observation(self, observation_id: str) -> Observation:
        return serialization.observation_from_dict(self._read_one("observations", observation_id))

    # -- has: one per category --

    def has_source(self, source_id: str) -> bool:
        return self._has("sources", source_id)

    def has_document(self, document_id: str) -> bool:
        return self._has("documents", document_id)

    def has_record(self, record_id: str) -> bool:
        return self._has("records", record_id)

    def has_observation(self, observation_id: str) -> bool:
        return self._has("observations", observation_id)

    # -- all: one per category, deterministic (sorted-by-filename) order --

    def all_sources(self) -> Tuple[Source, ...]:
        return self._all_typed("sources", serialization.source_from_dict)

    def all_documents(self) -> Tuple[Document, ...]:
        return tuple(self._document_from_dict(payload) for payload in self._read_all("documents"))

    def all_records(self) -> Tuple[Record, ...]:
        return tuple(self._record_from_dict(payload) for payload in self._read_all("records"))

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

    # -- cheap id-only listing: no JSON body is parsed -- used by
    #    DurablePool.fingerprint() for the 4 categories Phase K's index
    #    deliberately does not cover (see this module's own docstring
    #    and daf/storage/metadata_index.py's) --

    @classmethod
    def categories(cls) -> Tuple[str, ...]:
        """The persisted evidence categories.

        Public because another module legitimately needs to enumerate
        them: the unclassified-backlog metric
        (`daf/execution/metrics.py`) must cover every category the store
        actually has, and keeping a second copy of this list is how the
        two would silently drift apart when a ninth category appears."""
        return cls._CATEGORIES

    def all_ids_by_filename(self, category: str) -> Tuple[str, ...]:
        directory = self.root / category
        return tuple(sorted(path.stem for path in directory.glob("*.json")))
