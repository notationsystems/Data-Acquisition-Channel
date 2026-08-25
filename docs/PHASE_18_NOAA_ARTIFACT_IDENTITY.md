# Phase R — NOAA Artifact Identity Resolution

*(Repository phases are lettered; the prompt labels this "Phase 18". Continues
from Phase Q — `docs/PHASE_17_LIVE_SCIENTIFIC_OBSERVATION.md` — at `4a15afa`.)*

## Classification of the fix

> **The fix is NOAA-specific.** One f-string in
> `daf/adapters/noaa_water_level.py`. Nothing in `daf/storage/`,
> `daf/orchestration/orchestrator.py`, `daf/catalog/`, the evidence layer, or the
> vendored State-Space system was changed.

Justified from the code, not from preference: the defect is that **one adapter's
locator omitted two dimensions of its own request that change what is returned**.
`compute_artifact_id(source_id, locator) = H({source_id, locator})` is correct as
a generic rule — it says "an artifact is what a source calls a given externally
meaningful object". NOAA was simply *naming its objects wrongly*. Every other
adapter's locator already encodes everything that varies its payload:
EDGAR (a date), USGS (an event id), `incremental_dataset` (a sequence),
`local_dataset` (path#id). Generalising this into a storage-layer or
evidence-layer change would have imposed a fix for a naming bug on four sources
that never had it.

---

## 1. The observed collision

Measured against real NOAA data (Phase 17, re-confirmed live this phase):

| datum | station | product | window | first reading `t` | `v` |
|---|---|---|---|---|---|
| MLLW | 8454000 | water_level | 2024-01-15 | 2024-01-15 00:00 | **0.136 m** |
| STND | 8454000 | water_level | 2024-01-15 | 2024-01-15 00:00 | **1.2 m** |

Same instant, same gauge, genuinely different physical quantities — MLLW is mean
lower low water, STND is the station datum. Before this phase both produced the
locator `8454000:water_level:20240115:20240115`, hence one `artifact_id`, and the
second acquisition read as a **revision** of the first.

---

## 2. The exact identity chain

Traced through the actual implementation, not described:

```
adapter                RawDocument(source_name="NOAA CO-OPS Tides & Currents",
                                   source_kind="tide-station-window",
                                   locator=<see below>, content=<bytes>)
                              |
scout/pipeline.py:99   source      = make_source(kind, name)
evidence/types.py:43               = H({kind, name})
                              |
scout/pipeline.py      document    = make_document(source_id, raw_content, method, at)
evidence/types.py:65               = H({source_id, H(raw_content), retrieval_method})   <-- VERSION
                              |
                       record      = make_record(document_id, locator, raw_content)
                              |
orchestrator.py:146    artifact_id = ArtifactStore.artifact_id(document.source_id,
                                                               record.locator)
daf/storage/identity.py:16         = H({source_id, locator})                            <-- ARTIFACT
                              |
bindings.py:211        cursor      = window_end_of(record.locator)
noaa_water_level.py:158            = locator.rsplit(":", 1)[-1]                         <-- CURSOR
                              |
extractor              observation = H(content incl. datum, unit, measurement_time)     <-- MEASUREMENT
```

### Where the distinction was lost, for MLLW vs STND

| Quantity | MLLW vs STND | Correct? |
|---|---|---|
| `source.id` | **identical** — `kind`/`name` are hard-coded literals in the adapter, independent of the request | correct: it *is* the same source |
| `document.id` (version) | **differed** — `raw_content` differs, and version id hashes the content | correct |
| `observation.id` | **differed** — `datum` and `value` are both in `Observation.content` | correct |
| `artifact_id` | **IDENTICAL** — `source_id` identical **and** locator identical | ✗ **the defect** |

**Exactly one of the four identities was wrong.** That is the whole argument for
why the fix is one locator rather than a new identity layer: three of the four
identity computations already distinguished the two quantities correctly, and
they did so without consulting each other.

---

## 3. The four identities, and why they must remain distinct

**Acquisition cursor — "where should acquisition resume?"**
`window_end_of(locator)` = the window's end date. A *position in a scan*, not a
name for anything. It is deliberately recoverable from the locator for NOAA (as
for EDGAR, and unlike USGS where it had to come from `raw_content`), but it is
only ever the **last** component. Checkpoint positions themselves are bare date
strings — `"20240115"` — never locators.

**Logical artifact identity — "what externally meaningful acquired object is
this?"** `H({source_id, locator})`. Answers *what did I ask the world for*. Two
requests that name the same external object are the same artifact even when their
bytes differ.

**Version identity — "which concrete retrieved content is this?"**
`H({source_id, H(raw_content), retrieval_method})`. Answers *what did the world
actually return this time*. Never consults the locator.

**Scientific observation identity — "which measurement is this?"**
Content hash over `Observation.content`. Answers *what was measured, under what
conditions*. Never consults the locator or the artifact.

They must stay distinct because **each pair can genuinely disagree**, and this
phase demonstrates two such cases rather than asserting them:

- *Same artifact, different version* — NOAA re-issues a window when its QC
  pipeline flips readings from preliminary to verified
  (`test_same_quantity_with_changed_content_is_a_new_version_not_a_new_artifact`).
- *Same version, different artifact* — identical bytes acquired under two
  different declared datums share a version id (content-addressed) while now
  correctly belonging to two different artifacts
  (`test_version_identity_still_tracks_content_not_quantity`).

That second case is the crisp one: if artifact and version identity were the same
key, it could not exist. It does exist, and it is asserted.

---

## 4. Alternatives considered

| Option | Verdict |
|---|---|
| **A. Extend the locator** to `station:product:datum:units:begin:end` | **SELECTED** |
| B. Keep the locator as cursor; derive a separate artifact identity carrying the quantity dimension | Rejected — `artifact_id` is computed in **two** places (`orchestrator.py:146` and `metadata_index.py:117`), both from `record.locator`. A second locator-like value would need plumbing through the orchestrator *and* the index schema: a DAF-generic storage change for a one-adapter naming bug |
| C. Put datum/units in the **source** identity | Rejected on a hard mechanical ground: `document.id = H({source_id, ...})`, so changing `source.id` **also changes every version id**. That conflates artifact identity with version identity — the precise distinction §4 requires preserving — and rewrites version history. Also, `source_name`/`source_kind` are hard-coded literals inside `fetch()`, not request-derived |
| D. NOAA-specific identity projection at the DAF boundary | Rejected — the orchestrator would have to know about NOAA, breaking the invariant proven by `test_orchestrator_never_imports_domain_specific_adapter_modules` |
| E. Change generic `ArtifactStore` identity semantics | Rejected — `H({source_id, locator})` is correct; it would impose change on four adapters whose locators are already complete |

### Why A is minimal *and* correct

The locator **already carried `station` and `product`** — both scientific identity
dimensions of exactly the same kind as `datum` and `units`. Phase 17's omission
was an incompleteness in an existing scheme, not a missing concept. Option A
completes it; it does not introduce a new coupling.

§6 warns against coupling scientific identity to cursor semantics. Checked rather
than assumed: `window_end_of` is `locator.rsplit(":", 1)[-1]`, so it reads the
last component regardless of how many precede it, and checkpoint positions are
bare dates. The coupling §6 warns about does not arise —
`test_the_acquisition_cursor_is_unaffected_by_the_richer_locator` asserts that the
parser handles the old *and* new shapes identically.

---

## 5. The change

```python
# daf/adapters/noaa_water_level.py
locator = (
    f"{self.station}:{self.product}:{self.datum}:{self.units}"
    f":{_format_date(window_start)}:{_format_date(window_end)}"
)
```

One f-string, plus docstring corrections in the adapter and in
`bindings.py` (whose Phase 17 "caller constraint" note described a hazard that no
longer exists), and a supersede note on `docs/DAF_NOAA_WATER_LEVEL_ADAPTER.md`.

---

## 6. Compatibility analysis

**Is `artifact_id` persisted?** Almost not. `ArtifactStore` **recomputes** it —
`get()` derives the locator from the Document's Record and compares
(`artifact_store.py:98`), and `list_versions` groups by recomputation. It is
never a stored key in the blob store. `MetadataIndex` *does* store it
(`records.artifact_id`, computed at insert, `metadata_index.py:117`), but that
table is explicitly "an INDEX, never a second raw-content authority" and
`MetadataIndex.rebuild(store)` regenerates it from the store. So the migration
path for any existing deployment is **reindex, not data migration** — asserted by
`test_artifact_store_and_metadata_index_resolve_the_new_identities`, which calls
`rebuild()` and checks the index derives exactly what acquisition reported.

**What changes:** NOAA `artifact_id` values, for old and new acquisitions alike,
because they are derived from the locator. This is a deterministic, one-time
identity change, made explicit here rather than silently. It is confined to NOAA.

**What does NOT change:**

- **Version ids.** Confirmed empirically, not argued: the live MLLW acquisition
  in this phase produced version `3bc9041f042eb48f…`, byte-identical to the value
  recorded in Phase 17's transcript. Version identity never consulted the locator.
- **Observation ids**, for the same reason.
- **Checkpoint positions** — still `"20240115"`.
- **Every other adapter** — EDGAR, USGS, arXiv, local/incremental dataset are
  untouched, and their tests pass unchanged.

**Existing tests:** 14 pinned locator literals across 4 files were updated to the
corrected format. None was weakened or deleted — each still asserts an exact
locator string, and every surrounding behavioural assertion (checkpoint
advancement, trailing safety window, duplicate detection, restart, revision →
new version/same artifact) is unchanged and passing. Phase 17's test that
deliberately *pinned the defect* was rewritten to assert the fix and renamed
accordingly.

---

## 7. Live validation

Executed against the real NOAA CO-OPS API with the finished implementation:

```
MLLW: outcome=acquired  locator=8454000:water_level:MLLW:metric:20240115:20240115
      artifact_id=10037932fa8f756a7ba4fc23…   version_id=3bc9041f042eb48fdddaa046…
STND: outcome=acquired  locator=8454000:water_level:STND:metric:20240115:20240115
      artifact_id=4913108409303551d8fd6bae…   version_id=493d8acc0957140a19b6b65a…

A != B : True

re-acquire MLLW -> duplicate | same artifact: True | same version: True

MLLW: list_versions -> ['3bc9041f042eb48f']
STND: list_versions -> ['493d8acc0957140a']

analysis: 480 observations | 480 comparison groups | datums {'MLLW','STND'}
```

The stop condition, met: MLLW → identity A, STND → identity B, A ≠ B; duplicate
detection still correct; both artifacts separately addressable in
`ArtifactStore`.

---

## 8. Scientific semantics unchanged (§10)

The identity fix was **not** achieved by moving `datum` out of scientific content.
It remains a genuine conditioning variable in `Observation.content`, exactly as
Phase 17 established, and the live run still reports 480 observations in 480
comparison groups spanning both datums.

Acquisition identity and comparison context are separate concepts that happen to
*agree* about datum here — one because a different datum is a different request,
the other because a different datum is a different physical quantity. Neither
derives from the other, and
`test_the_scientific_comparison_context_is_not_how_the_fix_works` asserts that no
locator ever leaks into `Observation.content`.

---

## 9. Tests

`tests/test_noaa_artifact_identity.py` — 10 new tests:

| § | Test |
|---|---|
| 1 | `test_different_datums_produce_different_logical_artifact_identities` |
| 1 | `test_units_are_part_of_identity_for_the_same_reason_as_datum` |
| 2 | `test_same_datum_reacquisition_is_still_a_duplicate` |
| 3 | `test_same_quantity_with_changed_content_is_a_new_version_not_a_new_artifact` |
| 4 | `test_the_acquisition_cursor_is_unaffected_by_the_richer_locator` |
| 4/5 | `test_checkpoint_advances_and_restart_resumes_across_the_new_locator` |
| 7/8/11 | `test_artifact_store_and_metadata_index_resolve_the_new_identities` (incl. `rebuild()`) |
| 9 | `test_observation_identity_is_independent_of_artifact_identity` |
| 6 | `test_version_identity_still_tracks_content_not_quantity` |
| 10 | `test_scientific_comparison_context_is_not_how_the_fix_works` |

§12 item 12 (no regression in EDGAR/USGS/NOAA existing paths) is covered by the
existing suites, which pass unmodified apart from the locator literals.

Two defects of my own were found while writing these and fixed: a `_one()` helper
that consumed its generator twice, and a blind `except Exception` replaced with
`pytest.raises(ArtifactNotFoundError)`.

---

## 10. Validation

| Check | Result |
|---|---|
| DAF suite | **308 passed** (298 prior + 10 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule cleanliness | `git status --short` clean |
| `mypy daf/` | Success, 44 source files |
| `ruff` | `UP006`/`UP035`/`UP045` only — repo-wide conventions |
| Live NOAA acquisition | performed with the finished implementation (§7) |

---

## 11. Remaining limitations

1. **NOAA `artifact_id` values changed.** Deterministic and documented, but any
   external system that recorded a NOAA artifact_id before this commit must
   reindex. No in-repo data requires migration.
2. **Only datum and units were added.** If NOAA later returns payloads varying by
   another request parameter not in the locator (`time_zone` is the obvious
   candidate — it changes reported timestamps), the same class of collision
   returns. This phase fixed the dimensions demonstrated with real data, and did
   not speculatively add the rest.
3. **No general guard against the class of bug.** Nothing prevents a *future*
   adapter from omitting a payload-varying parameter from its locator. A generic
   guard would need to know which request parameters affect a response — source
   knowledge that lives only in each adapter.
4. **The revision test uses a controlled second version.** The real
   preliminary→verified transition for one timestamp still cannot be obtained from
   the live API at a single point in time (Phase 17 §4). The revised payload is
   the real MLLW response with one reading altered, used only to exercise the
   identity mechanism, and labelled as such.
5. **`AcquiredArtifact` remains per-finding, not per-document** (Phase 17 §8) —
   untouched here.

---

## 12. Next frontier

Unchanged from Phase 17, with item (a) now resolved:

- **A second, structurally different real source** — would test whether the
  field-classification and locator-completeness discipline generalises or was
  tuned to NOAA. Limitation 3 above is a concrete reason to want this.
- **Time-series semantics** — the honest gap: the comparison machinery answers
  "do these agree?", but nothing answers "how does this evolve?". Not on the
  deferred list.

**Expected information gain remains deferred** and untouched.

---

*Phase R halts here: inspected, collision reproduced, smallest correction
identified and implemented, tested, run live, defects fixed, invariants audited,
validated, documented, committed and pushed.*
