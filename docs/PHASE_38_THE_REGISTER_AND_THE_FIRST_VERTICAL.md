# Phase 38 — The Register, and the First Vertical

## What this phase was

Two things that turned out to be one. It began by asking what `extends: core@1.0.0`
actually refers to, and ended by measuring what a polymer measurement costs a
consumer who takes the substrate at its word. The join between them is that both
are claims made *relative to something*, and neither had anything checking what
that something was.

Thirty-three artifacts in this repository declare `extends: core@1.0.0`. Every
`bent: zero` and every `core_invariants_modified: 0` is a claim about that core.
Before this phase, all of them joined on the version string — the one field
upstream controls and can move — while `submodule_commit`, which cannot move
without the vendored code changing, was recorded and read by nothing.

---

## The referent, and the failure that is silent

A version bump is loud: a check fails and someone looks. The dangerous case is a
submodule bumped to a commit whose `pyproject.toml` still says `1.0.0`, which is
what a patch commit looks like. The recorded commit is then wrong, every check
passes, and all thirty-three `extends` agree with each other about a core that
moved underneath them.

Resolved in the vocabulary the compute layer already owns: the **submodule commit
is participating** — it determines what the core *is* — and the **version string
is annotating**, a human label upstream assigns. A join on an annotating field is
the defect. The label is kept and *bound* rather than removed, which is the
standard disposition for an annotating field: thirty-three artifacts read it, and
a commit hash is not a readable claim.

The one check that existed was also weak — a substring match over the whole
pyproject text, unable to tell the `[project]` version from a dependency pin, a
tool table or a comment. Now parsed.

---

## The probe had a gate and nothing read it

`architecture/_probes/generality.yaml` carries one line of policy: *re-run
whenever a core invariant changes*. It was declared in Phase 36 and read by
nothing. It failed exactly once, and silently.

`generation_depth_bounded` moved from `represented_unenforced` to `enforced` at
`6f890e5`, with an implementation and a 36-test suite. The probe's
`recursive_computation` FAIL was measured against the state *before* that commit
and was never re-run. Two later commits edited that very file to record two other
probe runs and walked past it. And a test **pinned** it:

```python
assert PROBE["outcome"]["failed"] == ["recursive_computation"]
```

So repairing the invariant turned nothing red. The suite was green *because* the
record was stale; the pin and the staleness agreed with each other.

That is not a check failing to fire. It is two mechanisms mutually confirming a
false state, with the suite correctly green from both — filed as the 21st
instance in the class record, whose general form is that **a test over a recorded
measurement pins the record, not the property**, and from inside it a stale record
and a true one are the same bytes.

The gate is now enforced by a digest over `(id, rule, status)` for every
invariant, and it was **shown capable of failing against real history** rather
than a synthetic mutation: recomputed over `git show 6f890e5^:architecture/invariants.yaml`,
the projection differs. Had the gate existed, it would have gone red at the repair
commit and forced the re-run before either probe run was written on top of a stale
result.

### The re-run, clause by clause

The FAIL rested on four measured clauses. Two are repaired and two still hold:

| clause | verdict |
|---|---|
| no depth/generation/lineage symbol anywhere | REPAIRED, 0 → 3 by AST |
| `DerivedValue` has no depth field | STILL TRUE, vendored |
| the invariant declares no bound value | REPAIRED, `MAX_LINEAGE_DEPTH = 3` |
| `ancestry_of` discards the level | STILL TRUE, vendored |

The two that stand are facts about the *vendored* types, which the repair routed
around rather than through. Recording them as repaired would be false.
`core_invariants_modified` stays 0: the invariant was **implemented**, not
weakened.

---

## The cross-repository check was itself specified by enumeration

`tests/test_cross_repository_claims.py` exists *because* a claim about the sibling
had no witness at home. Its header says DERIVED, NOT LISTED — and it is, for the
invariant ids and the status vocabulary. The **documents** it swept were two.

Widened to every YAML document outside `vendor/`, it flagged four rows where the
enumerated version reported green: three real stale claims, all naming
`generation_depth_bounded` two corrections behind, one of them inside the
hash-bound joint decision record. And one false positive, where a status word was
ordinary English.

The false positive is not patched away. The disposition — **reword the prose,
never teach the check an exception** — is recorded in the check's own docstring,
because an exception is a permanent hole in a check whose entire value is that it
has none, and it gets added by whoever is annoyed rather than whoever measured.

The same shape recurred twice more this phase, in `verify_pair_landed.py`'s
`SHARED` tuple (which did not contain `verify_pair_landed.py`) and in
`core.yaml`'s hardcoded artifact count. Both are now derived.

---

## The register: three parties, and one that enumerates nothing

`architecture/exchange/invariant_register.yaml`, derived rather than written.

| party | source | shape |
|---|---|---|
| daf | `architecture/invariants.yaml` | 43 entries, id + rule + **status** |
| scl | `native/include/scl/operation.hpp` | 11 clauses, suite enumerates the registry **from the binary** |
| ste | nowhere | referenced by **number**, defined in a brief the tree does not hold |

The asymmetry is the first finding, not an inconvenience to normalise away. SCL's
half is exchanged as `scl_contract_clauses.yaml`, parsed from its own header,
conformance suite and mutation table, and carries **no status field** —
borrowing this repository's vocabulary would make the register join on a word
meaning two different things on the two sides.

That derivation immediately found a gap on the compute side: clause 7 had tests
and no mutation. `CLAUSES_WITHOUT_A_DEDICATED_TEST` reported missing *tests*, and
nothing reported missing *mutations*, so a clause whose tests had never been shown
capable of failing looked identical to a covered one. Written and caught, 10/10.

### The core party's invariants are not enumerated anywhere

`ARCHITECTURE_SPEC.md` says *"Invariants I1–I8 (see brief)"*. `PHASE_13` says
*"all 10 invariants re-verified in Phase 12"*. Reconstructed from the vendored
documents at the pinned commit:

- **I3–I8** cited individually somewhere; reconstructable to varying strength
- **I1, I2** cited *only* inside the range `I1–I8`; not recoverable at all
- **I9, I10** referenced in no document in the tree

The last row is the sharp one: the competing count does not merely fail to
enumerate, it names two invariants nothing here ever mentions. Only **I5**
(*identity is the field name, never the value*) has enough distinct citations to
stop being inference; the other five each state what would refute them, and I7 is
flagged as the weakest offered at all.

`architecture/exchange/ste_invariants.yaml` carries `status:
RECONSTRUCTION_NOT_DECLARATION` and keeps it. A set written about a party by
another party is not that party's set — the same reason a decision authored with
both pens was demoted to a proposal in this pair's own history. It **cannot** be
written into STE: `modifiable: false`, and `bent: zero` is entailed by the core's
bytes being unmodified at the pin, so a declaration written into the vendored tree
would move the pin and destroy the entailment carrying the claim. It has to come
from upstream — and the bump that picks it up re-opens `bent: zero` against a set
that is enumerable for the first time.

---

## Bent: zero

**Bent: zero.** No core invariant required modification in this phase.

This is the first such claim written since the register established what it
quantifies over, so it states its basis rather than assuming one.

**The property set is the union of both axes of `architecture/_probes/generality.yaml`
— four observation properties plus `recursive_computation` — five in total.** That
matters because the set changed size once and nothing recorded it: `ca3d0aa` held
the probe at 52 lines with four observation properties and no computation axis;
`c80a2f0` held it at 73 with the fifth added. Every `Bent: zero` written before
`c80a2f0` quantifies over four properties and every one after over five. Ten of the
eleven claims in this repository's phase reports are the former; this one and Phase
36's are the latter. Verified against git rather than asserted.

**And the claim is supported by a different route than its wording implies.** An
unenumerated set has no members to check, so *"zero core invariants were modified"*
is unfalsifiable as worded. It is entailed by something stronger that is
checkable: the core's bytes are unmodified at the participating referent —
gitlink `3e5bea9` matches the recorded commit, and the working tree matches the
pin. Zero files changed entails zero invariants changed, whatever they are and
however many.

What is **not** claimed: that STE's invariants hold. Nothing here inspects them,
because nothing here can. The claim is that this pair did not modify them.

The standing consequence: **a submodule bump is not a routine update.** The moment
the pin moves, `bent: zero` stops being entailed by byte-identity and must be
re-established against a set still nobody has enumerated.

---

## The first vertical, and the first scientific finding

`architecture/polymer_vertical.yaml`, `status: measured_not_proposed` — which it
keeps. The cohort-identity probe left two gaps and named this vertical as where
they get decided. **This decides nothing.** What moved is that both consequences
were *argued* and are now numbers.

### Gap 1 — the recorded uncertainty is not the spread

For any chain-length distribution, `Var(M) = Mw·Mn − Mn²`, so
**`SD = Mn·√(PDI−1)`** — distribution-free, needing only the two moments the
instrument already prints. Verified two ways sharing no code: log-normal moment
integrals, and the discrete Flory distribution summed term by term.

On the probe's own batch (Mn = 104000 and PDI = 1.05 verbatim from the probe;
Mw = 109200 *forced* by those two and appearing nowhere in the repository, which
the record says rather than implying it was planted):

| | |
|---|---|
| SD of the chain-length distribution | 23255.1 g/mol |
| ratio to u(Mn) = 1200, the probe's own planted value | 19.4× |
| ratio to u(Mn) = 2000 | 11.6× |

A consumer reading *"104000 ± 2000 g/mol"* as one sigma **of the material**
concludes ~68% of chains lie in [102000, 106000]. Actually in it: **6.90%** —
overstated 9.9×. The interval that really holds 68.27% is **11.3× wider**.

The two gaps touch: the ratio is `√(PDI−1)/u_rel`, so **the information needed to
compute the gap's size arrives beside the number that hides it.**

### Gap 2 — a column that is a function of two others

PDI = Mw/Mn arrives beside its own inputs. Fitting the three-column row with
`least_squares` — which `aligned_observation_table.yaml` already names as the
table's consuming workload — reports `Var(ln Mn)` at 0.705 and `Var(ln Mw)` at
0.795 of the correct value. True degrees of freedom are **0, not 1**: the third
row is the second minus the first by construction, χ² is identically zero for
*all* data, and a goodness-of-fit test reads perfect agreement between three
measurements that are not three.

**The direction flipped twice, and reporting it shrunk is the discipline.** The
first measurement said the confidence region is exactly 1/√2 of its correct area
— overconfident, always. That holds only at `Cov(ln Mn, ln Mw) = 0`, a *chosen*
input never measured. Generally `det(Cov₃)/det(Cov₂) = 1/(2(1−ρ²))`, crossing 1 at
ρ = 1/√2. So the direction flips inside the physically plausible range.

Then ρ was modelled, and flipped it again — toward the safe side.

### The degenerate design, caught mid-measurement

The first ρ run reported **+1.0000 for three of four mechanisms**. Correct, and
not evidence: each was **one scalar parameter**, so ln Mn and ln Mw are two smooth
functions of one number and their correlation is ±1 before any chemistry enters.
It agreed with the hypothesis, at four decimal places, four times.

> A wrong answer that contradicts you gets investigated; a forced answer that
> confirms you gets published.

The tell was that the one mechanism which disagreed — per-slice detector noise,
800 independent parameters — differed from the others in **parameter count rather
than in physics**. Rebuilt on that mechanism, which is also the one least
favourable to the conclusion: ρ = 0.9625 alone, and 0.964–1.000 across every
modelled mixture, against a crossover of 0.7071. So the system sits in the
**underconfident** regime and ρ = 0 is not merely unmeasured but structurally
unreachable — Mn and Mw are computed from the same detector slices through the
same calibration curve.

Filed as the 23rd class instance: **a design with fewer free parameters than the
relation it measures returns the relation it was built with.**

**What survives untouched, ρ-independent, is the fabricated agreement** — and the
compute layer endorses rather than catches it. Measured through SCL's real solver:
`effective_rank = 2` (full rank), `condition_number = 1.4378` (excellent). At 1.44
the conditioning metric does not merely fail to warn; it **actively reassures**.
Rank and conditioning are properties of the design matrix's *columns*; this
dependence is among the *rows*.

---

## What would happen if the data arrived

The pre-arrival question was whether *"no content gate runs at ingest"* is the
state the replicate data should arrive into. Measured: **the gates are not the
constraint.** Five replicates pass every gate that exists — five content gates
derived by signature, three with zero non-test call sites, the other two reached
only through `assess_pool`, which itself has none. No content gate runs
automatically anywhere, and the vendored ingest gate checks that content is
non-empty without ever reading a key of it.

What decides it is one layer on. `ComparisonGroup` carries `(context, values,
disagreement)` with `values` a bare tuple of floats — no observation id, no
Record, no run identity. **Nothing pairs the i-th Mn with the i-th Mw**, and a
correlation is exactly a statement about that pairing. Also measured: `uncertainty`
is part of the comparison context, so replicates whose per-run figure differs by
1 g/mol split into five singleton groups; and the statistic over a well-formed
group is a *range* (490.0) where the standard deviation is 189.6.

It is a **missing consumer, not a missing capability** — the pairing survives in
the evidence pool, joinable on Record.

### The shape this repeats, three levels now

Chains summarised by a moment, distribution dropped. Runs summarised by a spread,
sample dropped. Paired runs summarised as two tuples, pairing dropped. **Each
summary is correct and each discards exactly what the next question needs.**

---

## The consumer, built before its data

`science/replicate_pairing.py`. The Record is the row, the variable is the column,
conditions are the group — the vendored Phase 16/17 argument applied rather than
re-derived. It diverges from the vendored grouping openly: a per-run uncertainty
travels *with its cell* and is not a grouping key, because it is a property of the
run rather than a condition the run was performed under. Nothing is discarded,
which is the line between this and suppressing the figures to keep a group intact.

Validated against a **known** correlation, never against itself: replicates drawn
from a bivariate normal by Cholesky with ρ fixed before the module sees them,
recovered to within 0.05 at ρ ∈ {−0.6, 0.0, 0.5, 0.9, 0.99}. And the pairing is
shown to be what carries it — shuffling one column while keeping both marginals
identical, which is exactly what the projection's bare tuples leave available,
takes ρ from 0.90 to under 0.15.

### The irreversible precondition, made loud

One precondition cannot be discharged before an extractor exists: **one Record per
run, run identifier out of content.** Which run produced which number cannot be
reconstructed afterwards.

Measured against the consumer's own first version, **violating it was silent**: a
run identifier in content gives every observation its own comparison context, so
five runs become five singleton sets, each reporting
`TOO_FEW_RUNS_FOR_A_COVARIANCE` — character for character what a pool holding one
genuine run reports. Irreversible, silent, and disguised as a benign condition.

The detection is Phase 16's own rule run forward: drop each context key; if the
groups merge and that key's values are in bijection with the runs, it is the key
splitting them.

| case | result |
|---|---|
| contract honoured | 1 set, no refusals |
| run id leaked into content | `EVERY_RUN_DIFFERS_IN: run_id` |
| temperature really changed each run | `EVERY_RUN_DIFFERS_IN: temperature_C` |
| temperature at two levels, 6 runs | no refusal, 2 groups of 3 |

The last row is the discriminating case; without it the check is indistinguishable
from *"complain whenever there is more than one set"*. The code is **named, not
diagnosed** — a leaked locator and a genuine per-run condition produce identical
structure, and in the second case these are not replicates at all.

---

## What the compute layer owes its callers

Two boundaries recorded on that side, both about what the caller must establish
before calling:

- **Row dependence is invisible to rank and conditioning**, structurally, because
  those are properties of the columns. Recorded rather than fixed: a rank check on
  the augmented `[X | y]` would catch this row *and* fire on any legitimate
  exactly-fitting dataset, converting a caller obligation into a false refusal.
- **A caller holding a covariance whitens, and that is exact.** The wire carries a
  diagonal, so a covariance cannot be handed over; for Σ = LLᵀ the caller solves
  `L X̃ = X`, `L ỹ = y` and the fit *is* the GLS estimate — agreeing with an
  independently computed GLS to 8.9e-16, where ignoring ρ = 0.8 moves the
  **coefficients** by 2.9e-03. No extension proposed; what was missing is that
  nothing said whitening is the route.

---

## The class record, and its own efficacy

Six instances filed this phase (19–24). The last is the one that had recurred most
and been named least: **a case that does not distinguish the property from its
negation** — four occurrences still recorded in the code that fixed them, every one
found by a mutation surviving and not one by reading the test. Its general form:
**a threshold is a number you chose; a contrast is a number the world produced.**

And the record's own promise is now measured, because 24 instances imply that
writing them down helps. Tested twice, at the shortest possible distance:
`coverage_specified_by_enumeration` recurred *inside* the check written to end a
coverage failure; the aggregate/substring class recurred **one commit** after being
filed, in a test written by the person who filed it, in a check whose whole subject
was that class.

Knowing a class exists did not prevent the next instance of it, twice, within
hours. **The instance never looks like the class while you are writing it** — it
looks like a reasonable line of code, which is what every instance in the file
looked like. That is not a case for deleting the record: both recurrences were
caught quickly, by someone with the vocabulary to name what they were seeing. The
value is recognition after the fact, not immunity before it — which is why the
*construction* step at the top of that file, plant the defect and watch it fail, is
stated as required and the list is not.

---

## What is not done

- **The polymer acquisition.** No instrument, no source, no material. Everything
  above is real code run against constructed observations.
- **ρ from an instrument.** What exists is ρ under a stated forward model, which
  establishes what ρ *cannot* be. Only data says what it is.
- **The extractor's Record granularity.** Still the one irreversible precondition,
  still undischargeable before the extractor exists — but getting it wrong is now
  loud at the first pairing instead of silent forever.
- **Both polymer gaps remain undecided as representation changes.** A workload
  names its extension, and none does yet.
