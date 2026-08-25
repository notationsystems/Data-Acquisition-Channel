"""`FrozenMapping` -- an immutable, hashable `dict` subclass.

PHASE 34's finding, in one sentence: no existing primitive in this
repository or its vendored substrate is simultaneously a `Mapping`,
natively hashable, and reconstructible from JSON as itself, and exactly
that intersection is what a Mapping-shaped `content` value (e.g.
`conditions`) needs to survive both `materials.analysis`'s
`_group_by_comparison_context` (requires native `hash()`) and
`evidence.identity.content_hash`'s own documented contract (payload must
reduce to plain dict/list/str/int/float/bool/None). See
`docs/PHASE_34_HASHABLE_CONDITION_REPRESENTATION.md` for the full
measurement.

WHY A `dict` SUBCLASS, NOT A `collections.abc.Mapping` implementation.
`Mapping` alone is not enough: `evidence.identity.content_hash` calls
`json.dumps` with no custom encoder, which only recognizes `dict`
instances (isinstance, so a subclass qualifies) -- a `Mapping` that is
not also a `dict` raises `TypeError: Object of type ... is not JSON
serializable` at `Observation`/`DerivedValue` construction time, measured
directly against `evidence.identity.content_hash` and
`evidence.types.make_observation` before this type was written. A `dict`
subclass serializes exactly like a plain dict (same keys, same values),
so `Observation.id`/`DerivedValue.id` are IDENTICAL whether a given
content value is a plain dict or a `FrozenMapping` of the same items --
measured, not assumed.

WHY THE SERIALIZATION LAYER ALSO RECONSTRUCTS THIS TYPE ON LOAD (see
`daf/storage/serialization.py`), not just the extractor that first
constructs one. Measured directly: `DurablePool`/`ClassifiedPool` hydrate
their full corpus from `FilesystemEvidenceStore` (plain JSON) the first
time any of `scout.pipeline.run_scout`'s own `build_trust_graph` calls
`all_referents`/`all_claimed_relationships` -- which happens on EVERY
acquisition, before any object is ever put. For a brand-new, empty store
this makes `_hydrated` become permanently `True` before extraction even
begins, so a same-process acquire-then-analyze never round-trips its own
observations through JSON at all. But `DurablePool.restore`/`load_pool`
-- the documented "process restart" / "reopen an existing store" path --
constructs a FRESH, unhydrated pool over an ALREADY non-empty store, and
that pool's first `run_scout` call hydrates a NON-empty corpus, which
means `FilesystemEvidenceStore.all_observations`/`get_observation`
(via `daf/storage/serialization.py`'s `observation_from_dict`) is what
actually reconstructs every previously-persisted `Observation.content`.
`json.loads` has no extension point installed anywhere in this codebase,
so with no counterpart on the read side, `conditions` would reconstruct
as a plain, unhashable `dict` for every already-persisted reading the
moment a second process (or a second, freshly-restored pool in the same
process) reopened the store -- confirmed by reproducing exactly this
`TypeError: unhashable type: 'dict'` with a two-pool-instance test before
this file's read-side counterpart was written. `FrozenMapping` alone,
without that counterpart, is not a fix; it only appears to work in the
one call order a test happens to use.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


class FrozenMapping(dict):
    """A `dict` that cannot be mutated after construction and is hashable
    by its sorted `(key, value)` pairs -- so two `FrozenMapping`s built
    from the same key/value pairs in a different order compare equal and
    hash equal, exactly as `_group_by_comparison_context`'s own
    `sorted(context.items(), key=lambda kv: kv[0])` already treats
    dict-shaped comparison contexts. Equality with a plain `dict` of the
    same items is unchanged `dict.__eq__` behaviour -- not overridden.

    Any nested `dict` value is itself wrapped as a `FrozenMapping` at
    construction, so `FrozenMapping({"a": {"b": 1}})` is fully immutable
    and fully hashable, not just at its top level -- the same recursive
    rule `daf/storage/serialization.py` applies when reconstructing one
    from persisted JSON, so a value built in an extractor and the same
    value reconstructed after a disk round trip are indistinguishable.

    Not a general-purpose immutable-dict library import: this repository
    has none (measured -- see the Phase 34 report's primitive inventory),
    and the whole type is the ~15 lines actually needed for one nested
    Mapping-valued content key to be hashable without weakening the
    Mapping requirement `science.admissibility.no_context_free_property`
    already enforces, or the native-hashability requirement
    `materials.analysis._group_by_comparison_context` already enforces."""

    __slots__ = ()

    def __init__(self, data: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(
            {
                key: (value if isinstance(value, FrozenMapping) else FrozenMapping(value))
                if isinstance(value, dict)
                else value
                for key, value in dict(data or {}).items()
            }
        )

    def __hash__(self) -> int:  # type: ignore[override]
        return hash(tuple(sorted(self.items(), key=lambda kv: kv[0])))

    def _refuse_mutation(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(f"{type(self).__name__} is immutable")

    __setitem__ = _refuse_mutation
    __delitem__ = _refuse_mutation
    __ior__ = _refuse_mutation
    update = _refuse_mutation
    pop = _refuse_mutation
    popitem = _refuse_mutation
    clear = _refuse_mutation
    setdefault = _refuse_mutation


def freeze_nested_mappings(content: Mapping[str, Any]) -> dict:
    """Wrap every `dict`-valued entry of `content` (not `content` itself)
    as a `FrozenMapping`, recursively. A no-op for every content shape
    every extractor produced before Phase 34: none has ever had a
    dict-valued content entry (measured directly against every shipped
    extractor's real acquisition fixtures), so this only changes anything
    once a `conditions`-shaped (or similarly Mapping-valued) key exists."""
    return {
        key: (value if isinstance(value, FrozenMapping) else FrozenMapping(value))
        if isinstance(value, dict)
        else value
        for key, value in content.items()
    }
