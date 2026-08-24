# SCOUT Live Ingestion — Vertical Slice

**Status:** implemented and passing. This is DAF Phase A/first-slice work,
per `docs/ARCHITECTURE_RECONNAISSANCE.md` section 19's phased sequence:
proving the existing SCOUT admission contract can ingest one real,
permitted external source end-to-end, before industrializing acquisition
at scale.

**Scope decision:** this implementation lives entirely inside
`Data-Acquisition-Fabric`, on `daf/`, with the existing State-Space
repository (`notationsystems/scout-retrieval-agent`) vendored, read-only,
as a pinned git submodule at `vendor/scout-retrieval-agent`. No file in
that submodule was modified. This repo has push access; the upstream
repo does not, and the user explicitly chose the "Data-Acquisition-Fabric
only" scope for this phase.

---

## Pre-implementation report

### 1. Current SCOUT contract

`scout/interface.py` (vendored, unmodified) defines three Protocol/value
stages:

```python
@dataclass(frozen=True)
class RawDocument:
    source_name: str
    source_kind: str
    content: str
    locator: str
    retrieval_method: str
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock

class SourceAdapter(Protocol):
    def fetch(self) -> Tuple[RawDocument, ...]: ...

@dataclass(frozen=True)
class ExtractionCandidate:
    content: Mapping[str, object]
    entities: Tuple[ExtractedEntity, ...]
    relations: Tuple[ExtractedRelation, ...]
    extraction_method: str
    confidence: Optional[float]  # MUST be non-None when extraction_method starts "model:"

class Extractor(Protocol):
    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]: ...
```

Before this work, the only implementations were fixture-based:
`scout.adapters.FixtureSourceAdapter` (returns a hardcoded tuple) and
`scout.extraction.DeterministicExtractor` (a regex parser over a fixed
`ENTITY:`/`RELATION:`/`FACT:` line format). No live network access existed
anywhere in the vendored repo.

### 2. Current evidence path

`scout.pipeline.run_scout(adapter, extractor, pool)` sequences, unmodified:

```
adapter.fetch() -> RawDocument*
  -> make_source / pool.put_source
  -> make_document -> admit_document -> pool.put_document
  -> make_record   -> admit_record   -> pool.put_record
  -> extractor.extract(record) -> ExtractionCandidate*
       -> make_observation -> admit_observation -> pool.put_observation
       -> per entity: make_referent -> admit_referent -> pool.put_referent
       -> per relation: make_claimed_relationship -> admit_claimed_relationship
                         -> pool.put_claimed_relationship
```

Every write is preceded by a successful `admit_*` call
(`evidence/admission.py`) — there is no path in `run_scout` that calls a
`pool.put_*` mutator without one. Admission failures are collected as
`ScoutAdmissionFailure` objects and returned, never raised.

### 3. Selected test source

**arXiv** (`https://export.arxiv.org/api/query`), chosen against the
task's own criteria: public, no authentication, stable (a permanent
public API), structured (Atom XML), deterministic enough to test (a
fixed arXiv id returns the same paper), no browser automation, and
directly representative of the "scientific literature" domain the
existing `materials/` State-Space model already consumes (its own
fixtures are simulated journal-paper excerpts). Confirmed reachable from
this environment (`curl https://export.arxiv.org/api/query?id_list=1706.03762`
→ HTTP 200) before committing to it.

### 4. Adapter design

`daf/adapters/arxiv.py::ArxivSourceAdapter` — a frozen dataclass
implementing `SourceAdapter` structurally (no inheritance needed; the
Protocol is duck-typed, matching how `FixtureSourceAdapter` already does
it). Responsibilities, matching exactly what the task scoped an adapter
to own:

- Source access: builds a deterministic query URL from `arxiv_ids` and
  performs one HTTPS GET (`urllib.request`, stdlib only — no new
  dependency, matching the vendored repo's own `dependencies = []`
  discipline).
- Retrieval: `fetch_bytes` is injectable (`Callable[[str], bytes]`),
  defaulting to a real network call — this is what makes the pipeline
  testable without a live network dependency in CI while still proving
  live integration when run for real.
- Source metadata / retrieval timestamp: `source_name="arXiv"`,
  `source_kind="paper"`, `retrieval_method="http:arxiv_api_v1"`,
  `retrieved_at` always caller-supplied (never wall-clock), matching
  every other `RawDocument.retrieved_at` in the vendored repo.
- Raw content: each `<entry>` in the Atom response becomes exactly one
  `RawDocument`, whose `content` is that entry's own **raw substring**
  from the response — not a reparsed/re-serialized XML tree — so it is
  byte-identical to what arXiv actually sent, and re-fetching an
  unrevised paper reproduces identical content.
- Deterministic acquisition identity: delegated entirely downstream, to
  `evidence.types.make_document`/`make_record` — the adapter assigns no
  id of its own, per `RawDocument`'s own "pre-identity" contract.
- Failure reporting: acquisition failures (network errors, malformed
  responses, an entry with no `<id>`) are raised as exceptions
  (`ArxivFetchError` for parse-level failures; underlying `OSError`
  subclasses for network failures) rather than returned as empty/partial
  results — failures must be visible, never silently swallowed.

It does **not**: decide canonical truth, construct `ModelState` or
`CanonicalState`, decide predictive variables, or do any indexing —
verified by an AST-level import check (see Validation below).

### 5. Extractor design

`daf/extractors/arxiv.py::ArxivExtractor` implements `Extractor`
structurally. Purely deterministic XML parsing (stdlib
`xml.etree.ElementTree`) of the raw `<entry>` fragment stored on the
`Record` — no model involved, so `extraction_method =
"xml:arxiv_atom_v1"` never starts with `"model:"` and the mandatory-
model-confidence rule in `run_scout` does not apply; `confidence` is
fixed at `1.0`, exactly the reasoning `DeterministicExtractor` already
uses for its own fixed `1.0`.

`content` is an open, extraction-defined mapping — `{arxiv_id, title,
summary, published, updated, primary_category}` — no new normalized-
record ontology invented; this is the same open-`Mapping` shape every
other `Observation.content` in the vendored repo already uses.
`entities`/`relations` produce one `paper` entity (natural key = the
arXiv entry id) and one `author` entity per listed author, connected by
an `authored_by` relation — using the existing `ExtractedEntity`/
`ExtractedRelation` shapes verbatim.

### 6. Admission path

Unchanged. `run_scout` is called directly, with real `ArxivSourceAdapter`/
`ArxivExtractor` instances substituted for the fixture-based ones — no
DAF-specific admission function, gate, or shortcut was written or would
even compile without importing the real `evidence.admission` gate.

### 7. Identity strategy

Fully delegated to the existing `evidence.identity.content_hash` scheme —
the adapter and extractor never compute or assign an id. Verified
directly by test (`test_admission_never_bypasses_existing_identity_computation`):
the admitted `Observation.id` is independently recomputed via the exact
same `content_hash({record_ids, extraction_method, content})` payload
`evidence.types.make_observation` itself builds, and matches exactly.

Because `Source` identity is `content_hash({kind, name})` — independent
of document content — every arXiv paper acquired converges on the same
one `Source` record (`kind="paper", name="arXiv"`), exactly matching the
existing design intent ("two documents from the same place converge on
one Source").

### 8. Provenance strategy

No new provenance type. The full chain
`Observation.record_ids -> Record.document_id -> Document.source_id ->
Source` is exactly the vendored repo's own existing provenance chain,
walked and asserted directly in
`test_provenance_survives_the_complete_pipeline` — nothing is flattened
into a string and no acquisition metadata is lost between raw acquisition
and admitted evidence.

### 9. Downstream State-Space boundary

The vertical slice stops at `run_scout`'s return value
(`Tuple[ScoutFinding, ...]`, `Tuple[ScoutAdmissionFailure, ...]`).
Nothing in `daf/` imports `materials`, `experiment`, `workbench`, `core`,
`morpho`, `backends`, or `runtime` — enforced by an AST-level test
(`test_adapter_and_extractor_never_reference_the_state_space_domain_layers`),
matching the vendored repo's own `tests/test_scout_boundaries.py` style.
No `ModelState`, no state resolution, no predictive-variable decision is
made anywhere in this slice.

### 10. Known workbench bypass (documented, not touched)

Confirmed by direct code reading during the earlier architecture
reconnaissance: `workbench/interaction.py::bootstrap_default_scenario`/
`bootstrap_research_scenario` construct their own `EvidencePool` and call
`make_source`/`admit_document`/`admit_referent`/etc. **directly**,
satisfying the same `evidence.admission` gate SCOUT uses but never
calling `scout.pipeline.run_scout` at all. `run_scout` is, today,
invoked only by its own test suite in the vendored repo — no production
code path in that repo calls it.

**Why this phase leaves it untouched:** this is a change to
`workbench/interaction.py`, a file inside `scout-retrieval-agent` — a
repository this session does not have push access to, and the user
explicitly scoped this phase to `Data-Acquisition-Fabric` only (see
"Scope decision" above). It is also not "small and clearly safe" in the
sense the task asked for: the workbench's bootstrap functions build
*synthetic, hand-crafted* fixture scenarios for interactive/demo use
(specific referents, specific claimed relationships, chosen to exercise
specific `materials/` decision paths) — routing them through
`run_scout(FixtureSourceAdapter(...), DeterministicExtractor(), pool)`
would require first expressing every one of those hand-crafted scenarios
as `RawDocument`/fixture text in SCOUT's line-oriented extraction format,
which is a real (if mechanical) piece of work, not a one-line change, and
touches a repository outside this phase's scope.

**Smallest future change identified:** rewrite `bootstrap_default_scenario`/
`bootstrap_research_scenario`'s admission calls as one or more
`scout.fixtures`-style `RawDocument` fixtures fed through
`run_scout(FixtureSourceAdapter(fixtures), DeterministicExtractor(), pool)`,
inside `scout-retrieval-agent` itself. This is recorded here as a
follow-up recommendation, not implemented in this phase.

### 11. Future DAF extension points (not built, deliberately)

- **Durable storage** underneath `EvidencePool` (still fully in-memory in
  this slice — `acquire_arxiv_papers`/the tests all construct a fresh
  `EvidencePool()`; nothing persists past one process).
- **Acquisition scheduling/policy** — this slice is invoked directly
  (`python -m daf.vertical_slice <arxiv_id>...`), on demand; no scheduler
  exists.
- **`evidence.fep_interface.FEPSignal.expected_information_gain` /
  `retrieval.seam.InquirySeam`** — confirmed still unimplemented upstream
  (re-checked against the current submodule pin,
  `3e5bea973d0e801eadfb9d472aa3d07c930616c3`, "Phase 102"). No caller was
  added for `InquirySeam` in this phase, per the task's explicit
  instruction not to invent one yet.

---

## Post-implementation report

### 1. Files changed

All new files; nothing pre-existing was modified.

```
.gitmodules                                              (new)
vendor/scout-retrieval-agent                              (new git submodule, pinned commit)
pyproject.toml                                            (new)
conftest.py                                               (new)
daf/__init__.py                                           (new)
daf/_vendor.py                                            (new)
daf/adapters/__init__.py                                  (new)
daf/adapters/arxiv.py                                     (new)
daf/extractors/__init__.py                                (new)
daf/extractors/arxiv.py                                   (new)
daf/vertical_slice.py                                     (new)
tests/fixtures/arxiv_single_entry_v1.xml                  (new)
tests/fixtures/arxiv_single_entry_v1_revised.xml          (new)
tests/fixtures/arxiv_two_entries.xml                      (new)
tests/fixtures/arxiv_entry_missing_id.xml                 (new)
tests/test_arxiv_adapter.py                               (new)
tests/test_arxiv_extractor.py                             (new)
tests/test_vertical_slice.py                              (new)
docs/SCOUT_VERTICAL_SLICE.md                              (new, this file)
```

### 2. Adapter/extractor added

`daf.adapters.arxiv.ArxivSourceAdapter` (real `SourceAdapter`) and
`daf.extractors.arxiv.ArxivExtractor` (real `Extractor`), both against
the public arXiv API, as designed above.

### 3. Exact evidence path (as actually exercised by the tests)

```
real arXiv API (or an injected fixture byte-string, for deterministic tests)
  -> ArxivSourceAdapter.fetch() -> RawDocument (one per <entry>)
  -> scout.pipeline.run_scout (UNMODIFIED)
       -> evidence.types.make_source/make_document/make_record
       -> evidence.admission.admit_document/admit_record (UNMODIFIED gate)
       -> ArxivExtractor.extract(record) -> ExtractionCandidate
       -> evidence.types.make_observation/make_referent/make_claimed_relationship
       -> evidence.admission.admit_observation/admit_referent/admit_claimed_relationship (UNMODIFIED gate)
       -> evidence.pool.EvidencePool.put_* (UNMODIFIED)
  -> ScoutFinding (source, document, record, observation, referents, relationships, ...)
```

### 4. Tests added

19 tests across three files, covering every one of the 10 required
properties (see inline docstrings/comments in the test files naming
which property each test proves) plus two additional structural tests
(multi-entry parsing, rejection of non-entry content):

- `tests/test_arxiv_adapter.py` — 6 tests (including one live network test)
- `tests/test_arxiv_extractor.py` — 4 tests
- `tests/test_vertical_slice.py` — 9 tests (the end-to-end admission-gate,
  provenance, identity, dedup/versioning, and boundary properties)

### 5. Validation results

```
$ pytest tests/ -v          -> 19 passed (including the live arXiv network test)
$ pytest (vendored repo)    -> 1273 passed, 0 failed, 0 modified  -- no regressions
$ ruff check daf/ tests/ conftest.py    -> All checks passed!
$ mypy daf/                              -> Success: no issues found in 7 source files
```

The live network test (`test_live_fetch_against_the_real_arxiv_api`) was
confirmed to actually exercise the real, live `export.arxiv.org` API
during this run — it is written to `pytest.skip()` cleanly on an `OSError`
so CI without network access degrades gracefully rather than failing.

### 6. Remaining bypasses

The interactive-workbench bypass documented in section 10 above remains
unaddressed — it lives in `scout-retrieval-agent`, out of this phase's
scope, and is recorded as a follow-up rather than silently left
undocumented.

### 7. Limitations

- `EvidencePool` remains fully in-memory; nothing acquired by this slice
  survives past one Python process (as designed for this phase — see
  `docs/ARCHITECTURE_RECONNAISSANCE.md` section 12).
- The vendored repo is consumed via a git submodule + `sys.path`
  injection (`daf/_vendor.py`), not a real package install, because
  `scout-retrieval-agent`'s own `pyproject.toml` has no `[build-system]`
  table. Its top-level package names (`evidence`, `scout`, `core`, etc.)
  are generic enough to risk collision in a larger environment — flagged
  in `daf/_vendor.py`'s own docstring.
- The `<entry>`-boundary extraction in `ArxivSourceAdapter` uses a regex
  over the raw response text rather than a namespace-aware XML parse, to
  guarantee byte-identical raw content preservation; this assumes arXiv's
  Atom output never contains a literal, unescaped `<entry>`/`</entry>`
  substring inside escaped text (true for well-formed XML, where such
  characters are always escaped as `&lt;`/`&gt;`).
- Only one source (arXiv) and one extraction method were built, exactly
  per the task's "ONE source only" instruction.

### 8. Recommended next phase

Per `docs/ARCHITECTURE_RECONNAISSANCE.md` section 19: **Phase B,
industrialize acquisition** — durable storage underneath `EvidencePool`
first (the current single biggest limitation — nothing acquired survives
a process restart), then additional domain adapters proving the evidence
substrate stays domain-agnostic (no new fields needed in `evidence.types`
to accommodate a second domain), then minimal scheduling. The
information-gap-driven acquisition loop (`FEPSignal.expected_information_gain`,
`InquirySeam`) should remain out of scope until a real
`InformationValueModel` implementation and a durable, multi-source
evidence substrate both exist.
