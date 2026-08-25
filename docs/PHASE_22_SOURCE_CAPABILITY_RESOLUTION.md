# Phase 22 — Source Capability and Scientific Requirement Resolution

*(Continues from `95c900e`. Closes Phase 21's named frontier: sources had no
semantic capability metadata, so a caller had to choose `source_id` by hand.)*

## The chain, executable

```
      ModelState_t -> InformationGap -> EvidenceRequirement     science/ + materials/
                                              |
                                              v  intent_for()   science/
                                     AcquisitionIntent          boundary/ (neutral)
                                              |
                                              v  resolve_sources()   bridge/  <-- NEW
                                     CandidateSource[]  + CapabilityMismatch[]
                                              |
                                              v  EXPLICIT human/application selection
                                     operationalize_intent()          bridge/ (Phase 21)
                                              |
                                              v  execute_plan()       daf/ (unchanged)
                            DAF -> SCOUT -> DurablePool -> Observation
                                              |
                                              v  update()  <-- EXPLICIT caller step
                                     ModelState_(t+1)
```

Selection stays explicit. Nothing auto-executes the first candidate.

---

## 1. Pre-implementation audit

Read at HEAD. Three findings decided the whole design.

**`SourceDefinition.capabilities` already exists — and already means something
else.** It is an *acquisition-mode* vocabulary (`"incremental"`, `"snapshot"`,
`"read"`), and `daf/catalog/plan.py:116` reads it to decide whether incremental
mode is supported. Overloading it with scientific meaning would silently change
plan validation.

**`SourceDefinition.configuration` is stored but never read by any logic.** It
round-trips through `SourceCatalog` and is otherwise inert. Hiding capability
declarations there would make them untyped, unvalidated, and indistinguishable
from adapter configuration.

**Nothing anywhere records scientific capability.** Phase 21's finding stands
unchanged: no field records which subjects, properties, or conditioning contexts a
source can supply.

### Current source metadata, in full

| Field | Meaning today | Usable for scientific capability? |
|---|---|---|
| `source_id`, `name`, `domain` | identity and labels | `domain` is a free-text label, not a vocabulary |
| `adapter_id` | which adapter acquires it | mechanism, not capability |
| `configuration` | free-form, **never read** | untyped bag — rejected |
| `capabilities` | acquisition modes, **read by `plan.py`** | already taken — rejected |
| `required_parameters` | the plan's parameter contract | acquisition vocabulary, not scientific |
| `enabled` | catalog state | used by resolution, unchanged |

### Two corrections to the brief

- **`daf/catalog/source_registry.py` does not exist.** `SourceDefinition` and
  `SourceRegistry` live in `daf/orchestration/source_registry.py`;
  `daf/catalog/source_catalog.py` is the persisting subclass.
- **`science/intent_execution.py` does not exist.** Phase 21 placed it at
  `bridge/intent_execution.py`, precisely because it may name both sides.

---

## 2. Minimum capability representation

```python
@dataclass(frozen=True)
class SourceCapability:
    source_id: str
    properties: Tuple[str, ...] = ()
    subject_kinds: Tuple[str, ...] = ()
    roles: Tuple[str, ...] = ()
    context_keys: Tuple[str, ...] = ()
```

Each dimension is present because it was **measured to discriminate** between the
real sources and the real intents in this repository:

| Dimension | Discriminates | Evidence |
|---|---|---|
| `properties` | `tensile_strength` vs `water_level` vs `magnitude` | the coarsest filter; rejects NOAA and USGS outright |
| `subject_kinds` | `formulation` vs `monitoring_station` vs `earthquake_event` | a source can report a property about one kind of subject and not another — tested in isolation, where the property matches and the kind does not |
| `roles` | OBSERVED vs PREDICTED | **Phase 20 emits BOTH roles for one criterion.** Without this, a measurement dataset is offered as a candidate for a request for a prediction |
| `context_keys` | `temperature` vs `datum` | a source that cannot condition on temperature cannot answer a 25 °C question |

`roles` is the one dimension §6 did not list. It was included only after checking
that Phase 20 really does produce a `PREDICTED` intent — without it, that intent
matches a tensile dataset, which is a false match of exactly the kind this layer
exists to prevent.

No confidence score, weight, or rank exists on any of these types (§5, §14).

---

## 3. Where it lives, and why `daf/` was not modified

**Zero files in `daf/` changed.** Capability metadata is descriptive catalog state
(§11), so it does not have to be a field on `SourceDefinition` — and keeping it
separate buys three things at once:

1. **Existing acquisition behaviour is provably untouched**, because no adapter,
   catalog, serializer, or validator was modified.
2. **"Unknown" is the natural default.** A source with no entry has no entry; it
   cannot accidentally inherit eligibility.
3. **The dependency direction survives.** A capability declaration naming the
   neutral scientific vocabulary inside `SourceDefinition` would force `daf` to
   import `boundary`, which Phase 21 asserted it must not.

### Why matching is against `AcquisitionIntent`, not `EvidenceRequirement`

§5 suggests `resolve_sources(requirement, catalog)`. An `EvidenceRequirement` is a
`materials` type, so a matcher taking one would import `materials` — and would
then be unable to read `SourceDefinition`. That is the same trap Phases 20 and 21
navigated.

`AcquisitionIntent` is already the neutral statement of what evidence is wanted and
already carries exactly the discriminating fields. Matching against it keeps the
resolver free of any scientific import, and leaves
`science.acquisition_seam.intent_for` as the single translation. Dependency
directions, all AST-asserted:

```
science  -> materials, boundary        never daf, never bridge
boundary -> evidence only              never materials/daf/science/bridge
bridge   -> boundary + daf             never materials, never science
daf      -> evidence                   never materials/science/boundary/bridge
```

---

## 4–6. Matching semantics

A source is a candidate **only if** it is registered, enabled, and *positively
declares* the intent's property, subject kind, role, and **every** key of its
conditioning context. Everything else is a mismatch, reported with reasons.

```
intent: tensile_strength / formulation / OBSERVED / {}

candidates: ['materials-tensile']
  reject empty-declaration  (NOT_REGISTERED, PROPERTY_NOT_DECLARED,
                             ROLE_NOT_DECLARED, SUBJECT_KIND_NOT_DECLARED)
  reject materials-disabled (DISABLED,)
  reject noaa-water         (PROPERTY_NOT_DECLARED, SUBJECT_KIND_NOT_DECLARED)
  reject usgs-quake         (PROPERTY_NOT_DECLARED, SUBJECT_KIND_NOT_DECLARED)

intent: tensile_strength / formulation / OBSERVED / {temperature: 25, unit: C}
candidates: ['materials-tensile']   matched context ('temperature','temperature_unit')

intent: tensile_strength / formulation / PREDICTED / {}
candidates: []                       ROLE_NOT_DECLARED
```

**Mismatches are returned, not discarded.** "Nothing matched" is otherwise
indistinguishable from "nothing was declared", and the difference matters to an
operator.

---

## 5. Context semantics (§7)

Two different questions, deliberately kept apart:

| Step | Question | Vocabulary |
|---|---|---|
| `resolve_sources` | does this source have the **scientific capability** to condition on `temperature`? | scientific (`temperature`, `datum`) |
| `operationalize_intent` (Phase 21) | can that context be **mapped into this source's request parameters**? | acquisition (`begin_date`, `station`, `path`) |

A source can therefore be a legitimate candidate and still fail to operationalize —
that is correct, not a defect. Collapsing the two would either let a source claim
capability it cannot express, or reject a capable source for a mapping the caller
had not yet supplied.

---

## 6. Unknown-capability semantics (§10)

> **Unknown stays unknown. Silence is never compatibility.**

- A registered, enabled source with **no** `SourceCapability` is not considered at
  all: it appears in neither candidates nor mismatches. Asserted for
  `undeclared-src`.
- A source declaring **nothing** (`SourceCapability("x")`) is rejected on every
  dimension.
- A capability naming an **unregistered** source is reported `NOT_REGISTERED`, never
  offered — a stale declaration cannot resurrect a source.
- **Explicit `source_id` + plan continues to work exactly as before**, with no
  capability declaration anywhere. Asserted directly by acquiring through
  `undeclared-src`.

---

## 7. Identity (§11, §15K)

Nothing about identity changed. Capability metadata is descriptive catalog state:
it is not evidence identity, not scientific-state identity, not execution identity.
Acquiring with declarations present produces byte-identical artifact ids and
observation ids, because **nothing in the acquisition path consults them**.

No catalog revision or versioning mechanism was invented: the existing catalog is
already mutable (`SourceCatalog.register` overwrites), and nothing in this phase
requires more. `capability_index` documents that later declarations replace earlier
ones — ordinary mutable-catalog behaviour, stated rather than hidden.

---

## 8. Integration with Phase 21, end to end

`test_requirement_to_candidate_to_acquisition_to_next_state` runs the whole chain
against the real DAF pipeline: gap → requirement → intent → **resolution** →
explicit selection → `operationalize_intent` → `execute_plan` → SCOUT → DurablePool
→ `analyze` (values 91 and 88 present) → and only then, by an explicit caller call,
`update` → `ModelState_(t+1)`.

Resolution and acquisition both leave the state at one sample; only the explicit
`update` moves it. **Capability resolution ≠ acquisition ≠ state transition** stays
an executable fact.

---

## 9. Tests and validation

`tests/test_source_capability_resolution.py` — 13 tests covering §15 A–K and §16:

| § | Test |
|---|---|
| A, G | `test_resolution_is_deterministic_and_explains_each_match` |
| B, 8 | `test_structurally_different_sources_are_rejected_not_offered` |
| C | `test_subject_kind_mismatch_alone_is_enough_to_reject` |
| D | `test_undeclared_context_rejects_and_names_the_missing_keys` |
| role | `test_role_is_a_real_discriminator` |
| E, 10 | `test_unknown_and_empty_declarations_never_match` |
| F | `test_disabled_source_never_matches` |
| stale | `test_a_capability_for_an_unregistered_source_is_reported_not_offered` |
| J | `test_resolution_performs_no_acquisition_and_touches_no_pool` |
| 12, H, I | `test_requirement_to_candidate_to_acquisition_to_next_state` |
| K | `test_capability_metadata_changes_no_identity` |
| H, 10 | `test_existing_explicit_acquisition_is_completely_unaffected` |
| 16 | `test_capability_resolution_lives_where_the_dependencies_allow` |

| Check | Result |
|---|---|
| DAF suite | **373 passed** (360 prior + 13 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git status --short` clean |
| `mypy daf/ science/ boundary/ bridge/` | Success, 54 source files |
| `ruff` (new files) | 18 findings, all `UP006`/`UP035`/`UP045`/`I001` repo-wide conventions — none genuine |
| Changed files | `bridge/source_capability.py`, `tests/test_source_capability_resolution.py`. **Purely additive; zero files in `daf/` changed** |

§19's confirmations: no adapter semantics broken (no adapter touched); no SCOUT
modification; no `materials`/`model_state` modification; no wall-clock read (the
resolver takes no time input at all); no network access; no `EvidencePool` access;
no automatic acquisition; no automatic state transition.

---

## 10. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **Reuse `SourceDefinition.capabilities`** | Already an acquisition-mode vocabulary read by `plan.py:116`. Overloading it would silently alter incremental-mode validation |
| **Put declarations in `configuration`** | Untyped, unvalidated, and indistinguishable from adapter configuration; nothing would prevent drift |
| **Add a capability field to `SourceDefinition`** | Would modify `daf/` (registry, catalog, serialization) for metadata nothing in the acquisition path reads, and would force `daf` to import the neutral vocabulary |
| **Match on `EvidenceRequirement`** | Forces `materials` into the matcher, which then cannot read `SourceDefinition` |
| **Infer capability from `adapter_id` or `domain`** | §2 forbids inferring capabilities from adapter names, and `domain` is free text |
| **Default undeclared sources to "compatible"** | The single most dangerous option: every source becomes eligible for every requirement. §10 is explicit |
| **Score or rank candidates** | Expected information gain by another name; remains `NOT_DETERMINABLE` |
| **A new top-level package** | `bridge/` is already the layer permitted to name an intent and a source. §16 says resolve from actual dependency structure |

---

## 11. Information-value boundary

Unchanged: `expected_information_gain` remains `NOT_DETERMINABLE`. Capability
matching answers *"could this source potentially satisfy the requirement?"*.
Information value asks *"how valuable would acquiring from it be?"*. Candidates are
returned in `source_id` order — deterministic without implying preference.

---

## 12. Remaining frontier

Deliberately not built: source ranking by information value, autonomous source
selection, expected information gain, active learning, FEP-driven acquisition, SCG
control, execution proofs, Bayesian optimization, Gaussian processes, scheduler
daemons, ontology expansion.

What a future phase would have to decide first, from this phase's evidence:

1. **Where capability declarations are authored and persisted.** They currently
   live in caller-supplied objects. Persisting them means either a new catalog file
   or a `SourceDefinition` field — the second re-opens the dependency question
   §3 answers here.
2. **Whether the property/subject vocabulary needs governance.** Matching is exact
   string equality today. `tensile_strength` vs `ultimate_tensile_strength` would
   not match, and deciding they are the same is an ontology decision this phase
   deliberately refused to make.
3. **Whether capability implies obligation.** A candidate says a source *could*
   supply the evidence, never that it *will*. Any autonomy built on top must keep
   that distinction or it will silently promise results.

Only after (2) could resolution be trusted across independently authored
catalogs — and autonomous selection should remain a deliberate decision about
autonomy, not a convenience.

---

*Halts here per the stop condition: audited, minimum representation measured and
built, run, observed, validated, documented, committed and pushed. Phase 23 is not
begun.*
