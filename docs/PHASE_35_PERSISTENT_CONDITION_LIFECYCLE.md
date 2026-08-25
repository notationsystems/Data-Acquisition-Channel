# Phase 35 — Persistent Hashable Conditions Through the Full Acquisition Loop

*(Continues from `f20b582`. Answers the question Phase 34 left open: does the
representation stay correct across the complete durable scientific lifecycle?)*

**Result: closed for NOAA, NOT closed for the substrate.**

All six invariants — semantic validity, immutable representation, deterministic
identity, durable serialization, process-restart reconstruction, downstream
compatibility — hold for `daf.extractors.noaa_water_level_measurements`, verified
through two genuinely separate OS processes producing **byte-identical** output on all
19 compared keys.

They do **not** hold uniformly. Phase 34 imposed the representation at only **one** of
the two boundaries where a Mapping value enters an `Observation`. The read side got
`freeze_nested_mappings`; the write side was fixed for NOAA alone, by hand, inside
NOAA's own extractor. `daf.extractors.graph_dataset` passes every non-structural key
through verbatim by design, so a source record declaring a `conditions` object still
produces a plain, unhashable `dict`.

Four gaps were measured. Per §7 ("do not modify them yet"), §9 ("do not invent conflict
policy") and §15, all four are **recorded and locked as characterization tests, not
fixed**. No production behaviour changed in this phase.

---

## Lifecycle Trace

Measured by monkeypatching each boundary and by reading the on-disk bytes directly —
never inferred.

| # | Boundary | Representation observed |
|---|---|---|
| 1 | extraction candidate construction | `FrozenMapping` |
| 2 | `run_scout` → `make_observation` | `FrozenMapping` |
| 3 | `Observation` in memory | `FrozenMapping` (outer container `mappingproxy`) |
| 4 | durable write bytes | **plain JSON object** |
| 5 | process termination | *(nothing survives but bytes)* |
| 6 | `get_observation` (single read) | `FrozenMapping` |
| 7 | `all_observations` (bulk read) | `FrozenMapping` |
| 8 | `_replay_into` hydration | `FrozenMapping` |
| 9 | `no_context_free_property` | `FrozenMapping` |
| 10 | `_comparison_context` | `FrozenMapping` |
| 11 | `analyze` | `FrozenMapping` |

Boundary 4 is the load-bearing one: **the `FrozenMapping` type is not encoded on disk.**
`observation_to_dict` does `dict(observation.content)` — a shallow copy — and `json.dumps`
writes an ordinary object. The representation is a layer *above* the bytes, so
persistence depends on no Python type surviving, and the type is re-imposed on read.

## Representation

The single most consequential measurement of this phase, and it is not the one the brief
anticipated:

> **`daf.storage.serialization.observation_from_dict` is called ZERO times during a
> complete real acquisition.**

`scout.pipeline.run_scout` calls `build_trust_graph(pool)` at the *start* of every
acquisition, which calls `pool.all_referents()` — a `DurablePool` full-corpus method that
triggers `_ensure_hydrated()`. For a brand-new empty store this hydrates an *empty* corpus
and permanently sets `_hydrated = True` **before the first `put_observation`**.

So a same-process acquire-then-analyze hands `materials.analysis` the extractor's own
in-memory objects, unmediated. **The read-side fix protects the reopened-store path and
only that path.** Whatever the extractor constructs is what the same-process consumer
sees. This is why the write-side gap below stayed invisible through Phase 34, and why a
read-side-only fix could never have been sufficient.

## Persistence

| Measure | Before | After hydration |
|---|---|---|
| `Observation.id` (all 240) | — | identical |
| content fingerprint (all 240) | — | identical |
| `pool.fingerprint()` | — | identical |
| `conditions` type | `FrozenMapping` | `FrozenMapping` |
| `conditions` equality | — | preserved |
| `conditions` hashability | — | preserved |

Round-tripping **twice** is identical to round-tripping once — which is what makes
repeated reopen/rewrite cycles safe.

## Process Restart

`tests/helpers_phase35_restart.py`, invoked as two separate `python3` processes sharing
nothing but a directory path. Process A acquires from a committed fixture (no network);
process B reopens, hydrates, assesses admissibility, and runs the real vendored
`materials.analysis.analyze`.

**Result: byte-identical on all 19 compared keys**, including `first_observation_id`,
`all_observation_ids_digest`, `content_fingerprint`, `conditions_type`,
`conditions_items`, `pool_fingerprint`, `analysis_observed_count`,
`analysis_group_datums`, and `admissibility_by_code`.

One key is **deliberately excluded**, and this is a measured correction to the naive
reading of §2's "hashability" invariant:

> `hash(FrozenMapping({"datum": "MLLW"}))` returns a **different value in every
> interpreter** — measured across three: `4253298624664292187`, `-4179817775865387385`,
> `-1459824758602709479`. `content_hash` was identical in all three.

Python randomizes string hashing per process (`PYTHONHASHSEED`). This is **correct, not a
defect**: the only consumer of the native hash,
`materials.analysis._group_by_comparison_context`, uses it as a dict key *within* one
process and never persists or compares it. What must survive a restart is that hashing
**succeeds** and that `content_hash` is stable — not the hash *value*. A test asserting a
stable native hash across processes would assert something Python does not promise and
this architecture does not need. That distinction is now locked by
`test_native_hash_is_process_local_but_content_hash_is_not`.

## Identity

`identity_before == identity_after` on **all 240** real observations, not a sample. The
§3 STOP condition was not triggered.

## NOAA

| Dimension | State |
|---|---|
| quantity | ✓ |
| uncertainty | ✓ |
| conditions | ✓ |
| method | ✗ `MISSING_METHOD` |

`assess_pool` reports `by_code == {"MISSING_METHOD": 240}` **identically before and after
restart**. No method was fabricated; `"method" not in content` is asserted directly.

## USGS

Unchanged, before and after restart: `candidates_examined == 3`, `accepted == 0`,
`by_code == {"MISSING_CONDITIONS", "MISSING_UNCERTAINTY_KIND"}`, and no USGS observation
declares a `conditions` key. USGS emits `entities=(), relations=()`, so it is not
graph-reachable at all — its `MISSING_CONDITIONS` is a data absence that no representation
choice can touch.

## Analysis

Real vendored `materials.analysis.analyze`, no mocks, no bypass of `_comparison_context`:

1. **newly acquired** — 240 observed, 240 singleton groups, no disagreement.
2. **after persistence/reopen** — identical on every field.
3. **without conditions** — still groups correctly; the absence of conditions was not made
   fatal by the representation's existence.
4. **multiple conditions** — `{datum, temperature_c, pressure_kpa}` declared in two
   different orders produce equal hashes, an **identical `Observation.id`**, and land in
   **one** comparison group. Differing conditions land in **two**.

## Quarantine

The refusal path was exercised, persisted, and reloaded through a **fresh store object**:
240 records, each with `execution_id` matching the real `ExecutionRecord`, `stage ==
"canonical_assertion"`, and `{MISSING_METHOD}`. Reloaded ids match written ids exactly.

A measured and load-bearing detail: a `QuarantineRecord`'s fields are exactly
`id`/`execution_id`/`stage`/`errors`. **The refused Observation's content is never
persisted into quarantine** — verified by substring probe across all 240 records for
`conditions`, `datum`, `MLLW`, `FrozenMapping`, `"content"`. So the representation is not
part of the quarantine contract at all, and the Phase 34 class of round-trip bug cannot
arise on that path. Quarantine was not redesigned.

## Multi-Condition

Order-independent equality, hash, identity, serialization, and real grouping all agree.
No conflict policy was invented — and none is needed for duplicate keys, because a Python
`dict` cannot hold two values under one key, so "duplicate condition keys" is not
expressible in this representation.

## Evidence Boundary

- `daf/storage/frozen_mapping.py` imports **only** `typing` and `__future__` (AST-verified),
  and its executable code references no `EvidencePool`, `pool`, `store`,
  `put_observation`, or `run_scout`.
- Analysing a real 240-observation pool leaves `pool.fingerprint()` and the observation
  count **byte-identical**.
- `assess_pool` likewise leaves `pool.fingerprint()` unchanged.

`condition representation ≠ evidence admission`, and `analysis output ≠ EvidencePool
write`, both proven by measurement rather than assertion.

---

## The Four Measured Gaps

All **recorded, not fixed**, and locked by characterization tests.

### 1. `write_side_asymmetry` — the mirror of the Phase 34 bug

A `graph_dataset` record declaring **both** conditions and a relation:

```
same process  ->  analyze() RAISES TypeError: unhashable type: 'dict'
after reopen  ->  analyze() SUCCEEDS, conditions is FrozenMapping
```

Phase 34's bug was the other way round. Same root cause: a Mapping-valued content entry
whose representation is imposed at only one of the two boundaries.

**Why it stayed latent:** it needs conditions *and* a relation together. The shipped
`ADMISSIBLE_RECORD` in `tests/test_property_admission_integration.py` declares conditions
but `relations: []`, and `retrieval.engine` reaches an Observation only through a
`ClaimedRelationship` — so analysis never touches it. Measured: that record yields
`observed == 0`.

**Not fixed because** patching `graph_dataset` would be per-source patching of exactly the
kind `architecture/condition_representation.yaml` deliberately avoided. The honest fix is a
single generic choke point where DAF extractor output becomes Observation content — a
design decision needing its own measurement, which §7's "do not modify them yet" defers.

### 2. `list_valued_conditions`

`FrozenMapping({"a": [1,2,3]})` is **admissible** and computes a stable `Observation.id`,
but `_group_by_comparison_context` raises `TypeError: unhashable type: 'list'`. And
`freeze_nested_mappings` does **not** recurse into lists, so a list of dicts stays plain.
The Phase 33 defect, one level deeper. No real source produces one today.

### 3. `vacuous_condition_values`

`FrozenMapping({"datum": None})` and `{"datum": ""}` are both **admissible**. The gate
checks that `conditions` is a non-empty Mapping and never inspects the values. Whether a
null condition value is vacuous or a legitimate "declared absent" is a semantic question
the substrate does not answer — recorded as unresolved rather than settled by fiat, since
adding value-level validation would modify `science/admissibility.py`, a gate this
sequence of phases has never changed to accommodate a source.

Two related asymmetries were also measured: an *empty* `FrozenMapping` is **refused** by
the gate yet still participates as a comparison-context key; and a **bare string**
`conditions` is refused by the gate but, being hashable, participates in grouping exactly
as a real condition mapping would. The gate and the analysis layer do not consult each
other — existing, unmodified behaviour, noted rather than changed.

### 4. `phase_34_no_op_claim_incorrect` — correcting my own prior record

`architecture/condition_representation.yaml` claimed `freeze_nested_mappings` was *"a
no-op for every content shape shipped before this phase (measured: no extractor has ever
produced a dict-valued content entry)"*.

**That claim is false.** `daf.extractors.edgar_daily_index` has always emitted
`form_type_counts`, and `daf.extractors.noaa_water_level` `quality_counts` — both dicts,
both long predating Phase 34. So the read-side fix *does* change their hydrated content
type.

Practical impact is nil (both emit `entities=(), relations=()`, so neither is reachable
through `materials.analysis`, and `Observation.id` is unchanged either way) — but the claim
was wrong, and is corrected in place via `corrected_in_phase_35` rather than left standing.

## Extractor Inventory (§7 — inventoried, not modified)

| Extractor | property-shaped | graph-reachable | dict-valued content | condition risk |
|---|---|---|---|---|
| `arxiv` | no | **yes** (3 ent, 2 rel) | — | none |
| `edgar_daily_index` | no | no | `form_type_counts` | latent, unreachable |
| `graph_dataset` | source-declared | **yes** (when a relation is declared) | source-declared | **active** |
| `local_dataset` | source-declared | no | source-declared | latent, unreachable |
| `noaa_water_level` (window) | no | no | `quality_counts` | latent, unreachable |
| `noaa_water_level_measurements` | **yes** | **yes** | `conditions` | **none — correct** |
| `usgs_earthquakes` | **yes** | no | — | none |

Exactly one extractor is property-shaped *and* graph-reachable *and* carries a
Mapping-valued content entry — and it is the one that correctly constructs a
`FrozenMapping`. (`arxiv` is graph-reachable but has no `property` key, so `analyze`
reaches its observation and then drops it at `_matches_property` — measured: `observed == 0`.)

## Architecture

- **New:** `architecture/condition_lifecycle.yaml` — the lifecycle trace, hydration
  asymmetry, restart result, identity measurements, extractor inventory, the four gaps,
  conflict semantics, and the evidence-boundary proof. Doctrine-registered, regenerated,
  **zero diff** (654/1400 words; only the source-digest line changed, since the routing
  rules keep determinations out of doctrine's rendered prose).
- **Corrected in place** with `corrected_in_phase_35` annotations, never rewritten:
  `architecture/condition_representation.yaml`'s false no-op claim, and its
  `implementation` block's implied closure.

## Regression

| Check | Result |
|---|---|
| `tests/test_persistent_condition_lifecycle.py` | **37 passed** (new) |
| DAF full suite | **712 passed** (675 prior + 37 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy .` | **4 pre-existing errors, 0 new** (unrelated adapter/state-gap test files, untouched) |
| `ruff` (new files) | **All checks passed** |
| Doctrine | regenerated, zero diff, 654/1400 words |
| `git diff --stat -- daf/ science/ boundary/ bridge/ epistemics/ assertion/ vendor/` | **empty** |

**No production code changed in this phase.** The only non-test, non-doc changes are
architecture YAML records and the doctrine digest.

One bug was caught and fixed during the work itself: `ruff --fix`'s isort reordered
`tests/helpers_phase35_restart.py`'s imports, moving `import daf` *after* the vendored
imports and breaking the submodule path bootstrap (`ModuleNotFoundError: No module named
'evidence'`). The driver is a standalone script and gets no `conftest.py`, so the
bootstrap is now explicit and fenced with `# ruff: isort: off`, and verified to survive a
subsequent `ruff --fix`.

## Bent

**Bent: zero.** No vendored file modified. No extractor, gate, quarantine mechanism, or
identity path changed. Every Phase 34 lock in
`tests/test_hashable_condition_representation.py` remains, unweakened and unmodified.

## Qualified

- "Closed" applies to NOAA's lifecycle, not the substrate's. The split verdict is the
  finding, not a hedge.
- The restart proof uses fixture bytes rather than a live network call — the same
  substitution every acquisition test here makes. Everything below the bytes is the real,
  unmodified production path.
- The three latent gaps are latent *given today's sources*. None is proven unreachable in
  principle; `graph_dataset` in particular becomes active the moment any caller declares
  conditions alongside a relation.
- The native-hash-is-process-local finding is a property of CPython's default
  configuration. Pinning `PYTHONHASHSEED` would make the value stable, which is why the
  test asserts variability and explains what a failure there would mean.

## Unresolved

- **`MISSING_METHOD` for NOAA** — CO-OPS reports no per-reading instrument/method
  provenance. Unchanged, not attempted.
- **USGS's two absences** — unchanged data absences.
- **Internal conflict semantics for a single conditions mapping** — no substrate mechanism
  defines it; none invented.
- Carried unchanged: `quarantine_repair`, `retraction_semantics`,
  `multi_writer.write_conflict`, `builder_check_lineage`, `attested_snapshot_identity`,
  `capabilities_5_to_9`.

## Measured Bottleneck

**The write boundary has no generic choke point.** Every read of persisted content funnels
through `daf/storage/serialization.py`, which is why a single function fixed the entire
read side. There is no equivalent single place where extractor output becomes
`Observation.content`: `run_scout` is vendored and unmodifiable, and each extractor
constructs its own content dict independently. That asymmetry — one choke point on read,
seven independent construction sites on write — is what made Phase 34's fix look complete
when it was half a fix, and it is the binding constraint on closing the representation for
the substrate rather than for one source.

## Next Executable Frontier

**Determine whether a single generic write-side choke point exists in the DAF layer where
all extractor output could be normalized before becoming `Observation.content`** — and if
so, whether normalizing there is correct or whether it would silently reshape content a
source deliberately declared. The candidate seam is the DAF orchestration boundary that
hands an extractor to the vendored `run_scout`, since that is the one place every DAF
acquisition passes through and the one place still above the unmodifiable substrate. It
must be evaluated against every existing consumer and against the `Observation.id` of every
shipped extractor before adoption — the same discipline Phase 34 applied to the read side,
now applied to the write side it left undone.
