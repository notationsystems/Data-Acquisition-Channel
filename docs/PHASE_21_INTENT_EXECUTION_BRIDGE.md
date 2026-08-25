# Phase 21 — Acquisition Intent Execution Bridge

*(Continues from `4821325`, completing Phase 20's seam with its first executable
closed loop.)*

## The loop, executable

```
      ModelState_t
          |
          v  diagnose_information_gap()          science/
      InformationGap
          |
          v  .requirements  (carried verbatim)
    EvidenceRequirement                          materials/  (vendored, unmodified)
          |
          v  intent_for()                        science/
     AcquisitionIntent                           boundary/   (neutral)
          |
          v  operationalize_intent()             bridge/     <-- NEW, the only
     AcquisitionPlan                                             layer naming both
          |
          v  execute_plan()                      daf/  (unchanged)
   DAF -> SCOUT -> DurablePool
          |
          v  analyze()                           materials/
   scientific Observation
          |
          v  update()   <-- EXPLICIT caller step, never automatic
      ModelState_(t+1)
```

Every arrow above is exercised by `test_the_complete_loop_from_state_to_next_state`.
The last one is taken **by the caller**, never as a side effect of acquisition —
asserted separately in `test_acquisition_alone_never_moves_the_model_state`.

---

## 1. Pre-implementation audit

Read at HEAD before any code was written.

| Question (§2) | Answer from the code |
|---|---|
| What does `AcquisitionIntent` contain? | `id`, `subject_natural_key`, `subject_kind`, `property`, `role`, `target_context` |
| Enough to produce an `AcquisitionPlan`? | **No.** A plan needs `plan_id`, `source_id`, `parameters`; the intent has none of them, by design |
| What cannot be translated automatically? | `source_id` and the adapter `parameters` |
| Can a `source_id` be selected from existing information? | **No.** `SourceDefinition` is `source_id, name, domain, adapter_id, configuration, capabilities, required_parameters, enabled` — **no metadata about which subjects or properties a source supplies.** Nothing anywhere can answer "which source supplies `tensile_strength` for `formulation-f1`?" |
| Can `target_context` go into `parameters` without loss? | **Only where the source declares the parameter.** `required_parameters` is the contract |
| Can an intent represent a source choice? | No — it is a scientific requirement only |
| What belongs to the caller/application layer? | Source selection, and the context→parameter correspondence |

**The decisive finding:** autonomous source selection is impossible without
inventing metadata, which §15 forbids. The source is therefore a **caller
decision**, exactly as §3 prescribes.

### What already existed and was deliberately not duplicated

`daf.catalog.plan.validate_plan` — already called inside `execute_plan` — checks
**unknown source, disabled source, unknown adapter, disabled plan, and missing
required parameters**. That covers §9's failure cases 2, 4 and part of 3 already.
Re-checking any of it in the bridge would duplicate DAF orchestration logic (§6).

So the bridge adds exactly **one** check — the one DAF cannot perform, because DAF
never sees an intent.

---

## 2. Dependency direction

```
science/     imports materials, boundary        NEVER daf, NEVER bridge
boundary/    imports evidence only              NEVER materials/daf/science/bridge
bridge/      imports boundary + daf             NEVER materials, NEVER science
daf/         imports evidence                   NEVER materials/science/boundary/bridge
```

`bridge/` is deliberately the **one** package allowed to see an
`AcquisitionIntent` and an `AcquisitionPlan` at the same time. That is what an
operationalization step *is*: a decision belonging to neither the scientific layer
(which must not choose sources) nor the acquisition layer (which must not read
scientific requirements).

Notably the bridge does **not** import `materials` or `science`, and does not need
to: the intent is already the neutral statement of what evidence is wanted, so the
bridge never touches a `ModelState`, an `EvidenceRequirement`, or an
`EvidencePool`. All four directions are asserted at AST level in
`test_the_bridge_is_the_only_layer_that_names_both_sides`.

---

## 3–5. Semantics

**`AcquisitionIntent`** — *"what evidence would resolve this scientific
requirement?"* Unchanged from Phase 20; this phase adds no field to it.

**Operationalization** — *"express this intent as a plan against this particular
source."* Pure, deterministic, no network, no clock, no `EvidencePool`, no registry
mutation, no acquisition:

```python
operationalize_intent(intent, source, *, plan_id, parameters=None,
                      context_parameters=None, mode="snapshot") -> AcquisitionPlan
```

**Context mapping** — the heart of the bridge. The tempting shortcut is
`parameters = dict(intent.target_context)`. It is wrong: an intent's context uses
the **scientific** vocabulary (`temperature`, `temperature_unit`), while a source's
`required_parameters` use its **acquisition** vocabulary (`station`, `begin_date`,
`path`). They coincide only by accident. So the caller states the correspondence
once and the bridge verifies it:

| Rule | Failure |
|---|---|
| every key of `target_context` must appear in `context_parameters` | `IntentNotOperationalizable` — it would otherwise be silently discarded |
| every mapped parameter must be in `source.required_parameters` | `IntentNotOperationalizable` — the source does not accept it |
| a mapping must not overwrite a differing caller parameter | `IntentNotOperationalizable` — an ambiguity only the caller can resolve |

This matters concretely: a water level measured under datum MLLW does not answer a
question about STND, and a tensile strength measured at 60 °C does not answer a
question about 25 °C. An acquisition that quietly ignored `target_context` would
return evidence that **looks responsive and is not**.

An intent with an empty context needs no mapping, so the common case stays simple.

**Execution boundary** — `daf.scheduling.runner.execute_plan` is already the
execution interface and is used unchanged. **No `execute_acquisition_intent`
wrapper was written**: it would have forwarded six arguments and added nothing.
§18 explicitly prefers proving an existing seam over duplicating infrastructure.

---

## 6. Identity separation

Seven identities in one loop, none derived from another, asserted in
`test_every_identity_in_the_loop_stays_distinct`:

| Identity | Origin |
|---|---|
| `intent.id` | content hash of the scientific requirement |
| `plan.plan_id` | caller-supplied |
| `plan.source_id` | caller's source choice |
| `artifact.artifact_id` | `H({source_id, locator})` |
| `artifact.version_id` | `H({source_id, H(content), method})` |
| `observation.id` | content hash of the observation |
| `ModelState.id` | content hash of the samples |

`plan_id` is **caller-supplied rather than derived from `intent.id`** on purpose:
`plan_id` is also the checkpoint key, so deriving it would tie checkpoint identity
to scientific identity — precisely the coupling Phase 20 established must not exist.

---

## 7. Failure semantics

| Case | Handled by | Result |
|---|---|---|
| context has no parameter mapping | **bridge** | `IntentNotOperationalizable` |
| mapped parameter not declared by source | **bridge** | `IntentNotOperationalizable` |
| mapping conflicts with a caller parameter | **bridge** | `IntentNotOperationalizable` |
| unknown source | existing `validate_plan` | `SOURCE_UNAVAILABLE`, `UNKNOWN_SOURCE` |
| disabled source | existing `validate_plan` | `SOURCE_UNAVAILABLE`, `SOURCE_DISABLED` |
| missing required parameter | existing `validate_plan` | `SOURCE_UNAVAILABLE` |
| adapter/extraction failure | existing orchestrator | `ADAPTER_FAILURE` / `EXTRACTION_FAILURE` |

Bridge failures raise (they are programming/configuration errors detectable before
any I/O); DAF failures are returned in the existing `AcquisitionResult` (they are
runtime outcomes). No new execution ledger, no operation ids, no provenance ids
were added — those belong to the separate verifiability plane (§9).

**Every failure path leaves the scientific state untouched**, asserted directly:
after unknown-source, disabled-source and a genuine adapter failure, `s1.id`, its
samples, and the intent are all unchanged.

---

## 8. Closed-loop demonstration

Measured, with the real DAF pipeline:

```
1. intent: 474259e2d428 formulation-f1 tensile_strength OBSERVED {}
2. plan:   intent-plan-1 qc-panel-2 {'path': '…/followup.json'} | mode: snapshot
           identities distinct: True
3. DAF:    acquired | artifacts: 2
4. pool observations: 6 | analysis observed: 6
5. state UNCHANGED by acquisition: 1 sample, id f788efc24861
6. S(t+1): 21daa31f9fe4 | predicted 83.5 | S1 still 1 sample
```

Line 5 is the one worth dwelling on: a successful acquisition completed and the
`ModelState` did not move. Line 6 moves it only because the caller invoked
`update` explicitly. **Acquisition ≠ scientific state transition** is preserved as
an executable fact rather than a convention.

---

## 9. Tests and validation

`tests/test_intent_execution_bridge.py` — 12 tests covering §13 A–I and §14:

| § | Test |
|---|---|
| A determinism | `test_operationalization_is_deterministic` |
| purity | `test_operationalization_performs_no_acquisition` |
| B context preservation | `test_conditioning_context_reaches_the_plan_when_the_source_declares_it` |
| C explicit failure | `test_unmappable_context_fails_explicitly_rather_than_being_dropped` |
| C simple case | `test_an_intent_with_no_context_needs_no_mapping` |
| D + E full loop | `test_the_complete_loop_from_state_to_next_state` |
| F no implicit mutation | `test_acquisition_alone_never_moves_the_model_state` |
| G restart | `test_evidence_acquired_through_an_intent_survives_restart` |
| 9.9 dedup | `test_repeating_an_intent_derived_plan_preserves_deduplication` |
| H identity | `test_every_identity_in_the_loop_stays_distinct` |
| I failure | `test_acquisition_failures_are_reported_and_never_touch_scientific_state` |
| 14 structure | `test_the_bridge_is_the_only_layer_that_names_both_sides` |

| Check | Result |
|---|---|
| DAF suite | **360 passed** (348 prior + 12 new) |
| Vendored SCOUT suite | **1273 passed**, unchanged |
| Submodule | `git status --short` clean |
| `mypy daf/ science/ boundary/ bridge/` | Success, 53 source files |
| `ruff` (new files) | 6 findings, all `UP006`/`UP035`/`UP045`/`I001` repo-wide conventions — none genuine |
| Changed files | `bridge/` (new), `tests/test_intent_execution_bridge.py` (new), this document. **Purely additive** |

§17's confirmations: existing DAF adapters unchanged; SCOUT unchanged; `materials/model_state` unchanged; no wall-clock read anywhere in the bridge (`requested_at` and `plan_id` are caller inputs); no `EvidencePool` access in intent translation; no state mutation during acquisition.

---

## 10. Rejected alternatives

| Alternative | Why rejected |
|---|---|
| **Autonomous source selection** (`intent -> source_id`) | Impossible without inventing metadata: `SourceDefinition` records nothing about which subjects or properties a source supplies. Forbidden by §15, and the audit confirms there is no data to do it with even if it were allowed |
| **`parameters = dict(intent.target_context)`** | Conflates scientific vocabulary with acquisition vocabulary. Would silently produce plans whose parameters the source ignores |
| **Dropping unmapped context with a warning** | Returns evidence that looks responsive and is not. Failing loudly is the only honest option |
| **Deriving `plan_id` from `intent.id`** | `plan_id` is the checkpoint key; deriving it would couple checkpoint identity to scientific identity |
| **An `execute_acquisition_intent` wrapper** | Would forward six arguments to `execute_plan` and add nothing. §18 prefers proving the existing seam |
| **Putting the bridge in `science/` or `daf/`** | Either placement creates the forbidden dependency. The whole point of a bridge is that it is the one place allowed to name both |
| **Re-validating source/adapter/parameters in the bridge** | `validate_plan` already does it; duplicating it would drift |

---

## 11. Information-value boundary

Unchanged and re-asserted: `expected_information_gain` remains `NOT_DETERMINABLE`.
This phase demonstrates that an intent was *generated from an identified evidence
gap*; it makes no claim about the **value of executing it**. The architecture
remains gap → requirement → intent → acquisition → observation → updated state →
information value, with expected gain a future capability.

---

## 12. Explicit boundary for Phase 22

**Deliberately not built here:** expected information gain, Bayesian optimization,
Gaussian processes, active learning, scheduler daemon, autonomous source selection,
generalized workflow engine, execution ledger, operation identity, provenance
identity, zkVM/SP1/Nexus, GraphRAG, ontology expansion, learned geometry,
transformer changes, FEP controller, SCG reconfiguration.

**What Phase 22 would need to decide first**, from this phase's evidence:

1. **Source capability metadata.** The single hard blocker to any automated
   selection. Today a caller must know which source supplies which property; a
   registry that recorded it would be the smallest honest step — and is a real
   ontology decision, not a mechanical one.
2. **Who owns the context→parameter correspondence.** Currently the caller states
   it per call. If it belongs to the `SourceDefinition`, that is a DAF-side schema
   change with its own identity consequences.
3. **Whether repeated intents should be tracked.** This phase deliberately adds no
   execution ledger, so nothing records that an intent was executed. That is the
   boundary of the verifiability plane, not of this seam.

Only after (1) could gap → acquisition become automatic — and that step should be a
deliberate decision about autonomy, not a convenience.

---

*Halts here per the stop condition: audited, smallest missing boundary identified,
built, run, observed, validated, documented, committed and pushed. Phase 22 is not
begun.*
