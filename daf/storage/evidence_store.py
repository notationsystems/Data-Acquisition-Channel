"""What a durable pool needs from a store, and nothing else.

WHY THIS EXISTS. `DurablePool.__init__` took `store: FilesystemEvidenceStore`
-- the concrete class -- while calling eighteen methods on it that have
nothing to do with a filesystem. So a PostgreSQL or S3-backed store was a
drop-in in SHAPE and not in TYPE, and the checker would have refused one.
`daf/catalog/cli.py` and `daf/catalog/history.py` had the same coupling.

The directive's layers 1 and 2 -- object storage and PostgreSQL as
canonical operational truth -- are exactly the substitution this protocol
makes possible. It does not perform that substitution; it removes the
reason the substitution would have been a rewrite.

WHAT IS AND IS NOT IN THE PROTOCOL. Every method here is one DurablePool
actually calls, enumerated from its source rather than from the concrete
class's public surface. A protocol listing what the filesystem store
happens to offer would be a description of today's implementation wearing
an interface's name, and the next implementation would have to grow
methods nobody needs.

THE STORE IS ALREADY SPLIT THE WAY THE DIRECTIVE SPLITS ITS FIRST TWO
LAYERS, and that was found by writing this protocol rather than known
before. `FilesystemEvidenceStore(root, blobs=..., index=...)` composes a
BLOB half and a METADATA INDEX, and the index is a real relational store
-- SQLite -- answering five catalog queries: all_ids, list_versions,
find_by_content_hash, list_source_artifacts and locator_for_document.

Those five are precisely what the directive gives to PostgreSQL, and the
blob half is precisely what it gives to S3. So the migration is not one
substitution but two, along a seam that already exists:

    BlobStore                -> S3-compatible object storage   (layer 1)
    MetadataIndex (SQLite)   -> PostgreSQL                     (layer 2)
    FilesystemEvidenceStore  -> whatever composes the two

`MetadataIndexQueries` below is stated separately for that reason. A
first draft of this file typed `index` as `Any`, which typechecked and
hid the most important structural fact in the module.

THIS IS A TYPING SEAM AND NOT AN ABSTRACTION LAYER. There is no base
class, no registry and no factory. Nothing is indirected at runtime;
`FilesystemEvidenceStore` satisfies it structurally without knowing it
exists, which is what a Protocol is for.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class MetadataIndexQueries(Protocol):
    """The catalog half of a store: the five questions asked of it.

    Enumerated from every `store.index.<method>` call in daf/, not from
    what MetadataIndex happens to offer -- it also has six `record_*`
    writers that only the filesystem store itself calls, and putting
    those here would make the next implementation carry the current
    one's write path.
    """

    def all_ids(self, category: str) -> Tuple[str, ...]: ...
    def list_versions(self, artifact_id: str) -> Tuple[str, ...]: ...
    def find_by_content_hash(self, doc_content_hash: str) -> Tuple[str, ...]: ...
    def list_source_artifacts(self, source_id: str) -> Tuple[str, ...]: ...
    def locator_for_document(self, document_id: str) -> Optional[str]: ...


@runtime_checkable
class EvidenceStore(Protocol):
    """The durable side of an evidence pool.

    Runtime-checkable so a test can assert that a second implementation
    satisfies it without importing it -- but `isinstance` against a
    Protocol checks METHOD NAMES ONLY, never signatures, so a green
    isinstance is not a working store. The test that matters drives a
    real DurablePool through a second implementation instead.
    """

    def put_source(self, source: Any) -> None: ...
    def put_document(self, document: Any) -> None: ...
    def put_record(self, record: Any) -> None: ...
    def put_observation(self, observation: Any) -> None: ...
    def put_referent(self, referent: Any) -> None: ...
    def put_claimed_relationship(self, relationship: Any) -> None: ...
    def put_derived_value(self, derived_value: Any) -> None: ...
    def put_derived_grounding(self, grounding: Any) -> None: ...

    def has_source(self, source_id: str) -> bool: ...
    def has_document(self, document_id: str) -> bool: ...
    def has_record(self, record_id: str) -> bool: ...
    def has_observation(self, observation_id: str) -> bool: ...

    def get_source(self, source_id: str) -> Any: ...
    def get_document(self, document_id: str) -> Any: ...
    def get_record(self, record_id: str) -> Any: ...
    def get_observation(self, observation_id: str) -> Any: ...

    # THE REPLAY SURFACE. A first draft of this protocol omitted all
    # eight of these, because it was enumerated by grepping
    # `self.store.<method>` inside DurablePool -- which misses the
    # module-level `_replay_into`, where the store is a parameter rather
    # than an attribute. mypy enumerated them properly. An interface
    # derived by pattern-matching one calling convention is the
    # coverage-by-enumeration shape this repository already files.
    def all_sources(self) -> Tuple[Any, ...]: ...
    def all_documents(self) -> Tuple[Any, ...]: ...
    def all_records(self) -> Tuple[Any, ...]: ...
    def all_observations(self) -> Tuple[Any, ...]: ...
    def all_referents(self) -> Tuple[Any, ...]: ...
    def all_claimed_relationships(self) -> Tuple[Any, ...]: ...
    def all_derived_values(self) -> Tuple[Any, ...]: ...
    def all_derived_groundings(self) -> Tuple[Any, ...]: ...

    def all_ids_by_filename(self, category: str) -> Tuple[str, ...]: ...

    @property
    def index(self) -> MetadataIndexQueries: ...
