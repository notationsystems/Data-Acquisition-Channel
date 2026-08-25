# Phase 25 — Canonical Architecture Synchronization and the Epistemic Boundary

*(Continues from `7a7f29d`. Absorbs the "Core/Evidence Boundary Enforcement" brief
and the Project-Wide Architecture Synchronization Addendum, which arrived together.)*

**Numbering note.** Three consecutive briefs were labelled "Phase 24". Commit
`7a7f29d` already holds *Phase 24 — Independent Scientific Vocabulary
Generalization*, so this work is filed as Phase 25 to keep the doc set and the
commit history addressable. Nothing about the content is changed by the name.

---

## 0. Reconnaissance — what is actually here

Every synchronization brief opens with `INSPECT`. This is what inspection found,
before anything was written:

| Referenced by the briefs | Present in this repository |
|---|---|
| `architecture/invariants.yaml` | **absent** — no `architecture/` directory, no YAML anywhere |
| `architecture/evidence_class.yaml` | **absent** |
| `architecture/model_binding.yaml` | **absent** |
| `architecture/functions.yaml` | **absent, and still is** — referenced by the briefs, specified by neither |
| doctrine files | **absent** — 26 hand-written `docs/PHASE_*.md`, no generated artifact |
| a doctrine generator | **absent** — no generator infrastructure of any kind |
| CI workflows | **absent** — no `.github/` |
| model bindings, vendors, snapshots | **absent** — no vendor SDK, no API client, `dependencies = []` |
| execution records | **absent** — `ExecutionRecord` matches nothing |
| chemistry representations | **absent** — every `chem`/`molecul`/`polymer`/`smiles` hit was the substring `schema`/`scheme` |
| EvidencePool records committed to the repo | **none** — every pool is built per run against a temporary root |
| `core@0.1` | **wrong version** — see below |
| Canonical State IR | **present**, vendored: `core/canonical/{schema,state,delta,version,validation}.py` |
| EvidencePool | **present**, vendored: 8 types, 8 `put_*`, no delete |
| retrieval | **present**, vendored: `retrieval/{engine,query,epistemic,seam,context,result}.py` |
| DAF acquisition | **present**: 6 adapters, 7 extractors, orchestrator, durable pool |

### The core version, measured

The briefs bind against `invariants.yaml core@0.1`. That is not what this
repository extends. `vendor/scout-retrieval-agent/pyproject.toml` reads:

```toml
name = "deterministic-state-architecture"
version = "1.0.0"
description = "Implementation of Deterministic State Architecture -- Frozen Specification v1.0.0"
```

So the core is **`core@1.0.0`**, submodule commit `3e5bea9`, and every artifact
committed in this phase declares `extends: core@1.0.0`.
`test_the_core_version_is_the_one_actually_in_the_repository` asserts the version
against the vendored file *and* asserts it is not `core@0.1`, so the discrepancy
cannot be quietly re-introduced.

`schema_version` in the core is a **per-`StateSchema` string** (`"1.0.0"`,
`"ingested-1.0.0"`, …), not a global core version. The two were not conflated.

---

## 1. The substrate is a loop — bound to edges, not boxes

```
acquisition ──> evidence ──> observation ──> trust ──> canonical_state
     ^                                                       │
     │                                                       v
derived_state <── validation <── retrieval_execution ────────┘
```

The correction is not cosmetic. A linear stack entered at *evidence* has no way
to say where evidence came from, and therefore **no way to forbid an
interpretation from becoming its own evidence** — the prohibition is a property
of an *edge*, and edges only become expressible once the graph closes.

`architecture/control_graph.yaml` declares 8 transitions and 4 forbidden ones.
`epistemics/control_graph.py` checks, mechanically:

- every stage has exactly one outgoing transition;
- the walk from `acquisition` returns to `acquisition` after exactly 8 steps,
  visiting every stage — a single cycle, no sub-loops;
- **`acquisition` is the only producer of `evidence`**;
- **`derived_state` has exactly one exit, it is `acquisition`, and it is declared
  `mandatory` and `exclusive`**;
- no edge is declared both permitted and forbidden.

Proved as a *failure*, not only as a pass: adding a `derived_state -> evidence`
bypass raises `ControlGraphViolation`
(`test_a_graph_where_derived_state_writes_evidence_is_refused`).

The edges are enforced where they actually live. An AST sweep of every
non-test `.py` in the repository finds every call named `put_*`/`admit_*`:
`vendor/scout-retrieval-agent/scout/pipeline.py` and `materials/results.py` write
evidence; `daf/storage/` *implements* `put_*` and delegates; and
**`science/`, `bridge/`, `boundary/` and `epistemics/` contain zero.**

---

## 2. `class_assigned_at_ingest` — the actual build

### What existed

No evidence type carries a class field. `evidence/types.py` has a de facto
two-class split — `Observation` (admitted from a `Record`) versus `DerivedValue`
(computed) — and nothing more. Adding a field to `Observation` means editing the
vendored submodule, which this repository never does.

### Where the class went instead

Beside the object, in its own content-addressed record:

```python
EvidenceClassAssignment(id, evidence_id, evidence_kind, evidence_class, assigned_by)
id = content_hash({evidence_id, evidence_kind, evidence_class, assigned_by})
```

`assigned_by` participates in identity because *who declared this* is part of what
the assignment asserts: the same evidence classified by two different declared
policies is two claims, and collapsing them would hide a disagreement.

### Why "at ingest" is real here and not a label

`run_scout` — the single evidence write path — writes exclusively through
`pool.put_*`, and `DurablePool` already overrides all eight. `ClassifiedPool` adds
the assignment **inside those same overrides**, so an object cannot enter the pool
by the supported path without its class being fixed in the same call. No second
pass to forget, no window where a classified and an unclassified copy coexist.
The vendored `scout/pipeline.py` is untouched and does not need to be: it accepts
any `EvidencePool`, and a `ClassifiedPool` is one.

### Immutability — three mechanisms, measured separately

| Attack | Mechanism | Test |
|---|---|---|
| Mutate the assignment object | frozen dataclass | `test_an_assignment_cannot_be_mutated_in_place` |
| Assign a second, different class | `ClassRegister.assign` raises `ClassReassignment` | `test_attempted_reclassification_is_refused` |
| Edit `evidence_class` on disk | re-hashes ≠ stored id → `ClassIdentityMismatch` | `test_deserialization_with_an_altered_class_is_refused` |
| Re-hash consistently under a new id | append-only store now holds two classes for one evidence id → caught at restore | `test_a_wholesale_rewrite_under_a_new_id_is_caught_at_restore` |
| Restart the process | register rebuilt from disk, classes identical | `test_class_survives_persistence_restart_and_retrieval` |

**What none of that proves,** stated in the module itself: an actor who can
*delete* files can remove the original assignment while writing a new one, and
nothing here would notice. The store has no tombstone and no retraction path at
all. These mechanisms detect alteration; they are not a defence against write
access to the store.

### Measured on real acquisition

The class tests run the **unmodified DAF path** over recorded NOAA CO-OPS bytes
and a graph-declaring dataset — adapter → `run_scout` → `ClassifiedPool` →
`FilesystemEvidenceStore`. Nothing simulates ingest. The NOAA chain comes back
`measured` at `Source`, `Document`, `Record` and `Observation`; the dataset chain
comes back `asserted`; the two stay separate.

### Unclassified is not a fifth class

A source kind absent from the declared policy produces **no assignment at all**.
Its evidence is `UNCLASSIFIED`, inadmissible for canonical assertion *and* for
training, and there is no bypass argument that would change that
(`test_an_undeclared_source_kind_yields_unclassified_and_is_inadmissible`). This
is §22's migration state made live rather than hypothetical.

---

## 3. `proposals_are_not_evidence` — three independent locks

1. **AST** — no interpretive layer calls a pool mutator (§1 above).
2. **Class** — `derived_value` and `derived_grounding` may only be `computed` or
   `derived`. `make_class_assignment("d", "derived_value", "measured", …)` raises
   `ProposalClassRefused`. A derivation over `measured` inputs still comes back
   `derived`, never inheriting its inputs' class.
3. **Graph** — `derived_state`'s only exit is `acquisition`.

And the trap named in every brief: **`validated` is a claim status, not a class.**
An earlier draft of this work kept `validated -> measured` in the vocabulary map
so a query for it would still resolve. That was wrong, and the reasoning is worth
keeping: *any* mapping at all is a promotion path from validation status into
evidence classification. It is now declared only in `statuses_not_classes`, and
`canonical_class("validated")` raises.

---

## 4. Doctrine is a generated projection

```
architecture/*.yaml  ──generate──>  docs/generated/DOCTRINE.md  ──diff──>  gate
    (canonical)                          (projection)                  pass/fail
```

Every phase in this repository so far ended in a hand-written `docs/PHASE_*.md`
restating architectural facts that also live in code. That is exactly how a
synchronization window silently drops an invariant: the prose and the enforcement
diverge and nobody can tell which is stale.

`epistemics/doctrine.py` generates doctrine from the five canonical sources and is
gated four ways:

| Gate | Result |
|---|---|
| Regeneration is deterministic | byte-identical across runs |
| Committed output matches regeneration | asserted; a non-zero diff fails closed |
| A manual edit is detected | asserted on a copy, so the committed file is never touched by a test |
| Budget | 544 words against a budget of 1400 |
| `no_vendor_in_doctrine` | passes; forbidden-token lint over the projection |

**The budget is proved as a failure, not as a pass.** 1400 is not currently
binding, so `test_the_budget_fails_closed_and_names_the_overflow` regenerates
against a tightened budget and asserts the error names the largest section and
says *"Do not raise the budget."* The forbidden-token list is drawn from
`architecture/doctrine.yaml` **plus every vendor declared in
`model_binding.yaml`**, so instantiating a binding extends the lint automatically
rather than relying on someone remembering.

Doctrine carries role *behaviour* and the abstract constraint
("the accepting role must be vendor-independent from the proposing lineage") and
**not the binding table** — asserted on the projection itself.

### The zero-dependency reader, and what it caught

`pyproject.toml` declares `dependencies = []` and every layer so far has held that
line, so `architecture/*.yaml` is read by `epistemics/_yaml.py`, a strict subset
parser that raises rather than guesses. That is only defensible if it agrees with
the reference implementation, so
`test_the_minimal_parser_agrees_with_the_reference_implementation` compares both
parsers on all seven committed files whenever PyYAML happens to be importable.

It immediately found a real ambiguity: PyYAML types a bare `2026-08-25` as
`datetime.date`, this parser as `str`. The dates are now quoted, and the two
parsers agree exactly.

---

## 5. Model bindings — blocked, and not faked

**There are none.** No vendor SDK, no API client, no model identifier anywhere in
`daf/`, `science/`, `boundary/`, `bridge/`, `epistemics/` or `tests/`. The only
network egress in the repository is NOAA/USGS/arXiv/EDGAR/Wikidata acquisition —
scientific data, not inference.

The brief says *"Do not invent snapshot identifiers. Inspect the actual deployment
and populate real values."* **The real value is the empty set.**
`architecture/model_binding.yaml` declares `bindings: {}` with
`status: no_model_binding_instantiated`, records the four roles and their
lineages, and leaves the table empty.

`pin_accepted`, `behavioral_canary` and `attested_snapshot_identity` are recorded
**`blocked`** with the blocker named. §8 of the brief is explicit that a
requested-string / echoed-response comparison verifies nothing about served
weights; the honest alternative to faking it is to say it is not implementable
here, which is what the ledger says.

What *was* built is the constraint checker, authored before there is a binding to
accommodate — so the first binding anyone adds is checked by a rule that did not
bend around it. It passes vacuously today, and
`test_cross_vendor_validation_fails_when_the_validator_shares_a_vendor` and
`test_a_placeholder_is_not_a_pin` prove it is not vacuous *as a rule*.

`INDEPENDENCE_CAVEAT` is stated in one place: different vendors are not thereby
statistically independent; the constraint is a boundary requirement, not an
independence claim.

---

## 6. `epistemics/` — a new layer added *beneath*, not a boundary moved

The class is assigned by acquisition (`daf`) and consumed by scientific
admissibility (`science`). The existing AST-asserted directions are
`daf -> evidence` only and `science -> materials, boundary` only — **there is no
existing package both may import.** Putting the class in `daf` would make
`science` import `daf`; putting it in `boundary` would make `daf` import
`boundary`. Either changes a verified boundary to avoid adding a layer.

```
epistemics/   imports evidence.identity.content_hash, and nothing else
    ^     ^
   daf/   science/, boundary/, bridge/
```

Every existing direction is preserved unchanged; the new one only points
downward. `test_epistemics_is_a_leaf_layer` and
`test_epistemics_touches_the_substrate_only_through_content_hash` assert this at
the AST level — the latter to an exact set, so a second vendored import cannot
slip in. `epistemics/_vendor.py` is the same deliberate seven-line copy
`science/` and `boundary/` already carry, for the same reason.

---

## 7. The invariant ledger — §1's four-way classification

`architecture/invariants.yaml` records **31 invariants** with a closed status
vocabulary. The distinctions are load-bearing, and
`epistemics.invariants.check_declarations` refuses a declaration that claims a
check without naming one, or a gap without a reason.

| Status | Count | Meaning |
|---|---|---|
| `enforced` | 13 | a test fails today if broken |
| `vacuously_enforced` | 6 | the check runs; the thing it constrains does not exist here **yet** |
| `partially_enforced` | 3 | a mechanism exists, nothing compels callers |
| `blocked` | 3 | not implementable without inventing repository state; blocker named |
| `represented_unenforced` | 1 | represented in data, no check |
| `absent` | 5 | neither represented nor enforced |

Selected rows:

| Invariant | Status | Note |
|---|---|---|
| `class_assigned_at_ingest` | enforced | this phase |
| `proposals_are_not_evidence` | enforced | this phase, three locks |
| `core_schema_closed` | enforced | **already** — `UNKNOWN_FIELD` at `core/canonical/validation.py:65`. Verified, not reimplemented |
| `metric_before_optimization` | enforced | **already** — `expected_information_gain=NOT_DETERMINABLE` at `materials/value.py:229` |
| `provenance_total` | enforced | **already** — measured on real acquired evidence rather than argued |
| `prediction_carries_uncertainty` | partially | validators exist and are pure; nothing compels a caller, because ingest is the vendored `run_scout` |
| `no_circular_training` | vacuous | no fit step, gradient or train loop exists — checked, so it stops being vacuous the day one appears |
| `generation_depth_bounded` | vacuous | `DerivedValue` identity makes a derivation cycle unconstructible |
| `execution_recorded` | **absent** | no execution-record type exists anywhere |
| chemistry invariants (4) | **absent** | no chemistry representation exists at all |

`test_every_named_enforcement_test_file_exists` asserts that every status
claiming a check points at a file that exists. A status of `enforced` naming a
test nobody wrote is worse than a status of `absent`.

---

## 8. Generality probe (paper-only)

`architecture/_probes/generality.yaml`, `status: paper_only`, `extends: core@1.0.0`.
No code imports it — asserted.

| Property | Verdict |
|---|---|
| `non_reproducible` | **ALREADY_QUALIFIED** — NOAA revises preliminary into verified for the same timestamp; artifact identity is stable across revisions while version identity changes. No core invariant modified. |
| `uncontrolled_conditions` | **ALREADY_QUALIFIED** — NOAA datum/units are *requested*, not set; already carried as conditioning context, which is why they live in the artifact locator. |
| `revocable_record` | **UNTESTED** — the probe's clearest live finding. |
| `cohort_identity` | **UNTESTED** — every subject here is an object; none is a population. |

**Core invariants modified: 0. Bent: none.** The generality claim survives — but
two of four properties were never exercised by any source in this repository, so
the probe did not so much run against them as find no way to run against them.
That is recorded in the probe's own `outcome` block rather than rounded up to a
pass.

---

## 9. Retraction — recorded, deliberately not built

`FilesystemEvidenceStore` is append-only and content-addressed and has **no delete
method**. No tombstone, supersession or retraction path exists for any evidence
type. A source compelling removal would today require deleting content-addressed
blobs that `materials` `ModelState.Sample.observation_id` still references,
orphaning scientific state.

The brief directs recording the gap, not building the system. Both directions are
checked: `architecture/invariants.yaml` carries the `retraction` block, and
`test_the_retraction_gap_is_recorded_and_not_quietly_built` asserts that no
`delete`/`remove`/`retract`/`unlink` path appeared in the store.

---

## 10. Required final report

**Implemented.** `epistemics/` (7 modules: `_vendor`, `_yaml`, `evidence_class`,
`control_graph`, `invariants`, `model_binding`, `doctrine`);
`daf/storage/class_store.py`; `daf/storage/classified_pool.py`;
`architecture/` (`core`, `invariants`, `evidence_class`, `model_binding`,
`control_graph`, `doctrine`, `_probes/generality`); `docs/generated/DOCTRINE.md`;
`.github/workflows/conformance.yml`; `science/admissibility.py`;
3 test modules (59 tests).

**Verified.**

| Check | Result |
|---|---|
| New tests | `test_epistemic_boundary.py` **27**, `test_doctrine_generation.py` **19**, `test_addendum_invariants.py` **13** |
| DAF suite | **484 passed** (425 prior + 59 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git -C vendor/scout-retrieval-agent status --short` clean |
| `mypy daf/ science/ boundary/ bridge/ epistemics/` | Success, 66 source files |
| `ruff` | new files carry only the repo-wide `UP006`/`UP035`/`UP045`/`UP037` conventions; `F401`, `PIE810` and `I001` found in new files were fixed |
| Doctrine regeneration | zero diff |

**Preserved.** Every prior AST-asserted direction: `science ↛ daf`,
`daf ↛ materials`, `bridge` as the only layer naming both sides, `boundary ->
evidence` only. `expected_information_gain` still `NOT_DETERMINABLE`. The vendored
submodule unmodified. `run_scout` as the single evidence write path. All 425 prior
tests pass unchanged.

**Extended.** A new bottom layer, added beneath every existing one. A class
carried beside evidence rather than inside it. A generated-projection path for
doctrine. A conformance gate.

**Qualified.** `non_reproducible` and `uncontrolled_conditions` are admitted as
per-source properties rather than substrate guarantees — which the repository was
already doing; the probe named it. Core semantics unchanged.

**Bent.** **None.** No core invariant changed, no core version increment, and the
vendored submodule is byte-identical.

**Generator state.** Canonical sources: 5 YAML files. Generator:
`epistemics/doctrine.py`. Generated doctrine: `docs/generated/DOCTRINE.md`,
committed. Regeneration diff: **zero**. CI gate: added, first workflow in this
repository. Budget: **544 / 1400 words**, fail-closed path proved on a tightened
budget.

**Execution record state.** **No agent execution occurs in this repository**, so
no retention field is captured and none is fabricated. The required ten-field
contract is recorded in `model_binding.yaml` so the first execution path built has
a contract to satisfy rather than a blank page.

**Canary state.** Binding: none. Fixture version: none. Noise floor: none.
Threshold: none. Current result: **not run — blocked**. Limitation: hosted
inference is not bit-deterministic and drift below a noise floor is undetectable
by construction; also, none of that is testable here, because there is nothing to
canary.

**Identity decisions.** **None taken** — no chemistry representation exists, and
§27 of the brief orders the generator path before domain expansion. Deciding a
tautomer or salt policy against zero chemistry records would be inventing
repository state.

**Migration state.** Total legacy records: **0**. No `EvidencePool` records are
committed to this repository; every pool is built per run against a temporary
root. Classified: n/a. Unclassified: n/a. Quarantined: n/a. Any pool persisted
before this phase has zero class assignments on disk and is therefore wholly
unclassified by construction — which is the correct answer, not a migration to
run. No bypass flag exists; no bulk auto-classification path exists.

**Unresolved** — carried forward, not silently decided:

- `multi_writer.write_conflict` — merge policy for concurrent canonical assertions.
- `builder_check_lineage` — whether enforcement-code review must itself be
  cross-vendor.
- `attested_snapshot_identity` — unavailable for hosted bindings; no binding
  exists here to attest.
- `capabilities_5_to_9` — acceptance criteria still required before
  self-optimization.
- `retraction_semantics` — no path removes an admitted `Observation` without
  orphaning scientific state.

---

## 11. Next executable frontier

The generator path is now mechanically reliable, which is the condition §27 sets
before domain expansion. The next concrete step is **not** chemistry ontology:

1. **`execution_recorded` is `absent`, and it is the one universal invariant the
   briefs name that this repository does not have in any form.** There is no
   execution-record type, so `retrieval_execution -> validation` is the only edge
   in the control loop with nothing behind it. Every downstream requirement —
   agent retention, canary provenance, computed-result method blocks — needs it
   first.
2. **Quarantine.** `ScoutAdmissionFailure` already retains the stage and errors of
   every refused admission and returns them to the caller. It is one step from
   §23's quarantine: what is missing is retention in a queryable, repairable form
   and a per-invariant rejection rate. There is already no `--force` path, and
   none should be added.
3. **Then chemistry identity resolution**, which needs (1) before a computed
   result can carry a method block that means anything.

---

*Halts here per the stop condition: inspected, built, run, observed, fixed,
audited, validated, documented, committed and pushed. Chemistry is not begun.*
