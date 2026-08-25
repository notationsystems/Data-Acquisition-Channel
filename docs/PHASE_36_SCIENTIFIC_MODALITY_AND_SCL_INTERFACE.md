# Phase 36 — Scientific Modality Reconnaissance and the DAQ/SCL Joint Decision

*(Continues from `ca3d0aa`. Coordinated DAQ/SCL phase, run as the brief's three stages:
parallel reconnaissance → requirement/capability exchange → one joint decision.)*

**Joint decision: build `fourier_transform_1d`; `daq_extension: none`.**

Recorded in `architecture/decisions/2026-08-25-workload-selection.yaml`, bound by SHA-256 to
the exact two exchange artifacts that produced it.

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

## SCL substrate reconnaissance

SCL exists as a separate repository (`notationsystems/Scientific-Compute-Layer-SCL-`, commit
`edfc2dc`), measured read-only. Its one scientific kernel is Lennard-Jones pairwise.

| Measured fact | Value |
|---|---|
| Operations | exactly one: `lj_pairwise_energy_forces` |
| Dispatch | a single string equality at `native/src/main.cpp:190` — no registry, no table |
| Wire format | JSON envelope, hex-encoded little-endian float64 |
| Shape field | **absent** |
| Dtype field | **absent** |
| Configuration | hard-fixed at exactly 24 bytes, LJ-validated (ε/σ/cutoff) |
| Input constraint | length ≡ 0 mod 24, decoded unconditionally as N×Vec3 |
| Backend abstraction | LJ-typed: `compute_lj_pairwise(...) → LJResult` |
| Transcendental functions in native code | **none** — the only cmath symbol is `std::isfinite` |
| BLAS / LAPACK / FFTW / cuFFT / cuBLAS / cuSOLVER | none linked, none present on the host |
| numpy / scipy | both absent |
| CUDA | never compiled, never run (the `.cu` file says so itself); no nvcc, no GPU |
| Tests | 32 passed, 31 skipped (22 need an STE checkout, 9 need nvcc); native 50/50 |
| Process-boundary cost | ~2.34 ms per round trip against ~290 ns of compute — **≈7700× overhead** |
| Union primitive coverage | **1 of 28 required primitives = 3.6%** |

The sharpest measured hazard: a payload whose byte count happens to be a multiple of 24 is
accepted and **silently reinterpreted as particles**. A 3×3 float64 matrix (72 B) returns
`completed, n_particles=3`; a 3-element complex128 array (48 B) returns `completed,
n_particles=2`. No error, no dtype check.

## DAQ capability exchange

`architecture/exchange/daq_capabilities.yaml` — `sha256:cd032f23…57129`

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

`architecture/exchange/scl_requirements.yaml` — `sha256:816ae02f…d5d45`

| Workload | DAQ availability (measured) |
|---|---|
| `fourier_transform_1d` | **satisfied** |
| `convolution_correlation_1d` | **satisfied** |
| `least_squares` | NOT satisfied — multivariate absent |
| `principal_component_analysis` | NOT satisfied — multivariate absent |
| `kalman_filter` | partially — scalar R exists, covariance absent |
| `pid_controller` | satisfied for pure computation only |
| `viterbi` | NOT satisfied — no categorical source |

Authored from measured SCL reconnaissance and **mirrored into the DAQ repository** because
this session holds read-only access to SCL. Its canonical home is SCL; see *Unresolved*.

## Workload / primitive matrix

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

## Joint decision

**`fourier_transform_1d`, `daq_extension: none`.**

The rule is: select the highest-leverage workload whose observation requirements are *already*
satisfied by DAQ. Applying it mechanically:

- `least_squares`, `principal_component_analysis`, `viterbi` — **forbidden**, DAQ marks their
  entry modality absent.
- `kalman_filter` — only partially satisfied, and worst-case to sequence first.
- `pid_controller` — satisfied for pure computation, but its distinctive value is actuation,
  and no actuation-authority boundary exists anywhere. Building it would create an implicit
  control plane.
- `fourier_transform_1d` and `convolution_correlation_1d` — identical observation
  requirements, both satisfied.

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

## Canonicalization

`epistemics/exchange.py` implements the pinned encoding as executable code. All three
artifacts are deterministic, fixed points of the encoder, and parse identically under this
repository's dependency-free reader and PyYAML.

That cross-parser check earned its keep immediately: an unquoted `2026-08-25` resolves to
`datetime.date` under PyYAML and to `str` under the repo reader. Unquoted, the artifact's hash
would have been **parser-dependent** — exactly what the pinned encoding exists to prevent.
Found by measurement, fixed in the encoder, locked by a test.

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
| `tests/test_recursive_lineage_depth.py` | **17 passed** (new) |
| `tests/test_exchange_canonicalization.py` | **30 passed** (new) |
| DAF full suite | **759 passed** (712 prior + 47 new) |
| Vendored SCOUT suite | 1273 passed, unchanged |
| Submodule | clean |
| SCL clone | untouched, `git status --porcelain` empty |
| `mypy .` | 4 pre-existing errors, 0 new |
| `ruff` (new files) | all checks passed |
| Doctrine | regenerated, 654/1400 words, zero diff |
| `git diff --stat -- daf/ science/ boundary/ bridge/ assertion/ vendor/` | **empty** |

No production acquisition code changed. The only code added is `epistemics/exchange.py`, a
serializer for architecture documents that touches no evidence path.

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

- **SCL implementation is BLOCKED.** This session holds read-only access to
  `notationsystems/Scientific-Compute-Layer-SCL-`; a push attachment was requested and
  denied. `fourier_transform_1d` cannot be committed there from here, and
  `architecture/exchange/scl_requirements.yaml` could only be mirrored into DAQ rather than
  committed to its canonical home.
- **17 invariants name an enforcement file that never mentions them** — locked, not fixed.
- **The write-side condition asymmetry** (Phase 35's `graph_dataset` gap) — unchanged.
- **NOAA timezone discard** — measured this phase, not fixed: it needs a named consuming
  workload, and `fourier_transform_1d` does not require it (a uniform offset does not change
  a spectrum).
- Carried unchanged: `quarantine_repair`, `retraction_semantics`, `multi_writer.write_conflict`,
  `builder_check_lineage`, `attested_snapshot_identity`, `capabilities_5_to_9`, PID actuation
  authority.

## Next executable frontier

**Implement `fourier_transform_1d` in SCL, behind the universal gate** — a variable-length
1-D float64 array on the wire with an explicit shape, a generic configuration block, and a
callable reduction — validated against analytic properties only (impulse, DC, pure tone,
Parseval, reconstruction), with `input_kind`, `spectrum_convention`, `direction`,
`normalization`, `precision` and `sample_spacing` in the parameter identity model, and with a
bin-index axis because CO-OPS states no Δt. **This requires push access to the SCL
repository**, which this session does not have.
