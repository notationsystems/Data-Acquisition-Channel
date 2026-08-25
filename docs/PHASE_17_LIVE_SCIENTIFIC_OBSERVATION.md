# Phase Q — Live Scientific Observation Acquisition

*(Repository phases are lettered; the prompt labels this "Phase 17". Continues
from Phase P — `docs/PHASE_16_ACQUIRED_EVIDENCE_ANALYSIS.md` — at `1a9aae1`.)*

## Answer to the stop-condition question

> **Can the DAF acquire real scientific observations and deliver them through the
> existing SCOUT/evidence architecture without corrupting their scientific
> semantics?**

**Yes** — demonstrated end to end against the live NOAA CO-OPS API. 240 real
water-level measurements were acquired, admitted with a declared trust graph,
durably stored, survived a process restart with identity intact, and were
consumed by `materials.analysis`.

With one important qualification, which is the phase's main scientific finding:
the correct analysis verdict on a tide-gauge series is **`INCOMPARABLE`**, and
that is a *right answer*, not a failure. And one genuine defect was found in the
existing adapter (§ Locator collision) which is documented and pinned by a test
rather than silently fixed.

---

## 1. Source selection

Four candidates were probed live. Reachability was checked first, but was *not*
the deciding criterion.

| Candidate | Reachable | Verdict |
|---|---|---|
| USGS Water Services (`waterservices.usgs.gov`) | ✗ HTTP 503 | Preferred on semantics; unavailable throughout the phase |
| Open-Meteo | ✓ 200 | **Rejected on semantics** — forecasts and reanalysis, not direct observations (§2 requires "actual scientific observations") |
| USGS Earthquakes | ✓ 200 | Rejected — an *event catalogue*; magnitude scales (ml/mw/mb) fit `property`/`value`/`unit` poorly, and DAF already has an adapter |
| **NOAA CO-OPS Tides & Currents** | ✓ 200 | **Selected** |

NOAA CO-OPS was selected because it satisfies every §2 criterion and, decisively,
is a genuine *measurement* source: one scalar physical quantity, a real unit, an
explicit vertical datum (a true conditioning variable), unambiguous station
identity, GMT timestamps, no authentication, deterministic bounded retrieval over
a historical window, and a **documented, observable revision lifecycle**
(preliminary → verified).

That last property was verified live rather than assumed: the 2024-01-15 window
returns `q="v"` for every reading, while a window two days before the phase date
returns `q="p"` for every reading. Both are committed as fixtures.

DAF already had a NOAA adapter (Phase I) but it had **only ever been exercised
against synthetic fixtures** — this phase is the first time it touched the live
service.

---

## 2. Source semantics — field classification (§3)

Decided by reading a real response, not the API documentation. A real reading:

```json
{"t": "2024-01-15 00:00", "v": "0.136", "s": "0.006", "f": "0,0,0,0", "q": "v"}
```

| Field | Classification | Destination |
|---|---|---|
| `v` | scientific content | `content["value"]`, parsed to `float` |
| `s` | scientific content | `content["sigma"]` (σ of the 1-second samples) |
| `t` | **scientific context** | `content["measurement_time"]` — see §3 |
| `datum` (request) | scientific context | `content["datum"]` |
| `units` (request) | scientific context | `content["unit"]` |
| `metadata.id` | source identity **and** context | station referent **and** `content["station_id"]` |
| `metadata.name/lat/lon` | source identity | dropped from content (describes the station, not the measurement) |
| `q` | **revision metadata** | deliberately excluded — see §4 |
| `f` | acquisition/QC metadata | excluded |
| request URL, window bounds, `product`, `time_zone`, `application`, `format` | acquisition metadata | excluded |

`v` is returned as a *string*. Parsing it to `float` is required, because
`materials.analysis._as_float` **asserts** a numeric type rather than coercing.
This is faithful parsing of a numeric literal, not interpretation.

Neither `datum` nor `units` is echoed in the response body — asserted directly in
`test_units_and_datum_come_from_the_request_not_from_the_response`. They can come
only from the request, which is why the binding parameterises adapter and
extractor **together** (§5).

---

## 3. The central finding: `measurement_time` is context, and `INCOMPARABLE` is correct

Phase 16 removed the acquisition locator `id` from `Observation.content` because a
field unique to each record makes every observation its own single-member
comparison group, so nothing is ever comparable. `t` is *also* unique per reading
and has exactly the same mechanical effect — **but the opposite classification is
correct**, and that contrast is the whole point of the Phase 16 invariant:

- `id` was an **acquisition identifier**. Two records with different ids could
  still be measurements of the same quantity, so letting it split the comparison
  context was a *defect*.
- `t` is a **scientific conditioning variable**. A water level at 00:00 and one at
  00:06 are measurements of genuinely *different* quantities. Pooling them and
  reporting a "disagreement" of 1.9 m would be reporting the **tidal range as
  measurement error** — a serious misrepresentation of the physics.

So the analysis result on real data is:

```
observed:                   240 observations
observed_comparison_groups: 240 groups, one value each
observed_disagreement:      None
```

**`INCOMPARABLE` is the scientifically correct verdict.** A tide-gauge series is
not a set of repeated measurements of one quantity, and the architecture is right
to refuse to treat it as one.

> The Phase 16 invariant is therefore **not** "strip fields that are unique per
> record". It is "classify every field as scientific or acquisition, and let the
> classification decide". Identical mechanics, opposite verdicts.

This also delimits the analysis layer's applicability: `materials.analysis`
answers *"do my measurements of this quantity agree?"*. A time series asks
*"how does this quantity evolve?"* — a different question the comparison
machinery does not claim to answer, and this phase does not force it to.

---

## 4. Revision semantics (§10)

The lifecycle is real and observable: NOAA revises preliminary readings into
verified ones **for the same timestamp**.

`q` is deliberately **excluded** from content, and that exclusion is load-bearing.
Were `q` part of content, it would join the comparison context, and a preliminary
reading and its own later verified correction would land in **different comparison
groups** — so the architecture could never see that they disagree. Excluding it
means they share a context and a genuine conflict is reported, which is correct.
The flag is not lost: it remains in the durably stored raw artifact.

**Duplicate behaviour (immutable window), tested live-truthfully:** re-acquiring
the same verified window yields `outcome == "duplicate"`, identical observation
ids, and identical version ids. An independent pool given the same bytes produces
byte-identical content-addressed ids.

**What was *not* manufactured:** a preliminary→verified transition for one
timestamp cannot be obtained from the live API at a single point in time (recent
data is preliminary; verified data is old). Rather than fabricate one, this phase
documents the lifecycle, commits real fixtures of both states, and proves the
*mechanism* that would carry it — same logical artifact + changed content → new
version id, historical version preserved — via the datum case in §6, which uses
two genuinely different real payloads.

---

## 5. Acquisition contract (§4) — what was built

Two files, no new acquisition framework, no change to SCOUT:

**`daf/extractors/noaa_water_level_measurements.py` (new).** Emits one
`ExtractionCandidate` **per reading** from one window record. This is the first
DAF extractor where findings ≠ documents.

The existing `daf.extractors.noaa_water_level` is **kept and unmodified**. It
produces one observation per *window* with a `readings` list — which Phase M
showed stops at the evidence boundary, since `materials` needs a scalar
`content["value"]`. Both are correct for different questions: the window extractor
answers "what did this acquisition window contain", the new one "what individual
measurements were made". Neither replaces the other.

**`daf/orchestration/bindings.py`.** `noaa_water_level_measurement_binding(*, datum,
units, fetch_bytes=None)` pairs the **existing, unmodified**
`NoaaWaterLevelSourceAdapter` with the new extractor. `datum`/`units` are accepted
once and handed to *both*, because the response echoes neither and
`BuildExtractor` is a zero-argument factory that cannot read the request. Passing
them separately would permit an adapter/extractor disagreement no test would
easily catch: every value silently labelled with a datum it was not measured
against.

### Graph declaration (§5), deliberately minimal

Two entities the source itself establishes — the **station** (explicitly
identified in every response) and the **vertical datum** every value is referenced
to — joined by one relation, `referenced_to`. Because each relation carries its own
`observation_id`, it asserts exactly *"this water-level observation, taken at this
station, is referenced to this datum"* — precisely what the CO-OPS API establishes,
and nothing more.

Rejected as fabrication: a *sensor* entity (the response never identifies one); a
*location* entity (lat/lon describe the station; a `located_at` place referent
would assert a spatial ontology the source does not supply); any relation between
successive readings (the source asserts no such link).

One relation per reading is also the **minimum for reachability** —
`retrieval.engine` reaches observations *only* through relationships
(`candidate_observation_ids = {relationships_by_id[rid].observation_id ...}`), so
an entity-only declaration would leave evidence admitted but invisible to
analysis.

---

## 6. Locator collision — a genuine defect, found by measurement

Real data, same station, same day, same product, **same locator**:

| datum | first reading `t` | `v` |
|---|---|---|
| MLLW | 2024-01-15 00:00 | **0.136 m** |
| STND | 2024-01-15 00:00 | **1.2 m** |

`NoaaWaterLevelSourceAdapter`'s locator is `station:product:start:end` and omits
datum and units, while `ArtifactStore.artifact_id` keys on `(source_id, locator)`.
Two scientifically distinct payloads therefore land under **one artifact
identity**, where the second reads as a *revision* of the first rather than a
different quantity.

**There is no caller-level remedy.** The `source_id` in that key is the *evidence*
`Document.source_id`, derived by `run_scout` from the `source_name`/`source_kind`
the adapter **hard-codes** — the DAF `SourceDefinition.source_id` never reaches it.
Registering the two datums under different DAF source ids does **not** separate
them. This was verified, not assumed: the first attempt at a remedy failed the
test, and the test now pins the true behaviour.

**Severity is bounded, and this matters.** No data is lost or silently
overwritten: the differing content still gets a distinct version id, and the
historical version is preserved. More importantly, the **scientific** layer is not
corrupted — because `datum` *is* part of each observation's comparison context,
`materials.analysis` correctly keeps MLLW and STND readings in separate comparison
groups even when their artifacts collide. The defect is in acquisition-identity
bookkeeping, not in scientific semantics.

**Left unfixed in this phase deliberately, not silently.** Both candidate fixes —
putting datum/units in the locator, or making the adapter's source identity
configurable — change artifact identity for the existing NOAA source, and the
locator format is additionally the checkpoint cursor parsed by `window_end_of()`.
It is pinned in 14 assertions across 4 existing test files. Changing it is a
scoped piece of work, not a drive-by edit, and this phase was told not to redesign
DAF.

**Recommended fix (next phase):** extend the locator to
`station:product:datum:units:start:end` and update `window_end_of()` to parse from
the end rather than by fixed index, migrating the 14 pinned assertions in one
commit.

---

## 7. Live acquisition transcript (§7)

Executed against `https://api.tidesandcurrents.noaa.gov/api/prod/datagetter`.

```
source        NOAA CO-OPS Tides & Currents (station 8454000, Providence RI)
request       product=water_level station=8454000
              begin_date=20240115 end_date=20240115
              datum=MLLW units=metric time_zone=gmt format=json
outcome       acquired
artifacts     240          (one AcquiredArtifact per finding -- see §8)
locator       8454000:water_level:20240115:20240115
version_id    3bc9041f042eb48f...
observations  240
referents     ('8454000','monitoring_station'), ('MLLW','vertical_datum')
relationships 240, all type 'referenced_to'
units         {'m'}          datum {'MLLW'}
value range   -0.204 m  ->  1.711 m     (real tidal range in the window)
quality       all q='v' (verified)

first three observations:
  9ca28038715d {"datum":"MLLW","measurement_time":"2024-01-15 00:00","property":"water_level",
                "sigma":0.006,"station_id":"8454000","unit":"m","value":0.136}
  aa94f6d7a4a2 {"datum":"MLLW","measurement_time":"2024-01-15 00:06","property":"water_level",
                "sigma":0.005,"station_id":"8454000","unit":"m","value":0.132}
  61c91e3498e3 {"datum":"MLLW","measurement_time":"2024-01-15 00:12","property":"water_level",
                "sigma":0.004,"station_id":"8454000","unit":"m","value":0.133}
```

No credentials or secrets are involved — the API requires none.

**Fixtures are verbatim.** The recorded bytes in `tests/fixtures/noaa_live_*.json`
are exactly what the live API returned. The committed tests replay them through
the adapter's own `fetch_bytes` injection point, so the suite is deterministic and
offline while every other stage is the real code path — the discipline Phases I
and M already established. That the fixture-replay tests produce **the same
observation ids** as the live run (`9ca28038715d…`) is direct evidence the replay
is faithful.

**Bounding (§7) — a deliberate deviation.** §7 suggests 5–50 measurements; this
acquires 240. `NoaaWaterLevelSourceAdapter`'s window granularity is a **calendar
day**, and `water_level` is sampled every 6 minutes, so 240 is the *minimum* a
single request can return. Narrowing it would mean changing the adapter's
windowing, i.e. redesigning DAF, which §1 forbids. The acquisition is nonetheless
strictly bounded in the sense that matters: one HTTP request, one station, one
day, ~18 KB.

---

## 8. Architectural finding: `AcquiredArtifact` is per-finding, not per-document

`len(result.artifacts) == 240` for a **single** fetched document. The orchestrator
builds one `AcquiredArtifact` per *finding* (per extraction candidate), and every
previous DAF extractor emitted exactly one candidate per record — so
findings-per-document was always 1 and the distinction was invisible.

This is not a defect: `artifact_id`, `version_id`, `locator` and `is_new` are all
correct on every one of the 240, and they correctly share one artifact/version
identity. But `len(result.artifacts)` counts **observations**, not documents, and
any caller reading it as a document count would be wrong. Pinned by
`test_real_measurements_are_admitted_with_the_declared_trust_graph`.

---

## 9. Restart (§8)

Process 1 acquires and persists; process 2 opens a fresh `DurablePool` over the
same on-disk store with nothing in memory. Preserved across the restart:

- all 240 observation identities, exactly
- both referents (`8454000`, `MLLW`)
- the raw acquired artifact, by `version_id` (`pool.has_document(version_id)`)
- the analysis result: same observation list, same ordering, same 240 comparison
  groups

---

## 10. Representation audit (§11)

| Stage | Preserved | Discarded | Why the loss is legitimate | Inference enabled |
|---|---|---|---|---|
| NOAA JSON → **RawDocument** | whole response verbatim; window locator; retrieval method/time | nothing | — | byte-exact provenance, re-extraction |
| RawDocument → **Document/Record** | raw content; locator as cursor | nothing | — | duplicate/revision detection by content hash |
| Record → **Observation** ×240 | value, sigma, time, datum, unit, station | `q`, `f`, station name/lat/lon, URL, product | `q`/`f` are revision/QC metadata that would corrupt comparison context (§4); name/lat/lon describe the station, which is a referent; URL/product are acquisition metadata. All recoverable from the retained raw artifact | comparison of like with like; conflict detection between a reading and its correction |
| Observation → **Referent/Relationship** | station identity, datum identity, per-observation link | any richer structure | not established by the source (§5) | graph reachability from station to every reading |
| Evidence → **analysis** | all 240 readings, grouped by context | — | — | *"do measurements of this quantity agree?"* — correctly answered `INCOMPARABLE` |

**What remains impossible, by construction:** trend, tidal harmonics, or any
time-evolution inference. `materials.analysis` compares within a context; it does
not model evolution *across* contexts. That is not a gap this phase should paper
over — it is the honest boundary of the comparison machinery.

Judged by the representation principle — *evaluated by the dynamics and inference
it enables* — the representation earns its keep for provenance, identity,
revision-safety and like-for-like comparison, and honestly declines to support
time-series inference it cannot ground.

---

## 11. Scientific analysis boundary (§9)

`materials.analysis.analyze` was used with `MaterialQuestion(material_natural_key,
property)` — **not** `reevaluate_program`. That choice is deliberate:
`reevaluate_program` requires formulation/process/criterion semantics that NOAA
does not supply, and forcing a tide gauge into the materials-experiment
abstraction is exactly what §9 forbids. Nothing here became a `ModelState` update,
and that boundary is left explicit.

---

## 12. Validation

| Check | Result |
|---|---|
| DAF suite | **298 passed** (289 prior + 9 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule cleanliness | `git status --short` clean |
| `mypy daf/` | Success, **44** source files |
| `ruff` | `UP006`/`UP035`/`UP045` only — repo-wide conventions already carried 100/53/28 times across `daf/`; new modules match their neighbours |
| Live run | real API, 240 observations, ids matching the fixture replay |

No existing test was weakened, skipped or deleted. No existing adapter, extractor
or binding was modified — `noaa_water_level_binding` and its extractor are
untouched.

---

## 13. Limitations

1. **One source, one station, one day.** No claim of generality across scientific
   APIs is made or supported.
2. **The locator collision is documented, not fixed** (§6).
3. **240 measurements, not 5–50** (§7) — floor imposed by the adapter's day-granular
   window.
4. **The preliminary→verified transition is documented and evidenced, not
   executed** (§4). Both states are committed as real fixtures; the same-timestamp
   transition would require waiting weeks for NOAA's QC pipeline.
5. **No `ModelState` transition** — correctly, since NOAA is not an experiment (§11).
6. **Time-series inference remains outside the analysis layer** (§10).
7. **USGS Water Services was the semantically preferred source** and was
   unavailable (HTTP 503) throughout; NOAA is a strong second choice, not a
   fallback of convenience.

---

## 14. Next genuine frontier

The apparatus demonstrably ingests real scientific observations without corrupting
their semantics. Three candidates, in the order I would take them:

- **(a) Fix the locator collision** (§6). Small, concrete, fully specified above,
  and it removes a real correctness hazard now demonstrated with real data.
- **(b) A second, structurally different real source.** One source proves the path
  works; two would test whether the field-classification discipline of §2–§3
  generalises or was tuned to NOAA. USGS Water Services, if it returns.
- **(c) Time-series semantics.** The honest gap §3/§10 identify: the comparison
  machinery answers "do these agree?" but nothing answers "how does this evolve?".
  This is a genuine scientific-representation question, and notably it is *not* on
  the deferred list — unlike expected-information-gain.

**Expected information gain remains deferred** and untouched, as §12 requires. It
should not begin without an explicit decision that the deferral has ended.

---

*Phase Q halts here: investigated, selected, audited, implemented, run live,
measured, defect found and pinned, validated, documented, committed and pushed.*
