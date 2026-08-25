# Phase 34 — Hashable Condition Representation

*(Continues from `1fc7730`. Answers the question Phase 33 posed: is there a
representation for `conditions` that is simultaneously a `Mapping`, natively hashable,
and safe across every existing consumer, including persistence?)*

**Result: yes — Decision B, a small shared representation extension.**
`daf.storage.frozen_mapping.FrozenMapping`, an immutable `dict` subclass, is `Mapping`
by construction, natively hashable, and (with one matching change on the deserialization
side) round-trip-stable through persistence. NOAA's `conditions = {"datum": ...}` is now
wired using it. **`Observation.id` is unchanged** by the representation choice — measured
directly, not assumed. No vendored file was touched. No other extractor was touched.
USGS is unaffected.

The single most consequential finding is that a hashable wrapper type **alone is not
sufficient**: `scout.pipeline.run_scout` hydrates a pool's full corpus from disk the
first time it is asked for referents/relationships, and for a *reopened, already
non-empty* store this reconstructs `content` purely from `json.loads`, with no
extension point anywhere in this codebase. Without a matching read-side fix, a hashable
`conditions` value works in one call order and silently degrades back into a plain,
unhashable `dict` in another — exactly the "convenient but not real" trap the brief
warned against. Both call orders are now exercised by real, vendored
`materials.analysis.analyze()`, not a mock.

---

## Consumer inventory

Every real consumer of `Observation.content`/`DerivedValue.content` that a
Mapping-valued entry could reach, inspected directly rather than assumed:

| Consumer | Vendored | Requirement | Modified? |
|---|---|---|---|
| `science.admissibility.no_context_free_property` | No | `isinstance(conditions, Mapping)`, non-empty | No |
| `materials.analysis._group_by_comparison_context` | Yes | every content value natively hashable (`hash()`) | No |
| `evidence.identity.content_hash` | Yes | payload reduces to plain dict/list/str/int/float/bool/None (`json.dumps`, no custom encoder) | No |
| `evidence.types.make_observation`/`make_derived_value` | Yes | same `content_hash` contract, at construction time | No |
| `daf.storage.serialization.observation_to_dict`/`derived_value_to_dict` | No | none beyond `content_hash`'s | No |
| `daf.storage.serialization.observation_from_dict`/`derived_value_from_dict` | No | reconstructs from JSON-parsed payload | **Yes** |
| `daf.storage.durable_pool.DurablePool`/`classified_pool.ClassifiedPool` | No | none directly — but its lazy-hydration timing decides whether the read-side fix matters | No |
| `daf.extractors.noaa_water_level_measurements` | No | constructs the value | **Yes** |

Two consumers, not one, impose the binding constraints: `materials.analysis` (native
hashability) and `evidence.identity.content_hash` (JSON-reducibility). Both were
measured directly, not inferred from the Phase 33 traceback alone.

## The hydration measurement

`scout.pipeline.run_scout` calls `build_trust_graph(pool)` at the *start* of every
acquisition, which calls `pool.all_referents()`/`pool.all_claimed_relationships()` —
`DurablePool` full-corpus methods that trigger `_ensure_hydrated()` the first time
either is called on a given pool instance.

- **Same-process case.** For a brand-new, empty `FilesystemEvidenceStore`, this first
  call hydrates an *empty* corpus, permanently setting `_hydrated = True` before any
  object is ever put. Every subsequent `put_observation` in that same pool instance
  stores the original in-memory Python object; `_ensure_hydrated` never runs again, so
  `materials.analysis.analyze()` sees the original object, never a JSON-reconstructed
  one. Measured directly: a same-process acquire-then-analyze sequence never round-trips
  its own `conditions` value through JSON at all, regardless of representation.
- **Reopened-store case.** `DurablePool.restore`/`load_pool` — this project's own
  documented "process restart" path — constructs a *fresh*, unhydrated pool over an
  *already non-empty* store. That pool's first `run_scout` call hydrates a non-empty
  corpus, so `FilesystemEvidenceStore.all_observations` (via `observation_from_dict`) is
  what actually reconstructs every previously-persisted `Observation.content`. Measured
  directly with a two-pool-instance test: **without** the `observation_from_dict`
  read-side fix, this raised the identical `TypeError: unhashable type: 'dict'` Phase 33
  first found. **With** the fix, the second pool's `analyze()` succeeds and reports the
  correct MLLW comparison group.

This is why Phase 33's `action_taken: none` was the correct call at the time — no
read-side counterpart existed yet to make any wrapper type safe — and why this phase's
decision is a representation change *plus* a serialization change, not a bare class
definition.

## Existing primitive search

Searched: every `@dataclass(frozen=True)` type in `daf/`, `science/`, `epistemics/`,
`boundary/`, `bridge/`, `assertion/`, and the vendored substrate; every
`MappingProxyType`/`frozendict`/hand-rolled immutable-Mapping usage repository-wide;
`materials/model_state.py`'s own `target_context`/`criterion_context` mechanism.

**Found: none.** The `model_state.py` mechanism is the closest relative — a
caller-curated `Mapping[str, object]` — but it is consumed only through
`content_hash`-based key derivation (`resolve_model_state_key`), never native `hash()`,
so it imposes no native-hashability requirement and is not itself a candidate. It does
confirm the vendored substrate already tolerates plain-dict-valued curated context
elsewhere; it just never asks Python's native `hash()` to operate on one directly.
Candidate B ("reuse an existing primitive") is unavailable, confirmed by search, not
assumed.

## Candidate evaluation

| Candidate | Description | Verdict |
|---|---|---|
| A | canonical immutable key/value tuple, e.g. `(("datum","MLLW"),)` | **Rejected** — fails `isinstance(x, Mapping)`; registering `tuple` as a virtual `Mapping` would be a global side effect for one content key |
| B (reuse) | an existing immutable Mapping primitive | **Rejected** — none exists (see search above) |
| C | `FrozenMapping`, a dedicated `dict` subclass | **Adopted** |

**Why a `dict` subclass, not a `collections.abc.Mapping` implementation.** Measured
directly: a `Mapping` that is *not* also a `dict` raises `TypeError: Object of type ...
is not JSON serializable` at `Observation`/`DerivedValue` construction — inside
`evidence.identity.content_hash`'s own `json.dumps` call, before `materials.analysis` is
ever reached. A `dict` subclass serializes exactly like a plain dict of the same items.

## Identity

**`Observation.id` is unchanged by the representation choice.** Measured directly: a
`FrozenMapping({"datum": "MLLW"})`-valued `conditions` and a plain
`{"datum": "MLLW"}`-valued `conditions`, built from the same items, produce byte-identical
canonical JSON and therefore the identical id. `content_hash`'s canonical serialization
is type-blind between `dict` and any `dict` subclass. No new identity scheme was
introduced, and none was needed — `evidence.identity`/`evidence.types` were not touched.

## Serialization

`observation_to_dict`/`derived_value_to_dict` needed **no change** — `dict(observation.content)`
is a shallow copy, and a `dict`-subclass value already serializes via `json.dumps`
exactly like a plain dict. `observation_from_dict`/`derived_value_from_dict` now apply
`daf.storage.frozen_mapping.freeze_nested_mappings` to `content` before reconstruction —
recursively wrapping any `dict`-valued entry as `FrozenMapping`. Measured to be a no-op
for every content shape shipped before this phase: no extractor has ever produced a
`dict`-valued content entry. `DerivedValue` was changed symmetrically with `Observation`
— both flow through the identical `_group_by_comparison_context` mechanism in
`materials.analysis.analyze()` (the "predicted" side), so treating one but not the other
would have been an unjustified inconsistency, not a narrower fix.

## Consumer compatibility

Verified against the real pipeline, not a mock, not a bypass of `_comparison_context`:

- `science.admissibility.no_context_free_property` accepts `FrozenMapping` unmodified
  (it already checks `isinstance(x, Mapping)`, and `dict` is Mapping-registered).
- `materials.analysis.analyze()` — real acquisition, same-process — succeeds; 240
  observations, all carrying `conditions`, no `TypeError`.
- `materials.analysis.analyze()` — real acquisition, **reopened store, second pool
  instance** — succeeds; the decisive test (see "hydration measurement" above).
- Multi-condition order independence: `FrozenMapping({"datum":"MLLW","station":"8454000"})
  == FrozenMapping({"station":"8454000","datum":"MLLW"})` and `hash()` agrees — no
  conflict semantics were needed or invented, since a Python `dict` cannot hold two
  values under one key to begin with.
- Immutability: every mutating method (`__setitem__`, `__delitem__`, `update`, `pop`,
  `popitem`, `clear`, `setdefault`) raises `TypeError`.
- Backward compatibility: content with no Mapping-valued entries (every pre-Phase-34
  shape) round-trips through `freeze_nested_mappings` unchanged.

## Provenance

`conditions` inherits provenance from `Observation`/`ExecutionRecord` exactly as every
other content field already does. No per-condition provenance mechanism was added or
found necessary — `conditions` is not itself a provenance-bearing structure any more
than `value` or `unit` are, and nothing in the consumer inventory required one.

## Decision: B

A small, shared representation extension, justified by two independent existing
consumers (`materials.analysis`'s native-hashability requirement and
`daf/storage/serialization.py`'s round-trip requirement) and verified against the real,
vendored pipeline in both the same-process and reopened-store cases. Not chosen for
implementation convenience: Candidates A and "reuse an existing primitive" were ruled
out by direct search and structural incompatibility *first* — see
`architecture/condition_representation.yaml` for the complete recorded determination.

## Implementation

| File | Change |
|---|---|
| `daf/storage/frozen_mapping.py` | **New.** `FrozenMapping` (immutable, hashable `dict` subclass) and `freeze_nested_mappings` (recursive wrap-on-load helper). |
| `daf/storage/serialization.py` | `observation_from_dict`/`derived_value_from_dict` apply `freeze_nested_mappings` to `content` before reconstruction. |
| `daf/extractors/noaa_water_level_measurements.py` | `conditions = FrozenMapping({"datum": self.datum})` added to every reading's content, replacing the Phase 33 reverted plain-dict attempt. Docstring updated to disclose the identity/comparability impact, mirroring Phase 32's own disclosure convention. |

**Not changed:** `materials.analysis`, `evidence.identity`, `evidence.types` (all
vendored); `science.admissibility.no_context_free_property`; every other extractor
(`usgs_earthquakes`, `edgar_daily_index`, `arxiv`, `graph_dataset`,
`noaa_water_level`) — none declares a `conditions` key.

## NOAA: real acquisition, resolved dimension

| Dimension | Before Phase 34 | After Phase 34 |
|---|---|---|
| quantity | ✓ | ✓ |
| uncertainty | ✓ (Phase 32) | ✓ |
| method | ✗ `MISSING_METHOD` | ✗ `MISSING_METHOD` — **not fabricated** |
| conditions | ✗ `MISSING_CONDITIONS` | ✓ `FrozenMapping({"datum": ...})` |

`assess_pool` over the real, recorded 240-reading NOAA acquisition now reports
`by_code == {"MISSING_METHOD": 240}` — down from `{"MISSING_CONDITIONS": 240,
"MISSING_METHOD": 240}`. CO-OPS still does not report, per reading, which sensor or
algorithm produced a value; nothing was invented to close that dimension.

## USGS: regression, unaffected

Re-ran the real USGS acquisition path unchanged: `candidates_examined == 3`,
`accepted == 0`, `by_code == {"MISSING_CONDITIONS", "MISSING_UNCERTAINTY_KIND"}`, and no
USGS observation declares a `conditions` key. USGS's negative finding
(`architecture/condition_provenance_reachability.yaml`) is about its *data*, not the
representation — a representation fix cannot and does not change it.

## Architecture

- **New:** `architecture/condition_representation.yaml` — the full determination:
  consumer inventory, hydration measurement, primitive search, candidate evaluation,
  decision, implementation, and measured outcome. Doctrine-registered
  (`architecture/doctrine.yaml`'s `sources`), regenerated, **zero diff**.
- **Corrected in place, with `corrected_in_phase_34` annotations (Phase 32's own
  precedent for `corrected_in_phase_32`), never silently rewritten:**
  `architecture/property_admissibility.yaml`'s NOAA `measured_reachability.reasons`
  (now `[MISSING_METHOD]`), and `architecture/uncertainty_provenance_reachability.yaml`'s
  `noaa_water_level_sigma.real_acquisition_result.reasons` (same). Both files' original
  `result`/`action_taken_reason`/`conditions_left_independent` prose is left exactly as
  each phase recorded it — accurate measurements at the time; only the deferred
  decision changed, one or two phases later.
- `architecture/condition_provenance_reachability.yaml`'s NOAA finding gained a
  `corrected_in_phase_34` note; its `verdict`/`result`/`action_taken`/`reversibility`
  fields are untouched, for the same reason.

## Regression

| Check | Result |
|---|---|
| `tests/test_hashable_condition_representation.py` | **23 passed** (new) |
| DAF full suite | **675 passed** (652 prior + 23 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy .` | **4 pre-existing errors, 0 new** (unrelated test files: `test_model_state_integration.py`, `test_usgs_earthquakes_adapter.py`, `test_noaa_water_level_adapter.py`, `test_edgar_daily_index_adapter.py` — none touched this phase) |
| `ruff` | `I001`/`F401` fixed in the new test file; `UP045` on `Optional[...]` in the new module matches this repository's own established `typing.Optional`/`Dict` convention (e.g. `daf/storage/serialization.py`), left alone like every other `UP0xx` finding repo-wide |
| Doctrine | regenerated, zero diff (only the source-digest line changed — the new/edited YAML content is not part of doctrine's rendered prose, per its own routing rules) |
| `git status` | clean except the intended file set |
| `git diff --stat -- vendor/` | **empty** |

Eleven pre-existing tests needed updating for NOAA's new content shape (an added
`conditions` key and a resolved rejection reason) — exact-set/reasons-set assertions
whose premise legitimately changed, updated in place with docstring notes explaining
the correction, exactly mirroring how Phase 32 handled the same kind of cascading update
when it added `uncertainty`/`uncertainty_kind`. None was weakened; each now asserts the
current, correct reality.

## Bent

**Bent: zero.** No vendored file was modified. No gate, extractor other than NOAA's, or
identity mechanism was touched. `Observation.id`/`DerivedValue.id` computation is
byte-identical to before this phase for any content with no Mapping-valued entries, and
measured-identical to the rejected plain-dict wiring for content that does have one.

## Qualified

- `FrozenMapping` is a representation primitive, not a semantic one. It does not by
  itself make any future source's field a "genuine condition" — that determination
  still needs the same per-source evidence Phase 33 required for NOAA's `datum`.
- The read-side fix (`freeze_nested_mappings`) wraps *any* dict-valued content entry,
  not only `conditions` — deliberately generic, to avoid a key-name-specific special
  case, but this means a future extractor that (incorrectly) puts a dict-valued
  non-condition field into content would also have it silently frozen. This has not
  happened and is not expected to (no shipped extractor does this), but it is a real
  scope boundary of the change, not a guarantee about future extractors.
- `USGS`'s `MISSING_CONDITIONS` remains a data absence, not a representation gap. This
  phase closes zero USGS dimensions.

## Unresolved

- **`MISSING_METHOD` for NOAA** — CO-OPS does not report per-reading method/instrument
  provenance; unchanged, and not attempted here.
- **USGS's two absences** (`MISSING_CONDITIONS`, `MISSING_UNCERTAINTY_KIND`) — unchanged;
  no genuine condition or uncertainty statistic exists in the real, acquired USGS data.
- Carried unchanged: `quarantine_repair`, `retraction_semantics`,
  `multi_writer.write_conflict`, `builder_check_lineage`, `attested_snapshot_identity`,
  `capabilities_5_to_9`.

## Next executable frontier

No source-agnostic representation obstacle remains for Mapping-shaped conditions. The
next frontier this project's own sequence of single-dimension resolutions points to is
**NOAA's `MISSING_METHOD`** — whether any DAF-reachable source (NOAA or otherwise)
genuinely documents per-reading instrument/method provenance the way USGS's
`magnitude_type` did (Phase 31), which would require the same real-source reconnaissance
discipline this phase and Phase 30/31/32/33 have each applied to their own dimension,
not an assumption that "conditions now works, so method should too."
