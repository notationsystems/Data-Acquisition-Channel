# Phase S — Acquisition Identity Generalization Audit + Build

*(Repository phases are lettered; the prompt labels this "Phase 19". Continues
from Phase R — `docs/PHASE_18_NOAA_ARTIFACT_IDENTITY.md` — at `21b7321`.)*

## Decision (§14): **B — the failure mode recurred**

A second, independent adapter exhibited the identical defect, and it was
**reproduced empirically before any code was changed**:

```
--- INCREMENTAL ---
  locators: {'000000000001'} vs {'000000000001'}
  artifact ids equal: True | version ids equal: False
  outcome2: acquired | COLLISION
--- LOCAL ---
  locators: {'…/stream_a.json#r1'} vs {'…/stream_b.json#r1'}
  artifact ids equal: False | version ids equal: False
  outcome2: acquired | separated
```

Two different dataset files, acquired under one registered source, each
containing a record with sequence 1: `incremental_dataset` gave them **one
artifact identity**, so the second read as a *revision* of the first.
`local_dataset` — same record shape, same extractor — separated them correctly,
because it already put `path` in its locator.

So NOAA was **not** an isolated source-specific naming slip. Both failures share
one shape:

> a **request parameter that varies the payload** was absent from the logical
> artifact's name.

### What B did *not* justify

§14 says that under B, "design the smallest generic contract justified by the
evidence, then implement it in this same phase." The smallest justified contract
turned out to be **an executable invariant, not a runtime abstraction**, and that
conclusion is grounded in the code rather than in taste:

`compute_artifact_id(source_id, locator) = H({source_id, locator})` is **already
the correct generic rule**. Neither defect was the rule being wrong; both were
adapters *naming their objects wrongly*. And a runtime framework could not have
prevented either, because deciding which request parameters vary a payload
requires knowledge that exists only inside each adapter — `min_magnitude` varies
USGS's result set but not any event's content, while `datum` varies NOAA's
content directly. The DAF core cannot tell those apart, and §1 forbids a generic
identity framework without empirical justification.

So: **two source-specific fixes** (NOAA in Phase R, `incremental_dataset` here)
plus **one reusable cross-source invariant suite** that states the rule once and
checks it against every adapter.

---

## 1. Cross-source identity table

Built by reading each adapter, not from prior phase reports.

| Adapter | Payload dimensions | Locator dimensions | Cursor | Artifact dimensions | Version dimensions | R1 |
|---|---|---|---|---|---|---|
| **arXiv** | `arxiv_ids` (which entries) | entry `<id>` from the response | — (not incremental) | source + entry id | content | ✓ |
| **EDGAR** | `year`, `quarter`, `since_date` | `date` | `date` (= locator) | source + date | content | ✓ |
| **USGS** | `start_time`, `end_time`, `min_magnitude`, `updated_after` | `event_id` | `properties.updated` (from **raw_content**, not the locator) | source + event id | content | ✓ |
| **local_dataset** | `path` | `path#id` | — | source + path + id | content | ✓ |
| **incremental_dataset** | `path`, `since_sequence` | ~~`sequence`~~ → **`path#sequence`** | `sequence` (last component) | source + path + sequence | content | **fixed here** |
| **NOAA** | `station`, `product`, `datum`, `units`, window | `station:product:datum:units:begin:end` | `end` (last component) | all of the above | content | fixed in Phase R |

Every adapter's **version** identity is `H({source_id, H(raw_content), retrieval_method})`
— content-derived, never locator-derived. That is why version identity was
correct everywhere even where artifact identity was not.

---

## 2. Rejected speculative collisions

Investigated and **deliberately not "fixed"**, because the code shows they are
not identity dimensions:

**NOAA `time_zone` (§5 — Phase R's explicitly deferred question).** It is a
hard-coded URL literal, `&time_zone=gmt`, **not** a dataclass field. It cannot
vary between acquisitions, so it cannot produce two payloads under one identity.
Adding it would have been speculative. Asserted in
`test_noaa_time_zone_is_not_an_identity_dimension`, which checks both the literal
and `NoaaWaterLevelSourceAdapter.__dataclass_fields__`. (`format=json` is a
literal for the same reason.)

**USGS filter parameters (§6).** `min_magnitude`, `start_time`, `end_time` vary
**which** events come back, not **what event X contains**. A payload-varying
parameter at the *result-set* level is not an identity dimension of an
*individual artifact*. Asserted directly: re-fetching event `synth00000001` under
`min_magnitude=0.1` instead of `3.0` yields a byte-identical identity pair.

**EDGAR `year`/`quarter` (§7).** A date belongs to exactly one year/quarter, so
`date` names the daily index completely. Unmodified, as §7 instructs.

---

## 3. The fix

`daf/adapters/incremental_dataset.py`. Through Phase F, **one function**
(`locator_for`) served as *both* the document locator and the checkpoint
position — precisely the cursor/identity conflation §8 warns against. They are
now separated:

```python
def locator_for(sequence: int) -> str:            # CHECKPOINT POSITION
    return str(sequence).zfill(_SEQUENCE_WIDTH)   # unchanged: "000000000007"

def document_locator_for(path: Path, sequence: int) -> str:   # LOGICAL ARTIFACT
    return f"{path}#{locator_for(sequence)}"

def sequence_of(value: str) -> int:               # CURSOR, from either shape
    return int(value.rsplit("#", 1)[-1])
```

`path` is the request parameter that determines the payload, so it belongs in the
artifact's name — the rule `local_dataset` already followed. The sequence stays
**last** so the cursor is recoverable without knowing what precedes it, mirroring
NOAA's `window_end_of` (`rsplit(":", 1)[-1]`). **Checkpoint positions are
unchanged** — still bare padded sequences, carrying no dataset identity.

---

## 4. A genuine consequence found by running it (§ observe → fix)

Updating the locator broke `test_late_arrival_safety_window.py` — and one failure
was **not** a literal:

```
assert len(pool.all_observations()) == 5
E  assert 6 == 5
```

**Root cause, traced through the evidence layer:**
`record_id = H({document_id, locator, raw_content})` and
`obs_id = H({record_ids, extraction_method, content})`. A different locator
therefore produces a different Record and hence a different Observation — *even
for byte-identical content*.

The test simulated one growing dataset using **two different fixture files**. That
worked only because the path was not part of identity — an incidental reliance on
the very defect being fixed. Under the fix, the two files are correctly two
datasets, so record 5 became two records and two observations.

**The fix was to the test, and it strengthens it:** a real incremental source is
one path whose file grows, so the test now copies each fixture over a *single*
path. That is a more faithful simulation, and it keeps the test about what it is
actually about — late-arriving sequences and cursor behaviour. Every behavioural
assertion (`is_new`, observation counts, checkpoint positions, the naive-vs-safety
-window contrast) is unchanged and passing; nothing was weakened.

**The real-world scenario never had the problem:** a plan holds a fixed `path`,
the file grows, locators are stable, and no duplicate observation arises.

---

## 5. Answers to §15's explicit questions

**Is artifact identity source-specific or generic?**
The *rule* is generic and unchanged: `H({source_id, locator})`. The *dimensions*
are irreducibly source-specific, because only an adapter knows which request
parameters change what comes back. Both defects lived in the dimensions, never in
the rule — which is exactly why both fixes were source-specific.

**When should a locator change?**
When it fails to distinguish two acquisitions that name different external
objects. Concretely: whenever a request parameter can vary the payload for
otherwise-identical requests. Not when the *content* changes — that is what
version identity is for.

**When should only content/version change?**
When the same external object is re-retrieved and the bytes differ: SEC
republishing a daily index, USGS revising an event, NOAA flipping preliminary
readings to verified, a dataset record corrected in place. All four are asserted.

**When may a cursor be encoded in a locator?**
Whenever it is recoverable without depending on the rest of the locator — in
practice, when it occupies a fixed *terminal* position. NOAA (`rsplit(":", 1)`)
and `incremental_dataset` (`rsplit("#", 1)`) both satisfy this. USGS is the
counterexample that proves it is optional: its cursor (`properties.updated`)
lives in `raw_content`, not the locator, which is why `AcquiredArtifact.raw_content`
exists. **Embedding is a source-specific implementation relationship, never an
architectural identity.**

**Can a scientific conditioning variable also be an acquisition identity
dimension?**
Yes — `datum` is both, and this is not a contradiction. It is an acquisition
dimension because a different datum is a *different request*; it is a scientific
conditioning variable because a different datum is a *different physical
quantity*. Neither derives from the other, and neither is computed from the
other: `Observation.content` never contains a locator, and `artifact_id` never
consults `Observation.content`. They agree here by coincidence of meaning, not by
construction — asserted in
`test_scientific_identity_is_independent_of_acquisition_identity`.

**When should a new generic abstraction be introduced?**
Not merely because a failure mode recurred. The test here is whether the abstraction
could actually *do* the job: a runtime identity framework would need to know which
request parameters vary a payload, which is source knowledge it cannot have. When
the shared thing is a *rule* rather than a *mechanism*, the right artifact is an
executable invariant, not a runtime layer.

---

## 6. Tests — the §10 matrix

`tests/test_acquisition_identity_invariants.py`, 14 tests. Three rules stated
once (`_assert_separated`, `_assert_same_artifact_new_version`, cursor checks)
and applied across every adapter. `_identity()` reproduces the production
computation exactly (`run_scout` + `orchestrator.py:146`), so adapters are
exercised directly and the suite stays fast.

| Row | Covered by |
|---|---|
| 1 EDGAR artifact separation | `test_edgar_separates_artifacts_by_date` |
| 2 EDGAR same-artifact revision | `test_edgar_same_date_with_changed_bytes_is_a_new_version_of_one_artifact` |
| 3 USGS stable identity across revisions | `test_usgs_keeps_one_artifact_identity_across_a_real_revision` |
| 4 USGS version separation | same test + `test_usgs_separates_distinct_events_and_ignores_filter_parameters` |
| 5 NOAA datum separation | `test_noaa_separates_artifacts_by_datum_and_by_product` |
| 6 NOAA product separation | same |
| 7 NOAA time-zone behaviour | `test_noaa_time_zone_is_not_an_identity_dimension` |
| 8 NOAA duplicate acquisition | `test_noaa_reacquisition_and_revision_keep_one_artifact` |
| 9 NOAA checkpoint restart | `test_noaa_cursor_survives_the_richer_locator` + Phase R's suite |
| 10 Incremental cursor behaviour | `test_incremental_dataset_cursor_is_recoverable_from_both_shapes` (+ separation and in-place revision) |
| 11 ArtifactStore lookup after restart | `test_storage_resolves_both_artifacts_after_restart_and_index_rebuild` |
| 12 MetadataIndex rebuild | same |
| 13 DurablePool fingerprint equivalence | same |
| 14 Observation identity independence | `test_scientific_identity_is_independent_of_acquisition_identity` |
| 15 Comparison context independence | same |

Plus `test_local_dataset_and_arxiv_already_satisfy_the_invariant`, covering the
two adapters that never had the defect (including a real arXiv v1→revised pair).

---

## 7. Live validation (§11)

All three live sources, bounded and respectful, with the finished implementation.
**Live observations**, not fixtures:

```
EDGAR   locator=20250102
        artifact=ee2c1c1d21b66752  version=867c0cbd02db851a  (711,144 bytes, 1 date)

USGS    locator=us6000m0xm  artifact=02c3d663e93dbd1c  version=21dbcf0447cc72a2
        locator=us6000m0xl  artifact=18c313249dd06ea8  version=fe1e9a3aeb84534f
        (M>=6.0, 2024-01-01..03, max 3 events)

NOAA    MLLW  locator=8454000:water_level:MLLW:metric:20240115:20240115
              artifact=10037932fa8f756a  version=3bc9041f042eb48f
        STND  locator=8454000:water_level:STND:metric:20240115:20240115
              artifact=4913108409303551  version=493d8acc0957140a
        artifact A != B : True
```

NOAA's artifact and version ids are **byte-identical to those recorded in Phase
R**, confirming this phase changed nothing about NOAA identity.

**Provenance of every input is distinguished**, as §11 requires:

- *Live observation* — the transcript above.
- *Captured real fixture* — `noaa_live_8454000_*.json` (verbatim live bytes,
  Phase Q), `usgs_event_detail_synth00000001_revised.json`,
  `arxiv_single_entry_v1_revised.xml`.
- *Synthetic unit fixture* — EDGAR synthetic index files, and the in-test
  datasets built in `tmp_path`. The EDGAR and NOAA revision payloads are
  **constructed second versions**, labelled as such in their tests: no revision
  was fabricated and presented as observed source behaviour.

---

## 8. Storage and scientific-boundary validation (§12, §13)

**Storage** — proven across the two artifacts that used to collide, after a
process restart: `ArtifactStore.get`, `list_versions`, duplicate detection,
`MetadataIndex.rebuild()`, and `DurablePool.fingerprint()` equivalence before and
after restart. No storage redesign; `daf/storage/` is untouched.

**Scientific boundary** — re-ran the established path. `Observation.content` still
carries exactly `{property, value, unit, datum, station_id, measurement_time,
sigma}` and never a locator; `analyze()` still returns 480 observations across
both datums with `observed_disagreement is None` (unchanged from Phase Q, since
distinct measurement times are distinct quantities). The scientific layer was not
made responsible for fixing acquisition identity.

---

## 9. Validation

| Check | Result |
|---|---|
| DAF suite | **322 passed** (308 prior + 14 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git status --short` clean |
| `mypy daf/` | Success, 44 source files |
| `ruff` | `UP006`/`UP035`/`UP045` (repo-wide conventions); one pre-existing `I001` in `test_late_arrival_safety_window.py`, present at HEAD before this phase |
| Changed files | `daf/adapters/incremental_dataset.py`, `tests/test_late_arrival_safety_window.py`, `tests/test_acquisition_identity_invariants.py` (new), this document. No unrelated files |

Production change: **one adapter**, 41 insertions / 8 deletions, mostly docstring.

---

## 10. Invariants preserved

- **Checkpoint semantics** — positions remain bare padded sequences; `advance_position`,
  the trailing safety window, and the naive-vs-safety-window contrast all
  unchanged and passing.
- **Version identity** — content-derived everywhere; NOAA's live version ids match
  Phase R exactly.
- **Observation identity and comparison context** — untouched by both fixes.
- **Storage contracts** — `ArtifactStore`, `MetadataIndex`, `BlobStore`,
  `DurablePool` unmodified.
- **Every other adapter** — EDGAR, USGS, arXiv, `local_dataset` unmodified.
- No existing test weakened or deleted.

---

## 11. Limitations

1. **`path` is now identity for `incremental_dataset`.** Relocating a dataset file
   re-identifies its artifacts. This is the same trade-off `local_dataset` already
   made, and the opposite choice caused the collision — but it is a real trade-off,
   not a free win. A source that legitimately moves must keep its path stable or
   accept re-identification.
2. **Artifact ids for `incremental_dataset` change**, deterministically. As in
   Phase R, `artifact_id` is derived and `MetadataIndex.rebuild()` regenerates it,
   so migration is a reindex. No in-repo data requires migration.
3. **The invariant is checked, not enforced.** Nothing stops a *future* adapter
   from omitting a payload-varying parameter. The new suite makes the rule explicit
   and cheap to extend — a new adapter should add its rows — but it cannot fail for
   an adapter nobody wrote a case for.
4. **Six adapters is the whole sample.** Two failed, four passed. The rule is well
   evidenced but not proven exhaustive.
5. **`AcquiredArtifact` remains per-finding, not per-document** (Phase Q §8) —
   untouched.

---

## 12. Next frontier

Chosen from this phase's evidence, as §18 requires:

- **A structurally different real source** — six adapters is a small sample, and
  limitation 3 means the invariant's generality is still partly assumed. A source
  with a genuinely different identity shape (paged APIs, content-addressed
  sources, sources with no stable object identity) would test it hardest.
- **Time-series semantics** — unchanged from Phase Q: the comparison machinery
  answers "do these agree?", nothing answers "how does this evolve?". Not on the
  deferred list.

**Expected information gain remains deferred**, and §18 explicitly forbids
proceeding into it merely because this phase completed.

---

*Phase S halts here: audited, collision reproduced before any change, fixed
source-specifically, run live against three real sources, a genuine test defect
observed and repaired, invariants audited, validated, documented, committed and
pushed.*
