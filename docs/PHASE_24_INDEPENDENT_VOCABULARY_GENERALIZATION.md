# Phase 24 — Independent Scientific Vocabulary Generalization

*(Continues from `ff59ef4`.)*

## Outcome: **A — generalization succeeds**

Phase 23's mechanism carries independently authored terminology to real acquired
evidence **without an ontology**, using one small representation change that the
external evidence itself forced.

```
   "ultimate tensile strength"          independently authored terminology
              |
              v  explicit, evidence-cited mapping     bridge/vocabulary.py
   "tensile_strength"                   canonical concept
              |
              v  resolve_sources(..., vocabulary)     bridge/source_capability.py
   CandidateSource   ->  EXPLICIT selection  ->  operationalize_intent()
              |
              v  execute_plan()  ->  DAF -> SCOUT -> DurablePool -> analyze()
```

---

## 1. Audit — candidate sources investigated

| Source | Reachable | Outcome |
|---|---|---|
| MatWeb | ✗ HTTP 403 | bot-blocked |
| ASTM (E6 terminology) | ✗ HTTP 403 | paywalled/bot-blocked |
| Materials Project API | ✗ HTTP 401 | requires an API key |
| Springer Materials | ✗ no response | unreachable |
| NIST Chemistry WebBook | ✓ 200 | thermophysical, not mechanical terminology |
| Wikidata REST API | ✗ 429 / egress policy | blocked |
| **Wikidata SPARQL** (`query.wikidata.org`) | **✓ 200** | **selected** |

Wikidata's SPARQL endpoint was selected because it publishes **machine-readable,
citable, independently authored** label/alias sets per concept — not because it was
convenient. Every retrieved record is stored verbatim in
`tests/fixtures/wikidata_mechanical_property_terms.json` so each claim is
re-checkable rather than trusted.

### Terminology actually observed

| Entity | Label | Published English aliases |
|---|---|---|
| **Q76005** | ultimate tensile strength | `UTS`, `TS`, `tensile strength`, `ultimate strength`, **`tensile force`** |
| **P5479** | ultimate tensile strength *(property)* | `UTS`, `TS`, `Tensile strength`, `Rm`, `Ftu`, `stress at break` |
| **Q2091584** | Young's modulus | `Young modulus`, `modulus of elasticity`, **`elastic modulus`** |
| **Q192005** | elastic modulus | *(none)* — **a separate concept** |
| **Q3807177** / P5529 | yield strength | `yield stress`, `yield point` |
| **Q5459047** / P5681 | flexural modulus | `bending modulus` |

### Mappings encoded

| Alias | Canonical | Relationship | Evidence |
|---|---|---|---|
| `ultimate tensile strength` | `tensile_strength` | EXACT_EQUIVALENT | Q76005 |
| `UTS` | `tensile_strength` | EXACT_EQUIVALENT | Q76005 |
| `ultimate strength` | `tensile_strength` | EXACT_EQUIVALENT | Q76005 |
| `Rm`, `Ftu` | `tensile_strength` | EXACT_EQUIVALENT | P5479 |
| `modulus of elasticity` | `youngs_modulus` | EXACT_EQUIVALENT | Q2091584 |
| `Young modulus` | `youngs_modulus` | EXACT_EQUIVALENT | Q2091584 |
| `elastic modulus` | `youngs_modulus` | **RELATED_BUT_NOT_EQUIVALENT** | Q192005 |

### Mappings rejected, and why

**`tensile force` → `tensile_strength` — rejected.** Wikidata publishes it as an
alias of Q76005. It is wrong: force is measured in newtons, strength in pascals.
They are dimensionally different quantities, so the published alias set contains an
error. **An alias list is a starting point for curation, not an import.** Asserted
by `test_a_published_alias_was_deliberately_not_encoded`, which also checks the
fixture still contains the alias, so the test cannot quietly stop being about
anything.

**`elastic modulus` → `youngs_modulus` — rejected as an equivalence, recorded as
related.** Wikidata lists it *both* as an alias of Q2091584 *and* as its own
concept Q192005. The second is right: "elastic modulus" names the general family
(Young's, shear, bulk), so encoding equivalence would silently broaden a
requirement for Young's modulus into any elastic modulus at all.

**`stress at break`, `TS`, `yield stress`, `yield point`, `bending modulus` — not
encoded.** No source in this repository uses them; encoding unused terms would be
speculative. They remain available if a real source ever needs them.

---

## 2. Implementation — the one change the evidence forced

Phase 23's `VocabularyMapping` could express only equivalence. `elastic modulus`
cannot be represented that way without lying, so §11.E's condition was met:

```python
EXACT_EQUIVALENT = "EXACT_EQUIVALENT"
RELATED          = "RELATED_BUT_NOT_EQUIVALENT"

@dataclass(frozen=True)
class VocabularyMapping:
    dimension: str
    alias: str
    canonical: str
    relationship: str = EXACT_EQUIVALENT   # <-- new, defaulted
    evidence: Optional[str] = None         # <-- new, defaulted
```

- **`relationship`** — only `EXACT_EQUIVALENT` canonicalizes. A `RELATED`
  declaration is **inert in matching**: `canonical_for` leaves the term unchanged,
  `declares` returns `False`, and it can never produce a candidate. It is stored so
  a rejected equivalence stays visible — which is what keeps the next reader of the
  same alias list from re-proposing it.
- **`evidence`** — a free-text citation (`"wikidata:Q76005"`), carried and never
  interpreted, so a reader can re-check rather than trust.
- **`Vocabulary.related_terms(dimension, term)`** — inspection only. Nothing in
  matching consults it; acting on it would be exactly the broadening the
  relationship exists to prevent.

Both fields are **defaulted**, so every Phase 23 declaration keeps its meaning and
all 42 Phase 22/23 tests pass unmodified. `RELATED` mappings are excluded from the
ambiguity and chain checks, because asserting non-equivalence is the opposite of a
conflicting equivalence.

**Nothing else changed.** §11's other questions were answered *no*: mapping alone
is sufficient (A); no synonym groups were needed — many-to-one already works, as
Vocabulary B's `Rm`/`Ftu` show (C); and **no hierarchy was added** (D) — the
`elastic modulus` case is precisely where an ontology would introduce `is-a`, and
recording non-equivalence solved it without one.

---

## 3. Scientific semantics

| Category | Meaning | Encoded as | Example |
|---|---|---|---|
| **Equivalent** | same quantity, different name | `EXACT_EQUIVALENT` | `UTS` ≡ `tensile_strength` |
| **Related** | connected but not interchangeable | `RELATED_BUT_NOT_EQUIVALENT` | `elastic modulus` ~ `youngs_modulus` |
| **Distinct** | different quantity | *nothing declared* | `yield_strength`, `flexural modulus` |
| **Unknown** | no declaration exists | *nothing declared* | any unlisted term |

**Distinct and Unknown are deliberately represented identically — by absence.** The
system does not claim to know that two terms differ; it only ever claims what
someone declared. Silence never matches, so both behave correctly without the
system pretending to a distinction it cannot justify.

---

## 4. Architecture

```
external vocabulary  ->  bridge/vocabulary.py  ->  canonical capability  ->  source resolution
   (Wikidata terms)        explicit mappings        resolve_sources()          CandidateSource
```

Dependency direction unchanged and still AST-asserted:

```
science  -> materials, boundary     never daf, never bridge
boundary -> evidence only
bridge   -> boundary + daf          never materials, never science
daf      -> evidence                never materials/science/boundary/bridge
```

`bridge/vocabulary.py` still imports only `dataclasses` and `typing`. Placement at
`bridge/` is preserved per §10 — no dependency evidence emerged against it.

**Acquisition and state identity remain independent**, measured rather than argued:
the same dataset acquired through a plan reached *with* the external vocabulary is
byte-identical to one reached without it, across `plan_id`, `source_id`,
`artifact_id`, `version_id`, evidence `Source.id`, `Document.id`, `Record.id` and
`Observation.id`. `ModelState` ids are separately shown unchanged.

---

## 5. Two independently authored vocabularies (§6)

`VOCABULARY_A` speaks words (Q76005: `ultimate tensile strength`, `UTS`);
`VOCABULARY_B` speaks symbols (P5479: `Rm`, `Ftu`). Both reach `tensile_strength`,
while remaining separate objects with separate citations — and neither knows the
other's terms (`A.canonical_for("Rm") == "Rm"`). Which source term matched stays
recoverable through `TermMatch.declared`.

---

## 6. Conditioning dimensions survive (§7)

Vocabulary maps **terminology, never values**. Tensile strength at 25 °C and at
100 °C remain different intents with different ids and different candidates;
`water_level` at MLLW stays distinct from STND. Context *values* (`"MLLW"`,
`"25"`, `"C"`) are never canonicalized — only key *names* ever are.

---

## 7. Validation

| Check | Result |
|---|---|
| Phase 24 tests | **23 passed** |
| Phase 23 + 22 suites | **42 passed, unmodified** |
| DAF suite | **425 passed** (402 prior + 23 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git status --short` clean |
| `mypy daf/ science/ boundary/ bridge/` | Success, 55 source files |
| `ruff` | 37 findings, all `UP006`/`UP035`/`UP045`/`I001` repo-wide conventions. One `RUF059` found and fixed |
| Changed files | `bridge/vocabulary.py` (relationship + evidence), `tests/test_independent_vocabulary.py` (new), `tests/fixtures/wikidata_mechanical_property_terms.json` (new), this document. **Zero changes in `daf/`, `science/`, `boundary/`** |

No expected-information-gain was implemented; vocabulary resolution estimates no
information value (§12).

---

## 8. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **Importing the published alias set wholesale** | Would have encoded `tensile force ≡ tensile strength`, a dimensional error |
| **Encoding `elastic modulus` as equivalent** | Silently broadens a Young's-modulus requirement into any elastic modulus |
| **Adding `is-a` hierarchy for the modulus family** | §11.D. The one case that seemed to need it was solved by recording non-equivalence instead |
| **Merging A and B into one synonym list** | §6. Which vocabulary asserted what would become unrecoverable |
| **Making `RELATED` participate in matching** | It asserts non-equivalence; matching on it would invert its meaning |
| **A confidence score on mappings** | Nothing consumes it, and it invites probabilistic matching |
| **Scraping MatWeb/ASTM despite 403** | Bot-blocked and paywalled; circumventing that is not evidence-gathering |

---

## 9. Limitations

1. **This is a manually authored declaration mechanism, not an ontology.** Every
   equivalence is a line someone wrote after checking a citation.
2. **Seven mappings, two concepts.** Generalization is demonstrated, not proven at
   scale.
3. **Wikidata is community-curated.** Its alias sets contain at least one error
   (`tensile force`) — found here. Citing it records *where a claim came from*, not
   that it is authoritative. Every mapping still required human judgement.
4. **`Distinct` and `Unknown` are indistinguishable to the system.** Both are
   absence. Representing "known to be different" would need its own evidence.
5. **Units remain untouched**, unchanged from Phase 23: `tensile_strength` in MPa
   vs psi is one concept in two units, and that is a different mechanism.
6. **No real source in this repository uses the external terminology.** The
   capability declarations in the tests are authored as an operator would author
   them; the underlying acquisition still runs on the graph-dataset fixture.

---

## 10. Remaining frontier

Phase 24 did **not** solve ontology alignment, and the evidence does not yet
justify attempting it. The next legitimate question, per §15, is whether enough
independently authored vocabulary accumulates to require more than declaration:

1. **Does a real source ever need `is-a`?** The modulus family was the natural
   candidate and did not. A hierarchy should wait for a case that non-equivalence
   cannot express.
2. **Where do vocabularies live once there are several?** Two exist here as test
   objects. Persistence, ownership and combination raise the ambiguity question at
   a new scale — `make_vocabulary` detects conflicts only when mappings are
   combined, so *when* they combine becomes a design decision.
3. **Units.** Still the clearest unaddressed gap, and genuinely separate from
   naming.

---

*Halts here per the stop condition (Outcome A): audited, evidence retrieved and
recorded, smallest justified representation change built, run, observed, validated,
documented, committed and pushed. Phase 25 is not begun.*
