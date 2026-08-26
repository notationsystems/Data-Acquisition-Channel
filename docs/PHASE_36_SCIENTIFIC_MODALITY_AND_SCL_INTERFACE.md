# Phase 36 — Scientific Modality Reconnaissance and the DAQ/SCL Joint Decision

*(Continues from `ca3d0aa`. Coordinated DAQ/SCL phase, run as the brief's three stages:
parallel reconnaissance → requirement/capability exchange → one joint decision.)*

**Joint decision (SCL-authored, mirrored here): `fourier_transform_1d`, `daq_extension: none`.**
**DAQ's proposal is issue 5 and frames the choice the rule could not pose.**

Recorded in `architecture/proposals/2026-08-25-daq-workload-proposal.yaml`, carrying the
SHA-256 of both exchange artifacts.

**This is deliberately a proposal, not the joint decision.** A joint decision is a two-party
act, and this session has write access to DAQ and read-only access to SCL — so a decision
record authored here would be one party writing both sides, destroying the exact property such
a record exists to provide. The decision belongs where both digests can be verified against
their origin repositories. DAQ's half is committed: its capability measurement, its reading of
SCL's *published* requirements, and a recommendation with rationale.

**DAQ's contribution to that decision is gate A** — the current representation is sufficient
for the selected workload. No DAQ representation change was made, and none is required.

Two things this phase found that were not on the brief's list, both corrections to my own
prior work or to the repository's verification substrate:

1. **`generation_depth_bounded` was a claim, not an invariant.** It declared "derivation from
   derivation is bounded and the depth is recorded" with `status: vacuously_enforced` — and
   nothing in this repository computes, records, or bounds a depth. Its evidence line argued
   only that a *cycle* is unconstructible, which is true and does not support the rule:
   acyclicity is not boundedness.
2. **The meta-test that should have caught that is too weak, and 17 other invariants are in
   the same position.** Locked, not silently fixed.

---

## SCL substrate reconnaissance — and a stale-checkout correction

**The reconnaissance measured `edfc2dc`, which is three commits stale.** SCL has since done
Phase 1 recon and its exchange artifact (`0bb3e66`), generalized the operation boundary and
implemented `fourier_transform_1d` (`e49828b`), and stated the operation contract (`5447df3`).
Re-measured at `5447df3`, most of the headline numbers I reported are wrong:

| Claim as reported | Measured at `5447df3` |
|---|---|
| one operation, `lj_pairwise_energy_forces` | **two** — a real `operation_registry.cpp` table also carries `fourier_transform_1d` |
| dispatch is a single string equality | **a registry table** with `find_operation(name)` |
| complex arithmetic MISSING | **present** — `fourier.cpp` uses `std::complex<double>` |
| transform MISSING | **present** — `fourier.cpp`, `op_fourier.cpp`, `fourier.hpp` |
| 63 tests collected, 32 passed | **204 collected** |
| **1 of 28 primitives = 3.6%** | **wrong as of current SCL** |
| "every workload blocked at the protocol boundary" | **wrong** — the boundary was generalized in `e49828b` |

SCL reports Fourier validated 40/40 with 203 tests passing. **Those are SCL's figures, carried
with attribution, not DAQ's re-derivation.** SCL's native build needs `nlohmann_json`, absent on
this host, so its suite errors here at the build fixture: DAQ can measure SCL's *structure*
(sources, registry table, type signatures, wire layout, 204 collected) but not its *behaviour*.
Cross-repo measurement without the build is exactly where a confident wrong number enters, so
the capabilities artifact carries no SCL figures at all — verified, it re-derives none.

`3.6%` and "every workload blocked at the protocol boundary" are **withdrawn**. The matrix was
rebuilt on `5447df3` before any recommendation was carried forward — see
**Workload / primitive matrix** below. It moved the recommendation, which is what a re-measure
is for.

## DAQ capability exchange

`architecture/exchange/daq_capabilities.yaml` — `sha256:9961596953ea…f210b3cb`

*(The committed artifact is the concurrent session's — see* **Canonicalization** *below. The
statuses below are what both independent measurements agreed on.)*

| Modality | Status |
|---|---|
| scalar | **supported** |
| vector | partial |
| time series | partial |
| multivariate time series | **absent** |
| spatial field | **absent** |
| spectrum | **absent** |
| trajectory | **absent** |

Measured details that drive the decision:

- **Vector** is carried, hashes deterministically, and survives the full persistence round
  trip — but `quantity_is_typed` requires `isinstance(value, (int, float))`, so it is refused
  `UNTYPED_QUANTITY`. And a list under any **non-`value`** key passes
  `no_context_free_property` *and* raises `TypeError: unhashable type: 'list'` in
  `_group_by_comparison_context` — admissible yet unanalysable. That is the exact bite.
- **Time series** has two incompatible carriers of the same 240 real readings. The
  per-reading carrier is property-shaped and graph-reachable but emits 240 independent
  Observations with **no series object**. The window carrier keeps a `readings` list but
  never parses its numbers (every element is a string), is not property-shaped, and is not
  graph-reachable (0 referents, 0 relationships).
- **Discarded, and it is DAQ's discard, not the source's:** the adapter hardcodes
  `time_zone=gmt` into the request URL and no extractor carries it into content. DAQ knows
  the time base and drops it — an asymmetry with `unit`, which is equally request-determined
  and *is* threaded through the binding.
- **Ordering** is not represented: `all_observations()` returns content-hash order. It is
  *recoverable* (lexicographic sort of `measurement_time` equals chronological for this
  fixed-width format) but the representation makes no guarantee.
- **Sampling interval / frequency**: absent from the representation, and **not stated by the
  source**. Not fabricated.

## SCL requirements exchange

`architecture/exchange/scl_requirements.yaml` — `sha256:be15539449f2…95636017`

**A read-only mirror, and marked as one.** The origin is SCL's own artifact at `5447df3`; the
copy here is byte-identical to those committed bytes and hashes to the digest in the *origin*
repository's own `.sha256` sidecar.

**I over-stated the objection here earlier.** I wrote that a locally-held copy would be "DAQ's
account of SCL's requirements". That is wrong for this artifact: byte-identity plus a matching
upstream sidecar means it *is* SCL's own emission, and the proposal may reference its hash
directly. The mirror was fine as it stood. What the sidecar and the byte check actually protect
against is a future session **regenerating it locally and not noticing** — which is why it is
labelled a mirror with the upstream digest recorded, rather than left looking like an artifact
this repository owns. The labeling is the safeguard; the provenance was never in doubt.

| Workload | DAQ availability (measured) |
|---|---|
| `fourier_transform_1d` | all DAQ-owned requirements **SATISFIED** |
| `convolution_1d` | satisfied |
| `least_squares` | unmet: `stable_sample_and_variable_identity` |
| `pca` | unmet: `stable_sample_and_variable_identity`, `commensurable_units_or_explicit_scaling` |
| `kalman_filter_linear` | unmet DAQ-side requirements |
| `pid_controller` | pure computation only |
| `viterbi` | unmet DAQ-side requirements |

Statuses are SCL's own, read from its `blocking_requirements` blocks, not this repository's
reading of them. The decision record and its test use SCL's exact workload names so the two
artifacts share one vocabulary.

## Workload / primitive matrix — rebuilt on the current commit

The earlier matrix was measured at `edfc2dc` and its central claim — a "universal gate" of wire,
configuration and result primitives that unblocked zero workloads and behind which everything
sat — described a substrate that **no longer exists**. Rebuilt at `5447df3`
(`architecture/workload_primitive_matrix.yaml`):

**8 primitives EXISTING, 8 MISSING** — not 1 of 28.

| Now EXISTING | Still MISSING |
|---|---|
| variable-length 1-D array on the wire | explicit rank/dims on the wire |
| generic per-operation configuration block | matrix multiplication |
| operation-generic result shape | transpose |
| operation registry | stable linear solve |
| complex arithmetic | symmetric eigendecomposition / SVD |
| discrete Fourier transform | covariance propagation |
| normalization convention as a parameter | stateful feedback across calls |
| annotating-parameter rule | DP table with backtracking |

The gate is **built**. Its cost is paid and it is no longer a term in any candidate's cost.

Workload states, read from SCL's own `blocking_requirements` rather than re-derived:

| Workload | Blockers | State |
|---|---|---|
| `fourier_transform_1d` | 0 | **BUILT** |
| `convolution_1d` | 0 | **UNBLOCKED** |
| `pid_controller` | 0 | unblocked but out of scope (actuation) |
| `viterbi` | 1 | blocked (DAQ) |
| `pca` | 2 | blocked (DAQ) |
| `kalman_filter_linear` | 2 | blocked — **both DAQ-owned** |
| `least_squares` | 3 | blocked — **splits across both repos** |

Two things the re-measure surfaced that the stale matrix could not:

- **`kalman_filter_linear`'s blockers are both DAQ-owned**, and one of them is
  `recursive_generation_depth` — the invariant this phase corrected. That prerequisite is now
  supplied; `structured_measurement_uncertainty` remains open.
- **`least_squares` is the only candidate whose blockers split across both repositories**
  (two DAQ-owned, one SCL-owned), which makes it the natural subject of the joint rule's second
  clause: the smallest DAQ extension that unblocks the highest-leverage workload, paired with
  the workload that consumes it.

## The recommendation — reissued

**`convolution_1d`, `daq_extension: none`.** DAQ's answer is gate A.

The first issue recommended `fourier_transform_1d`. That is **withdrawn on completion, not on
merit** — SCL built it, and recommending something that exists is not a decision.

Applying the rule to SCL's own blocking requirements at `5447df3`, `convolution_1d` is the only
in-scope candidate with zero blockers on either side. SCL states its DAQ requirement is
satisfied wherever Fourier's is, because it shares the ordered-1d modality.

**This is a weaker recommendation than the first, and the report should say so.** The
generality-falsification argument that selected a transform has been partly *spent*: the
substrate had been exercised by one kernel family, now by two, and convolution is adjacent to
the transform rather than orthogonal to it — it can even be implemented *through* it via the
convolution theorem. It is recommended because it is what the rule admits, not because it is
the most valuable thing to build.

**The rule's answer and the highest-value answer have come apart.** `least_squares` carries more
leverage and DAQ cannot elect it alone: its blockers split across both repositories, which is
exactly the shape the joint rule's second clause addresses. Framing that choice is DAQ's job;
making it is not.

## Canonicalization — resolved by coordinated reissue

The defect was a **class**, not the ISO-date bug I first reported: 6 of 20 scalars diverged
(date, datetime, sexagesimal `1:30:00`, hex `0x1F`, `.inf`, `.nan`), and the passing ones passed
*incidentally* — `0o777` only because PyYAML's 1.1 resolver doesn't know that form.

**The coordinated reissue landed.** SCL authored the corrected emitter citing this repository's
measurement; DAQ adopted it **byte-identically rather than reimplementing it**. Every digest
moved in one step, as the recorded blast radius predicted:

| Artifact | New digest |
|---|---|
| `daq_capabilities.yaml` | `sha256:d985e1a3…` |
| `scl_requirements.yaml` | `sha256:0ce4753c…` |
| `canonicalization_fixture.yaml` | `sha256:11521f5b…` |

Verified after the reissue: serializer, fixture, requirements mirror and decision mirror are all
byte-identical across the two repositories, and **all 23 scalars round-trip with zero
divergences**. The fix is emitter-side (`"k": "2026-08-25"`, quoted); a reader-side normalization
would have made an artifact's meaning depend on which reader opened it.

The characterization locks **fired as designed** when the serializer changed, with the message
telling the next reader to update the artifact rather than the assertion. They are now inverted
to lock the class *closed*, plus a new test asserting the two serializers stay byte-identical —
if they ever drift, every digest on both sides is suspect.

## The rule is defective, not merely in tension

Recorded in `architecture/selection_rule_defect.yaml`.

The rule reads: *select the highest-leverage workload whose requirements are ALREADY satisfied,
extend only as fallback.* **Satisfied-ness is a gate; leverage is only a tie-break inside it.** So
a blocked high-leverage workload can never beat an unblocked low-leverage one however small the
unblocking extension is — the two are never on the same axis.

Its answer *degrades as the substrate improves*: each build leaves the satisfied set populated by
whatever is adjacent to what was just done, which is by construction what generalizes least.

**The measured instance.** The rule admits `convolution_1d` — zero cost, adjacent to the transform
just built, implementable *through* it, adding no third family and no unpaid primitive. It excludes
the entire linear-algebra family.

**The sharpest case against it** is Kalman, and it is sharper than a tension:

- Both its blockers are **DAQ-owned** — the only candidate with *no* SCL-side blocker, so no
  linear-algebra family need be built for it.
- One blocker, `recursive_generation_depth`, **was supplied this phase**.
- Its one remaining blocker is `structured_measurement_uncertainty` — which is exactly the half of
  the non-scalar extension **DAQ's own coupling finding says must LEAD**, because it is the silent
  half (closing the multivariate half first turns a loud gate refusal into a silent late `TypeError`).

So the half that must go first for reasons internal to DAQ's own measurement is precisely the half
that makes Kalman fully admissible — and the *other* half is the shared blocker of `least_squares`
and `pca`. **One extension clears the DAQ side of three workloads.** The rule cannot act on this,
because Kalman isn't in the satisfied set and the extension branch is a fallback it never reaches.

**Proposed correction:** compare leverage-per-cost *across both branches*. Satisfied-ness becomes a
cost term (zero when satisfied, the extension's size otherwise) rather than a filter applied before
leverage is consulted. The named-consuming-workload constraint stays — that was never the defect.
Not applied unilaterally: changing a joint rule is a joint act.

## The workload didn't lose — the phase did

The gate was built to select an **unbuilt** workload. While it was blocked on exchange artifacts
and their canonicalization, SCL built `fourier_transform_1d`. By the time the gate could run, its
intended winner was complete.

The symptom is visible in the joint record: it selects `fourier_transform_1d` and reasons about
generality falsification and validation quality *as though choosing among unbuilt options*. The
reasoning is sound; the referent is stale.

Nothing about the sequence was unusual — reconnaissance, exchange, canonicalization repair and a
decision record are all necessary. Their combined latency simply exceeded the build latency of the
thing being gated. **A gate slower than the work it gates will be overtaken again**, and the second
time will look exactly like the first.

## The concurrent session

This phase ran alongside another session on the same branch, and merged with it three times.
Resolved on the merits each time, never by force-push:

- **Their `daq_capabilities.yaml` was taken over mine**, because they vendored SCL's actual
  `canonical_yaml.py` byte-identically and verified fixture agreement — what §2.1 requires and
  what a self-authored serializer cannot establish. **My serializer and its test were deleted**;
  two serializers would be the second system this project forbids.
- **They kept a decision record where I had demoted mine to a proposal.** The proposal wins:
  one party with read-only access to the other must not author a two-party decision. Their
  `reissue:` block is kept — it records that the capability artifact gained measured content
  after first issue, so the recorded digest stopped binding, caught by the same
  hash-binding test. The proposal now carries the current digest
  (`sha256:6e38c9cc…`), reissued rather than edited.
- Their depth correction and mine converged on the same result: `represented_unenforced`,
  enforced by `tests/test_recursive_lineage_depth.py`.

The reissue is worth noting on its own: the binding guarantee **fired in anger**. An artifact
changed, a recorded hash stopped matching its bytes, and the test that exists for exactly that
caught it rather than the drift going unnoticed.

## Independent corroboration of the selection

A concurrent SCL session generalized the operation boundary and implemented
`fourier_transform_1d` at `e49828b`, **independently selecting the same workload** from the same
two artifacts. SCL's own requirements artifact marks both DAQ-owned requirements for that
workload `SATISFIED` — `ordered_scalar_sequence` and `annotating_sample_spacing`, the latter
explicitly noting that SCL never assumes Δt=1 and that a result computed without spacing is
bin-indexed and says so, which is exactly the honest outcome this record's `daq_extension: none`
rests on.

That convergence is **corroboration of the selection, not validation of either side by the
other** — neither session reviewed the other's work, and the decision record says so. The
implementation is **cited, not claimed**: it was neither authored nor pushed from this session.

## Recursive computation and generation depth

The brief's conditional was: *if implemented, demonstrate the failure; if not, implement the
corrected semantics.* Measured, it is neither cleanly — it was **declared and never
implemented**:

- `architecture/invariants.yaml` was its only home; it is a YAML string with no code behind it.
- No authored or vendored evidence module defines any depth/generation/lineage symbol.
- `DerivedValue`'s fields are exactly `(id, derived_from, method, content, confidence,
  derived_at)` — **no depth**. The rule says the depth "is recorded"; there is nowhere to
  record it.
- The invariant declares **no bound value**.
- `evidence.provenance.ancestry_of` returns a flat set union that discards the level at which
  each node was reached.
- **No test anywhere exercised it.** Every `depth` hit in the suite is `depth_km`.

The original evidence line — "DerivedValue identity makes a derivation cycle unconstructible"
— is true and does not support the rule. **Acyclicity is not boundedness**, and an unbounded
acyclic chain is exactly what a recursive estimator produces. `tests/test_recursive_lineage_depth.py`
demonstrates this directly by constructing a 51-link acyclic chain that nothing prevents.

**The rule text was not weakened.** The *status* was corrected downward from
`vacuously_enforced` to `represented_unenforced` — an existing vocabulary value, not an
invented one — and the evidence line now states what is measurably true. The corrected
semantic domain (depth is evidence lineage, never iteration count; a recursive computation
carries `stream_identity`, `window_or_horizon`, `initialization_provenance`) is recorded on
the invariant and asserted by tests: N iterations over one measurement stream derive from the
**stream**, not from the previous iterate, so iteration count changes identity but not lineage.

## Generality-probe correction

The probe never caught this because **every property it enumerated was a property of an
observation**, so it had no way to falsify anything about computation. Recorded as a probe
limitation, with `recursive_computation` added under a new `computation_properties` key —
deliberately *not* appended to `observation_properties`, which would have been a category
error.

It is the **first FAIL the probe has ever returned**. `core_invariants_modified` remains 0: a
truthfulness repair to a status is not a semantic weakening. The probe remains `paper_only`.

## The meta-test that hid it

`test_the_invariant_ledger_names_every_test_in_this_file_it_claims` asserts only that the
named set is non-empty and contains two hardcoded ids — it never checks that a given invariant
corresponds to any test. Measuring the real bar exposed that **17 other invariants also name
an enforcement file that never mentions them**. Forcing all 17 to change belongs to a phase
about them, so the new test **locks the current set so it cannot grow** and asserts
`generation_depth_bounded` is no longer in it.

## PID actuation boundary

Pure PID computation is a candidate SCL workload. **Physical actuation is UNRESOLVED**: no
actuation-authority boundary exists in DAQ, SCL, or STE. Recorded, not built. No control plane
was created.

## Access / admissibility boundary

DAQ emits `class = measured` and never `computed`. Re-entry of SCL output as a DAQ observation
is forbidden, and measured to be unreachable: no shipped adapter or extractor produces a
`DerivedValue`; `ClassifiedPool` forces class `derived` for derived kinds and
`make_class_assignment` refuses `measured`/`asserted` for them; the only evidence write path is
`run_scout`, AST-asserted.

## Migration state (§17)

**Greenfield.** Zero committed evidence records; already enforced by an existing test. No
migration rules were needed and none were invented.

## Regression

| Check | Result |
|---|---|
| `tests/test_canonicalization_defect.py` | **38 passed** (new) |
| `tests/test_daq_workload_proposal.py` | **25 passed** (new) |
| `tests/test_recursive_lineage_depth.py` | **17 passed** (new) |
| DAF full suite | **847 passed** |
| Vendored SCOUT suite | 1273 passed, unchanged |
| Submodule | clean |
| SCL clone | untouched, `git status --porcelain` empty |
| `mypy .` | 4 pre-existing errors, 0 new |
| Doctrine | regenerated, zero diff |
| `git diff --stat -- daf/ science/ boundary/ bridge/ assertion/ vendor/` | **empty** |

No production acquisition code changed in this phase.

## Bent

**Bent: zero.** `core_invariants_modified` remains 0. `generation_depth_bounded`'s *rule* is
retained verbatim; only its status and evidence were corrected to match measurement, which is
a truthfulness repair. No invariant was weakened to accommodate recursion, and the probe
remains `paper_only`.

## Qualified

- The DAQ capability statuses are measured against *this repository's* sources. `absent`
  means "no real source here produces it", not "unrepresentable in principle".
- The FFT selection rests on DAQ availability plus generality; convolution is genuinely
  cheaper (6 primitives vs 11) and would be the right answer under a pure-cost criterion.
- The SCL substrate measurements were taken on a host with no GPU, no BLAS, and no
  `nlohmann_json` installed; the native build required vendoring that header into scratch.
  Nothing about GPU numerical behaviour may be claimed.
- `sha256` over document bytes is not the substrate's evidence identity and does not become
  one: nothing in `epistemics/exchange.py` produces an id that enters the evidence pool.

## Unresolved

- **The canonicalization defect is open and needs coordination.** The corrected rule is
  measured and recorded; applying it re-hashes both exchange artifacts, the agreement fixture,
  and every digest reference, so it must land in both repositories as one reissue.
- **The joint decision is not written.** DAQ's proposal is committed; the decision needs an
  author who can verify both digests against their origin repositories.
- **SCL implementation access.** Push to `Scientific-Compute-Layer-SCL-` was denied, so SCL's
  Fourier work could only be read and cited, never verified by building it here (`nlohmann_json`
  is absent on this host).
- **17 invariants name an enforcement file that never mentions them** — locked, not fixed.
- **The write-side condition asymmetry** (Phase 35's `graph_dataset` gap) — unchanged.
- **NOAA timezone discard** — measured, not fixed: no named consuming workload requires it, and
  a uniform offset does not change a spectrum.
- Carried unchanged: `quarantine_repair`, `retraction_semantics`, `multi_writer.write_conflict`,
  `builder_check_lineage`, `attested_snapshot_identity`, `capabilities_5_to_9`, PID actuation
  authority.

## Next executable frontier

**Land the corrected §2.1 canonicalization rule in both repositories as one coordinated
reissue** — strings always double-quoted, implicit typing forbidden, two-parser *typed*
agreement as a required verification step — then re-emit both exchange artifacts, the agreement
fixture, and every digest reference together, and write the joint decision record against the
reissued digests where both can be verified against their origin repositories. This is a single
change with a known blast radius, recorded in `architecture/canonicalization_defect.yaml`, and
everything downstream of the exchange is blocked behind it: a proposal carrying digests that
are about to change cannot become a decision until they have.
