# Phase 38 — GPC Extractor: the first acquisition path that reaches the chemistry-shaped gates

**No acquisition was performed.** There is no GPC instrument, no polymer and no
replicate data anywhere in reach of this repository. Every number in this phase is
fabricated, is labelled `fabricated_fixture` inside the content it produces, and says
nothing about any material. What is real is the path.

---

## 0. The INSPECT pass, and what it corrected

The brief's own first instruction was that §2 was stated from the program record rather
than from the repository, and was to be verified before anything was built on it. It was.
Most of §2 held. Three things did not.

**§2.1 held, in substance, and its OWNER was wrong.** The brief and
`architecture/polymer_acquisition_readiness.yaml` both phrase the irreversible
precondition as *"the extractor emits one Record per RUN."* Extractors do not emit
Records. `scout.pipeline.run_scout` builds exactly one Record per RawDocument
(`make_record(document_id=document.id, locator=raw_doc.locator,
raw_content=raw_doc.content)`), and `Extractor.extract` **receives** that one Record;
every candidate it returns names it. An extractor handed one Record per report cannot
emit five, whatever it does.

So the one precondition the readiness record calls unrepairable belongs to the
**adapter**, and a careful author who read that record and wrote only an extractor would
have violated it while believing they had satisfied it. The obligation is now discharged
and documented in `daf/adapters/gpc_report.py`, where the next adapter author will be
standing.

**§2.6 does not hold at all.** The brief presents `no_point_identity_for_distributions`
and the `resolution_policy` requirement as active rules the extractor must satisfy.
Measured in `architecture/invariants.yaml`:

    identity_policy_declared            status: absent
    no_point_identity_for_distributions status: absent
    computed_fully_specified            status: absent
    applicability_domain_declared       status: absent
      gap (all four): "no chemistry representation exists in this repository at all"

There is no gate to satisfy **in DAQ**, and building one would be building the chemistry
representation §7 explicitly forbids. **Nothing was built for §2.6 and nothing was
proposed.**

**Sharpened after the first draft: the rules are not absent, they are STE's.** All four
are implemented and enforced in `structures/` at the pin — see §4. So the row's word
`absent` is true and the inference a reader draws from it is wrong, because the row
answers *absent where?* with a scope nobody wrote down. §2.6 was misfiled in the brief,
not mistaken. Recorded in `architecture/chemistry_rule_ownership.yaml`.

**A third thing, found by measurement and in neither the brief nor the program record:
the two DAF-owned content gates disagree on the column key, and one requires a key the
other never mentions.**

    science.table.observation_is_table_alignable   requires  sample_id, variable
    science.admissibility.no_context_free_property requires  property, method

Neither mentions the other's key. `architecture/polymer_acquisition_readiness.yaml`
states that five replicates *"pass every gate that exists"* — that claim is scoped to the
table gate, and the very content its own tests use is refused by the second gate:

    no_context_free_property(readiness_shape)
      -> ('MISSING_METHOD', 'MISSING_PROPERTY')

Both gates are correct on their own terms and nothing owns the relation between them.
This is the `two_correct_gates_and_an_unowned_relation` class already filed in
`architecture/proof_integrity.yaml`, arriving again. The extractor satisfies both by
carrying one string under both names and emitting `method` beside them. That is
duplication in content, it is recorded as such, and reconciling two science-layer gates
is not an acquisition extractor's decision — see §7 below.

---

## 1. Implemented

| Artifact | What it is |
|---|---|
| `daf/adapters/gpc_report.py` | One RawDocument **per run**. Run and report ids go on `locator`, never into content. `data_provenance` required from a closed vocabulary, never defaulted. |
| `daf/extractors/gpc_report.py` | Typed, not pass-through. One ExtractionCandidate per measurement. Refuses derived columns, unlabelled provenance, leaked locators, empty conditions. |
| `tests/fixtures/gpc_report_synthetic_ps4471.json` | Five injections, two variables, per-run uncertainty, eight conditions. Fabricated. |
| `tests/fixtures/gpc_report_synthetic_derived_column.json` | Same, plus a `dispersity` column. |
| `tests/fixtures/gpc_report_synthetic_unlabelled_provenance.json` | Same, with the provenance label removed. |
| `tests/test_gpc_acquisition.py` | 19 tests, including five detector proofs. |
| `tests/test_condition_provenance_reachability.py` | §20's check repaired from a grep to a derived property — see §6. |

## 2. Contract

An acquired GPC observation carries exactly:

    sample_id, variable, property, value, unit, uncertainty, uncertainty_kind,
    method, conditions (FrozenMapping), data_provenance

`variable` and `property` are the same string, for the reason in §0. Run identity is
absent by construction and asserted absent by the extractor. Nothing is defaulted,
inferred, or supplied by either module: every field is one the report declared.

## 3. Loop

    fixture -> GpcReportSourceAdapter -> 5 RawDocuments -> run_scout
            -> 5 Records -> GpcReportExtractor -> 10 ExtractionCandidates
            -> 10 Observations (10 distinct ids, 5 distinct Records), 0 admission failures
            -> observation_is_table_alignable   admissible on all 10
            -> no_context_free_property         admissible on all 10
            -> pair_replicates                  1 set, 5 runs x 2 variables, 0 refusals
            -> covariance_of                    rho = 0.8962762979716654

**That rho is a property of the fixture, not a measurement.** It is asserted against the
value recomputed from the fixture file's own numbers, not against a literal constant that
would read like a finding. The test additionally asserts `0 < |rho| < 1`, because
`architecture/polymer_vertical.yaml` records that a degenerate design returns a confident
number that is not a measurement, and a fixture producing rho = ±1 would exercise the
path without exercising the pairing.

## 4. Reachability

The evidence is reachable as a referent. Every earlier DAF extractor except
`graph_dataset` emits `entities=()`, which is why acquired evidence had never been
reachable from `materials` at all. The GPC extractor transports the sample identity the
report itself declares (`sample_id`, `sample_kind`) as one `ExtractedEntity`, and the
pool admits `('PS-lot-4471', 'sample')`. It invents nothing: `kind` is the report's word.

**The chemistry gate number is not DAQ's to report.** Verified at the pin
(`5e146d5`): `vendor/scout-retrieval-agent/architecture/chemistry_reachability.yaml`
records `codes_total: 20`, `live: 20`, `reachable_from_any_entry: 0`, generated by
`scripts/chemistry_reachability.py` inside the unmodifiable submodule. Its own text
carries DAQ's `admission_reachability.yaml` rule verbatim: *"zero_rate_when_unreachable:
no entry path can reach the gate. NOT a measurement; the metric is silent, not clean."*

DAQ's report is therefore only this: **an acquisition path now exists that enters at the
adapter, carries a property with method, conditions, units and an uncertainty posture,
and lands in the pool with a referent.** DAQ has not re-run the probe and does not claim
any code moved.

**CORRECTED after this report's first draft, which left open whether the new path moves
STE's number.** Measured, it cannot on its own. Across the whole vendored tree at the pin,
the only callers of the four chemistry guards outside `structures/` and `tests/` are
`scripts/chemistry_reachability.py` and `scripts/mutate_reachability_checks.py` — the
probe itself and its mutation harness. **Nothing in any admission or acquisition path
calls any of them.** Reachability needs a call site, not richer content: an acquisition
path carrying chemistry-shaped content past a guard nobody calls is still zero reachable,
and that call site would be inside the unmodifiable submodule. STE's own summary carries
the field that would move — `exercised_by_real_acquisition: 0` — and DAQ now asserts it
is still zero rather than leaving the inference open.

**And §2.6 was misfiled, not absent.** All four rules the brief filed to DAQ are
implemented and enforced in STE's `structures/` at the pin: `assert_identity_policy` and
`assert_distribution_identity` in `structures/substance.py`, `assert_method_block` and
`assert_applicability` in `structures/method_blocks.py`. DAQ's four `status: absent` rows
are true *of DAQ* and say nothing about the pair — a row reading `absent` answers *absent
where?*, and the scope was never written down, so the row was true and unfalsifiable at
once. The rows are left as they are, because one that started describing another
repository's state would be a worse record; what is added is
`architecture/chemistry_rule_ownership.yaml`, naming the owner and the pin, enforced by
`tests/test_chemistry_rule_ownership.py`. Nothing was built to satisfy the clause and the
clause was not dropped.

## 5. Discriminating

A check that fires on everything discriminates nothing.

- **A genuine condition with repeated levels is not flagged.** Five runs at two column
  temperatures (three and two) produce two genuine replicate sets and zero refusals.
  Without this case `EVERY_RUN_DIFFERS_IN` would be indistinguishable from *complain
  whenever there is more than one set*.
- **Carrying a source's own conditions is not flagged** by the repaired §20 check, while
  fabricating them is — both halves asserted, because a check that flags every mention is
  the grep again under a new name.

## 6. Mutations (detector proofs)

Every check below was proved by planting the defect it claims to catch and watching it
fail first.

1. **One Record per report, differing values → LOUD.** Ten observations land under one
   Record; `pair_replicates` refuses with `CONFLICTING_VALUE_FOR_A_RUN` and
   `covariance_of` yields no covariance.
2. **One Record per report, equal values → SILENT, and this is the unrepairable one.**
   Five identical runs per variable collapse to **two** observations, because Observation
   identity is over `(record_ids, extraction_method, content)` and all three agree.
   Nothing raises. No admission failure. The pairing has nothing to complain about: one
   run reporting two variables once each is a well-formed — and entirely wrong —
   replicate set. The members the spread was to be computed over never existed. The same
   data through the real adapter keeps all ten.
3. **A run identifier in content is refused at the extractor**, and separately, **would
   otherwise be silent**: with the guard removed the pairing reports
   `EVERY_RUN_DIFFERS_IN` over five single-member sets — the shape indistinguishable from
   a pool genuinely holding one run.
4. **A derived column is refused, not dropped.** `dispersity` is Mw/Mn.
   `architecture/evidence_class.yaml` classes computed evidence as
   `evidence.types.DerivedValue`, and there is no path from `Extractor` to DerivedValue —
   so the only thing this interface could do with it is emit it wearing the `measured`
   class. Dropping it silently is the other failure: the report would say something the
   pool does not.
5. **The repaired §20 check catches a fabricated condition in a real extractor file**,
   naming the keys (`['datum', 'solvent']` planted in `local_dataset.py`, reverted after).

## 7. Self-corrections

Four, all caught by a mechanism rather than by review.

- **The first draft of the extractor imported `science.admissibility.UNCERTAINTY_KINDS`.**
  The layer test caught it: `daf` must not import `science`. The rule it was reaching for
  was not missing — it was already owned; `quantity_is_typed` returns
  `UNKNOWN_UNCERTAINTY_KIND` for exactly this. The vocabulary is now neither imported nor
  restated (a second copy would drift); the extractor asserts only what an acquisition
  layer can know, that the report said something rather than nothing.
- **The first draft of the one-Record-per-report detector proof asserted the wrong
  thing** — that ten measurements would collapse to fewer than ten. They do not, because
  `value` differs between runs. The collapse the readiness record describes needs *equal*
  values. Correcting it split one test into two and produced finding 6.2 above, which is
  the more serious half and was not in the brief.
- **The discriminating-case test grouped by observation index** rather than by Record.
  `pool.all_observations()` is unordered by run, so the two observations of one run were
  split across temperature levels and the sets came back ragged. Fixed by grouping on
  `record_ids[0]`.
- **§20's check was a grep, and the GPC extractor made that visible.** See below.

## 8. Bent / Qualified / Unresolved

**BENT — one, and it was repaired rather than added to.**
`test_no_extractor_declares_a_conditions_key` was a search for the literal string
`"conditions"` against a hard-coded list of files permitted to contain it. The GPC
extractor declares a `conditions` key and fabricates nothing — the value is the source
report's own mapping, passed through the shared tightening seam. Under the grep that is a
violation; under §20 it is precisely the intended behaviour, while a bespoke fabricated
mapping inside a file already on the list would have passed.

The check read a proxy for its target — the root class in
`architecture/proof_integrity.yaml`, which records **24** instances of it. That number is
counted from the artifact, not recalled: an earlier draft of this report said eleven,
which is the `reading_a_subset_as_though_it_were_the_set` class committed in the sentence
citing it. Adding a ninth filename to the allowlist would have been the
enumerated-coverage repair again. The property is derived instead, from the syntax: **an extractor may CARRY conditions freely and may not
CONSTRUCT them.** The exception list now covers exactly the violating behaviour (NOAA
constructs `FrozenMapping({"datum": self.datum})`, a genuine condition with a shared
representation) rather than every mention of the word. A new pass-through extractor needs
no entry; only a new extractor that fabricates condition keys does, which is the thing
§20 wants visible.

**QUALIFIED — "doctrine zero diff" was vacuous for this phase's artifact change, and
saying so is the point.** The standing phase discipline is that every architecture change
goes through the doctrine generator with a verified zero regeneration diff. That was run
and it was zero. It was also silent: `architecture/doctrine.yaml` lists **19 sources**
where `architecture/` holds **27** YAML files, and
`polymer_acquisition_readiness.yaml` — the file this phase corrected — is not among
them. Neither are `polymer_vertical.yaml`, `canonicalization_defect.yaml`,
`selection_rule_defect.yaml`, `nonfinite_identity_reachability.yaml`,
`kalman_validation_preregistration.yaml` or `workload_primitive_matrix.yaml`.

The curation looks deliberate rather than drifted — the doctrine projection covers the
control loop, evidence classes, roles, invariants and unresolved items, and a defect
record or a readiness record is not doctrine. **No change is proposed here**, because
rewriting the source list would move the source digest and every hash reference bound to
it, and that is not this phase's call. It is now recorded as an explicit UNDECIDED with a
trigger rather than as this paragraph — `architecture/doctrine_coverage.yaml`, enforced by
`tests/test_doctrine_coverage.py` — because two parked items have already faded from
prose. Measuring it for the record turned up something worse than the vacuous green:
**two artifacts, `kalman_validation_preregistration.yaml` and `selection_rule_defect.yaml`,
are covered by neither the projection nor any test at all.** They could be arbitrarily
stale and the whole suite stays green. Named as executable work rather than bound in
passing, since binding an artifact whose claims have not been re-measured is worse than
marking it honestly unbound. What is recorded is narrower and is the
`zero_rate_when_unreachable` rule turned on the repository's own process: for 7 of 27
architecture files, a zero doctrine diff is not evidence that nothing broke. It is the
metric being silent, not clean. The artifact change in this phase is instead bound by
`tests/test_polymer_acquisition_readiness.py`, which reads it directly.

**QUALIFIED — the precondition gate is a self-check.** Build order step 4 pointed DAQ's
own `science.replicate_pairing` at DAQ's own extractor's output. A gate validating output
from the same repository that wrote it is weaker evidence than the cross-repo cases, and
it is stated as such rather than read as independent confirmation. What partly offsets it
is that the gate was written before this extractor existed and was validated against a
known correlation, and that the detector proofs plant defects rather than confirm
successes.

**UNRESOLVED, and deliberately untouched.** §2.6's four chemistry invariants are
`status: absent` and stay absent. The polymer vertical's status stays
`measured_not_proposed`. A gap measured is not a change proposed. Nothing here decides
whether the substrate should distinguish a population from an object; no surrogate model,
candidate generation, optimizer, `ProposalStore`, polymer ontology or CUDA was built; and
none of the parked decisions (tombstone semantics, `multi_writer.write_conflict`,
`builder_check_lineage`, capabilities 7–9) was resolved.

**Also unresolved: the duplicated column key.** `variable` and `property` carry one
string because two science-layer gates read two different keys for one concept. The
extractor asserts they can never drift, and
`test_the_two_science_gates_disagree_on_the_column_key` binds the finding to a mechanism
rather than to this paragraph — if either gate is ever reconciled with the other, that
test fails and the duplication can be removed.

## 8b. What the follow-up pass added

Four things, after the phase first landed.

- **The §20 repair was re-run against the probe that motivated it.** A repair is an
  untested assertion until that happens, and the suite is green on both sides of it. The
  old check's predicate still fires on `gpc_report.py` (it does contain the string) — which
  is why the fix was a repair and not a ninth allowlist entry — and the repaired check
  refuses **that same file** the moment it constructs a condition instead of carrying one
  (`['solvent', 'column_temperature_c']`). Bound as
  `test_the_repair_is_re_run_against_the_probe_that_motivated_it`, with the mutation
  asserted to have applied, so a diff that cannot reach the property counts as malformed
  rather than as caught.
- **§2.6 recorded as a misfiling**, in `architecture/chemistry_rule_ownership.yaml` with
  `tests/test_chemistry_rule_ownership.py`. The rules are STE's, live at the pin; the
  record re-measures the vendored tree rather than restating it, and its coverage is
  derived from `invariants.yaml` so a fifth row acquiring the same gap cannot sit
  unrecorded. The four DAQ rows are left reading `absent`.
- **§4's reachability claim corrected.** The acquisition path cannot move STE's number on
  its own; reachability needs a call site inside the unmodifiable submodule, and there is
  none.
- **The register census moved 36 → 37** and was regenerated: the new artifact declares
  `extends: core@1.0.0`, so it is counted. Exactly one line and its digest changed, and no
  other artifact referenced the superseded hash.

## 8c. Binding the defect record, and what the pair boundary turned out to be

`selection_rule_defect.yaml` bound first, because a stale defect record is worse than a
stale pre-registration: the pre-registration's thresholds are dated by construction, and
a defect record makes claims about a live rule with no such marking. The rule had moved.

**Four stale claims, one of them the record's own headline.**

| Dated claim | Measured |
|---|---|
| the joint record *"selects fourier_transform_1d"* | it elected **option_b, least_squares**; fourier was *withdrawn on completion*, never selected |
| correction *"not_yet_applied"* | the joint record carries it and **decided a workload under it** |
| Kalman's *"one remaining blocker"* | **both** its DAQ blockers are `SATISFIED` at the pinned hash |
| `generation_depth_bounded` *"represented_unenforced"* | **`enforced`**, two corrections on |

The dated sentences are kept beside the corrections rather than rewritten. What survives
untouched: the process finding (a gate slower than the work it gates was overtaken — that
is unchanged, and the symptom was mis-stated as a *selection* when it was a *withdrawal*),
and the least_squares/pca blocker sets, which measure exactly as recorded. The rule
critique is an argument, and the binding deliberately does **not** certify it — a test
asserting an argument is true is the self-consistent-and-wrong shape.

**Then I edited a shared artifact and had to revert it.** Recording the
knowing-the-class-does-not-inoculate property in `proof_integrity.yaml` was a unilateral
edit to a file the pair holds byte-identically. Caught by reading the file's own header
after writing, and reverted; `proof_integrity.yaml` is byte-identical across the pair
again, verified. The property is not lost — it is the user's, and stating it in a joint
artifact is a joint act.

**And measuring the pair boundary corrected my own record from the previous pass.** I had
written that `kalman_validation_preregistration.yaml` is *covered by nothing*. Measured:
SCL's `architecture/` holds exactly two files — `kalman_validation_preregistration.yaml`
and `proof_integrity.yaml` — so the remaining unbound artifact is **shared**, and
`verify_pair_landed.py` compares it byte for byte. Both are byte-identical today.

That is coverage for **divergence**, not for **currency**: a byte-identical pair of equally
stale artifacts passes every check either repository has. Those are different properties
and the first version conflated them — and the distinction supplies a stronger reason for
the ordering than the one either of us gave. Binding the pre-registration means
re-measuring it, re-measuring may find a correction, and a correction changes bytes the
pair verifier holds identical. `selection_rule_defect.yaml` is DAQ-only and was
correctable alone; **the pre-registration is shared and its correction is a joint reissue.**

The divergence check is detector-proved by planting a one-byte change in SCL's copy and
watching it fail by name; SCL's tree was restored and verified clean. The check skips
rather than passes when the counterparty is absent — a claim about an intersection
measured against a missing repository is the vacuous pass this repository has filed
repeatedly.

**The trigger tightened its own baseline.** It fired on the *shrink* direction naming
`selection_rule_defect.yaml`, which is the direction a baseline quietly rots in if it only
ever fires on growth.

## 9. The next executable frontier

Exactly one:

> **Point `no_context_free_property` and `observation_is_table_alignable` at the same
> content from a single call site, and decide which of `variable` and `property` is the
> column key.**

It is executable today, needs no data and no instrument, and it is the only item here
that is currently costing a real content key on every acquired observation. It is a
science-layer decision, so it is named rather than taken.
