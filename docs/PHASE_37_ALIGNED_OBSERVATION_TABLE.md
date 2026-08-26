# Phase 37 — The Aligned Observation Table

The extension and its named consuming workload, built as one deliverable.

## What this phase was

The joint decision record elected `least_squares` **paired with** the DAQ
extension that unblocks it. The pairing is what made it a decision rather
than a wish, so the extension and its consumer land together rather than the
capability landing first and a consumer being found for it later.

On the DAQ side that extension is the **aligned observation table**: variable
identity, sample identity, missing-value semantics. On the compute layer's
side it is the linear-algebra family; that half is being built there.

Two things were held throughout, and both changed what got built:

1. **`absent` is now a fourth-instance pattern in this project** —
   `uncertainty_kind: absent`, the Fourier metrics DAQ refuses to fabricate,
   Δt-as-sentinel, and now missing values. Missing must not be encodable as
   an in-range value, **NaN included**.
2. **The §7/§8 asymmetry applies to this extension too**, even though it
   isn't the covariance one. A partially-typed table admitted at the gate
   and failing later is the same silent-late-failure shape. So the gate
   check covers the table's **element types**, not just its presence.

## The sentinel hole, measured before it was closed

Every line here was established by running it.

| | measured |
|---|---|
| `NaN`, `+inf`, `-inf` through the full property gate | **all ADMISSIBLE** |
| `content_hash` of a NaN-valued content | serializes with a bare `NaN` token — **not valid strict JSON** |
| `FilesystemEvidenceStore` | persists that literal, so the stored file isn't valid JSON either |
| `back.content["value"] == back.content["value"]` after a round trip | **False** |
| `json.loads` on a source file containing bare `NaN` | **accepts it**, by default |

The reason all three sentinels passed is worth stating plainly: NaN and the
infinities **are** instances of `float`, so every `isinstance(value, (int,
float))` check in `science/admissibility.py` admitted them. The type check
was never the wrong check — it was not sufficient, and finiteness was the
missing half.

The last row is why the pass-through routes mattered. A sentinel travelled
`local_dataset` end to end without one error being raised anywhere.

### It is three distinct failures, and only one is about absence

Sentinel-encoded absence was the stated concern, and the gate closes it. But
collapsing the finding into "the sentinel gap" loses two thirds of it:

1. **An identity minted over a document no conformant parser will read
   back.** Not an absence problem at all, and the largest of the three:
   content addressing across processes and languages is what the whole
   repository rests on.
2. **A persisted artifact outside the format it claims.**
3. **A value that breaks reflexivity** — so any dedup, cache, or comparison
   keyed on it misbehaves *silently* rather than erroring.

### The writer repair — fourth instance of one rule

`NaN`/`Infinity` in emitted JSON is the same class as clause 2 and the YAML
implicit-typing defect: **a writer emitting a form its own reader can't
accept.** With the YAML collection and escape classes measured in this same
phase, that is now four. The §6.2 repair applies unchanged — canonical at the
writer, refuse the ambiguous form. A reader taught to tolerate `NaN` only
relocates the problem to every other reader, including the ones in other
languages the format exists to reach.

Every DAF-owned `json.dumps` on a write path now sets `allow_nan=False`,
enforced tree-wide by a test rather than one call at a time, so a new writer
added without it fails here rather than at whichever consumer first reads the
file back.

**Bounded honestly.** `evidence.identity.content_hash` is vendored and uses
the permissive default, so DAQ cannot make *id minting* refuse. An
`Observation` built directly in memory with a NaN still gets an id over
invalid JSON. What DAQ closes is every route it owns — both gates, both
pass-through extractors, every DAF-owned writer. The residue is recorded, not
papered over.

### Forensics: has anything already been persisted?

The same check the covariance case earned, and for the same reason — an id
minted over invalid JSON cannot be recomputed by a conformant reader, so a
stored record carrying one would be *unrecoverable*, not merely wrong.

Searched every committed file in both repositories for a bare `NaN`/`Infinity`
token, and counted committed evidence-store artifacts. **Committed evidence
records: 0.** Every `NaN` hit is prose about this defect — gate sources, tests,
records written this phase. No emitted JSON, no artifact.

**Nothing was persisted, no id was minted over one, nothing to recover.** The
finding is forward-only. Consistent with `architecture/invariants.yaml`'s
migration section recording zero committed records — re-verified rather than
assumed.

## The bool class, and what the covariance work inherits

`isinstance(True, int)` is `True`, so a bool passes every numeric check that
doesn't exclude it *by name*. Measured: a bool was already refused as a
**quantity**, but was **admissible as an uncertainty** and **admissible as a
table cell**. Both now closed.

The harm is silent, which is why it earns a reason code rather than a
coercion: `sum([True, True, False])` is `2`, so a bool column quietly becomes
a count nobody asserted.

It is also a modelling boundary, not only a type check. If the source means
an indicator, encoding it as 0/1 is a *design matrix* decision — and the
requirements artifact records the choice of design matrix as a modelling
assertion rather than an observation. Letting `True` arrive where a number is
read makes that choice silently.

**A covariance is a matrix of cells and inherits this surface directly**: a
bool in a covariance passes a positive-semidefiniteness check while meaning
nothing. Recorded against the covariance extension rather than left to be
rediscovered inside it.

### The string cell: a decision, made rather than inherited

A concurrent session probed this gate against its *own stated rule* — "checks
the TYPE of every identity field, not its presence" — and asked whether that
holds for the **cell**. It didn't, and they split what they found into two
things, which was the right split:

| | table gate | scalar gate | |
|---|---|---|---|
| `1.5` | admissible | admissible | |
| `"1.5"` | **admissible** | `UNTYPED_QUANTITY` | ← decision |
| `True` | **admissible** | `UNTYPED_QUANTITY` | ← defect |

They left both to the gate's author. The bool half is the defect above. The
string half was a real question: this gate answers *alignability*, not
fittability, so a categorical column may well be alignable without being
numerically fittable.

Decided by measuring, not by taste:

```
True     float() -> 1.0   SILENT    sum -> 2   SILENT
"1.5"    float() -> 1.5   SILENT    sum RAISES LOUD
"B7"     float() RAISES   LOUD      sum RAISES LOUD
```

All three separate cleanly on the loud/silent axis this repository keeps
measuring, and the line falls between the second and third. **A categorical
string cell is admitted** — a categorical column is a real column, the
requirement asks for identity rather than numerics, and `float()` raises on it
loudly. Refusing it would make this gate answer fittability, which is not its
question. **A numeric-looking string cell is refused** — it coerces *silently*,
so a column holding `1.5` in one observation and `"1.5"` in another merges
under a coercing consumer and splits under a strict one, and neither says
anything. That is the implicit-typing defect one layer in: the same class the
always-quote rule closed, where a value's type depended on who read it.

The test is `float()` itself rather than a regex, because `float()` is what a
consumer actually calls. `"nan"` and `"inf"` fall out as a consequence — a
sentinel absence smuggled in as text is the same forbidden encoding wearing a
different type.

**The limit this gate cannot close**, named rather than assumed: it is
per-observation and cannot see a column. A variable whose cells are `float` in
one observation and a categorical string in another is admissible cell by cell
and is still a broken column. Refusing numeric-looking strings removes the case
where that inconsistency is silent; the rest raise at the consumer. Whoever
assembles the table owns the cross-observation check.

One departure worth recording: their bool test said "if this starts failing,
the defect has been fixed — delete this test rather than updating it." It is
**inverted** rather than deleted, because every other closed gap here kept its
lock as the regression surface and a deleted test cannot catch the defect
coming back.

## What was built

| file | what it is |
|---|---|
| `science/table.py` | the alignability gate — identity types, structural absence, positional-identity refusal |
| `science/admissibility.py` | `NON_FINITE_QUANTITY`, `NON_FINITE_UNCERTAINTY` |
| `daf/extractors/_passthrough.py` | the shared seam both verbatim pass-through extractors now go through |
| `architecture/aligned_observation_table.yaml` | the record, doctrine-registered |
| `tests/test_aligned_observation_table.py` | 62 tests |

**No table artifact.** A table is not a new evidence type here; it is what a
consumer *builds* from observations that carry enough identity to be joined,
one observation per `(sample, variable)` cell. A table artifact would add a
second identity system for something `Observation` already carries, and every
identity system in this repository has to be content-addressed, persisted and
restart-verified. The gate states what an observation must carry to be
alignable, and refuses the rest.

**Absence is structural.** The `value` key is absent and a `value_absence`
reason is stated, from a closed vocabulary: `not_measured`,
`below_detection`, `above_range`, `withheld`, `lost_in_acquisition`. Each
states something different about the world — `withheld` is the source's
choice, `lost_in_acquisition` is DAQ's own failure — and the vocabulary is
closed for the same reason `uncertainty_kind` is: an open free-text reason
lets `n/a`, `missing` and `""` accumulate as three names for one fact.

**Element types, not presence.** An `int` sample id in one observation and
the `str` form of the same number in another are *different join keys*, so
the table silently splits in two and the fit runs over half its rows with
residuals that look entirely healthy. `True` is refused explicitly, because
`isinstance(True, int)` is `True` in Python and a bool slips through any
numeric-or-string check that doesn't exclude it by name.

## The pass-through routes, tightened

These were the live risk: a gate is enforceable only on the paths that reach
it, and these two reached none. `local_dataset` passed the entire parsed JSON
object with no structural extraction; `graph_dataset` passed any
non-structural key verbatim.

Both now go through `daf/extractors/_passthrough.py`, which refuses a
non-finite number at any nesting depth (naming the record, the path, and the
honest alternative) and freezes every dict-valued entry into `FrozenMapping`.
Nothing else changed: no key is added, renamed, dropped or interpreted, which
is what keeps these generic transports rather than typed ones.

Fixed at the **shared seam**, not per-source. Fixing it inside either
extractor is exactly the per-source patching `condition_representation.yaml`
deliberately avoided — and is what produced the Phase 35 asymmetry in the
first place.

### A gap closed as a consequence

Phase 35 measured `write_side_asymmetry` and *stated the condition for
fixing it*: a single generic choke point, not a per-source patch. This phase
built that choke point for an independent reason, and the same seam closes
the gap.

The two characterization tests that locked it **open** both fired on the
change and were **inverted rather than deleted**. Measured after: a
`graph_dataset` record declaring conditions and a relation yields a
`FrozenMapping` in-process; analysis succeeds in-process **and** after a
reopen; the `Observation.id` is identical on both sides of the process
boundary.

The other three condition-lifecycle gaps are unchanged and
`closure.substrate` remains `not_closed`. One gap closing is not substrate
closure and the record does not claim it is.

## A third requirement that was nearly missed

`least_squares` has two **blocking** DAQ-owned requirements, which are the
headline of this extension. It has a third —
`conditions_that_distinguish_samples_must_be_recoverable_as_predictors_or_strata`
— recorded under `condition_requirements` rather than
`blocking_requirements`. Reading only the blocking rows would have shipped an
extension claiming to unblock a workload while leaving one of its stated
requirements unchecked. It was caught by reading the workload entry whole,
and the record now names it with its status.

DAQ's part of it is deliberately narrow. Whether a condition becomes a
predictor column or a stratum is a **modelling assertion** — the same
artifact says so — so the gate does not decide it, and a test asserts that no
name defined in `science/table.py` decides it either. What DAQ owes is that
conditions are carried under stable identifiers, and that no condition key
silently shadows one of the table's own identity columns.

## Four tests fired that were designed to

Each was a lock written by an earlier phase to catch exactly this change, and
each was inverted rather than weakened:

| test | what it caught |
|---|---|
| `test_two_extractors_pass_arbitrary_content_through_verbatim` | said in so many words that "the repair has to tighten this route". It did. |
| `test_graph_dataset_still_produces_an_unhashable_plain_dict` | the Phase 35 gap, closed |
| `test_the_write_side_gap_is_the_exact_mirror_of_the_phase_34_bug` | same, from the other side |
| `test_admissibility_is_pure_and_deterministic` | `math` was a new import in a module pinned to three |

The purity one deserves a note, because widening an allowlist is normally how
a purity check dies. `math` was added for `math.isfinite`, and the widening
is **paired with an explicit denylist** — the allowlist now says which pure
modules are permitted and the denylist says what purity actually means here
(no I/O, no clock, no network, no reaching into another layer). Purity is
also now measured rather than only inferred from an import list.

A fifth fired and was **not** inverted:
`test_every_invariant_naming_an_enforcement_test_file_has_one_that_runs`
caught that the two new invariants named an enforcement file that never
mentioned them. The fix was to make the file mention them, which is what the
test was asking for.

## The second coordinated reissue: two more canonicalization classes

What began as "a parser disagreement on a hand-written flow sequence" was
pulled on and turned into two real defects in the **shared** serializer's
neighbourhood — one level up from the scalar class the always-quote rule
closed, and one beside it.

### The collection class — emitter-side refusal

`canonical_dump({"k": [["a"], ["b"]]})` emitted the compact block form
`- - "a"`. PyYAML types that as `[["a"], ["b"]]`; the minimal reader types it
as the **strings** `['- "a"', '- "b"']`. Same bytes, same digest, two values.
Separately, an empty collection nested in a sequence didn't merely diverge —
the emitter **crashed**, raising `unsupported scalar type for canonical YAML:
list` from the scalar formatter.

One correction to the initial framing: the emitter *was* honouring block
style. `- - "a"` is block. So this wasn't "an emitter ignoring its own rule" —
it was a block-style shape the pair can't agree on, which the spec never
excluded.

Repaired the way the scalar rule was: **refuse at the writer.** There is no
emitted form both readers accept — written out long instead of collapsed, the
minimal reader *raises* on the bare `-` rather than mistyping it. Teaching one
reader the compact form would leave the bytes ambiguous for every other
reader. The refusal is narrow: sequence-directly-inside-sequence only.

### The escape class — reader-side, and that's not a contradiction

Wider, and always-quote *widened* it. `_quote` escapes five sequences
(`\\`, `\"`, `\n`, `\r`, `\t`) and always-quote sends **every** string
through it. The minimal reader returned the quoted body verbatim via
`text[1:-1]`, decoding none of them. Measured across 13 shapes: **all 13
diverged.**

This one is fixed reader-side, and the difference from the scalar rule is the
whole point. There the *bytes* were ambiguous, so a reader-side normalization
would have hidden it. Here the bytes have exactly one correct meaning under
YAML 1.2 and PyYAML already returns it — the minimal reader was simply
non-conformant. Fixing a wrong reader isn't relocating a problem, and it moves
no artifact and no digest.

### The enforcement hole that let it through

The escape defect reached a **hash-bearing artifact** — the reissued decision
record — and the suite stayed green. Cause: the two-parser agreement check
globbed `exchange/` and `proposals/`. **`decisions/` was not in the list.** The
one artifact type that binds a joint decision to its input hashes was never
checked. Fixed by adding the directory *and* asserting the coverage rule:
every directory carrying a `.sha256` sidecar must have its artifacts checked.

`verify_pair_landed.py` had the same shape of hole — its `SHARED` list named
five files, omitting the serializer's own source pin and the decision record.
A fixture change reissues that record, so the check would have said PAIR
LANDED while the two repos held different records. Not hypothetical: they had
already diverged once, when one clone was three commits stale.

### Blast radius, measured rather than estimated

Narrower than expected, and worth stating precisely rather than repeating
"every digest moves":

| moved | did not move |
|---|---|
| `canonical_yaml.py` + source pin | `daq_capabilities.yaml` + sidecar |
| `canonicalization_fixture.yaml` + sidecar | `scl_requirements.yaml` + sidecar |
| joint decision record + sidecar | |

Six files per repo, one commit each. The capabilities and requirements
artifacts regenerate **byte-identically** from their own repositories'
committed generators — because no committed artifact in either repo contained
a nested sequence, checked across every `architecture/**/*.yaml` on both
sides. The first reissue changed how every string is emitted and moved
everything; this one refuses a shape nothing used and fixes a reader.

The decision record moved only because it binds `canonicalization_fixture_hash`
and its own `binding_rule` says a bound artifact changing means **reissue, not
edit**. It was reissued: the decision is untouched, and the reissue block
states what forced it.

## The serializer pin: both suites, not both CI paths

The compute layer authored `tests/test_shared_serializer_pin.py`, which pins
the shared serializer's own SHA-256 so either side catches a local edit
without needing the other tree present. DAQ **adopted it byte-identically** —
pin, digest sidecar and cross-repo verifier copied verbatim, not
reimplemented. Reimplementing a check whose entire purpose is that both sides
agree would restate the problem it solves.

The claim has to be stated precisely, though, because it now **runs in both
suites but not in both CI paths — there is only one CI path**. Measured: this
repository has `.github/workflows/conformance.yml`, which runs the full suite
on every push; the compute layer's tree contains no CI configuration at all —
no `.github`, no workflow file, no Makefile, no tox or nox. On that side the
pin runs only when someone runs the suite.

Recorded rather than fixed. Authoring CI for the other repository would mean
shipping a workflow this session cannot verify passes: that suite's
`conftest.py` builds a native CMake target whose `nlohmann_json` dependency
is absent from this container, so every test there errors during setup.

Verified byte-identical across the pair after fetching the compute layer's
three newer commits: the serializer, the agreement fixture and its sidecar,
the requirements mirror and its sidecar, and the joint decision record and
its sidecar. Before the fetch, the decision records **differed** — the local
clone held the pre-correction version. Worth noting as a live hazard of the
mirror arrangement: byte-identity is a property of a moment, not a standing
guarantee.

## Deliberately not done

**The covariance extension** — structured measurement uncertainty plus
recursive generation depth, which unblocks Kalman. It is the next *decision*,
not a queue item, and it goes through the same joint record. Starting it here
would be the conflated-extension error again in the opposite direction.

**Wiring the table gate into an admission path.** It is a scientific-layer
gate, exactly like `quantity_is_typed` and `no_context_free_property` before
it. Ingest is `scout.pipeline.run_scout`, inside the vendored submodule that
is never modified. Its invariant is recorded as `partially_enforced`, which
is the honest status.

**A table builder.** DAQ states what an observation must carry to be joined.
Performing the join is the compute layer's work.

## Verification

- full DAF suite: **960 passed**
- vendored SCOUT suite: **1273 passed**, unchanged; submodule tree clean
- `mypy daf/ science/ boundary/ bridge/ epistemics/`: clean
- doctrine regenerated from `architecture/*.yaml`; re-running the generator
  produces **zero** further diff
- both new invariants trace to an enforcement test that names them
