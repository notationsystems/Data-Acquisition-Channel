"""DurablePool: an EvidencePool *subclass* that persists every admitted
object in addition to the normal in-memory storage EvidencePool already
provides.

This is the whole persistence mechanism -- nothing else changes.
`EvidencePool`'s own code (in the vendored, read-only State-Space repo)
is never touched. Every read method (`get_*`, `all_*`, `has_*`,
`fingerprint`, `fingerprint_history`, `__len__`) is inherited verbatim,
with its existing semantics completely unchanged. Only the 8 `put_*`
methods are overridden, each adding exactly one line -- write it to the
`FilesystemEvidenceStore` -- before delegating to the real
`EvidencePool.put_*` implementation via `super()`.

Because `scout.pipeline.run_scout` only ever calls the documented
EvidencePool surface (`put_*`, plus what `evidence.admission` needs:
`has_*`/`get_*`), passing a `DurablePool` instance in place of a plain
`EvidencePool` is a drop-in substitution -- `run_scout` cannot tell the
difference, and nothing about the admission gate, identity, or Evidence
types changes as a result.
"""

from __future__ import annotations

from evidence.pool import EvidencePool
from evidence.types import ClaimedRelationship, DerivedGrounding, DerivedValue, Document, Observation, Record, Referent, Source

from daf.storage.filesystem_store import FilesystemEvidenceStore


class DurablePool(EvidencePool):
    def __init__(self, store: FilesystemEvidenceStore) -> None:
        super().__init__()
        self.store = store

    def put_source(self, source: Source) -> None:
        self.store.put_source(source)
        super().put_source(source)

    def put_document(self, document: Document) -> None:
        self.store.put_document(document)
        super().put_document(document)

    def put_record(self, record: Record) -> None:
        self.store.put_record(record)
        super().put_record(record)

    def put_observation(self, observation: Observation) -> None:
        self.store.put_observation(observation)
        super().put_observation(observation)

    def put_referent(self, referent: Referent) -> None:
        self.store.put_referent(referent)
        super().put_referent(referent)

    def put_claimed_relationship(self, relationship: ClaimedRelationship) -> None:
        self.store.put_claimed_relationship(relationship)
        super().put_claimed_relationship(relationship)

    def put_derived_value(self, derived_value: DerivedValue) -> None:
        self.store.put_derived_value(derived_value)
        super().put_derived_value(derived_value)

    def put_derived_grounding(self, grounding: DerivedGrounding) -> None:
        self.store.put_derived_grounding(grounding)
        super().put_derived_grounding(grounding)

    @classmethod
    def restore(cls, store: FilesystemEvidenceStore) -> "DurablePool":
        """The "process restart" step: reconstructs a DurablePool purely
        from what `store` has durably persisted. Never reuses any
        in-memory object from a prior pool -- every object is rebuilt
        from its persisted raw fields and re-verified against its own
        content-hash identity (see daf.storage.serialization), then
        loaded via the plain `EvidencePool.put_*` methods (bypassing
        this class's own overrides, since these objects are already on
        disk and re-persisting them would be redundant, not incorrect --
        see `_replay_into`).

        This does not re-run `evidence.admission` -- these objects were
        already admitted once, before persistence. Replay reconstructs
        already-validated state; it does not re-validate it, exactly as
        loading an existing database table back into memory does not
        re-run the constraints that accepted each row originally."""
        pool = cls(store)
        _replay_into(pool, store)
        return pool


def load_pool(store: FilesystemEvidenceStore) -> EvidencePool:
    """Like `DurablePool.restore`, but returns a plain, non-durable
    `EvidencePool` -- for a read-only "retrieve after restart" use case
    that has no need to keep writing back to `store`."""
    pool = EvidencePool()
    _replay_into(pool, store)
    return pool


def _replay_into(pool: EvidencePool, store: FilesystemEvidenceStore) -> None:
    """Loads every persisted object into `pool` in dependency order,
    calling the base `EvidencePool.put_*` methods explicitly (not
    `pool.put_*`, which would re-persist already-persisted objects if
    `pool` happens to be a `DurablePool`)."""
    for source in store.all_sources():
        EvidencePool.put_source(pool, source)
    for document in store.all_documents():
        EvidencePool.put_document(pool, document)
    for record in store.all_records():
        EvidencePool.put_record(pool, record)
    for observation in store.all_observations():
        EvidencePool.put_observation(pool, observation)
    for referent in store.all_referents():
        EvidencePool.put_referent(pool, referent)
    for relationship in store.all_claimed_relationships():
        EvidencePool.put_claimed_relationship(pool, relationship)
    for derived_value in store.all_derived_values():
        EvidencePool.put_derived_value(pool, derived_value)
    for grounding in store.all_derived_groundings():
        EvidencePool.put_derived_grounding(pool, grounding)
