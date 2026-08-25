# Phase 23 — Scientific Capability Vocabulary Normalization

*(Continues from `2d3f43d`. Closes Phase 22's named frontier: capability matching
was exact string equality, so `tensile_strength` and `ultimate_tensile_strength`
could never meet.)*

## The chain

```
   lexical requirement  ("UTS")
            |
            v  explicit, declared mapping        bridge/vocabulary.py   <-- NEW
   canonical concept    ("tensile_strength")
            |
            v  resolve_sources(..., vocabulary)  bridge/source_capability.py
   CandidateSource[]  carrying requested / canonical / declared
            |
            v  EXPLICIT selection
   operationalize_intent()  ->  AcquisitionPlan  ->  DAF -> SCOUT -> Evidence
```

---

## 1. Pre-implementation audit

Searched the whole repository for `alias`, `synonym`, `canonical`, `normalize`,
`vocabulary`, `concept`, `ontology`, `property name`, `subject kind`, `semantic
equivalence` — across `daf/`, `science/`, `boundary/`, `bridge/`, `tests/`, **and**
the vendored State-Space system.

**There is no vocabulary, alias, canonical or normalization primitive anywhere.**
What exists instead are repeated *refusals* to invent one:

- `materials/program.py:68` — `Referent.kind` "has no controlled vocabulary
  anywhere in the" system.
- every DAF extractor docstring declines to assert a domain ontology
  (`graph_dataset.py:11`, `noaa_water_level.py:4`, `usgs_earthquakes.py:4`,
  `local_dataset.py:9`).
- `materials/value.py:34` uses the word "synonyms" only to describe two of its own
  internal constants.

So there was nothing to reuse, and a new representation is justified.

---

## 2. Measured lexical divergence — and the honest result

| Source | property | subject kinds | context keys |
|---|---|---|---|
| `graph_dataset` | record-declared (`tensile_strength` in fixtures) | `formulation`, `process` | record-declared |
| `noaa_water_level_measurements` | `water_level` | `monitoring_station`, `vertical_datum` | `datum`, `unit` |
| `arxiv` | — | `paper`, `author` | — |
| `usgs` / `edgar` / `local_dataset` / `incremental_dataset` | — | — | — |

> **No two labels in this repository denote the same scientific concept today.**
> The two property-emitting sources mean genuinely different things.

Per §3, the `UTS → tensile_strength` mappings in the tests are therefore a
**deliberate proof fixture demonstrating the mechanism** — not a production
ontology, and not a claim about materials science. This is stated in the module
docstring and the test docstring as well as here, so it cannot be mistaken for
domain content later.

The *mechanism* is still justified: Phase 22 named this as its own frontier, and
independently authored catalogs diverge the moment there is more than one author.

---

## 3. Representation

```python
DIMENSIONS = ("property", "subject_kind", "role", "context_key")

@dataclass(frozen=True)
class VocabularyMapping:
    dimension: str
    alias: str
    canonical: str

@dataclass(frozen=True)
class Vocabulary:            # built only by make_vocabulary()
    mappings: Tuple[VocabularyMapping, ...]
    def canonical_for(dimension, term) -> str   # identity when unmapped
    def declares(dimension, term) -> bool
```

Smaller than §4's sketch: no `source` or `status` field, because nothing in the
repository consumes either, and adding them would be descriptive completeness
rather than enabled inference.

`EMPTY_VOCABULARY` is the default everywhere.

---

## 4. Normalization semantics

**Identity when unmapped.** `canonical_for` returns the term unchanged if nothing
declares it. This is what makes the layer strictly additive: two unmapped terms are
compared literally, so `strength` still does not match `tensile_strength`, and
**no existing Phase 22 match changes**. All 13 Phase 22 tests pass unmodified.

**Both sides are canonicalized.** A match can arise from an alias on the
requirement side, on the source side, or on neither — asserted for all three.

**Exactly one hop; chains are rejected, not followed.** If `UTS → X` and
`X → tensile_strength` both existed, `UTS` would have two canonical forms depending
on where you entered the chain. Following it transitively would be inference, so
`make_vocabulary` **refuses** any vocabulary where a term is both an alias and a
canonical target in the same dimension.

**Dimensions are independent namespaces** (§7). A `PROPERTY` mapping
`station → formulation` has no effect whatsoever on subject-kind comparison —
asserted directly. The same alias may be declared in two dimensions without
conflict, because they cannot interact.

**Direction is one-way** (§9). `alias → canonical` never implies the reverse.
Nothing here can generate an acquisition parameter named `UTS`; the full
composition test asserts `"UTS" not in plan.parameters`. Request-parameter
translation remains Phase 21's separate, caller-supplied mapping.

**Case is not normalized.** `Tensile_Strength` does not match `tensile_strength`.
Case folding is a lexical guess, and this layer makes none.

---

## 5. Ambiguity semantics

Two conditions make a vocabulary un-canonicalizable, and both raise
`AmbiguousVocabulary` at construction rather than being resolved:

| Condition | Example |
|---|---|
| one alias, two canonical targets | `UTS → tensile_strength` **and** `UTS → ultimate_modulus` |
| a chain | `UTS → interim_term` **and** `interim_term → tensile_strength` |

Rejection is **order-independent** — `make_vocabulary` sorts its input before
validating, and the test builds both orderings. No interpretation is ever selected,
so declaration order can never become significant.

---

## 6. Provenance / explanation (§5, §10)

Each matched dimension yields a `TermMatch` answering all three questions at once:

```
requested   UTS                        what the scientist asked
canonical   tensile_strength           what the catalog explicitly mapped it to
declared    ultimate_tensile_strength  what the SOURCE calls it
via_alias   True                       whether any mapping was actually used
```

The source's declaration is **never overwritten** — `SourceCapability.properties`
still reads `("ultimate_tensile_strength",)` after a match. `via_alias` separates a
match that needed a mapping from one that did not, so exact matches remain
distinguishable from normalized ones. No new provenance ledger was introduced; a
deterministic explanation is sufficient, as §10 allows.

---

## 7. Dependency direction

Unchanged, and still AST-asserted by the Phase 22 suite:

```
science  -> materials, boundary        never daf, never bridge
boundary -> evidence only              never materials/daf/science/bridge
bridge   -> boundary + daf             never materials, never science
daf      -> evidence                   never materials/science/boundary/bridge
```

`bridge/vocabulary.py` imports **nothing beyond `dataclasses` and `typing`** — it
operates on plain strings, so it introduces no dependency in any direction.
Asserted at AST level in `test_the_vocabulary_module_can_reach_nothing_impure`,
which also rules out `os`, `io`, `sys`, `socket`, `random`, `time`, `datetime`,
`pathlib`, `urllib`, `requests`, `sqlite3`, `subprocess`, `secrets` and `uuid`.

### A note on placement

The module lives in `bridge/`, **not** `science/`. It is semantic infrastructure,
and §4's three invariants hold for it trivially and are asserted directly — it
imports no `daf`, introduces no reverse dependency, and no DAF module imports it
(`test_daf_never_imports_the_normalization_layer`, an AST check over every file in
`daf/`).

Moving it to `science/` would actively break a standing invariant: its only
consumer is `bridge.source_capability.resolve_sources`, so `bridge` would then have
to import `science`, which Phases 21 and 22 assert it never does. Placement was
resolved from the actual dependency structure, as Phase 22 §16 required, and the
module sits beside its only consumer. If a future caller needs to canonicalize a
requirement's terms *before* an intent exists, `boundary/` — importable by every
layer — would be the right home; nothing needs that today.

That AST check found a real defect in its own first draft: a naive substring search
for `"vocabulary"` flagged `daf/adapters/usgs_earthquakes.py`, which uses the word
in prose ("the fixed vocabulary of values this adapter ever substitutes"). The test
now inspects imports rather than text.

---

## 8. Phase 22 integration

`resolve_sources` gained one optional parameter, `vocabulary=EMPTY_VOCABULARY`.
Omitting it reproduces exact-string matching precisely.

Measured, with the same source and the same requirement, the only difference being
a declared mapping:

```
no vocabulary            candidates: []            PROPERTY_NOT_DECLARED
with vocabulary
  tensile_strength       MATCH   declared=ultimate_tensile_strength  via_alias=True
  UTS                    MATCH   canonical=tensile_strength          via_alias=True
  strength               no match (PROPERTY_NOT_DECLARED)
  tensile_modulus        no match (PROPERTY_NOT_DECLARED)

cross-dimension property alias -> subject:  SUBJECT_KIND_NOT_DECLARED
ambiguity (two canonicals):  rejected, order-independent
ambiguity (chain):           rejected
```

Both halves of §14 hold: an explicit alias turns a previously rejected candidate
into a valid one, **and** an unrelated term stays rejected.

---

## 8b. Identity, measured rather than argued

§6 asked for an empirical before/after. The **same dataset** is acquired twice
through two different routes to the same plan:

| arm | how the candidate was reached |
|---|---|
| A | source already speaks canonically; `EMPTY_VOCABULARY` |
| B | source says `ultimate_tensile_strength`; reachable **only** through the mapping |

Both arms are asserted byte-identical across `plan_id`, `source_id`,
`artifact_id`, `version_id`, evidence `Source.id`, `Document.id`, `Record.id` and
`Observation.id`. `AcquisitionRequest` semantics are checked separately, and
`ModelState` ids are shown unchanged by a resolution call. Normalization
participates in no content hash anywhere.

---

## 9. Tests and validation

`tests/test_vocabulary_normalization.py` — 29 tests:

| § | Test |
|---|---|
| A, 14 | `test_an_explicit_alias_turns_a_rejected_source_into_a_candidate` |
| A | `test_the_requirement_side_may_also_be_an_alias` |
| B | `test_exact_matching_still_works_with_no_vocabulary_at_all` |
| C, 17 | `test_lexically_similar_terms_never_match_without_an_explicit_mapping` (6 parametrized cases) |
| 14 | `test_an_unrelated_source_stays_rejected_even_with_a_vocabulary` |
| D, 12 | `test_one_alias_with_two_canonical_targets_is_rejected` |
| D | `test_a_chain_is_rejected_rather_than_followed` |
| 7 | `test_the_same_alias_in_two_dimensions_is_not_a_conflict` |
| 11 | `test_malformed_mappings_are_rejected_at_construction` |
| E, 7 | `test_a_property_alias_cannot_satisfy_subject_matching` |
| E | `test_context_keys_normalize_in_their_own_dimension` |
| F, 5, 10 | `test_source_terminology_is_preserved_alongside_the_canonical_concept` |
| G | `test_normalization_is_deterministic_and_order_independent` |
| H | `test_unrelated_mappings_do_not_change_existing_matches` |
| 9 | `test_direction_is_one_way` |
| I, 13 | `test_normalization_changes_no_identity_and_acquires_nothing` |
| J | `test_full_composition_from_alias_requirement_to_acquired_evidence` |
| 1.13 | `test_a_property_mapping_never_changes_the_role` |
| 1.12 | `test_normalizing_one_context_key_leaves_the_others_untouched` |
| 5 | `test_the_vocabulary_module_can_reach_nothing_impure` |
| 4 | `test_daf_never_imports_the_normalization_layer` |
| 1.9, 6 | `test_normalization_changes_no_acquisition_or_evidence_identity` |
| 1.9 | `test_normalization_changes_no_model_state_identity` |
| 8 | `test_a_canonical_requirement_never_generates_a_source_flavoured_parameter` |

| Check | Result |
|---|---|
| DAF suite | **402 passed** (373 prior + 29 new) |
| Phase 22 suite | **13 passed, unmodified** — backward compatibility |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git status --short` clean |
| `mypy daf/ science/ boundary/ bridge/` | Success, 55 source files |
| `ruff` | 32 findings, all `UP006`/`UP035`/`UP045`/`I001` repo-wide conventions — none genuine. One `RUF059` was found and fixed |
| Changed files | `bridge/vocabulary.py` (new), `tests/test_vocabulary_normalization.py` (new), `bridge/source_capability.py` (one optional parameter + `TermMatch`). **Zero changes in `daf/`, `science/`, `boundary/`** |

§21's confirmations: DAF acquisition behaviour unchanged (no file in `daf/`
touched); SCOUT unchanged; `materials`/`model_state` unchanged; no network access;
no `EvidencePool` access; no state mutation; no wall-clock dependency (the
normalizer takes no time input at all); no automatic source selection; no
information-value scoring.

---

## 10. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **Transitive chain resolution** | Inference. The canonical form would depend on chain entry point; rejected at validation instead |
| **Case-insensitive or fuzzy matching** | Lexical guessing. `Tensile_Strength` is asserted *not* to match |
| **Prefix/substring rules** (`strength` ⊂ `tensile_strength`) | Would silently broaden requirements — §6's explicit prohibition |
| **Embeddings / LLM semantic matching** | §18. Non-deterministic and uninspectable |
| **RDF/OWL/SHACL** | §1. A universal ontology for a repository with zero measured synonyms |
| **A shared cross-dimensional term table** | Would let `station → formulation` leak between dimensions |
| **Rewriting `SourceCapability` in place** | Destroys the source's own terminology, which §5 requires preserving |
| **`source`/`status` fields on the mapping** | Nothing consumes them; descriptive completeness rather than enabled inference |
| **A required (non-optional) vocabulary parameter** | Would change every Phase 22 call site and risk altering existing matches |

---

## 11. Future ontology boundary

**Phase 23 is not an ontology system.** It provides *explicit vocabulary
normalization*: every equivalence is a line someone wrote down.

It does **not** provide semantic inference, hierarchical reasoning (`tensile_strength`
is-a `strength`), synonym discovery, ontology alignment, unit reasoning, embedding
similarity, or LLM interpretation. None of those may be smuggled into this layer —
the chain rejection and the case-sensitivity test exist specifically to keep the
line visible.

---

## 12. Remaining frontier

1. **Where vocabularies are authored and persisted.** They live in caller-supplied
   objects. Persisting them raises the same question Phase 22 answered for
   capabilities, and the answer may differ: a vocabulary is shared across catalogs,
   whereas a capability belongs to one source.
2. **Governance across independently authored catalogs.** Two catalogs can each be
   internally consistent and jointly ambiguous. `make_vocabulary` detects that only
   when the mappings are combined — so *when* they are combined becomes a real
   design decision.
3. **Units are still untouched.** `tensile_strength` in MPa and in psi are the same
   concept in different units. This layer normalizes names only; unit reasoning is
   a genuinely different mechanism and should not be added here by widening
   `context_key` mappings.

None of these should be taken as a step toward inference. Every one of them is
about *where explicit declarations live*, not about deriving new ones.

---

*Halts here per the stop condition: audited, divergence measured (and honestly
found absent), smallest representation built, run, observed, validated, documented,
committed and pushed. Phase 24 is not begun.*
