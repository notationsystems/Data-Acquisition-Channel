"""DurablePool: an EvidencePool *subclass* that persists every admitted
object in addition to the normal in-memory storage EvidencePool already
provides.

This is the whole persistence mechanism -- nothing else changes.
`EvidencePool`'s own code (in the vendored, read-only State-Space repo)
is never touched. Every read method (`get_*`, `all_*`, `has_*`,
`fingerprint`, `fingerprint_history`, `__len__`) still behaves exactly
as documented on `EvidencePool` -- only the 8 `put_*` methods are
overridden (unchanged since Phase B, each adding exactly one line --
write it to the `FilesystemEvidenceStore` -- before delegating to the
real `EvidencePool.put_*` implementation via `super()`).

Because `scout.pipeline.run_scout` only ever calls the documented
EvidencePool surface (`put_*`, plus what `evidence.admission` needs:
`has_*`/`get_*`), passing a `DurablePool` instance in place of a plain
`EvidencePool` is a drop-in substitution -- `run_scout` cannot tell the
difference, and nothing about the admission gate, identity, or Evidence
types changes as a result.

PHASE K -- LAZY RESTORE:

Through Phase J, `DurablePool.restore(store)` eagerly loaded the ENTIRE
historical corpus into memory before returning -- exactly the
algorithmic problem that phase's reconnaissance identified (every
checkpoint-aware CLI invocation paid this cost, regardless of whether it
ever needed more than a handful of `has_document`/`get_document` calls
for duplicate detection). `restore()` is now cheap: it returns
immediately, and full corpus materialization (`_replay_into`, identical
to Phase B-J's own replay logic, same dependency order) is deferred
until a caller actually invokes a method whose CORRECT answer requires
seeing the whole corpus (`all_referents`, `all_claimed_relationships`,
`all_observations`, `all_derived_values`, `all_derived_groundings`,
`fingerprint_history`, `__len__`) -- at which point it runs exactly
once, memoized via `self._hydrated`.

Individual `get_source`/`has_source`/`get_document`/`has_document`/
`get_record`/`has_record`/`get_observation`/`has_observation` calls --
the orchestrator's actual acquisition-time hot path (duplicate
detection via `has_document`, admission's own `has_*`/`get_*` checks)
-- never require full hydration: each resolves against the already-O(1)
`FilesystemEvidenceStore` (filename = id, direct path lookup, unchanged
since Phase B) on first miss, memoizing the result into the same
in-memory dict `_replay_into` would have populated it into, via the
same `EvidencePool.put_*` call `_replay_into` already uses -- so a pool
that only ever calls these methods hydrates only the objects it
actually touches, never the rest of the corpus.

`get_referent`/`has_referent`/`get_derived_value`/`has_derived_value`/
`get_derived_grounding`/`has_derived_grounding` fall back to full
hydration on any access -- these three categories are never populated
by any adapter built so far (arXiv, EDGAR, USGS, NOAA all extract
`entities=()`, `relations=()`), so there is no real corpus to avoid
loading for them, and a bespoke lazy path would add complexity with no
measurable benefit. `evidence.pool.EvidencePool` has no `get_claimed_relationship`/
`has_claimed_relationship` at all (only `all_claimed_relationships`),
so there is nothing to override there beyond the `all_*` case already
covered above.

`fingerprint()` is the one method optimized WITHOUT ever hydrating at
all -- see its own docstring below.

`EvidencePool.fingerprint()`/`fingerprint_history()`/`__len__()`'s
MEANING is completely unchanged by any of this: once a caller actually
invokes one of the full-corpus methods, it sees exactly the same
answer restoring eagerly would have produced (same objects, same
in-memory dicts, same vendored code computing the result) -- only the
TIMING of when that cost is paid has moved, from "always, at restore()"
to "only if and when a caller's own request actually requires it."
"""

from __future__ import annotations

from typing import Tuple

from evidence.identity import content_hash
from evidence.pool import EvidencePool
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

from daf.storage.evidence_store import EvidenceStore

_INDEXED_FINGERPRINT_CATEGORIES = ("sources", "documents", "records", "observations")
_SCANNED_FINGERPRINT_CATEGORIES = (
    "referents",
    "claimed_relationships",
    "derived_values",
    "derived_groundings",
)


class DurablePool(EvidencePool):
    def __init__(self, store: EvidenceStore) -> None:
        super().__init__()
        self.store = store
        self._hydrated = False

    # -- put: unchanged since Phase B --

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

    # -- lazy single-object access: the 4 categories that scale with
    #    acquisition volume in every real DAF workload built so far --

    def has_source(self, source_id: str) -> bool:
        return super().has_source(source_id) or (not self._hydrated and self.store.has_source(source_id))

    def get_source(self, source_id: str) -> Source:
        if not super().has_source(source_id) and not self._hydrated:
            EvidencePool.put_source(self, self.store.get_source(source_id))
        return super().get_source(source_id)

    def has_document(self, document_id: str) -> bool:
        return super().has_document(document_id) or (not self._hydrated and self.store.has_document(document_id))

    def get_document(self, document_id: str) -> Document:
        if not super().has_document(document_id) and not self._hydrated:
            EvidencePool.put_document(self, self.store.get_document(document_id))
        return super().get_document(document_id)

    def has_record(self, record_id: str) -> bool:
        return super().has_record(record_id) or (not self._hydrated and self.store.has_record(record_id))

    def get_record(self, record_id: str) -> Record:
        if not super().has_record(record_id) and not self._hydrated:
            EvidencePool.put_record(self, self.store.get_record(record_id))
        return super().get_record(record_id)

    def has_observation(self, observation_id: str) -> bool:
        return super().has_observation(observation_id) or (
            not self._hydrated and self.store.has_observation(observation_id)
        )

    def get_observation(self, observation_id: str) -> Observation:
        if not super().has_observation(observation_id) and not self._hydrated:
            EvidencePool.put_observation(self, self.store.get_observation(observation_id))
        return super().get_observation(observation_id)

    # -- the 3 categories no real adapter has ever populated: correct,
    #    but not specially optimized -- see module docstring --

    def has_referent(self, referent_id: str) -> bool:
        self._ensure_hydrated()
        return super().has_referent(referent_id)

    def get_referent(self, referent_id: str) -> Referent:
        self._ensure_hydrated()
        return super().get_referent(referent_id)

    def has_derived_value(self, derived_value_id: str) -> bool:
        self._ensure_hydrated()
        return super().has_derived_value(derived_value_id)

    def get_derived_value(self, derived_value_id: str) -> DerivedValue:
        self._ensure_hydrated()
        return super().get_derived_value(derived_value_id)

    def has_derived_grounding(self, grounding_id: str) -> bool:
        self._ensure_hydrated()
        return super().has_derived_grounding(grounding_id)

    def get_derived_grounding(self, grounding_id: str) -> DerivedGrounding:
        self._ensure_hydrated()
        return super().get_derived_grounding(grounding_id)

    # -- full-corpus methods: correct by construction (they hydrate
    #    fully before delegating to the unmodified vendored logic) --

    def all_referents(self) -> Tuple[Referent, ...]:
        self._ensure_hydrated()
        return super().all_referents()

    def all_claimed_relationships(self) -> Tuple[ClaimedRelationship, ...]:
        self._ensure_hydrated()
        return super().all_claimed_relationships()

    def all_observations(self) -> Tuple[Observation, ...]:
        self._ensure_hydrated()
        return super().all_observations()

    def all_derived_values(self) -> Tuple[DerivedValue, ...]:
        self._ensure_hydrated()
        return super().all_derived_values()

    def all_derived_groundings(self) -> Tuple[DerivedGrounding, ...]:
        self._ensure_hydrated()
        return super().all_derived_groundings()

    def fingerprint_history(self) -> Tuple[str, ...]:
        self._ensure_hydrated()
        return super().fingerprint_history()

    def __len__(self) -> int:
        self._ensure_hydrated()
        return super().__len__()

    def fingerprint(self) -> str:
        """Phase J section 8's explicit question, answered: YES,
        `fingerprint()` can be computed from the metadata index without
        loading any object's content -- because
        `evidence.pool.EvidencePool.fingerprint()` (vendored, unchanged)
        is ITSELF already a pure function of the *sorted set of ids*
        each category currently holds, never of any object's actual
        content (confirmed by reading its source directly: it hashes
        `sorted(self._sources)`, ..., `sorted(self._derived_groundings)`
        -- dict keys, not values). So instead of paying
        `_ensure_hydrated()`'s full-corpus cost, this override reproduces
        that exact same payload shape directly: already-hydrated ids
        (if any objects were lazily loaded above) unioned with whatever
        this pool has NOT yet hydrated, read as id-only listings --
        `self.store.index.all_ids(...)` for the four categories Phase K
        actually indexes (sources/documents/records/observations), and
        `self.store.all_ids_by_filename(...)` (a filename glob, no JSON
        body parsed) for the four categories Phase K's index does not
        cover, because no real adapter has ever populated them (see this
        module's own docstring). The result is byte-for-byte identical
        to calling `_ensure_hydrated()` first and then
        `super().fingerprint()` -- proven by
        `tests/test_durable_pool.py`'s equivalence tests -- but this
        path never reads a single Document/Record/Observation's actual
        content to get there."""
        if self._hydrated:
            return super().fingerprint()

        payload = {}
        for category in _INDEXED_FINGERPRINT_CATEGORIES:
            in_memory_ids = set(getattr(self, f"_{category}").keys())
            payload[category] = sorted(in_memory_ids | set(self.store.index.all_ids(category)))
        for category in _SCANNED_FINGERPRINT_CATEGORIES:
            in_memory_ids = set(getattr(self, f"_{category}").keys())
            payload[category] = sorted(in_memory_ids | set(self.store.all_ids_by_filename(category)))

        return content_hash(payload)

    def _ensure_hydrated(self) -> None:
        if not self._hydrated:
            _replay_into(self, self.store)
            self._hydrated = True

    @classmethod
    def restore(cls, store: EvidenceStore) -> "DurablePool":
        """The "process restart" step: reconstructs a DurablePool that
        answers exactly as if the entire durable corpus had been loaded
        -- but, since Phase K, does not actually pay that cost until a
        caller asks for something that requires it (see this module's
        own docstring). This does not re-run `evidence.admission` --
        those objects were already admitted once, before persistence.
        Replay (whenever it does happen) reconstructs already-validated
        state; it does not re-validate it, exactly as loading an
        existing database table back into memory does not re-run the
        constraints that accepted each row originally."""
        return cls(store)

    def force_full_hydration(self) -> None:
        """Explicit escape hatch for a caller that specifically wants
        the pre-Phase-K "load everything now" behavior (e.g. to front-
        load the cost outside a latency-sensitive request). Never called
        internally -- every method above hydrates lazily and correctly
        on its own."""
        self._ensure_hydrated()


def load_pool(store: EvidenceStore) -> EvidencePool:
    """Like `DurablePool.restore`, but returns a plain, non-durable
    `EvidencePool` -- for a read-only "retrieve after restart" use case
    that has no need to keep writing back to `store`. Unlike
    `DurablePool`, a plain `EvidencePool` has no lazy-loading override,
    so this still fully replays the corpus up front -- exactly Phase
    A-J's existing behavior, unchanged, for exactly the same reason a
    read-only snapshot has no "only load what's touched" benefit to
    offer if the caller's whole point is inspecting the full pool."""
    pool = EvidencePool()
    _replay_into(pool, store)
    return pool


def _replay_into(pool: EvidencePool, store: EvidenceStore) -> None:
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
