# Phase 33 — Source-Authentic Measurement Conditions

*(Continues from `0b39f12`. Answers the question Phase 32 posed: does any DAF-reachable
source contain a genuinely source-authentic measurement condition?)*

**Result: neither a clean yes nor a clean no.** USGS: no genuine condition exists in the
source data at all. NOAA: a genuine condition (`datum`) *does* exist — but wiring it
through the existing `conditions` representation demonstrably breaks a real, vendored
consumer. `MISSING_CONDITIONS` is preserved for both sources, for two precisely
different, evidenced reasons. **No production code changed** — a wiring attempt was
built, measured to break two pre-existing tests, and reverted within this phase.

---

## Source sweep

Every shipped production extractor was inspected, not only the three named in the
brief: `noaa_water_level_measurements`, `usgs_earthquakes`, `edgar_daily_index`,
`arxiv`, plus the window-shaped `noaa_water_level` and the generic
`local_dataset`/`graph_dataset` pattern.

**Three sources are not property-shaped at all**, so the conditions question does not
arise for them — measured directly, not merely re-cited from Phase 30:

| Source | Content shape | Property key? |
|---|---|---|
| `edgar_daily_index` | `date_filed`/`filing_count`/`form_type_counts`/`filings` | No |
| `arxiv` | `arxiv_id`/`title`/`summary`/`published`/`updated`/`primary_category` | No |
| `noaa_water_level` (window) | `station_id`/`station_name`/`reading_count`/`quality_counts`/`readings` | No |

`local_dataset`/`graph_dataset` were excluded from the sweep on the same standing
ground every phase since 29 has used: they pass through whatever a JSON file declares,
with no fixed real-world API behind them (Phase M's finding: no DAF-reachable source is
a materials experiment).

That leaves exactly the two property-shaped sources this project has examined since
Phase 29: `noaa_water_level_measurements` and `usgs_earthquakes`.

---

## Candidate inventory and classification

Every candidate field on both sources was inspected and classified — including fields
previously ruled on, per §5's instruction to reconsider without automatically reversing.

| Source | Field | Classification | Changed from prior phase? |
|---|---|---|---|
| USGS | `place` | identity metadata | No |
| USGS | `origin_time` | identity metadata | No |
| USGS | `depth_km` | identity metadata | **Reconsidered, not reversed** |
| USGS | `status` | revision/QC metadata | No |
| USGS | `magnitude_type` | provenance/method (already wired, Phase 31) | No |
| USGS | network/`magSource` | *(absent from every real fixture)* | n/a — not present to classify |
| NOAA | `station_id` | identity metadata | New ruling (none existed before) |
| NOAA | `measurement_time` | identity metadata | New ruling (none existed before) |
| NOAA | `datum` | **measurement condition** | **New positive finding** |

**`depth_km` was specifically reconsidered**, since depth genuinely affects seismic wave
propagation in general geophysics. But no field in this repository's real fixtures or
extractor documents depth as an input the source *itself* uses to compute or correct the
reported magnitude — it is reported as a property of the event, in the same list as
latitude/longitude. Preserved as identity, absent the stronger evidence that would
justify promoting it.

**The network/`magSource` field** — a real USGS GeoJSON concept in general — is absent
from every fixture this repository actually acquires
(`test_network_field_is_absent_from_every_real_usgs_fixture` greps every real USGS
fixture and confirms). Recorded so a future phase does not re-discover the same absence
from scratch.

## The positive finding: NOAA's `datum`

**`datum` is a genuine measurement condition, evidenced three independent ways:**

1. **Physical fact, measured directly.** The identical physical water surface, at the
   identical station and instant, is reported as a *different number* under a different
   datum: `tests/fixtures/noaa_live_8454000_20240115_mllw.json` and `_stnd.json` report
   `0.136` m and `1.2` m respectively for the same timestamp.
2. **This repository's own prior, independent statement.** Not discovered by this
   phase — `tests/test_live_scientific_observation.py` already carries the comment
   *"`datum` is a genuine scientific conditioning variable in its own right,"* written in
   an earlier phase, before this determination was made.
3. **The gate's own definition.** `no_context_free_property`'s docstring: conditions are
   "circumstances under which a fixed quantity was measured" — datum is exactly that: a
   reference-frame choice applied *on top of* a fixed physical quantity, changing its
   numeric expression without changing the underlying subject, instant, or location.

This is categorically different from `station_id`/`measurement_time`, which identify
*which* physical quantity is being reported (different station or instant = a genuinely
different quantity, not the same one under different conditions) — the same distinction
Phase 31 already applied to USGS's `place`/`origin_time`.

---

## The representation gap

Wiring `datum` into `conditions` looks trivial: add `content["conditions"] = {"datum":
self.datum}`, the same additive pattern every prior phase used. **It was implemented,
measured, and reverted within this phase**, because it breaks real, existing, passing
behavior:

```
TypeError: unhashable type: 'dict'
  materials/analysis.py:200, in _group_by_comparison_context
    key = tuple(sorted(context.items(), key=lambda kv: kv[0]))
    bucket = groups.setdefault(key, ...)   # <- dict used as a dict KEY
```

`materials.analysis._comparison_context` (vendored, never modified) is *every* content
key except `property` and the value key, and `_group_by_comparison_context` hashes that
entire context as a sorted tuple to group observations. **Any Mapping-valued content
key is unhashable**, and Python's standard `Mapping` types (`dict`, `MappingProxyType`,
`OrderedDict`) are all unhashable by construction — there is no way to satisfy
`science.admissibility.no_context_free_property`'s `isinstance(conditions, Mapping)`
requirement with a value that also survives `materials.analysis`'s hashing, without
introducing a new, custom, hashable Mapping type.

**Confirmed general, not NOAA-specific**: the identical `TypeError` is reproduced
against a synthetic content shape entirely unrelated to NOAA
(`test_the_incompatibility_is_general_not_noaa_specific`) — this would block *any*
future graph-reachable property source that tried to declare `conditions`.

**Why the fix was not implemented anyway.** A custom hashable-Mapping type would be a
new shared primitive that every future conditions-bearing source would need to adopt —
exactly the "new ontology" §11 says not to implement "unless the evidence demonstrates
that it is necessary." That decision belongs to whoever next needs `conditions` to
actually admit evidence, informed by this phase's precise diagnosis, not decided here on
this phase's own initiative.

**The attempted wiring left no trace.** `git diff` on `daf/extractors/noaa_water_level_measurements.py`
against the prior commit is empty; `test_the_noaa_extractor_was_left_exactly_as_phase_32_produced_it`
locks the exact Phase 32 content-key set.

---

## Conditions contract, measured

`science.admissibility.no_context_free_property`'s check, read directly from source:

```python
conditions = content.get("conditions")
if not isinstance(conditions, Mapping) or not conditions:
    reasons.append(MISSING_CONDITIONS)
```

Requires a non-empty `Mapping`. Nothing more, nothing about hashability — that
requirement comes entirely from a *different*, vendored module this gate has no
awareness of. This is Phase 31's "the quantity contract validates nothing about unit
content" pattern, inverted: here two independently-correct contracts (an admissibility
gate requiring a Mapping; an analysis function requiring hashability) are individually
sound and mutually incompatible.

---

## Real acquisition, unchanged

Both real acquisitions were re-run to confirm this phase's investigation left no
residue:

| | NOAA (this phase) | NOAA (Phase 32) | USGS (this phase) | USGS (Phase 31) |
|---|---:|---:|---:|---:|
| Candidates examined | 240 | 240 | 3 | 3 |
| Accepted | 0 | 0 | 0 | 0 |
| Rejection codes | `MISSING_CONDITIONS`, `MISSING_METHOD` | *(identical)* | `MISSING_CONDITIONS`, `MISSING_UNCERTAINTY_KIND` | *(identical)* |

Phase 17's `INCOMPARABLE` finding was re-verified once more, end to end, against real
acquisition (`test_the_incomparable_finding_is_still_intact`).

## Identity

**No identity change survives this phase.** The wiring attempt would have changed
`Observation.id` for every NOAA reading (a new `conditions` key in content); it was
reverted before commit, so no NOAA or USGS `Observation.id` differs from Phase 32.

## Evidence

No condition, real or attempted, ever bypassed admissibility: the poisoned-extractor
reproduction test runs the *complete* real pipeline (adapter → `run_scout` → admission →
pool) and the resulting observation is genuinely admitted evidence *before*
`analyze()` fails on it — the failure is in a downstream, read-only analysis function,
never in evidence admission itself, confirming the evidence boundary held throughout the
investigation.

## Quarantine

**`partially_enforced` — unchanged.** No new refusal reason was produced; both sources'
`MISSING_CONDITIONS` refusals are retained exactly as Phase 31/32 left them.

## Metrics

See the "Real acquisition, unchanged" table above — no metric shape or value changed
from Phase 31/32 for either source.

---

## Regression

| Check | Result |
|---|---|
| `tests/test_condition_provenance_reachability.py` | **17 passed** |
| DAF full suite | **652 passed** (635 prior + 17 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/ assertion/` | Success, **75 source files**, unchanged |
| `ruff` | one `I001`, one `F401`, one `RUF059` found and fixed in the new test file; all else repo-wide conventions |
| Doctrine | regenerated, **654 / 1400 words**, zero diff |
| `git status` | clean; only the new test file and new architecture YAML untracked |
| `git diff --stat -- daf/ science/ boundary/ bridge/ epistemics/ assertion/ vendor/` | **empty** |

## Bent

**Bent: zero.** No gate, extractor, adapter, execution record, or quarantine mechanism
was modified. The vendored submodule is byte-identical.

## Qualified

- The representation-gap finding is specific to *Mapping-valued* conditions colliding
  with *graph-reachable* observations — it says nothing about sources that are
  property-shaped but never analyzed via `materials.analysis` (like a hypothetical
  future extractor with `entities=(), relations=()`).
- `datum`'s classification as a condition is grounded in this specific physical fact
  (a reference-frame choice changing a reported number) and should not be read as a
  general license to treat every source-declared reference value as a condition.
- Depth, network identifiers, and every other reconsidered field were found *not*
  promotable given currently available evidence — not proven permanently unpromotable.

## Unresolved

- **The representation gap itself is now the concrete blocker to canonical admission for
  NOAA.** Whether the shared substrate should grow a hashable-Mapping primitive, or
  whether `conditions` should be redefined some other way, is a genuine open design
  question this phase deliberately did not resolve.
- No source in this repository can currently produce an *accepted* property assertion
  through real, unmodified acquisition — unchanged in aggregate, and now understood
  precisely: NOAA is blocked by exactly one representation-level obstacle plus the
  still-unresolved `MISSING_METHOD`; USGS by two independently genuine absences.
- Carried unchanged: `quarantine_repair`, `retraction_semantics`,
  `multi_writer.write_conflict`, `builder_check_lineage`, `attested_snapshot_identity`,
  `capabilities_5_to_9`.

## Measured bottleneck

**The `conditions` representation itself — not any single source's data — is now the
binding constraint.** Every source-specific admissibility gap this project has examined
(method, unit, uncertainty, and now conditions) has been resolved or precisely diagnosed
except this one, and this one is structural rather than source-specific: it blocks any
future graph-reachable source, not just NOAA, from ever satisfying `conditions` under
the current representation.

## Next executable frontier

**Design and evaluate a hashable representation for `conditions`** — the smallest shared
extension that would let a Mapping-shaped condition coexist with
`materials.analysis`'s hashing requirement, without modifying the vendored analysis
module or weakening `no_context_free_property`. This is squarely a shared-substrate
design question (per §11, deliberately not decided here): candidates include a frozen,
hashable mapping type in `science/` that still satisfies `isinstance(x, Mapping)`, or a
canonical-ordering tuple-of-pairs representation with its own accessor helpers. Either
choice needs to be evaluated against every existing consumer of `Observation.content`
before being adopted, which is exactly the kind of decision this phase's own scope
excluded.

---

*Halts here per the stop condition: swept every source, reconsidered every prior
classification without reversing any without evidence, found one genuine condition and
one genuine structural incompatibility, implemented the wiring, measured it break real
behavior, reverted it, documented precisely, tested, committed and pushed. Neither gate
was weakened, no condition was fabricated, and no new ontology was implemented on this
phase's own initiative.*
