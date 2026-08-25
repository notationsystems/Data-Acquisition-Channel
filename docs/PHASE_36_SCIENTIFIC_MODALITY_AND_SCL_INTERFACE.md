# Phase 36 — Scientific Modality Reconnaissance and the DAQ/SCL Joint Decision

*(Continues from `ca3d0aa`. Coordinated DAQ/SCL phase, run as the brief's three stages:
parallel reconnaissance → requirement/capability exchange → one joint decision.)*

**DAQ's proposal: build `fourier_transform_1d`; `daq_extension: none`.**

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

SCL reports Fourier built and validated 40/40 with 203 tests passing. **I did not verify those
numbers**: SCL's native build needs `nlohmann_json`, which is not installed on this host (a
recon agent vendored it into scratch to build at all), so its suite errors here at the build
fixture. 204-collected is measured; the pass counts are SCL's own and are cited, not confirmed.

**What survives the correction, and why the recommendation is unaffected:** the primitive
matrix measured *primitive absence at `edfc2dc`*, which is a narrower claim than "workload
runnable" — and the workload it scored as most-unblocked-by-DAQ-availability is precisely the
one SCL then built. The leverage *arithmetic* (Kalman's 14× sequencing penalty, the
linear-algebra cluster's shared cost) is about relative ordering among unbuilt workloads and is
not disturbed by Fourier existing. But the report should not have carried `3.6%` and
"every workload blocked" as current facts, and they are withdrawn here.

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
copy here is byte-identical to those committed bytes and was **not regenerated in this
repository**. Verified: the mirrored bytes hash to the digest in the *origin* repository's own
`.sha256` sidecar — no divergence exists.

Regenerating it here would have made it *DAQ's account of SCL's requirements* rather than SCL's
measured claim about itself, and the proposal's hash would then bind a copy whose provenance is
a different repo than the one it describes. That is the same failure as an agent validating its
own output through a second file it also wrote.

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

## Workload / primitive matrix (measured at `edfc2dc`, superseded for Fourier)

*(Fourier's row is historical: it describes the substrate before `e49828b`. The rest still
describes unbuilt workloads.)*

| Workload | Required | Hard-missing | Needs new code |
|---|---|---|---|
| convolution | 7 | 4 | 6/7 |
| PID | 7 | 4 | 6/7 |
| **FFT** | 10 | 7 | 9/10 |
| Viterbi | 11 | 9 | 10/11 |
| PCA | 11 | 8 | 10/11 |
| least squares | 12 | 8 | 11/12 |
| Kalman | 15 | 11 | **14/15** |

The universal gate — a variable-length array on the wire with an explicit shape, a generic
configuration block, and a callable reduction — unblocks **zero** workloads by itself, and
nothing is reachable without it.

Ordering result worth recording: **Kalman costs 1 additional primitive if built after the
linear-algebra cluster and 14 if built first — a 14× sequencing penalty.**

## The recommendation

**`fourier_transform_1d`, `daq_extension: none`.**

The rule is: select the highest-leverage workload whose observation requirements are *already*
satisfied by DAQ. Applying it mechanically:

- `least_squares`, `pca`, `viterbi` — **forbidden**, DAQ marks their entry modality absent.
- `kalman_filter_linear` — only partially satisfied, and worst-case to sequence first.
- `pid_controller` — satisfied for pure computation, but its distinctive value is actuation,
  and no actuation-authority boundary exists anywhere. Building it would create an implicit
  control plane.
- `fourier_transform_1d` and `convolution_1d` — identical observation requirements, both
  satisfied.

FFT wins over convolution on three measured grounds: **generality falsification** (the
substrate has been exercised by exactly one MD kernel; a transform is orthogonal to it and to
the linear-algebra family, whereas convolution shares the existing kernel's reduction shape),
**independent validation quality** (impulse, DC, pure tone, Parseval, reconstruction — none of
which requires a second implementation, while convolution's natural oracle is another
convolution), and **contract generality** (it forces `input_kind`, `spectrum_convention`,
`direction`, `normalization`, `precision`, `sample_spacing` into the parameter identity model).

`daq_extension: none` because the workload needs nothing DAQ lacks. CO-OPS states no Δt, and
the correct consequence is a **bin-index axis, not a fabricated frequency axis**. Extending
DAQ to carry a Δt the source never provided would be fabrication; extending it for any other
modality would be representation work with no named consuming workload, which the joint rule
forbids.

The reuse-leverage argument (least squares → linear algebra → Kalman → PCA, 17 primitives for
3 workloads) is **not rejected — it is unreachable today**, and is recorded in the decision as
deferred on availability rather than on merit.

## Canonicalization — the defect is a class, not a date bug

My earlier report called this an ISO-date divergence. That was too narrow, and the actual
defect is the spec's scalar rule. YAML implicit type resolution lets two conformant parsers
agree on the bytes and disagree on the **type** — so a byte-identical artifact can hash-bind a
different typed structure on each side, which is exactly what pinning was meant to prevent.

Measured against the shared serializer, **6 of 20 scalars diverge**, not one:

| Scalar | This repo's reader | PyYAML |
|---|---|---|
| `2026-08-25` | `str` | `datetime.date` |
| `2026-08-25T12:00:00Z` | `str` | `datetime.datetime` |
| `1:30:00` | `str` | `int 5400` (sexagesimal) |
| `0x1F` | `str` | `int 31` |
| `.inf` | `str` | `float inf` |
| `.nan` | `str` | `float nan` |

`yes`/`no`/`on`/`off`, `null`, `~`, `007`, `1_000` pass **incidentally** — caught by the
emitter's numeric-and-reserved-word checks, not by a rule closing the class. `0o777` passes
only because PyYAML's 1.1 resolver doesn't recognise the `0o` form.

The corrected rule — **strings always double-quoted**, not "only where required" — was measured
to close **all 23** tested scalars, every current divergence included. And the two-parser check
is promoted from something I happened to do into a required step, compared on **typed
structures rather than bytes**, because byte comparison cannot see this class at all.

**The shared serializer was not patched.** `architecture/exchange/canonical_yaml.py` is
byte-identical to SCL's copy *by agreement*, and that agreement is what makes any hash
meaningful. Editing it on one side would break the agreement and silently re-hash every
artifact already committed against it — both exchange artifacts, the agreement fixture itself,
and every digest reference. Recorded in `architecture/canonicalization_defect.yaml` with its
blast radius; the fix must land in both repositories in one coordinated reissue.

Interim mitigation is enforced, not promised: `tests/test_canonicalization_defect.py` locks the
exact class, proves the prescribed fix closes it, and checks every hash-bearing artifact both
for cross-parser *typed* agreement and for absence of any diverging scalar shape.

## The concurrent session

This phase also collided with a concurrent session on the same branch (`a0622f4`). Resolved by
merge, on the merits: **their `daq_capabilities.yaml` was taken over mine** because they
vendored SCL's actual `canonical_yaml.py` byte-identically and verified fixture agreement,
which is what §2.1 requires and which a self-authored serializer cannot establish. **My
serializer and its test were deleted** — two serializers would be the second system this
project forbids.

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
| `tests/test_canonicalization_defect.py` | **35 passed** (new) |
| `tests/test_daq_workload_proposal.py` | **22 passed** (new) |
| `tests/test_recursive_lineage_depth.py` | **17 passed** (new) |
| DAF full suite | **826 passed** |
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
