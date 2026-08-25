# Phase F — DAF Domain Acquisition Reconnaissance and Adapter Architecture

**Status:** reconnaissance complete. **Zero changes to `daf/` production
code this phase.** One test file added, proving (not asserting) the
single real nuance this investigation surfaced is already expressible
with existing Phase A–E primitives.

**Governing question:** what acquisition semantics are actually common
across the domains the DAF intends to industrialize, and where — if
anywhere — does the current architecture (`SourceDefinition`,
`SourceAdapter`, `Extractor`, `AdapterBinding`, `AcquisitionPlan`,
`AcquisitionRequest`, `AcquisitionCheckpoint`, `AcquisitionOrchestrator`,
`DurablePool`, `ArtifactStore`) actually fall short?

**Headline finding:** it doesn't fall short anywhere investigated. Ten
domains, roughly twenty representative source patterns, and the
requested fourteen-question checklist all resolve to **two** acquisition
semantics at the orchestration level — SNAPSHOT and INCREMENTAL — both
already fully implemented and proven (Phases A, C, E). Every other
category the task asked me to consider (EVENT, VERSIONED, IDENTIFIER,
BULK, TIME-WINDOW) turned out to be a **usage mode** of one of those two,
not an independent primitive. One genuine nuance surfaced (late-arriving/
out-of-order incremental data) and is resolved by an **adapter-level
idiom**, not a core abstraction change — proven with one new test, zero
new production code.

---

## 1–2. Domains investigated and representative source patterns

For each domain, the representative patterns actually used in practice
(not hypothetical):

| Domain | Representative patterns |
|---|---|
| Scientific literature | Query/identifier API (arXiv, PubMed, Crossref); git-style repository (commit-addressed, natively content-hashed); periodic bulk archive (PubMed baseline+update XML, arXiv S3 bulk dataset) |
| Patents | Periodic bulk archive (USPTO/EPO weekly XML dumps); identifier/query API (PatentsView, EPO OPS); sequential publication-number stream (patents publish in numbered weekly batches) |
| Real estate | Listing feed with `ModificationTimestamp`-based sync (RETS/RESO Web API); identifier/query API; periodic bulk snapshot (county assessor rolls, published quarterly/annually) |
| Logistics/shipping | Per-shipment event log, re-fetched whole (container tracking APIs); tracking-by-identifier snapshot; high-frequency position stream (AIS vessel pings) |
| Commodities | Daily settlement time series (timestamp-keyed); bulk historical archive; tick-by-tick trade stream |
| Financial markets | EOD/intraday bar series (timestamp-keyed); bulk historical dataset; tick/quote stream with exchange-issued trade corrections |
| Derivatives | Instrument reference data (identifier snapshot, low churn); option-chain market data (timestamp-keyed); EOD historical archive |
| Corporate/regulatory filings | Daily filing index (SEC EDGAR full-text/daily-index — one new immutable index per day); individual filings, amendable (10-K/A amends a 10-K) |
| Industrial datasets | Per-device sensor telemetry (sequence/timestamp stream); periodic inspection/maintenance records (identifier snapshot) |
| Public datasets | Open-data portal "rows updated since T" (Socrata/CKAN-style); full bulk CSV/JSON download |

---

## 3. Architectural questions, answered per PATTERN (not per domain)

Patterns recur across domains far more than domain names suggest, so the
fourteen questions are answered once per pattern:

### Pattern: identifier/query snapshot (arXiv, PatentsView, tracking-by-id, instrument reference data)
- **Acquisition unit**: one externally-named object per identifier.
- **Source identity**: the API endpoint/config (`SourceDefinition`).
- **Artifact identity**: `(source_id, locator)` — locator = the external identifier. Already `ArtifactStore.artifact_id`.
- **Version identity**: content-hash of the fetched representation (`Document.id`). Already exists.
- **Mutability**: mutable — re-fetching the same identifier can return different content over time (a patent's PatentsView record gets enriched; a tracking record's status changes).
- **Acquisition mode**: SNAPSHOT (re-fetch by identifier; dedup by content-hash).
- **Cursor**: none needed — the identifier IS the addressing scheme.
- **Pagination**: only within one `fetch()` call if a query returns many identifiers (adapter-internal, invisible to the orchestrator).
- **Late/reorder/disappear**: a fetched-and-vanished identifier is invisible to the DAF (it simply isn't returned) — no special handling needed or possible without external replay capability the source itself would have to expose.
- **What's "new"**: any content-hash not already in `ArtifactStore`.

### Pattern: whole-file/whole-archive snapshot (local datasets, county rolls, bulk PubMed/USPTO archives, bulk CSV downloads)
- **Acquisition unit**: the whole published artifact (a file, or one row/record within it, adapter's choice).
- **Artifact identity**: `(source_id, locator)` where locator names the row/record, or the archive's own publication label if treated as one unit.
- **Version identity**: content-hash, exactly `daf.adapters.local_dataset`'s existing behavior.
- **Mutability**: immutable once published (each periodic publication is a new, distinct artifact) — this is the same shape whether "publication" means "county assessor Q3 roll" or "today's PubMed update file."
- **Acquisition mode**: SNAPSHOT. BULK is this pattern at larger scale — a scale/throughput property of the adapter's own I/O, not a different orchestration semantic.
- **Cursor**: none needed at the orchestration level (each publication is fully re-acquired and deduplicated by content-hash); an adapter MAY track "which publications have I already downloaded" internally as an optimization, but that is an internal adapter concern, not a DAF-core one.

### Pattern: cursor/timestamp/sequence incremental (RESO `ModificationTimestamp` sync, EDGAR daily index, commodities EOD series, sensor telemetry, patent publication-number stream)
- **Acquisition unit**: one changed/new object since a prior position.
- **Artifact identity**: `(source_id, locator)`, locator = the object's own identifier (a listing MLS#, a filing accession number, a sensor reading id).
- **Version identity**: content-hash, as always.
- **Mutability**: append-only from the DAF's perspective (a "changed since T" query only ever adds newly-visible content; whether the SOURCE mutates its own backing store is invisible and irrelevant to the DAF).
- **Acquisition mode**: INCREMENTAL. TIME-WINDOW is this pattern where `position` happens to be a timestamp string instead of a sequence number — the SAME opaque `Optional[str]` `AcquisitionCheckpoint.position` Phase E already defined, interpreted only by the adapter binding that produced it (`daf.orchestration.adapter_registry.AdapterBinding.advance_position`). No new field, no new type.
- **Cursor meaning**: adapter-defined and OPAQUE to the DAF core, exactly as designed in Phase E — a `ModificationTimestamp` cursor and a publication-sequence cursor are structurally identical to the checkpoint machinery; only the specific binding's `build_adapter`/`advance_position` pair knows which one it is.
- **Pagination/continuation token**: also just another shape of opaque position, OR (if a source uses a token only within one polling cycle, discarded once fully drained) purely an adapter-internal loop inside one `fetch()` call — never surfaces to the DAF core either way.
- **Can records arrive late / out of order**: **yes, for some of these sources** (see section 11 — this is the one real nuance).
- **Can the same logical object appear in multiple artifacts**: yes and by design — a listing that changes twice produces two distinct, coexisting artifacts under one `artifact_id`, exactly `ArtifactStore.list_versions`'s existing contract.
- **What's "new"**: anything with `locator`/content-hash not already durably persisted, exactly as today's `AcquiredArtifact.is_new`.

### Pattern: discrete event stream (shipment tracking events, tick data, high-frequency telemetry)
- **Acquisition unit**: one discrete event.
- Structurally: **this is the INCREMENTAL pattern at its finest granularity** — one event = one `RawDocument` = one `locator` (its own sequence/timestamp/event-id), exactly `daf.adapters.incremental_dataset`'s existing shape. EVENT is not a fourth category; it is INCREMENTAL where the "position" unit happens to be "one event" rather than "one batch of many records since T."
- The one architecturally distinct sub-question EVENT sources raise more sharply than others: **out-of-order/late delivery is the norm, not the exception**, for genuinely high-frequency or multi-producer event sources (see section 11).

### Pattern: versioned/amendable object (10-K vs. 10-K/A, a corrected trade, a re-issued patent claim)
- This is **not a fifth acquisition pattern** — it is a **content-hash identity question**, answered entirely at the storage layer, orthogonal to whether the object was acquired via SNAPSHOT or INCREMENTAL. See section 10.

---

## 4. Derived acquisition-semantics taxonomy

Only two acquisition semantics are needed at the orchestration level,
and both already exist:

| Category | Why needed | Representative source | Already supported by |
|---|---|---|---|
| **SNAPSHOT** | "give me the current state," relying on content-hash dedup to detect change | Identifier APIs, bulk archives, county rolls | `daf.adapters.arxiv`, `daf.adapters.local_dataset` (Phases A, C) |
| **INCREMENTAL** | "give me what's new since opaque position X" | Timestamp-sync feeds, sequence streams, event streams | `daf.adapters.incremental_dataset` + `AdapterBinding.advance_position` (Phase E) |

The five other categories the task asked me to test (EVENT, VERSIONED,
IDENTIFIER, BULK, TIME-WINDOW) are each a **usage mode**, not an
independent primitive:

- **IDENTIFIER** = a parameter shape within SNAPSHOT (`arxiv_ids` already works this way).
- **BULK** = SNAPSHOT at larger I/O scale — an adapter implementation concern, invisible to the orchestrator.
- **TIME-WINDOW** = INCREMENTAL where `position` is a timestamp string — already exactly what the opaque `position: Optional[str]` was designed for.
- **EVENT** = INCREMENTAL at one-event granularity — already exactly `incremental_dataset`'s shape.
- **VERSIONED** = a property of the durable storage layer (content-hash + `ArtifactStore.list_versions`), orthogonal to acquisition mode — already present regardless of whether acquisition is SNAPSHOT or INCREMENTAL.

No new top-level category survived investigation against real source
behavior.

---

## 5. Testing current DAF primitives against every investigated pattern

| Pattern | `SourceDefinition` | `SourceAdapter`/`Extractor` | `AcquisitionPlan`/`Request` | `AcquisitionCheckpoint` | `DurablePool`/`ArtifactStore` |
|---|---|---|---|---|---|
| Identifier/query snapshot | sufficient | sufficient (`arxiv` proves it) | sufficient | not needed (`mode="snapshot"`) | sufficient |
| Whole-file/bulk snapshot | sufficient | sufficient (`local_dataset` proves it) | sufficient | not needed | sufficient |
| Timestamp/sequence incremental | sufficient (`capabilities=("incremental",)` already exists) | sufficient (`incremental_dataset` proves it) | sufficient (`mode="incremental"` already exists) | sufficient (opaque `position` already exists) | sufficient |
| Discrete event stream | sufficient | sufficient (same as incremental) | sufficient | sufficient | sufficient |
| Versioned/amendable object | sufficient | sufficient (no new field needed) | sufficient | n/a | sufficient (`list_versions` already exists) |

**Every row says "sufficient." No abstraction is added this phase, per
the task's own instruction: "If yes: DO NOT add an abstraction."**

---

## 6. Domain independence test

Already true and already enforced by existing tests, re-confirmed here
rather than re-built: `SourceDefinition.domain` is a free-form label
`daf.orchestration.orchestrator`/`daf.scheduling.*` never branch on
(AST-verified since Phase C:
`tests/test_acquisition_orchestrator.py::test_orchestrator_never_imports_domain_specific_adapter_modules`,
extended in Phase D/E to `daf.catalog.*`/`daf.scheduling.*`). Adding a
real "materials," "commodities," or "real-estate" source would mean
writing one adapter + one extractor + one `SourceDefinition` +
optionally one `AdapterBinding` in `daf.orchestration.bindings` — never
touching `daf.orchestration.orchestrator`, `daf.scheduling.*`, or
`daf.catalog.plan`. No domain-name branch could even compile in the
orchestration core, because it has no way to import a domain-specific
type in the first place.

---

## 7. Adapter contract review

`SourceAdapter{fetch() -> Tuple[RawDocument,...]}`, `Extractor{extract(record) -> Tuple[ExtractionCandidate,...]}`,
and `AdapterBinding{build_adapter, build_extractor, advance_position}`
are sufficient for every capability tested:

| Capability | Where it lives | Already sufficient? |
|---|---|---|
| Snapshot acquisition | `SourceAdapter.fetch()` returns everything requested | Yes (`arxiv`, `local_dataset`) |
| Incremental acquisition | `AcquisitionRequest.parameters["since"]` + `AdapterBinding.advance_position` | Yes (`incremental_dataset`) |
| Pagination | Internal to one adapter's `fetch()` call — loop over pages, concatenate, return once | Yes — never needs to surface past the adapter |
| Cursor advancement | `AdapterBinding.advance_position`, opaque `position` | Yes |
| Time-window acquisition | Same opaque `position`, adapter interprets it as a timestamp | Yes |
| Identifier acquisition | `AcquisitionRequest.parameters` (open mapping, e.g. `arxiv_ids`) | Yes |
| Event-like acquisition | One `RawDocument` per event, `locator` = event id/sequence | Yes (`incremental_dataset`'s existing shape) |

**No protocol expansion is justified.** Nothing tested requires a new
method on `SourceAdapter`/`Extractor`, a new field on `AdapterBinding`,
or a new field on `AcquisitionPlan`/`AcquisitionRequest`/`AcquisitionCheckpoint`
beyond what Phases C–E already added.

---

## 8. Extraction vs. acquisition vs. evidence admission vs. state projection

Confirmed intact, not re-designed:

```
ACQUISITION        "how do I obtain the external artifact?"        SourceAdapter.fetch()
        |                                                          [daf/adapters/*, DAF-owned]
        v
EXTRACTION         "how do I turn it into candidates?"             Extractor.extract()
        |                                                          [daf/extractors/*, DAF-owned]
        v
EVIDENCE ADMISSION "how does SCOUT admit it?"                      evidence.admission (UNMODIFIED,
        |                                                          vendored State-Space repo)
        v
STATE PROJECTION   "how does a downstream model interpret it?"     materials.model_state / a future
                                                                    MarketState, etc. -- NEVER the DAF
```

No source pattern investigated required collapsing any of these. A
market feed's transport (HTTP/websocket bytes), its financial semantic
extraction (what fields mean "price," "volume"), Evidence
(`evidence.types.Observation`), and a hypothetical `MarketState` remain
four distinct layers, exactly as the DAF's existing architecture
already keeps `daf.adapters.arxiv` (transport) separate from
`daf.extractors.arxiv` (extraction) separate from `evidence.admission`
(vendored, untouched) separate from `materials.model_state` (never
imported by anything in `daf/`).

---

## 9. Raw artifact requirement per source class

Every pattern investigated preserves original bytes, retrieval
metadata, source identity, version identity, and content hash without
modification — this was true before Phase F and remains true:

- **Identifier/query snapshot**: `RawDocument.content` = the raw response body for that identifier (`daf.adapters.arxiv` already stores the raw `<entry>` XML fragment verbatim, not a reparsed tree).
- **Whole-file/bulk snapshot**: `RawDocument.content` = the raw record/row exactly as published (`daf.adapters.local_dataset` already does this).
- **Incremental/event streams**: **the persisted raw artifact is one `RawDocument` per discrete unit returned by one `fetch()` call** — for `incremental_dataset`, one JSON record per event; for a hypothetical tick-data adapter, one tick per `RawDocument`. **The DAF never converts a stream into a semantic database**: each unit is preserved as its own immutable, content-addressed `Document`/`Record`, exactly the same discipline as a snapshot source's per-record artifacts — there is no separate "streaming" storage model, because there is no separate "streaming" acquisition model (see section 4).

---

## 10. Correction/revision semantics

Investigated precisely for markets (busted-trade corrections), filings
(10-K/A amending a 10-K), and real estate (listing price/status
updates). **Existing identity is sufficient in every case — no
deficiency found:**

- A **revision of the same logical object** (a listing's price changes,
  a sensor reading gets recalibrated) is, from the DAF's point of view,
  simply new content at the same `locator` → a new `Document.id` → a
  new, coexisting version under the same `artifact_id` → exactly
  `ArtifactStore.list_versions`'s existing, tested contract (proven
  since Phase B: "changed content is distinguishable as a new version").
- An **explicit correction referencing a prior object** (a busted-trade
  message naming the original trade id; a 10-K/A naming the original
  10-K's accession number) is, from the DAF's point of view, simply a
  **new artifact at a new locator** (the correction's own id), whose
  `content` happens to include a field like `"corrects": "<original-id>"`
  — an ordinary, open, extraction-defined content field, no different
  in kind from any other field `Extractor.extract()` already produces.
  **The DAF's job is only to preserve both the original and the
  correction as distinct, immutable, verbatim artifacts — which the
  existing append-only, content-addressed evidence pool already
  guarantees by construction.** Interpreting "this corrects that" as a
  scientific claim (e.g., materializing a `ClaimedRelationship`, or
  deciding which value a downstream model should trust) is squarely
  scientific/evidence-layer interpretation, out of the DAF's boundary
  per section 16 — and appropriately so, since two different downstream
  consumers might legitimately disagree about how to interpret the same
  correction (one analysis might want the original, another the
  corrected value; that is not the DAF's decision to make).

**Conclusion: identity does not need to be redesigned.** No real
deficiency was found in this investigation.

---

## 11. Late data — the one genuine nuance

This is the one place the investigation surfaced something worth
respecting carefully rather than waving away.

**The finding**: for genuinely multi-producer or high-frequency
INCREMENTAL/EVENT sources (tick data across multiple exchange feeds,
distributed IoT telemetry, occasionally MLS sync across multiple broker
back-ends), records can legitimately arrive at the DAF **out of the
order their own sequence/timestamp implies**, due to producer clock
skew, network delay, or multi-writer fan-in upstream of the source's own
API. `timestamp = acquisition order` **cannot be assumed** — exactly the
task's own warning.

**Why this is not a missing DAF primitive**: `AcquisitionCheckpoint.position`
is already opaque, and `AdapterBinding.advance_position` already
receives every `AcquiredArtifact` from the current run plus the previous
position — nothing about its existing signature prevents a binding from
computing a **conservative** next position instead of the naive maximum.
The correct, well-known pattern (used by real streaming systems under
the name "watermark with a trailing grace window") is entirely an
**adapter-level idiom**:

```
naive (what daf.orchestration.bindings.incremental_dataset_binding does today):
    new_position = max(sequence seen this run)

late-arrival-tolerant variant (an adapter/binding choice, NOT a DAF-core change):
    new_position = max(sequence seen this run) - SAFETY_WINDOW
```

Combined with the ALREADY-EXISTING, content-addressed, idempotent
deduplication (Phases A/B), re-requesting a trailing window of
already-seen positions on every run is entirely safe: previously-seen
records come back as `DUPLICATE`/`is_new=False`, and any record that
arrived late — with a sequence number inside that trailing window — is
captured on the next poll instead of being silently and permanently
lost.

**Proven, not just asserted**: `tests/test_late_arrival_safety_window.py`
(new this phase, no production code changed) demonstrates both halves
of this claim directly: a naive `advance_position` permanently loses a
record that arrives after the checkpoint has advanced past its
position, while a safety-window `advance_position` — built entirely
from existing primitives, in the test itself — correctly captures it on
the very next run, with zero duplication of already-seen records.

**Verdict**: no change to `AcquisitionCheckpoint`, `AdapterBinding`, or
`AcquisitionOrchestrator` is justified. This is documented here as
required guidance for any future adapter targeting a source with this
property, not as a gap to close.

---

## 12. Acquisition normalization: transport vs. semantic

`scout.interface.RawDocument{source_name, source_kind, content, locator,
retrieval_method, retrieved_at}` (vendored, unmodified since Phase A) is
already the DAF's transport-normalization boundary — every adapter
investigated or built (arXiv's XML, a local JSON file, an incremental
JSON stream) converges on this one shape regardless of how different
their actual transport mechanics are (HTTP GET vs. filesystem read).
**No new normalization layer is needed or justified**: this already *is*
"one common transport-level normalized form before SCOUT," exactly what
the task asked whether the DAF needed. Semantic normalization (what the
bytes mean) stays entirely inside `Extractor.extract()`, per-adapter,
exactly as `daf.extractors.local_dataset` (zero semantic interpretation
beyond JSON parsing) and `daf.extractors.arxiv` (entity/relation
extraction) already demonstrate two very different amounts of semantic
work behind the identical `RawDocument`/`ExtractionCandidate` contract.

---

## 13. Source capability matrix

| Source type (representative) | snapshot | incremental | cursor | pagination | sequence | timestamp | revision | event | identifier lookup | bulk | correction | late arrival |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Scientific literature API (arXiv-like) | supported | unsupported | — | adapter-specific | — | — | supported* | — | supported | — | supported* | unsupported |
| Bulk archive (PubMed/USPTO-style) | supported | unsupported | — | adapter-specific | — | — | supported* | — | — | supported | supported* | unsupported |
| Real-estate listing feed (RESO-style) | supported | supported | supported | adapter-specific | — | supported | supported* | — | supported | — | supported* | adapter-specific |
| Logistics tracking (per-shipment) | supported | unsupported† | — | adapter-specific | — | — | supported* | supported† | supported | — | — | unsupported |
| Commodities/markets tick data | unsupported‡ | supported | supported | adapter-specific | supported | supported | supported* | supported | — | — | supported* | adapter-specific |
| Corporate filings (EDGAR-style) | supported | supported | supported | adapter-specific | — | supported | supported* | — | supported | supported | supported* | unsupported |
| Industrial telemetry | unsupported‡ | supported | supported | adapter-specific | supported | supported | supported* | supported | supported | — | — | adapter-specific |

`supported` = directly expressible with existing primitives, no gap.
`supported*` = supported at the storage layer (`ArtifactStore.list_versions`)
regardless of acquisition mode. `adapter-specific` = the DAF core is
correctly indifferent; whether a given real API happens to expose the
capability determines whether that adapter implements it. `unsupported†`
= not the natural fit for this pattern (a per-shipment poll is naturally
a snapshot of an append-only event list, not a discrete-event feed,
though the latter is possible if the source is high-frequency enough to
warrant it). `unsupported‡` = would be architecturally *possible*
(nothing prevents a snapshot-mode tick adapter) but throws away the
point of the source (a full snapshot of years of tick data on every
poll is not what any real system does) — the pattern itself rules it
out, not the DAF.

**Which capabilities belong in the DAF core**: exactly the two already
there — SNAPSHOT and INCREMENTAL (opaque position). Every other column
in this matrix is either a storage-layer property already present
(`revision`), an adapter-internal implementation detail invisible to
the orchestrator (`pagination`, `bulk`), a specific interpretation of
the existing opaque position (`cursor`, `sequence`, `timestamp`,
`event`), a request-parameter shape (`identifier lookup`), a
content-field convention with no orchestration effect (`correction`),
or an adapter-level idiom requiring no core change (`late arrival`).

---

## 14–15. Implementation

Per this phase's own instruction ("If yes: DO NOT add an abstraction")
and the fact that every row in sections 5 and 13 resolved to "already
sufficient": **no new adapters, no new domain packages, no protocol
changes, no new catalog/checkpoint/orchestrator fields.** The three
existing prototype adapters (`arxiv`: identifier/snapshot;
`local_dataset`: whole-file/snapshot; `incremental_dataset`: sequence/
incremental) already span the two real acquisition semantics this
investigation confirmed are the only ones that exist at the
orchestration level — a fourth or fifth prototype would not validate
anything new.

The one artifact of this phase is a single **test** (not a new adapter,
not new production code) proving section 11's claim empirically:
`tests/test_late_arrival_safety_window.py`.

---

## 16. DAF boundary — unchanged

Confirmed, not re-litigated: the DAF owns acquisition, source
configuration, planning, scheduling, checkpoints, raw artifact
persistence, acquisition metadata, replay, adapters, and orchestration.
It does not own scientific ontology, evidence semantics, canonical
research state, `ModelState`, prediction, geometry, learned latent
state, GraphRAG semantics, FEP, information gain, or agent policy —
every domain investigated confirmed this boundary holds without strain
(see section 10's correction analysis in particular: even the most
"scientifically loaded"-seeming case, a busted-trade correction,
resolves cleanly into "the DAF preserves both artifacts verbatim; a
downstream system decides what they mean").

---

## Post-investigation validation

```
$ pytest tests/ -q          -> 139 passed (137 existing + 2 new)
$ pytest (vendored repo)    -> 1273 passed, 0 failed, 0 modified
$ ruff check daf/ tests/ conftest.py    -> All checks passed!
$ mypy daf/                              -> Success: no issues found
```

## Recommended Phase G

Per the task's own framing, Phase F's job was reconnaissance, and it
concluded the DAF core needs no extension to industrialize the
investigated domains. The natural next real step is therefore not
architectural but operational: implement ONE additional REAL adapter
(not a deterministic local prototype) against an actual external source
in a domain the user cares about first (materials literature, real
estate, or commodities are all now equally well-supported by the
existing primitives) — proving the architecture against a genuine
integration, not another synthetic fixture. The FEP/information-gain
acquisition-request loop and the separate Rust/zkVM/Morpho/CUDA
execution plane remain untouched and out of scope, as in every prior
phase.
