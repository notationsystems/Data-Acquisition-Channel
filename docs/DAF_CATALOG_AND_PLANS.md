# Phase D — DAF Acquisition Catalog and Repeatable Acquisition Plans

**Status:** implemented and passing. Fourth DAF phase: a persistent
source catalog, declarative repeatable acquisition plans, deterministic
validation, and a minimal operator CLI — all layered strictly above the
unmodified Phase A/B/C acquisition/persistence/orchestration contract.

---

## Pre-implementation report

1. **Current Phase C architecture**: `SourceRegistry`/`AdapterRegistry`
   (in-memory only), `AcquisitionRequest`, `AcquisitionOrchestrator.run()`,
   `AcquisitionResult`. `SourceDefinition` already had `{source_id, name,
   domain, adapter_id, configuration, capabilities, enabled}`.
2. **What already supports catalog behavior**: the whole shape —
   `SourceRegistry.get`/`all_sources` is already the catalog's read
   contract. Only durability and a declarative plan concept were missing.
3. **Missing capability**: (a) persistence/reload for `SourceDefinition`,
   (b) a persistable `AcquisitionPlan` distinct from the ephemeral
   `AcquisitionRequest`, (c) deterministic validation, (d) a declared
   "required parameters" concept for validation to check against, (e) a
   minimal operator CLI.
4. **Proposed `SourceCatalog`**: `SourceCatalog(SourceRegistry)` — same
   relationship as `DurablePool(EvidencePool)` — persists each
   `SourceDefinition` as one "last write wins" JSON file per `source_id`.
   Deliberately NOT content-addressed like Phase B's evidence store:
   catalog entries are operator-declared, legitimately mutable
   configuration, never scientific evidence.
5. **Proposed `AcquisitionPlan`**: `{plan_id, source_id, parameters,
   enabled, schedule}`, converted via `to_request(requested_at)` — never
   replacing `AcquisitionRequest`.
6. **Configuration strategy**: reused `SourceDefinition.configuration`
   (source-level) and `AcquisitionPlan.parameters` (per-execution,
   already the `AcquisitionRequest` shape). No secrets stored; no secret
   abstraction existed to reuse, and none was built.
7. **Validation strategy**: `validate_plan() -> Tuple[PlanValidationIssue, ...]`
   — structural, non-raising, matching `evidence.admission`'s own
   collect-issues discipline rather than raising exceptions for expected
   problems.
8. **Schedule representation**: `AcquisitionPlan.schedule: Optional[str]`
   — free-form, declarative only, never interpreted or executed.
9. **Why no scheduler**: nothing reads `schedule` automatically; every
   execution in this phase is explicit (`orchestrator.run(plan.to_request(...))`,
   called by a human or a script).
10. **Why no execution ledger**: "what versions exist for an artifact" is
    answered by `daf.catalog.history`, a thin derived wrapper over Phase
    B's `ArtifactStore` — no new persistent record.
11. **Expected Phase E boundary**: a real scheduler reading `schedule`
    and calling `execute-plan` on a cadence; still out of scope here.

---

## Design

```
SourceCatalog (persisted)          PlanCatalog (persisted)
      |                                    |
      v                                    v
SourceDefinition                    AcquisitionPlan
      |                                    | to_request(requested_at)
      |                                    v
      |                          AcquisitionRequest        [unmodified, Phase C]
      |                                    |
      +--------- validate_plan() ----------+
                       |
                       v
              AcquisitionOrchestrator      [unmodified, Phase C]
                       |
                       v
     scout.pipeline.run_scout -> DurablePool -> ArtifactStore   [unmodified, Phase A/B]
```

`daf.catalog.plan`, `daf.catalog.source_catalog`, and `daf.catalog.plan_catalog`
never import `daf.adapters`/`daf.extractors`/`evidence.admission` and
never call a pool mutator (AST-verified) — the only module in `daf.catalog`
allowed to import concrete adapters is `daf.catalog.cli`, mirroring
`daf.orchestration.bindings`'s role in Phase C.

`daf.catalog.history` derives "what versions exist" purely from
`ArtifactStore.list_versions` — see its own docstring for why "has this
catalog source ever produced anything" (a source-wide query, not an
artifact-id-scoped one) was deliberately NOT implemented generically:
the two existing adapters disagree on whether the evidence-layer
`Source.name`/`kind` is derived from the catalog's `SourceDefinition` at
all (`local_dataset` does; `arxiv` hardcodes its own), so inferring that
mapping in the catalog layer would mean reaching into adapter internals
— exactly what the orchestrator is built to avoid.

---

## A bug found and fixed along the way

The CLI's `execute-plan` originally constructed a plain `DurablePool(store)`
per invocation. Since each CLI invocation is a fresh OS process, that
pool's in-memory state starts empty regardless of what's already durably
persisted — so `AcquisitionOrchestrator`'s duplicate-detection (which
checks `pool.has_document(...)`, an in-memory check) reported everything
as newly acquired on every run, even though the underlying storage itself
stayed correctly deduplicated (no duplicate files were ever written).
Fixed by using `DurablePool.restore(store)` in the CLI, which replays
existing durable state into memory before use — exactly Phase B's own
"process restart" pattern. Documented prominently in
`AcquisitionOrchestrator`'s own docstring as a caller responsibility,
since it is a real, non-obvious correctness requirement for any
fresh-process caller (not just the CLI).

---

## Post-implementation report

### 1. Files changed

```
daf/orchestration/source_registry.py     (additive field: required_parameters)
daf/orchestration/orchestrator.py        (docstring: caller responsibility re: DurablePool.restore)
daf/catalog/__init__.py
daf/catalog/source_catalog.py
daf/catalog/plan.py
daf/catalog/plan_catalog.py
daf/catalog/history.py
daf/catalog/cli.py
tests/test_source_catalog.py
tests/test_plan.py
tests/test_plan_catalog.py
tests/test_catalog_history.py
tests/test_catalog_integration.py
docs/DAF_CATALOG_AND_PLANS.md            (this file)
```

### 2. New abstractions

`SourceCatalog`, `AcquisitionPlan`, `PlanValidationIssue`/`validate_plan`,
`PlanCatalog`, `daf.catalog.history.{known_versions, has_ever_been_acquired}`,
a minimal CLI. One additive field on the existing `SourceDefinition`
(`required_parameters`). No new evidence type, no execution ledger, no
scheduler daemon.

### 3. Source catalog behavior

Register → persisted as `<root>/sources/<source_id>.json` → survives
across a brand new `SourceCatalog` instance at the same path
(`test_source_persists_and_reloads_across_a_fresh_catalog_instance`).
Re-registering the same `source_id` updates it (last-write-wins, correct
for mutable operator config, unlike evidence).

### 4. Plan behavior

`AcquisitionPlan.to_request(requested_at)` is a pure function of
`(source_id, parameters, requested_at)` — proven deterministic
(`test_to_request_is_deterministic`). Plans persist/reload the same way
sources do.

### 5. Validation behavior

`validate_plan()` returns zero or more typed issues: `UNKNOWN_SOURCE`
(early-returns, since nothing else is checkable), `SOURCE_DISABLED`,
`UNKNOWN_ADAPTER`, `PLAN_DISABLED`, `MISSING_PARAMETERS` — all
independently triggerable and jointly reportable in one call
(`test_multiple_issues_can_be_reported_together`).

### 6. CLI/operator behavior

`python -m daf.catalog.cli <root> {list-sources, inspect-source,
list-plans, inspect-plan, validate-plan, execute-plan}` — every command
calls exactly the same Python interfaces a programmatic caller would.
Registration is programmatic (`SourceCatalog`/`PlanCatalog.register()`),
not a CLI verb, matching how `daf.orchestration.bindings` (not the
orchestrator) is where concrete wiring happens.

### 7. Repeatability demonstration

`test_repeat_execution_of_the_same_plan_is_duplicate` and
`test_cli_smoke_end_to_end` both execute the same plan twice (with
different `requested_at` values, proving `requested_at` — not content —
is what legitimately varies) and confirm the second run reports
`DUPLICATE` with identical `version_id`s.

### 8. Durable persistence demonstration

`test_register_persist_plan_validate_execute` registers a source and a
plan, reloads BOTH catalogs from disk as brand-new objects, validates,
and executes — proving the full "persist → reload → validate → execute"
chain, not just in-memory behavior.

### 9. SCOUT one-door proof

`test_one_door_invariant_for_catalog_modules` (AST-level: no
`evidence.admission` import, no direct `put_*` call anywhere in
`daf.catalog.{plan,source_catalog,plan_catalog}`) and
`test_domain_independent_execution_of_two_different_sources` (two
different sources' evidence coexists in the same pool after both plans
execute through the same orchestrator).

### 10. Full test results

`pytest tests/` (DAF, all four phases): **102 passed** — 19 (A) + 26 (B)
+ 32 (C) + 25 new (D). Full vendored State-Space suite: **1273 passed, 0
failed, 0 files modified.**

### 11. ruff

`ruff check daf/ tests/ conftest.py` → **All checks passed!**

### 12. mypy

`mypy daf/` → **Success: no issues found in 28 source files.**

### 13. Limitations

- `required_parameters` validation checks only key *presence*, not value
  shape/type — deliberately, per the task's "do not introduce a
  general-purpose schema language" instruction.
- No scheduler reads `schedule`; it is inert metadata this phase.
- `daf.catalog.history` cannot answer "has this catalog source EVER
  produced anything" in general — only "what versions exist for a known
  `artifact_id`" (see Design section above for why).
- The CLI has no `register-source`/`register-plan` verb — registration
  is a Python API action; adding CLI verbs for it would be
  straightforward but wasn't required to prove the phase's success
  criterion.

### 14. Recommended Phase E

Per the task's own stop condition, this phase is complete: register →
persist → plan → validate → execute → orchestrator → SCOUT → DurablePool
→ ArtifactStore, all tested, reproducing identical acquisition intent
deterministically. A real Phase E scheduler would read `AcquisitionPlan.schedule`
and call `execute-plan` on a cadence — still explicitly out of scope, as
is any FEP/information-gain-driven acquisition request targeting a
registered plan/source (which this phase's `AcquisitionRequest`/`AcquisitionPlan`
shapes remain deliberately ready to receive, without depending on it).
