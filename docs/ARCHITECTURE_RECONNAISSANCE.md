# Data Acquisition Fabric — Architecture Reconnaissance & Integration Specification

**Status:** architecture-first reconnaissance. No DAF code, packages, databases, or
infrastructure are implemented by this document. Nothing in the existing
State-Space repository is modified.

**Scope:** determine the boundary between an eventual Data Acquisition Fabric
(DAF) and the existing State-Space system, grounded in the actual source code
of `notationsystems/scout-retrieval-agent` (hereafter "the SSA repo"), at
commit `d43a569` ("Phase 101: coordinate / fiber architecture audit").

**Method:** four independent code-reading passes over the SSA repo (materials/
canonical layer, evidence/Morpho layer, SCOUT/retrieval/orchestration layer,
and the full `docs/` tree), cross-checked against each other and against
direct reads of the highest-decision-weight files
(`materials/model_state.py`, `retrieval/seam.py`, `evidence/__init__.py`,
`docs/ARCHITECTURE.md`). Code is treated as authoritative; where a doc and the
code seemed to disagree, the code's own docstrings (which this repo uses as a
living engineering log) were trusted.

---

## 0. The single most important finding, stated up front

**The SSA repo contains two structurally similar but functionally unrelated
architectures that never import each other, in either direction:**

| | Track 1 — "Frozen Specification v1.0.0" | Track 2 — Materials-discovery evidence system |
|---|---|---|
| Packages | `core/canonical`, `core/projection`, `morpho`, `backends/*`, `runtime`, `adapters` | `evidence`, `scout`, `retrieval`, `materials`, `experiment`, `workbench` |
| Domain | A deterministic 3D-scene / digital-twin compiler: canonical state → schema validation → projection → Morpho HDL → Three.js/SVG/graph-analysis backends, with a simulation/neural feedback loop bolted on | Materials-science evidence reasoning: literature/repo mining → evidence pool → trust graph → retrieval → predictive `ModelState` → experiment design/decision loop |
| State type | `CanonicalState` / `Version` (single-head, `validate_candidate`-gated) | `EvidencePool` (append-only, multi-head) and, downstream of it, `materials.model_state.ModelState` (a third, separate state type) |
| Doc home | `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE_SPEC.md`, `docs/CONTRADICTIONS.md`, `docs/DATA_CAPABILITIES.md` | `docs/PHASE_13_ARCHITECTURE_INVESTIGATION.md`, `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md`, `docs/SCOUT_ARCHITECTURE.md`, `docs/RETRIEVAL_ARCHITECTURE.md`, `docs/EXPERIMENT_ARCHITECTURE.md`, `docs/COMPUTATIONAL_COMMONS.md` |

This is stated explicitly in the repo's own `docs/ARCHITECTURE.md:43-61`: `evidence/`
and `scout/` "are also not part of the original frozen specification... never
reachable from `core.canonical` in either direction." The two tracks even
independently reinvent the same primitive (SHA-256 over canonical
sorted-key JSON) in two different modules
(`evidence/identity.py::content_hash`, `core/canonical/version.py::compute_version_id`)
without sharing code — a sign these were built as genuinely separate
subsystems, not a single system with an internal seam.

**Consequence for this task:** everything in the task prompt that names
`ModelState`, `Prediction`, "(formulation, property)", "Phase 53",
SCOUT/GraphRAG, and evidence/provenance concepts refers to **Track 2**. Track
1 is a different, unrelated project living in the same repository (a
digital-twin/3D-scene compiler) and is **not** the "State-Space architecture"
this task is integrating with. The DAF must integrate with Track 2. Track 1
is noted here only because its `adapters/` package is easy to mistake for the
DAF's job — it is not; see §8.

A second, load-bearing naming discipline appears throughout Track 2: several
concepts were deliberately renamed to avoid colliding with Track 1 names that
already existed in the same repo (`Entity`, `Relationship`, `Observation`).
Track 2 uses `Referent` (not `Entity`), `ClaimedRelationship` (not
`Relationship`), and has its own `evidence.types.Observation`, distinct from
an unrelated, interface-only `Observation` sketched in Track 1's frozen spec
§17. **The DAF must preserve this discipline** — it must not reintroduce
generic `Entity`/`Relationship`/`Observation` names that collide across
layers; see §16.

---

## 1. Existing architecture inventory

Track 2, module by module (this is the inventory the DAF must integrate
with):

| Package | Role |
|---|---|
| `evidence/` | Content-addressed, append-only pool of uncertain/conflicting evidence: `Source`, `Document`, `Record`, `Observation`, `Referent`, `ClaimedRelationship`, `DerivedValue`, `DerivedGrounding`. Its own admission gate (`evidence/admission.py`), its own identity scheme (`evidence/identity.py`), a derived trust graph (`evidence/trust_graph.py`), computed metrics (`evidence/metrics.py`), and an interface-only "FEP" (Free Energy Principle) signal (`evidence/fep_interface.py`). |
| `scout/` | The one implemented acquisition producer: `SourceAdapter`/`Extractor` Protocols, a `DeterministicExtractor` (regex-based, fixture-only), and `run_scout`, which admits new evidence into an `EvidencePool` through the admission gate. |
| `retrieval/` | Strictly read-only query layer over the evidence pool: `RetrievalQuery → RetrievalEngine (DeterministicRetrievalEngine, bounded BFS over the trust graph) → RetrievalResult → ContextPackage`, plus a deliberately unimplemented `InquirySeam` marking a future boundary. |
| `materials/` | The one existing domain-specific "state-space model": `ModelState`, `Prediction`, `predict`/`update`, plus ~25 supporting modules for candidate generation, selection, ranking, optimization, decision/gap-analysis, and information-value estimation. |
| `experiment/` | Sequencing/workflow layer above `materials/`: `ExperimentSession`, `ActionDispatcher` Protocol, `run_experiment_step`. Owns *no* new mathematics — only orchestration. |
| `workbench/` | The human-facing CLI/REPL that ties `evidence` + `retrieval` + `materials` + `experiment` together for interactive investigation. Notably, it does **not** use `scout/` — it hand-admits evidence directly (see §4). |
| `adapters/` (top-level) | Belongs to **Track 1**, not Track 2 — feeds `CandidateDelta` into `core.canonical.validate_candidate`. Structurally analogous to `scout/` but targets a different, unrelated state system. |

Both tracks share a house style worth naming explicitly, because the DAF
should adopt it: every domain object is an immutable, content-addressed
`@dataclass(frozen=True)`, constructed only via a `make_*` factory that
derives `id` from a canonical-JSON SHA-256 hash, never from a caller-supplied
value; identity hashes always exclude epistemic annotations (confidence,
timestamps, free text); and every subsystem boundary is enforced by an
AST-walking test that inspects real `import` statements, not a hand-maintained
list.

---

## 2. Existing State-Space architecture (`materials/model_state.py` and its
satellites)

### What is a state?

`ModelState` (`materials/model_state.py`):

```python
@dataclass(frozen=True)
class Sample:
    value: float
    observation_id: str

@dataclass(frozen=True)
class ModelState:
    id: str
    samples: Mapping[str, Tuple[Sample, ...]]
```

- **Not** a generic/universal state container. It holds, per *cell*, the full
  immutable list of `Sample`s observed so far for that cell — nothing is
  incrementally accumulated (no running mean/variance kept in the state
  itself); `predict` recomputes statistics on demand from the raw sample list.
- **Identity**: `ModelState.id = content_hash(...)` over every cell's
  sorted sample list (`evidence.identity.content_hash`, reused directly — no
  separate hashing system was invented for this layer). Two independently
  constructed `ModelState`s with identical content get an identical `id`,
  order- and `PYTHONHASHSEED`-independent.
- **Cell key** (the answer to "(formulation, property) or something richer?"
  — see §9, Phase 53): `resolve_model_state_key(formulation_id, property,
  target_context)` — a 3-tuple, content-hashed. `(formulation, property)`
  alone was tried (Phase 52) and found insufficient; a third component,
  `target_context` (a caller-curated conditioning declaration, e.g.
  `{"temperature": 25}`), is required and is *always* sourced from
  `ActionCandidate.target_context`, identically on both the predict and
  update sides.
- **Immutable**: `update()` never mutates; it always returns a new
  `ModelState`. This is described in the module's own docstring as an
  "EPISTEMIC BOUNDARY."

### What is a prediction?

```python
@dataclass(frozen=True)
class Prediction:
    candidate_id: str
    formulation: Referent
    property: str
    context: Mapping[str, object]
    predicted_value: Optional[float]
    uncertainty: Optional[float]     # population variance, None if <2 samples
    sample_count: int
    state_id: str
    model_state_key: str
```

`Prediction` carries **no identity of its own** — it is a pure, reproducible
function of `(state.id, candidate.id)`; the module explicitly declined to add
a third hashing/identity system for it.

### What is a transition / update?

```
y_hat   = G(S_t, x)        # predict: ModelState x ActionCandidate -> Prediction
S_(t+1) = F(S_t, y_t)      # update:  ModelState x Observation     -> ModelState
```

`predict(state, candidate) -> Prediction` is pure: resolves the cell key from
`candidate`, reads `state.samples.get(key, ())`, computes mean/variance.
Never touches `EvidencePool` or `RetrievalEngine` directly.

`update(state, candidate, result, observation) -> ModelState`: asserts the
state contains no hypothetical samples (see below) and that
`candidate.id == result.candidate_id`; reads `observation.content["value"]`
directly; resolves the same cell key as `predict`; appends one `Sample` via a
shared private `_transition()` helper; returns a new `ModelState`. It
"trusts, rather than re-validates" that `candidate`, `result`, and
`observation` describe the same measurement (only the identity-equality
check above is performed) — deliberately, since Phase 55's finding is that
`predict`/`update` are pure functions of exactly their stated arguments
(state-sufficiency), and adding cross-validation of caller-supplied
consistency was judged unneeded complexity for a "reference" model.

### What determines state identity vs. state resolution?

Two separate, deliberately distinguished axes, formalized in Phase 100/101 as
a **coordinate/fiber structure**, not a tensor:

- **Coordinate** = `(formulation_id, property, target_context)`, realized by
  `resolve_model_state_key`. This selects *which cell* within a `ModelState`
  a candidate/prediction/update refers to.
- **Fiber** = the sequence of `ModelState`s that contain that coordinate
  (i.e., `ModelState.samples` is literally a mapping from coordinate to that
  cell's accumulated contents at a given state).
- **`ModelState.id`** = a fourth, separate axis: the same coordinate persists
  across states while its contents accumulate; the whole-state identity
  changes as any cell's contents change.

Phase 100 explicitly tested and **rejected** several candidate "extra
dimensions" for this space — `epistemic_side` (not orthogonal: a `Prediction`
is derived, not a stored/addressable second store), `counterfactual` (a point
in the *same* coordinate space, not a new axis — see below),
`decision`/`authority` (not real dimensions; not addressable, and the
invariants they might deliver already exist via immutability + append-only
pool + `DerivedValue.derived_from` DAG). It also confirmed, by AST-scanning
the whole materials/experiment/evidence/retrieval tree for
`contract`/`tensor`/`einsum`/`outer_product`/`covariance`/etc., that **no
operation anywhere combines two axes into a product quantity** — the
structure is fibered, not tensorial. This is a strong, code-verified
constraint the DAF must respect: it should not propose a design that
requires cross-axis contraction of state.

### What information can/must enter state, and what must remain outside it?

Only `observation.content["value"]` and `observation.id` (wrapped as a
`Sample`) enter `ModelState`. Everything else that exists on an `Observation`
— confidence, extraction method, timestamps, the rest of `content` — never
enters `ModelState` directly. Conditioning context enters only through the
caller-curated `target_context` on the `ActionCandidate`/`Criterion` that
requested the measurement, never through the raw `Observation.content`
mechanically. This is precisely the "a context field belongs in model state
only if its inclusion is justified by the dynamics/inference the model must
perform" principle the task's governing principle names — and it is already
how this repo's own state-space model behaves, not a design proposal.

### What is a counterfactual, and how is it kept from contaminating history?

`materials.counterfactual.project_update(state, candidate, hypothetical_value)`
reuses the exact same `_transition()` core as real `update()`, but the
resulting `Sample.observation_id` is prefixed `"hypothetical:"`
(`HYPOTHETICAL_SAMPLE_PREFIX`). `update()` refuses (via an `assert`,
Phase 61) to operate on any `ModelState` containing a sample with that
prefix — a real guard against silently folding a hypothetical branch into
real history. This is a directly reusable pattern for a DAF-level concern:
**speculative/derived data must be tagged so it can never silently re-enter a
"real" pipeline**, and the tag should live on the leaf record, not on the
container.

### Downstream analytics on the trajectory of states

`materials/trajectory.py`, `materials/assessment.py`,
`materials/diagnostics.py`, `materials/ensemble.py` build purely computed,
non-authoritative views over sequences of `ModelState`s and `Prediction`s
(residuals, prediction-evolution, transition diagnostics, counterfactual
branching with optional caller-supplied branch probabilities). None of these
mutate `ModelState` or add fields to it; lineage across states
(`predecessor_state_id`) lives only in a separate `TrajectoryEntry` view, not
baked into `ModelState`'s own content hash — explicitly to avoid corrupting
identity or carrying dead weight nothing else reads.

---

## 3. Existing epistemic/evidence architecture

### The type ladder

| Type | Identity hash inputs | Role |
|---|---|---|
| `Source` | `{kind, name}` | Origin of documents. |
| `Document` | `{source_id, content_hash(raw_content), retrieval_method}` | Immutable; stores full raw content (not just a hash) — the durable store-of-record for raw evidence. |
| `Record` | `{document_id, locator, raw_content}` | A raw structural unit within a document (page/table/byte-range/etc.) — not yet semantic. `locator` is deliberately untyped. |
| `Observation` | `{record_ids(sorted), extraction_method, content(sorted)}` (excludes confidence/timestamp) | A semantic extracted fact: `content: Mapping` is an open, extraction-defined mapping — no forced ontology. `confidence` is required and range-checked. |
| `Referent` | `{natural_key, kind}` | An entity reference (named to avoid colliding with `morpho.ir.Entity`). No fuzzy resolution — merges must be an explicit `same_as`-typed `ClaimedRelationship`. |
| `ClaimedRelationship` | `{from_referent_id, to_referent_id, type, observation_id}` (excludes confidence) | Identity includes `observation_id`, so **contradictory claims between the same referents coexist as distinct edges** — the trust graph is a multigraph by construction, never silently collapsed. |
| `DerivedValue` | `{derived_from(dedup+sorted), method, content(sorted)}` (excludes confidence/timestamp) | Synthesized from Observations and/or other DerivedValues. Cycles are structurally impossible (id = hash of derived_from, so a mutually-referencing pair could never compute either id first). |
| `DerivedGrounding` | `{derived_value_id, referent_ids(dedup+sorted)}` | What a `DerivedValue` is *about*, kept strictly separate from what it's derived *from*; multiple/conflicting groundings can coexist. |

### The admission gate

`evidence/admission.py` provides one `admit_*` function per type, each
returning the object unchanged on success or a list of `AdmissionError`s on
failure — atomic accept/reject, purely **structural/referential** (existence
of referenced ids, non-empty required fields, confidence in range). It never
judges truth and never resolves conflicts. A model-attributed observation
(`extraction_method` starting `"model:"`) must carry a genuinely supplied,
non-defaulted confidence.

The evidence "state machine" has exactly three stages and no more:
`constructed (make_*) → admitted (admit_*) → stored (pool.put_*)`. There is
no "verified"/"superseded"/"rejected-permanently" status field anywhere —
an update is always a new content-addressed object; nothing is ever marked
stale or deleted.

### The pool

`EvidencePool` (`evidence/pool.py`) is in-memory, append-only, and
**multi-head** — explicitly contrasted in its own docstring with
`CanonicalState`/`Version`'s single-head model: "unlike CanonicalState there
is no single 'current' evidence state — conflicting, coexisting Observations
are the point." `fingerprint()` is a content hash of exactly which object ids
the pool holds (order-independent); `fingerprint_history()` is an
append-only log of observed fingerprints. **Load-bearing distinction, stated
explicitly in `docs/RETRIEVAL_ARCHITECTURE.md`:** a fingerprint proves
"this evidence state was observed" (deterministic identifiability) — it does
**not** prove the evidence's contents are recoverable from the fingerprint
alone (historical reconstructability). No method anywhere maps a fingerprint
back to its constituent object ids or contents. Any DAF versioning/audit
story must not conflate these two guarantees.

### Provenance

Provenance exists as **three separate, deliberately non-unified types**,
each scoped to its own layer:

- `evidence.provenance.ProvenanceAncestry` — a pure, derived, read-only
  traversal of `DerivedValue.derived_from` chains back to `Observation`s.
  Never stored; recomputed on demand; output is id-sorted, not
  traversal-ordered.
- `morpho.provenance.ProvenanceRecord` — `{source, origin_version,
  compiler_version, transaction_id, confidence, timestamp}`; tracks Morpho
  compilation lineage from a canonical `Version`, entirely within Track 1.
- `core.canonical.version.ProvenanceInfo` — `{author, transaction_id,
  source, timestamp}`; tracks who/what minted a canonical `Version`.

None of these three import or reference each other. A DAF-level provenance
concept must not attempt to unify them retroactively; it should instead sit
"above" the evidence-layer one (`ProvenanceAncestry`) as the origin of the
chain, per §7.

### Trust graph and metrics

`evidence/trust_graph.py::TrustGraph` is a derived, read-only multigraph view
(`build_trust_graph(pool) = TrustGraph(nodes=pool.all_referents(),
edges=pool.all_claimed_relationships())`) — never independently stored,
recomputed any time the pool changes. `evidence/metrics.py` computes
connectivity, novelty, redundancy, source diversity, observation/aggregate
uncertainty (`1 - confidence`), evidence density, and bridge potential —
all explicitly scoped to "only implemented because directly computable from
data this architecture already has"; confidence/source-quality-weighted
variants are documented as unresolved research, not silently approximated.

### The "FEP" interface — the closest existing hook to "information gap"

`evidence/fep_interface.py::FEPSignal` explicitly separates three confidence
tiers that must not be conflated:

```python
@dataclass(frozen=True)
class FEPSignal:
    observation_id: str
    uncertainty: float                              # ESTABLISHED
    novelty: float                                   # ESTABLISHED
    relevance: Optional[float] = None                # PROPOSED EXTENSION (caller-supplied)
    investigation_cost: Optional[float] = None       # PROPOSED EXTENSION
    expected_information_gain: Optional[float] = None  # RESEARCH HYPOTHESIS -- always None
    priority: Optional[float] = None                  # placeholder formula, only if relevance & cost given
```

`expected_information_gain` has **no estimator anywhere in this codebase**
and is always `None`. This is the exact seam the task's "information gap →
SCOUT → DAF request" loop would eventually attach to — and the repo's own
position is that it is a named, deliberately unimplemented research
hypothesis, not a live mechanism. The DAF must not be designed as though this
loop already exists.

### Where does evidence become canonical? (The crossing rule)

`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §O states the rule precisely: **only
a reviewed `DerivedValue` — never a raw `Observation` directly — may ever
seed a `CandidateDelta`** into `core.canonical`'s state/version system. This
crossing is **explicitly not yet implemented** — `evidence/__init__.py`'s own
docstring says the package "stops one stage short of that." Grepping the
whole tree for `ModelState` inside `evidence/`, `morpho/`, `core/` returns
nothing; grepping for cross-imports between `evidence/`/`core.canonical`
returns nothing either. **`core.canonical.CanonicalState`/`Version` has never
received anything derived from evidence.**

Separately, and importantly: `materials.model_state.ModelState` **does**
ingest `evidence.types.Observation` directly (`observation.content["value"]`,
inside `update()`), with **no** canonical/projection intermediary at all —
but this is because `ModelState` was never part of the canonical-state system
to begin with; it is a third, independent state abstraction, built for the
experimental-decision feedback loop, that happens to also live downstream of
`evidence/`. See §8 for why this matters to the DAF boundary design.

---

## 4. Existing SCOUT/GraphRAG architecture

### What SCOUT currently does

`scout/` is a pure **acquisition → evidence-admission** pipeline; it is not a
retrieval/query system at all (that is `retrieval/`'s job) and it never
reaches `core.canonical` (no import, confirmed by direct inspection of every
file in the package).

Public contract (`scout/interface.py`): three Protocol/value-type stages —
`RawDocument` (what a source hands back: `source_name, source_kind, content,
locator, retrieval_method, retrieved_at`), `SourceAdapter.fetch() ->
Tuple[RawDocument, ...]`, and `Extractor.extract(record) ->
Tuple[ExtractionCandidate, ...]`. `ExtractionCandidate` carries `content`,
`entities`, `relations`, `extraction_method`, and an optional `confidence`
that becomes mandatory whenever `extraction_method` starts with `"model:"`.

`scout/pipeline.py::run_scout(adapter, extractor, pool)` sequences:
`fetch → make/admit Source/Document/Record → extract → make/admit
Observation/Referent/ClaimedRelationship → compute trust-graph deltas and
metrics → compute FEPSignal → ScoutFinding`. Every write is gated: there is
no code path that calls `pool.put_*` without a preceding successful
`admit_*`. On admission failure, the item is skipped and recorded as a
`ScoutAdmissionFailure`, never raised as an exception.

**The only implemented `Extractor` is `DeterministicExtractor`** — a
regex-based parser over a fixed `ENTITY:`/`RELATION:`/`FACT:` fixture format,
fixed `extraction_method = "regex:kv_v1"`, fixed `confidence = 1.0`. **The
only implemented `SourceAdapter` is `FixtureSourceAdapter`**, returning a
hardcoded tuple of `RawDocument`s. There is no live network access anywhere
in `scout/` — explicitly out of scope per `docs/SCOUT_ARCHITECTURE.md`.

### What SCOUT is NOT currently doing (and this matters for the DAF)

`run_scout` is never called by any production code path — not `runtime/`,
not `workbench/`, not `materials/`, not `experiment/`. The interactive
workbench (`workbench/interaction.py::bootstrap_default_scenario`/
`bootstrap_research_scenario`) constructs its own `EvidencePool` and admits
evidence **by hand**, calling `make_source`/`admit_document`/`admit_referent`
etc. directly — satisfying the same admission gate SCOUT would use, but
bypassing SCOUT's pipeline entirely. **SCOUT is architecturally wired to
`evidence/` but is currently a dead-end, unconsumed producer relative to the
rest of the running system.** This is the single clearest gap the DAF exists
to fill: SCOUT's contract is sound and proven; it has never been given real
adapters, and nothing currently depends on it being the actual ingestion
path.

### Retrieval — is there a real graph/vector index?

No. `retrieval/engine.py::DeterministicRetrievalEngine` (the only
`RetrievalEngine` implementation) recomputes the trust graph on every call
(`build_trust_graph(pool)` — a pure function, never cached/persisted), does a
plain bounded BFS from exact-match `Referent.natural_key` seeds, filters by
epistemic status/source kind/text substring, and returns results sorted by
id — explicitly documented as "ordering, not ranking." `RetrievalEngine` is a
`Protocol`; the docs are explicit that a future `SemanticRetrieval`/
`VectorRetrieval`/`GraphRetrieval`/`HybridRetrieval` engine would implement
the same Protocol, and that no stub subclasses for those were added
("five empty subclasses would add names without adding a capability"). There
is no vector index, no external graph database, no embeddings anywhere in
this codebase.

`retrieval/epistemic.py::classify_epistemic_status(observation)` is the
entirety of "epistemic reasoning" in this layer — a static lookup on
`extraction_method` returning one of a 7-value taxonomy (`observed`,
`extracted`, `inferred`, `hypothesized`, `simulated`, `predicted`,
`validated`, defined in `docs/COMPUTATIONAL_COMMONS.md` §K), of which only
`observed`/`extracted`/`inferred`/`simulated` are currently reachable —
`hypothesized`/`predicted`/`validated` require agent/review machinery that
doesn't exist yet. Not probabilistic, not calibrated — a closed vocabulary
lookup.

### `ContextPackage` and the seam to a future `InquiryState`

`retrieval/context.py::ContextPackage` is a reproducible, content-hashed
*selection of persistent evidence* — it holds only id references (referent,
relationship, observation, source ids, plus the set of distinct evidence
fingerprints contributing to it), never copies, and dereferences back to the
*same* pool object instances (`is`, not `==`).

`retrieval/seam.py::InquirySeam{context_id, opened_at}` is, by its own
docstring, "the smallest possible boundary marker, not an implementation" —
it records only that a `ContextPackage` was handed off toward computation. It
creates no mutable state and performs no computation. **`InquiryState` — a
temporary, mutable computational workspace built from a `ContextPackage`,
where hypotheses/derived quantities/half-finished calculations would live —
does not exist as code anywhere in this repo.** It is sketched only
conceptually, in `docs/COMPUTATIONAL_COMMONS.md`, as future, non-authoritative,
freely-mutable, schema-free state, explicitly separate from the
evidence/knowledge-graph layer beneath it and from `CanonicalState` above it.
`InquirySeam` currently has zero live callers outside its own module.

### The intended future loop (documented, not built)

`docs/SCOUT_ARCHITECTURE.md` §12 names a future agent topology explicitly
flagged as unbuilt: `SCOUT → TRACE → VALIDATE → DYNAMICS → PRIORITIZATION →
HUMAN/EXPERIMENT → VALIDATION → YIELD → FEP-UPDATE`. Grepping `scout/`,
`retrieval/`, `runtime/` for `information_gap`, `uncertainty-driven`, or
`acquisition` (as a triggered event) confirms: uncertainty flows only
one direction today — evidence → `observation_uncertainty` metric →
`FEPSignal.uncertainty` — never the reverse (state/model uncertainty
triggering a new `RetrievalQuery` or a `run_scout` call). The nearest
*implemented* analog to "gap analysis" lives in `materials/`, not
`scout/`/`retrieval/`: `materials.iteration.reevaluate_program` composes
`analyze_program → evaluate_program → audit_program →
analyze_experiment_gaps → specify_experiment_requirements`, but this drives
*which laboratory experiment a human should run next*, not a SCOUT/retrieval
call, and it is not triggered by SCOUT in any way.

**Conclusion:** the "current state → uncertainty/information gap →
retrieval/acquisition request → new evidence → observation → state update →
new state" loop the task describes is the repo's own stated future
direction, not a live mechanism. The DAF should be designed so that this loop
becomes *possible* to build later (i.e., it should not foreclose it), but
should not attempt to implement the loop itself right now.

---

## 5. Existing Morpho/IR architecture

Morpho belongs entirely to **Track 1** and has no relationship to Track 2's
evidence/materials pipeline (confirmed: no `evidence` import anywhere in
`morpho/*.py`). It is included here because the task explicitly asks about
it as a candidate computational substrate.

Morpho is **not** a general map/filter/aggregate transformation DSL. It is a
declarative, HDL-style modeling language for spatial/relational scenes:
typed entities with attributes, typed relations carrying two independent
axes (`is_canonical: bool`, `inference_status: "explicit"|"inferred"` — a
relation with `is_canonical=True` and `inference_status="inferred"` is
structurally illegal, enforced by a raised `SemanticError` at construction),
coordinate frames with parent hierarchies and transforms, groups, and
constraints.

Two paths produce a `MorphoDocument`:
1. Text `.morpho` source → lexer → parser → AST → `from_ast` semantic
   analysis (used for hand-authored fixtures/tests).
2. The production path: `core.projection.ProjectedState` →
   `morpho.compiler.compile_morpho` → `MorphoDocument` directly, no text
   round-trip. `compile_morpho` is pure and deterministic; canonical facts
   always compile to `is_canonical=True, inference_status="explicit"`
   relations — Morpho never invents `derived`/`inferred` relations from
   canonical state.

Morpho's own identity scheme (`morpho/identity.py`) is a **deliberate,
permanent pass-through**: `node_id(entity_id) == entity_id`, and likewise for
`cell_id`/`visual_id`/`geometry_id` — no hashing, no namespacing. The
docstring explicitly warns future maintainers not to "improve" this into a
UUID/hashing scheme. This is a materially different identity discipline from
`evidence/identity.py`'s content-hash scheme: **Morpho IR node identity is
inherited from upstream canonical `Field.id`/`EdgeRecord.id`, never
independently derived.**

Multiple real backends confirm Morpho is a genuine hardware/target-independent
substrate: `backends/threejs` (JSON scene descriptor), `backends/diagram`
(deterministic SVG layout), `backends/graph` (descriptive metrics only, never
invents new relations), and two interface-only seams,
`backends/neural/interface.py` and `backends/simulation/interface.py`
(`Estimator`/`DynamicsSpec` Protocols producing `CandidateNextState`/
`BeliefState`, with no actual model/physics logic implemented). No backend
imports another backend; no backend has a path back into canonical state
("no backend may promote anything it computes into canonical state,"
`backends/graph/analysis.py`'s own docstring).

**Relevance to the DAF:** Morpho is a plausible future execution substrate
for deterministic transformations *over already-resolved, canonical or
evidence-adjacent structure* — but it is not, and should not become, a
semantic-identity system, and it has no ingestion role. The DAF's
observation/evidence layer should never depend on Morpho, and Morpho should
never be asked to define what an `Observation` or `Referent` *means*.

---

## 6. Current state-transition graph (as implemented, Track 2 only)

```
EvidencePool (append-only, multi-head)
      │  admit_*  (scout/pipeline.py::run_scout, OR hand-admission
      │            in workbench/interaction.py -- both call the SAME
      │            evidence.admission gate)
      ▼
Observation ──────────────────────────────────────────────┐
      │                                                     │ (content["value"], id)
      │ build_trust_graph (pure, recomputed each call)      │
      ▼                                                     ▼
TrustGraph ──▶ RetrievalQuery ──▶ DeterministicRetrievalEngine     ModelState_t
      │              │                    │                        (samples keyed by
      │              ▼                    ▼                         (formulation,property,
      │        RetrievalResult ──▶ ContextPackage                   target_context))
      │                                   │                              │
      │                                   ▼                       predict(state, candidate)
      │                            InquirySeam (marker only,              │
      │                             zero live callers;                   ▼
      │                             no InquiryState exists)          Prediction_t
      │                                                                   │
      │                                                    (human/dispatcher executes
      │                                                     an ActionCandidate; result
      │                                                     obtained)
      │                                                                   │
      │                                          materials.results.admit_experimental_result
      │◀──────────────────────────────────────────────────────────────────┘
      │        (constructs a NEW Observation, admits it through the
      │         SAME evidence.admission gate -- the only write path
      │         into EvidencePool from materials/)
      ▼
  (assess: residual = observed - predicted)  ──▶ update(state, candidate, result, observation)
                                                              │
                                                              ▼
                                                        ModelState_(t+1)
```

Track 1's own transition graph (for completeness, disjoint from the above):

```
CandidateDelta ──▶ validate_candidate(schema, base, candidate) ──▶ Version | [ValidationError]
                          (the ONLY function that can mint a Version;
                           enforced by an AST-walking test)
Version ──▶ project_state (pure) ──▶ ProjectedState ──▶ compile_morpho (pure) ──▶ MorphoDocument
                                                                    │
                              ┌─────────────────────────────────────┼───────────────────┐
                              ▼                     ▼                ▼                   ▼
                        compile_threejs      compile_svg      graph analyze      (neural/sim:
                                                                                   interface-only)
runtime.feedback_loop.submit_simulation_candidate / submit_neural_belief
        (wraps a CandidateNextState/BeliefState into a CandidateDelta,
         re-enters at validate_candidate -- the only bridge back to canonical state)
```

---

## 7. Current representation hierarchy

From least to most processed, Track 2:

```
RawDocument (scout.interface)          -- pre-identity, pre-pool, adapter output
      ↓
Document, Record (evidence.types)      -- durable raw evidence, content-addressed
      ↓
Observation (evidence.types)           -- semantic extracted fact, open `content` mapping,
                                            required confidence
      ↓
Referent, ClaimedRelationship          -- entity/relationship claims about Observations,
(evidence.types)                          contradictions coexist (multigraph)
      ↓
DerivedValue, DerivedGrounding         -- synthesized from Observations/other DerivedValues;
(evidence.types)                          NOT YET connected to canonical state (crossing
                                           rule unimplemented, Phase 14 §O)
      ↓
TrustGraph (evidence.trust_graph)      -- derived, read-only multigraph view
      ↓
RetrievalResult, ContextPackage        -- derived, read-only, content-addressed selections
(retrieval.*)                             of evidence; hold references, never copies
      ↓
[InquirySeam marker -- no InquiryState exists]
      ↓
ModelState (materials.model_state)     -- a domain-specific (materials-only), separate
                                           state abstraction; ingests Observation.content
                                           directly, with NO canonical/projection
                                           intermediary, because it was never part of
                                           that system
      ↓
Prediction (materials.model_state)     -- pure function of (state, candidate); no
                                           independent identity
```

Track 1's representation hierarchy is disjoint: `CanonicalState`/`Field`/
`EdgeRecord` → `Version` → `ProjectedState` → `MorphoDocument` (`Entity`/
`MorphoRelation`/`CoordinateFrame`) → backend-specific descriptors
(`ThreeJSSceneDescriptor`, SVG string, `GraphAnalysisReport`).

**No single representation hierarchy spans both tracks**, and the DAF must
not invent one that pretends they are unified — see §15.

---

## 8. DAF responsibility boundary

Given §0–§7, the DAF's boundary is determined by where Track 2's own
ingestion story is real but unfinished, not by inventing a new boundary from
first principles:

- **The DAF is the thing that makes `scout/`'s `SourceAdapter`/`Extractor`
  Protocols real, at scale, across domains.** Today only
  `FixtureSourceAdapter` and `DeterministicExtractor` exist. The DAF's job is
  to industrialize this exact seam — literature/patent/API/document/database
  adapters per domain, each producing `RawDocument`s and
  `ExtractionCandidate`s that flow through the **unchanged**
  `evidence.admission` gate.
- **The DAF owns evidence durability that `EvidencePool` does not have
  today.** `EvidencePool` is in-memory only. Raw-object storage, durable
  content addressing, and replay/versioning of the evidence pool's state
  over time are DAF responsibilities — Track 2 has no opinion on this beyond
  "it must be content-addressed and append-only," which the DAF must
  preserve.
- **The DAF must make SCOUT's admission gate the one real ingestion door.**
  Currently even the interactive workbench bypasses `run_scout` and
  hand-admits evidence. A working DAF should be the thing that makes
  hand-admission unnecessary in production use, without changing the gate
  itself.
- **The DAF stops at admitted `Observation`s (and, once the Phase 14 §O
  crossing is implemented, reviewed `DerivedValue`s). It must never
  construct `ModelState`, `CanonicalState`, or any other domain-specific
  predictive state.** That is `materials/`'s job today, and would be each
  future domain's equivalent-of-`materials/` package's job tomorrow (see
  §11). This mirrors exactly how `scout/` itself is already scoped: an
  observer, never a decision-maker.
- **The DAF is not `adapters/` (the top-level package).** That package
  belongs to Track 1 and feeds an unrelated 3D-scene canonical state system.
  Do not extend it; do not use it as a template for domain data ingestion —
  its target (`CandidateDelta` → `validate_candidate`) is the wrong target
  for anything the DAF is acquiring.
- **The DAF should not attempt to build the information-gap-driven
  acquisition loop yet** (§4). It should expose an acquisition-request
  interface that a future prioritization/FEP-update stage could call, but
  should not itself decide what has "information value" — that is
  `materials.information`/`evidence.fep_interface`'s conceptual territory
  (currently unimplemented, by design), one layer downstream of the DAF.

---

## 9. Observation/state boundary

The task explicitly forbids the DAF from constructing `ModelState` unless
the architecture requires it. The code answers this directly: it does not,
and the actual promotion path already implemented for the one existing
domain is:

```
Observation (evidence.types, admitted via evidence.admission)
      │
      │  (materials.results.admit_experimental_result -- domain-specific,
      │   lives in materials/, constructs the Observation AND links it to
      │   a formulation Referent via a ClaimedRelationship, through the
      │   SAME unmodified evidence.admission gate)
      ▼
[consumed directly by materials.model_state.update(), which reads
 observation.content["value"] -- no StateProjection/StateInput
 intermediary type exists in this codebase]
      ▼
ModelState_(t+1)
```

There is **no** `StateProjection`/`StateInput` type and no
`resolve_model_state_key(...)`-as-a-general-DAF-facing-function pattern —
`resolve_model_state_key` is materials-specific and lives inside
`materials/model_state.py`, not in a shared/generic layer. The repo's actual
answer to "what is the boundary contract" is:

- Evidence layer emits `Observation`s (and, once built, reviewed
  `DerivedValue`s) — domain-agnostic, open `content: Mapping`.
- Each domain owns a **domain-specific resolution function** analogous to
  `resolve_model_state_key`, and a **domain-specific write boundary**
  analogous to `materials.results.admit_experimental_result`, that decides
  which `Observation.content` keys become predictive state, which become
  conditioning context, and which are discarded as incidental.
- Nothing upstream of that domain-specific function (i.e., nothing in
  `evidence/`, `scout/`, `retrieval/`, or the DAF) may make that decision on
  the domain's behalf.

**Recommendation for future work (not yet needed at DAF-architecture stage):**
if a second domain state-space model is built, it should define its own
`resolve_<domain>_state_key`-equivalent and its own
`admit_<domain>_result`-equivalent, following the `materials/` precedent,
rather than the DAF or evidence layer providing a generic "state resolution"
service. This is consistent with §9's own governing principle: state
resolution is inherently domain/model-specific, and generalizing it
prematurely would be exactly the kind of universal-ontology mistake
`docs/PHASE_13_ARCHITECTURE_INVESTIGATION.md` explicitly rejected for a
structurally similar problem (Option A, "Structured Canonical State,"
scored 48/90 and was rejected for requiring a universal ontology engine).

---

## 10. State-resolution semantics (Phase 53, in full, since the task calls
it out specifically)

**Confirmed, from direct reads of `materials/model_state.py`'s docstring and
`tests/test_materials_model_state.py`:** `(formulation, property)` alone was
tried (an "interim simplification," Phase 52) and found insufficient. The
bug: two genuinely different notions of "context" existed and were silently
conflated —

1. **Evidence comparison context** (`materials.analysis._comparison_context`)
   — every `Observation`/`DerivedValue.content` key except `property` and the
   value key, e.g. `{"unit": "MPa", "temperature": 100}`. Grouped by *exact*
   equality to decide which raw values are safe to compare. Mechanically
   derived — necessarily includes incidental metadata (`unit`) alongside
   genuine experimental conditions (`temperature`), because it cannot
   structurally distinguish the two.
2. **Model-state conditioning context** (`ActionCandidate.target_context` ==
   `EvidenceRequirement.criterion_context`) — a caller-curated, deliberately
   narrow declaration of which conditions a `Criterion` cares about, e.g.
   `{"temperature": 25}`. A caller has no reason to put `unit` here.

Phase 52's bug was comparing these two *different representations* for exact
equality across the predict/update boundary, silently producing empty
predictions. **Phase 53's fix**: key `ModelState` cells by
`resolve_model_state_key(formulation_id, property, target_context)`, where
`target_context` is *always* sourced from `ActionCandidate.target_context` on
both sides.

**Two alternative fixes were explicitly considered and rejected** — this is
directly relevant to how the DAF's own context-preservation should be
designed:

- Reimplementing `materials.decision`'s subset-matching context logic inside
  `model_state.py` — rejected as unneeded complexity for a "reference" model.
- Inventing a scheme to classify which `Observation.content` keys are causal
  conditioning variables versus incidental metadata — rejected because
  "nothing upstream of this module records" that distinction, and fabricating
  one would be "exactly the invented ontology this phase's own instructions
  forbid."

**Mapping onto the task's own vocabulary** ("comparison context /
observation context / criterion context / model conditioning variables /
model state identity" — are these distinct?): **yes, confirmed distinct by
the codebase's own analysis**, but the codebase does not unify them under a
shared formal type — it keeps them apart by *discipline* (always source
`target_context` from the same place on both sides of a transition), not by
a shared abstraction:

- *Comparison context* = `materials.analysis._comparison_context` (evidence-
  side, mechanical, over-inclusive).
- *Criterion context* = `EvidenceRequirement.criterion_context`, identical in
  shape/provenance to `target_context` (caller-curated, narrow).
- *Model conditioning variables / model state identity* =
  `resolve_model_state_key(formulation_id, property, target_context)` for the
  cell coordinate; `ModelState.id` (content hash over all cells) for whole-
  state identity — two distinct identity axes, confirmed by Phase 100/101's
  coordinate/fiber analysis (§2).
- *Observation context*: not a separately named type — implicit in
  `Observation.content`, from which comparison context is mechanically
  derived. There is no dedicated `ObservationContext` type in this codebase.

**This finding must directly govern the DAF's data contract (§13):** the DAF
must preserve *both* kinds of context on every observation it emits — the
full, unfiltered content mapping (so a future comparison-context computation
remains possible) and, where the acquisition request that produced the
observation was itself criterion-scoped, the criterion/target context that
motivated it — without trying to decide, at acquisition time, which parts of
either are "real" conditioning variables. That decision is downstream and
domain-specific, exactly as Phase 53 concluded for materials.

---

## 11. Multiple-model compatibility analysis

The task assumes the DAF will eventually feed several independent
state-space models (materials, market, logistics, real estate, industrial).
The codebase already demonstrates the correct shape for this, though only
one instance (`materials/`) exists:

- The evidence substrate (`evidence/`, `scout/`, `retrieval/`) is **already
  domain-agnostic** — `Referent`, `ClaimedRelationship`, `Observation`,
  `DerivedValue` mention nothing materials-specific. `Observation.content` is
  an open mapping precisely so any domain can populate it.
- **Only `materials/` is domain-specific**, and it is domain-specific in
  exactly the right place: `ModelState`, `resolve_model_state_key`,
  `ActionCandidate`, `admit_experimental_result` all live inside `materials/`,
  not inside `evidence/`/`scout/`/`retrieval/`.
- A second domain (say, a future `markets/` package) would, by this
  precedent, define **its own** `ModelState`-equivalent, its own
  `resolve_<domain>_key`-equivalent, and its own
  `admit_<domain>_observation`-equivalent write boundary — all built on the
  *same*, unmodified `evidence.admission` gate and the *same*
  `EvidencePool`/`retrieval` layer.
- Phase 100/101's own finding — that `ModelState` is a **fiber bundle over a
  coordinate space**, not a tensor, and that no cross-axis contraction exists
  anywhere in the codebase — is direct evidence that the current design
  already resists being generalized into one universal predictive ontology.
  A single shared `ModelState` type across materials/markets/logistics would
  either force a shared coordinate schema (violating "acquisition
  representations and predictive representations must remain conceptually
  distinct," since different domains have incompatible notions of
  "formulation"/"property"/"context") or degrade into an untyped bag,
  reproducing exactly the anti-pattern
  `docs/PHASE_13_ARCHITECTURE_INVESTIGATION.md` rejected (Option A,
  "Structured Canonical State" / "universal ontology engine," scored lowest
  of three options considered for a structurally similar generalization
  question).

**Conclusion, stated as the common representation sufficient to support
multiple models:**

```
common substrate (domain-agnostic, DAF + evidence/scout/retrieval own this):
    Source, Document, Record, Observation, Referent, ClaimedRelationship,
    DerivedValue, DerivedGrounding, TrustGraph, RetrievalQuery/Result,
    ContextPackage
              │
              ▼  (each domain defines its own resolution + write boundary)
per-domain state-space packages (materials/ exists; markets/, logistics/,
real-estate/, industrial/ would each be new, analogous packages):
    Domain-specific ModelState-equivalent, coordinate-key function,
    admit_<domain>_observation write boundary, predict/update
```

The DAF's data contract (§13) must be rich enough to let *any* future
domain package perform this resolution — it must not pre-select which
fields matter, because that choice is provably domain-specific (Phase 53's
own conclusion, generalized).

---

## 12. Storage/projection architecture

Nothing in the SSA repo currently persists evidence beyond one Python
process (`EvidencePool` is in-memory; `InMemoryVersionStore` likewise, and is
explicitly scoped as v1-only, single-writer, no concurrency). The repo's own
*design* documents (not yet implemented) already converge on the layering the
task's principle recommends:

- `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §I recommends (conceptually,
  no product chosen): content-addressed blob storage for raw `Document`s +
  a structured record store for `Record`/`Observation`/`Referent`/
  `ClaimedRelationship`/`DerivedValue` + a derived graph index + an optional
  future vector index. Graph is explicitly named a **derived index, never
  primary storage** (§G) — "mirrors Phase 13's Morpho-vs-`CanonicalState`
  conclusion one layer upstream," i.e., the same "compiled fact, never
  stored fact" discipline Track 1 already enforces for Morpho.
- `docs/COMPUTATIONAL_COMMONS.md` sketches one further, still-unimplemented
  promotion tier — an "Immutable Knowledge Graph" sitting between
  Evidence/Warehouse and a future `InquiryState`, gated by a **different,
  stricter promotion gate than `evidence.admission`** (not yet designed;
  explicitly not the same gate reused). This is presented as a
  design hypothesis, not a decided architecture — treat it as informative,
  not authoritative, for the DAF.

Applying the task's own storage principle, now grounded in what actually
exists vs. is proposed:

```
raw evidence (Document.raw_content, Record.raw_content)
    = durable source material                              [DAF owns; not yet persisted anywhere]

Observation / Referent / ClaimedRelationship / DerivedValue
    = the closest thing to "authoritative structured observation" that
      exists today -- authoritative FOR EVIDENCE, not for truth           [evidence/ owns; DAF feeds]

TrustGraph, RetrievalResult, ContextPackage
    = derived retrieval projections, always recomputable, never
      independently authoritative                                        [retrieval/ owns]

ModelState (materials/, and future per-domain equivalents)
    = model-specific computational representation                        [each domain package owns]

CanonicalState/Version (Track 1)
    = a DIFFERENT system's sole source of truth, for a different domain
      (3D-scene/digital-twin state) -- not part of this ladder at all
```

The DAF should not select a specific database technology at this stage (per
the task's explicit prohibition); it should ensure whatever raw/structured
storage it eventually picks preserves: content-addressability (so
`Document`/`Record`/`Observation` ids remain stable across storage
migrations), append-only history (matching `EvidencePool`'s existing
discipline), and a clean separation between raw storage and any derived
index (graph, search, vector) — none of which may become a second source of
truth for evidence, mirroring the "no backend may promote anything it
computes into canonical state" rule already enforced for Morpho backends.

---

## 13. Plane separation

Mapped onto what actually exists (not all planes are populated with real
implementations today — this is noted per plane):

| Plane | Existing code | DAF's relationship |
|---|---|---|
| **Data plane** (acquisition, evidence, storage) | `evidence/` (types, admission, pool — in-memory only), `scout/` (fixture-only) | **This is the DAF's home plane.** DAF = real acquisition + durable storage, feeding the existing `evidence.admission` gate unchanged. |
| **Epistemic plane** (observations, provenance, claims, canonical knowledge) | `evidence.provenance`, `evidence.trust_graph`, the (unimplemented) Phase 14 §O crossing rule | DAF feeds this plane; does not decide what becomes canonical. |
| **Compute plane** (deterministic transformations, Morpho, CUDA) | `morpho/`, `backends/*` — entirely Track 1, unrelated domain | Not a DAF concern today; a possible future execution substrate for domain-specific transformations, never a semantic-identity authority. |
| **Learning plane** (State-Space Transformer / learned dynamics) | `materials.model_state` (a simple sample-statistics model, explicitly **not** Bayesian/neural/calibrated); `backends/neural/interface.py` (interface-only, Track 1) | Downstream of the DAF; DAF must never construct this plane's state. |
| **Retrieval plane** (search, graph, vector, SCOUT) | `retrieval/` (deterministic BFS only, no vector/semantic search), `scout/` (acquisition, not retrieval, despite the name) | DAF is a *producer into* this plane (via evidence), not a consumer of it. |
| **Control/orchestration plane** (scheduling, acquisition policy, pipeline control) | `experiment/` (sequencing only, no new math), `workbench/` (human-facing orchestration) | DAF's own acquisition scheduling/policy is new work; it should not be modeled on `experiment/`'s pattern verbatim, since that pattern already assumes a human/dispatcher executing a physical action — DAF's acquisition actions are typically network/API calls, a different action shape. |

These are conceptual boundaries. Nothing above requires separate deployments
today; the SSA repo runs all of Track 2 as one in-process library.

---

## 14. Minimum interface set

Given §8–§13, the minimum set the DAF actually needs to compose with the
existing system — deliberately smaller than the task's illustrative list,
because most of the illustrative interfaces already exist inside Track 2 and
the DAF should reuse them rather than re-specify them:

1. **`SourceAdapter.fetch() -> Tuple[RawDocument, ...]`** — *already
   defined*, `scout/interface.py`. The DAF's job is to implement many real
   adapters against this existing Protocol, not to define a new one.
2. **`Extractor.extract(record: Record) -> Tuple[ExtractionCandidate, ...]`**
   — *already defined*, `scout/interface.py`. Same relationship: DAF
   implements real (model-backed or rule-based) extractors here.
3. **`run_scout(adapter, extractor, pool) -> (findings, admission_failures)`**
   — *already defined*, `scout/pipeline.py`. The DAF's orchestration layer
   should drive this function (or a durable-storage-aware evolution of it)
   at scale, rather than replacing it.
4. **Durable evidence storage boundary** (new — the one genuinely new
   interface the DAF must define): a persistence layer underneath
   `EvidencePool` so that `Source`/`Document`/`Record`/`Observation`/
   `Referent`/`ClaimedRelationship`/`DerivedValue` survive past one process,
   while preserving `EvidencePool`'s existing public contract
   (`put_*`/`get_*`/`all_*`/`fingerprint()`) so nothing above it (SCOUT,
   retrieval, materials) needs to change.
5. **Acquisition scheduling/policy interface** (new): something that decides
   *when* and *what* to acquire — today nothing in the repo does this at all
   (SCOUT is invoked directly, only in tests). This is legitimately new DAF
   territory, not a reuse of an existing type.

For each:

| Interface | Input | Output | Owner | Mutability | Sync/async | Canonical/derived |
|---|---|---|---|---|---|---|
| `SourceAdapter.fetch` | (adapter config) | `Tuple[RawDocument,...]` | DAF (implements against SSA's Protocol) | `RawDocument` immutable | Either — SSA repo doesn't constrain this; DAF should assume async in practice for real network sources | n/a (pre-identity) |
| `Extractor.extract` | `Record` | `Tuple[ExtractionCandidate,...]` | DAF (implements against SSA's Protocol) | immutable | sync-shaped in current code; DAF's real implementations (e.g. model-backed) may need an async wrapper at the orchestration layer | n/a (pre-identity) |
| `run_scout` | adapter, extractor, `EvidencePool` | admitted `ScoutFinding`s + `ScoutAdmissionFailure`s | SSA (`scout/pipeline.py`, unmodified) | writes only via `admit_*` | sync today | derived findings; writes are canonical-for-evidence |
| Durable evidence store | `EvidencePool` mutations | persisted `Source`/`Document`/.../`DerivedValue` records | DAF (new) | append-only, matching `EvidencePool` | must support both, given real-world acquisition latency | authoritative for evidence, never for `CanonicalState`/`ModelState` |
| Acquisition scheduling/policy | acquisition requests (initially human/config-driven; later, information-gap-driven per §4) | scheduled `run_scout` invocations | DAF (new) | n/a | async | derived (policy), never itself evidence |

Everything else in the task's illustrative list
(`Observation → StateProjection`, `StateSpace → InformationGap`,
`InformationGap → SCOUT`, `State → MorphoExecution`) names **interfaces that
don't exist in this codebase and that this reconnaissance found no present
need to build** — they belong to the deliberately-deferred future loop (§4)
or to domain-specific resolution the DAF must not perform (§9). Building them
now would be exactly the premature layering the task's stop condition warns
against.

---

## 15. Coupling prohibitions

Confirmed by the existing codebase's own enforced rules (AST-walking
boundary tests), extended by direct analogy where the DAF introduces a new
edge of the same kind:

- **The DAF must not depend on `materials/` (or any future domain
  state-space package) internals.** Exactly mirrors "`evidence/` does not
  import `core.canonical.validation`."
- **`materials/` (and any future domain package) must not depend on DAF
  implementation details** (which adapter fetched a document, how it's
  stored) — only on the `evidence.types`/`evidence.admission` contract,
  exactly as it does today.
- **The DAF must not construct or bypass `evidence.admission`.** Every
  DAF-sourced observation must pass through the unmodified admission gate,
  the same way SCOUT and the workbench's hand-admission both do today —
  there must never be a second, DAF-specific admission path.
- **The DAF must not construct `ModelState`, `CanonicalState`, or any
  domain-specific predictive state.** Confirmed as a real, already-enforced
  boundary for `scout/` (no import of `core.canonical` anywhere); the DAF
  inherits the same restriction.
- **The DAF's evidence storage must not depend on a specific graph
  database, vector store, or search index.** `TrustGraph` is already a pure,
  derived, recomputable view over the pool — any DAF storage choice must
  preserve the ability to rebuild that view from raw stored evidence, never
  make the graph/index itself the source of truth.
- **Morpho must not define semantic identity for DAF/evidence objects.**
  Already true by construction (Morpho's identity is a pass-through of
  upstream canonical `Field.id`s, unrelated to evidence identity) — the DAF
  must not introduce a dependency that would change this.
- **Retrieval/GraphRAG must not become canonical truth.** Already enforced:
  `retrieval/` never calls `admit_*`/`put_*`. The DAF must not add a path
  that lets a retrieval result be written back into the evidence pool as if
  it were newly observed.
- **Learned/predictive state must never become evidence.** `ModelState`
  (and any future domain model's state) must never be admitted back into
  `EvidencePool` as an `Observation` — this would silently launder a
  model's own belief as if it were externally observed fact. Nothing in the
  current codebase does this; the DAF must not introduce a path that would.
- **Predictions must not automatically become observations.** Already true:
  `Prediction` and `Observation` are unrelated types with no conversion
  function between them anywhere in the codebase.
- **Observations must not automatically become canonical truth.** Already
  true and explicitly not-yet-crossed even for `DerivedValue` (Phase 14 §O);
  the DAF must not build a shortcut around this incomplete crossing rule.
- **Domain-specific acquisition adapters must not redefine core identity
  semantics.** A materials-paper adapter, a real-estate-listing adapter, and
  a commodities-feed adapter must all still produce `RawDocument`/
  `ExtractionCandidate` shapes that flow through the *same*
  `evidence.types.make_*`/`evidence.admission.admit_*` functions — no
  adapter may mint its own `Observation.id` scheme or bypass `content_hash`.
- **Additional coupling hazard identified by this reconnaissance:**
  the DAF must not assume Track 1's `adapters/` package or `core.canonical`
  is a template or a dependency. They are unrelated. A future engineer
  extending `adapters/csv_adapter.py`/`json_adapter.py` thinking they are
  building "the CSV/JSON path into the DAF" would silently wire new data
  into the wrong (3D-scene) state system. This should be called out
  explicitly in any DAF README, since the naming collision (`adapters/`
  sounds exactly like what a DAF needs) is a realistic future mistake.
- **Additional coupling hazard:** the two independently-implemented
  content-hashing functions (`evidence.identity.content_hash` and
  `core.canonical.version.compute_version_id`) must not be silently unified
  by a future refactor that makes one call the other — they hash different
  payload shapes for different purposes, and the two tracks are supposed to
  remain independent per §0.

---

## 16. Representation evaluation criteria

Adopting the task's framework as a standing design invariant, and testing it
immediately against the representations already in this codebase to show
it's not vacuous:

For any representation `R`, before it is added to the DAF or accepted from
the DAF into Track 2, ask:

1. **What does `R` preserve?** (e.g. `Observation.content` preserves the
   full open extraction result; `RetrievalResult` preserves id-references
   only, not content — a real, already-made tradeoff.)
2. **What does `R` discard?** (e.g. `resolve_model_state_key` discards every
   `Observation.content` key except the ones named in `target_context` — a
   deliberate, domain-owned discard, not the DAF's to make.)
3. **What transformations does `R` enable?** (e.g. `TrustGraph` enables BFS
   traversal and connectivity/novelty metrics; it does not enable ranking,
   because nothing computes a ranking function over it.)
4. **What inference does `R` enable?** (e.g. `classify_epistemic_status`
   enables a 4-of-7-value classification; it does not enable confidence
   calibration, because no calibration model consumes `Observation.confidence`
   beyond the raw `1 - confidence` uncertainty metric.)
5. **What predictions does `R` enable?** (e.g. `ModelState` enables
   sample-mean/variance prediction only; it explicitly does not enable any
   physically-grounded or Bayesian prediction, by the module's own
   disclaimer.)
6. **What state transitions does `R` support?** (e.g. `Sample` supports
   exactly one transition, append; there is no revise/retract transition
   anywhere in the evidence or materials layers — matching the "nothing is
   ever marked stale or deleted" discipline.)
7. **What uncertainty does `R` preserve?** (e.g. `Observation.confidence` is
   preserved through admission and through `evidence.metrics`, but is
   **not** read at all by `retrieval.epistemic.classify_epistemic_status`,
   which reads `extraction_method` instead — a real, checkable gap worth
   knowing before assuming confidence propagates everywhere it sounds like
   it should.)
8. **What provenance does `R` preserve?** (e.g. `ContextPackage` preserves
   `evidence_version_ids` — which pool snapshot(s) contributed — but per
   §3's fingerprint-vs-reconstructability distinction, this proves
   identifiability, not recoverability of prior contents.)
9. **What computational substrates can execute over `R`?** (e.g. Morpho can
   execute over `ProjectedState`/`MorphoDocument`, never over `Observation`
   or `ModelState` — the two tracks' substrates do not cross.)
10. **What downstream systems consume `R`?** (e.g. `RetrievalResult` is
    consumed only by `ContextPackage` construction today — nothing else in
    the repo consumes it directly.)

**Applying this to the DAF's own eventual output** (a `RawDocument`/
`ExtractionCandidate` pair, and the resulting admitted `Observation`): it
must preserve the full source payload and both context concepts named in
§10 (comparison-eligible content and any criterion/target context that
motivated the acquisition); it may discard nothing that a downstream
domain's coordinate-resolution function might need, because — per §9 — the
DAF is not the layer allowed to decide what's needed.

---

## 17. Unresolved questions

Carried over honestly from the codebase's own self-assessment, plus a few
raised by this reconnaissance:

1. **Entity-resolution/deduplication methodology** — `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md`
   §S names this a genuinely unresolved research question, not just
   deferred work. `Referent` identity is exact-match on
   `(natural_key, kind)`; nothing fuzzy-matches "FEP" and "Teflon FEP." The
   DAF will surface this gap immediately at any real scale (many sources
   naming the same real-world entity differently) — it is not the DAF's job
   to solve it, but the DAF's adapters will be the primary source of the
   duplicate `Referent`s that make this problem visible.
2. **Confidence/source-quality scoring methodology** — likewise named
   unresolved research in the same doc. `source_diversity` is explicitly
   **not** quality-weighted today. The DAF will be the primary source of
   variance in source quality (a peer-reviewed paper vs. a scraped listing
   vs. a self-reported API field) and has no existing scoring model to plug
   into.
3. **Per-change provenance collapse** — `docs/PHASE_13_ARCHITECTURE_INVESTIGATION.md`
   documents that `validate_candidate` (Track 1) currently derives the whole
   accepted `Version.provenance` from only the *first* `Change` in a batch,
   silently discarding the rest. This is Track 1's bug, not Track 2's, and
   the DAF (feeding Track 2) is not directly exposed to it — flagged here
   only so a future engineer doesn't assume Track 1's provenance model is a
   safe pattern to copy for DAF-level multi-source batch admission.
4. **Whether `Sequence`/`Composite` Morpho IR constructs (proposed,
   "IMPLEMENTATION READY," in `docs/PHASE_13_ARCHITECTURE_INVESTIGATION.md`)
   were ever actually implemented** — this reconnaissance did not verify
   `morpho/ir.py`'s current contents against that proposal. Irrelevant to
   the DAF (Track 1 concern) but worth resolving before any future work that
   assumes it.
5. **What a real, durable `EvidencePool` backing store should be** — this
   task deliberately does not choose one (§12, and the task's own
   prohibition on choosing infrastructure now). It is the first concrete
   decision the *next* phase of DAF work will need to make.
6. **How acquisition scheduling/policy should work** — nothing in the
   existing codebase does this at all today (§14, item 5). This is
   genuinely new design territory with no existing precedent in the repo to
   reuse, beyond the general observation that `experiment/`'s
   sequencing-without-new-math pattern is a reasonable style template even
   though its concrete `ActionDispatcher` shape (dispatching a physical lab
   action) doesn't fit acquisition actions directly.
7. **Whether/how the Phase 14 §O crossing rule (`DerivedValue` →
   `CandidateDelta`) should ever be implemented, and by whom** — this is a
   Track 2-internal decision the DAF does not need to make, but the DAF's
   evidence output is exactly what would eventually feed a `DerivedValue`
   review step, so the DAF's data contract should not foreclose it (§13).

---

## 18. Recommended repository architecture (still architecture-only — no
code, no packages)

Given §8's boundary and §11's multi-model conclusion, the DAF's own eventual
internal shape (not built yet, described only for planning) should mirror
the discipline already proven in `evidence/`/`scout/`:

```
DAF (new repository / package, domain-agnostic)
  ├── contracts/        -- re-exports or thin re-implementations of the
  │                        EXISTING scout.interface Protocols (RawDocument,
  │                        SourceAdapter, ExtractionCandidate, Extractor) --
  │                        never a competing, DAF-invented shape
  ├── adapters/<domain>/  -- one subpackage per domain (materials-literature,
  │                          real-estate, commodities, logistics, ...),
  │                          each implementing SourceAdapter + Extractor
  │                          against real sources instead of fixtures
  ├── storage/           -- durable, content-addressed, append-only backing
  │                          store underneath EvidencePool's existing
  │                          public contract (new; the one genuinely new
  │                          infrastructure surface)
  ├── scheduling/         -- acquisition policy/scheduling (new; §14 item 5,
  │                          §17 item 6)
  └── (explicitly no `model_state`, `canonical`, `morpho`, or `retrieval`
       subpackage -- those remain owned by the existing State-Space repo)
```

The DAF should depend on the SSA repo's `evidence`/`scout` packages (or a
versioned copy of their Protocols, if independent deployability is required
— a decision explicitly out of scope here); it must not depend on
`materials`, `experiment`, `workbench`, `core`, `morpho`, `backends`, or
`runtime`.

---

## 19. Phased implementation sequence (planning only)

1. **Contract alignment** — confirm (or, if the DAF must be a separate
   deployable, formally version) the exact `scout.interface` Protocol shapes
   the DAF will implement against. No new types invented at this stage.
2. **Durable evidence storage** — implement the persistence layer beneath
   `EvidencePool`'s existing contract (§14 item 4, §17 item 5). This unblocks
   everything else, since without it any DAF-acquired evidence disappears
   when the process exits.
3. **First real domain adapter** — one `SourceAdapter` + `Extractor` pair for
   one real, permitted external source (e.g. a literature/patent API for the
   existing materials domain, since `materials/` already exists to consume
   the resulting evidence end-to-end). Prove the full loop:
   real source → `RawDocument` → admitted `Observation`/`Referent`/
   `ClaimedRelationship` → retrievable via the unmodified `retrieval/`
   layer → consumable by `materials.results.admit_experimental_result` and
   `materials.model_state.update`, exactly as fixture data is today.
4. **Acquisition scheduling (minimal)** — a simple, human/config-triggered
   scheduler that runs adapters on a cadence or on demand; explicitly not
   yet information-gap-driven.
5. **Additional domain adapters** — repeat step 3 for further domains,
   confirming the evidence substrate genuinely stays domain-agnostic (no new
   fields added to `evidence.types` to accommodate a new domain — if one is
   ever needed, that is a signal the boundary in §9/§11 has been violated).
6. **(Future, not this phase)** Information-gap-driven acquisition — only
   once a domain's `InformationValueModel` (materials/information.py's
   Protocol, or an equivalent for a new domain) has a real, non-placeholder
   implementation, and only once `evidence.fep_interface.FEPSignal
   .expected_information_gain` has an actual estimator. Wiring this before
   either exists would create an acquisition-priority signal with nothing
   real behind it.

For each new abstraction proposed anywhere above, the required justification:

| Abstraction | Why doesn't it already exist? | Capability missing | Owner | Canonical/derived | Dynamics/inference enabled |
|---|---|---|---|---|---|
| Real `SourceAdapter`/`Extractor` implementations | Only fixtures exist; no one has built a live adapter yet | Actual external-world acquisition | DAF | n/a (producers) | Enables `scout/pipeline.py::run_scout` to admit real evidence instead of fixture evidence — no new dynamics, just real inputs to existing ones |
| Durable evidence storage | `EvidencePool` was deliberately scoped in-memory-only for this phase of Track 2's own development | Evidence surviving past one process | DAF | derived storage of canonical-for-evidence objects; never authoritative beyond what `evidence.admission` already grants them | Enables replay/audit and multi-session retrieval; no new inference |
| Acquisition scheduling/policy | Never built; SCOUT has only ever been invoked directly in tests | Deciding when/what to acquire | DAF | derived (policy) | Enables the *volume* of evidence needed for `materials.iteration`'s gap-analysis loop to have something new to close; no new inference itself |

No other new abstraction (a generic `StateProjection`, a generic
`InformationGap`, a DAF-level `ModelState`) is justified by this
reconnaissance — each would either duplicate an existing, working construct
in Track 2, or would require deciding something (domain-specific state
resolution, information-value estimation) that the codebase's own history
(Phase 53, Phase 13's Option-A rejection) shows should not be decided
upstream of the domain that needs it.

---

## 20. Summary: the composable architecture

```
WORLD
  │
  ▼
DAF acquisition (NEW: real SourceAdapter/Extractor implementations,
                 durable storage, scheduling)
  │
  ▼
scout.pipeline.run_scout  (EXISTING, unmodified — the admission gate)
  │
  ▼
evidence.pool.EvidencePool  (EXISTING; DAF adds durability underneath it)
  │
  ├─▶ evidence.trust_graph.TrustGraph  (EXISTING, derived)
  │
  ▼
retrieval.*  (EXISTING, unmodified, read-only) ──▶ ContextPackage ──▶ [InquirySeam marker;
                                                                        InquiryState: future,
                                                                        not this phase]
  │
  ▼ (domain-specific, e.g. materials.results.admit_experimental_result)
Domain state-space model (materials/ exists; markets/, logistics/,
real-estate/, industrial/ would each be new, analogous packages —
NEVER a DAF or evidence-layer responsibility)
  │
  ▼
predict / update  (EXISTING pattern, per domain)
  │
  ▼
Prediction, ModelState_(t+1)
  │
  ▼ (future, NOT this phase)
Information gap (evidence.fep_interface.FEPSignal.expected_information_gain
                 — currently always None, no estimator exists)
  │
  ▼ (future, NOT this phase)
Acquisition request ──────────────────────────────────────────▶ back to DAF
```

Each stage above remains independently replaceable, exactly as the existing
repo's own boundary tests already enforce for `evidence/`↔`retrieval/`↔
`materials/`. The DAF's job is to become a trustworthy, domain-agnostic,
durable producer at the top of this chain — nothing more, and, per every
coupling rule in §15, nothing else.
