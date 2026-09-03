# Phase 43 — The Instrument Was the Stale Thing

## What this phase was

Four working cycles across one night, on an instruction to develop the
information systems and make them coherent as apparatuses of one
ecosystem. What it produced is not a diagram. It is one class of defect,
found four times, each time in a check written to prevent it — and one
real inconsistency inside a published laboratory report.

The class: **reasoning from a stale or partial local artifact to a claim
about the world, when a remote query was available and cheap.**

---

## The four turns of the same screw

**One — the core's ancestry.** `architecture/ecosystem_census.yaml` said
the relationship between the vendored core pin and a sibling checkout was
undeterminable, "because the pinned commit is not in its object
database." A concurrent session had already measured that this reason is
an artefact of a *partial clone*, where a presence query **fetches** the
object and answers yes — the question creates its own answer. They
corrected the census before I read it.

**Two — the pair.** Three tests reported `proof_integrity.yaml has
DIVERGED across the pair`, the most serious alarm this system raises, on
the one artifact neither party may edit alone. It had not diverged. Both
parties held `c9be0996…` at their own heads. The sibling checkout on this
machine was four commits behind, missing exactly the mirror commit.

The check asks *has this jointly-held artifact been edited by one party
alone*. What it evaluated is *do these two directories hold the same
bytes right now*. Those coincide only while the sibling happens to be
current, and **a checkout is versioned with nothing.**

The failure direction is what makes it serious: a false positive that
fires precisely when a reissue is in flight — the one moment the two
sides are legitimately unequal. A guard that cries wolf on every
legitimate reissue is one people learn to wave through.

**Three — the chain.** CI went red. Two checks reported the joint
workload decision binds a requirements set that no longer exists and
names the wrong predecessor. Both false; the record binds exactly what
the compute layer's artifact currently is. Both read git history from
that same stale sibling.

The sharpest part: both had been rewritten *the same day* to read the
**owner's** history rather than this repository's mirror. That rewrite
was right — a mirror's history skips versions the owner committed. And it
**moved the staleness rather than removing it.** Reading the owner is
more correct in principle and still reads a *directory*.

**Four — the guard itself.** The guard written for turn three skipped
when the owner was *behind* and let the *absent* case through. Absent is
the CI case, where the fallback reads the mirror. False red on the
runner, green on any machine that happened to have a sibling directory.
The guard had asked whether the instrument was stale and not whether it
was the instrument at all.

The repair is two fallbacks, because the two checks rest on different
things. The predecessor check needs the owner's **chain**, and a mirror
cannot supply one, so it declines. The stability check needs the
artifact's **current value**, and a mirror *is* byte-identical in the
present — which is exactly what `verify_pair_landed.py` guarantees — so
it falls back to the mirror and keeps its coverage.

**The general form:** before trusting a comparison, ask what the *other
side* is. A path is a location, not an identity; whatever sits there is a
snapshot of somebody's last pull. Where a claim is about a counterparty,
name the counterparty — a URL, a ref, a digest — and accept that the
check now needs the network and must say so when it cannot run.

---

## The finding inside the document

Section 12's Table 8 prints a maximum difference of **0.83**. The
report's own formula, stated verbatim on page 33 — *(highest − lowest) ÷
the mean of the highest and lowest* — applied to the report's own two
flow-rate means gives **0.824657**, which prints as **0.82**.

Five denominators were tested before saying so:

| denominator | value | prints as |
|---|---|---|
| mean of the extremes — **the formula's own** | 0.824657 | 0.82 |
| the highest mean | 0.821271 | 0.82 |
| **the lowest mean** | **0.828072** | **0.83** |
| the reported result 9.70 | 0.824742 | 0.82 |
| from the rounded printed means | 0.824742 | 0.82 |

Only the lowest reproduces the printed figure, and it is not the
denominator the formula names. **Which the laboratory did is not
determined and is not guessed** — an arithmetic slip and an unwritten
house convention are equally consistent with what is visible.

It is one unit in the second decimal of a ratio, on a study whose
acceptance criterion is 30 % and which passes it by a factor of
thirty-six. The finding is not that the study is wrong. It is that a
document's internal consistency is checkable, and this is the first place
this one fails.

### It was missed twice, and both misses are this repository's

A hand-check printed three decimals, read `0.825`, and wrote that the
printed 0.83 was half-up rounding of a value on a boundary. It is not
0.825 and it is not on a boundary.

Worse: the enforcement written to catch exactly this asserted
`abs(computed − printed) < 0.01`. The discrepancy is **0.0053**. The
tolerance was wide enough to absorb the difference the check existed to
detect, and it passed, green, through the whole anchor arc.

A tolerance is a claim about how much disagreement is expected. That one
was chosen to accommodate the CVs — which differ by rounding of the
inputs — and then applied to a quantity whose disagreement is of a
different kind. One tolerance over quantities with different error
sources cannot separate them.

---

## What was built

**`science/set_attestation.py`** — a statistic a *source* states about a
**set** of runs, checked against one the substrate computes. Predictions
pinned before any code existed; all five held.

The shape is what found the discrepancy. The tolerance has **no default**
— deciding how close counts as agreement is a judgement about the
source's rounding and belongs to whoever read the document. There are
**three** verdicts, not two: `AGREED`, `DISAGREED`, `UNCHECKED`, because
a shape with only the first two reports *nothing could be computed* as
*fine*.

P4 held and is the useful remainder: section 10 states a correlation
coefficient was obtained and **archived rather than released**. That is a
set-level *absence*, and `SetAttestation` requires a finite value.
`withheld` remains the one absence reason never exercised — now for a
stated reason rather than for want of a document. The one real instance
ever found is withheld at the wrong level.

P5 was a **stop condition**, not a boast: if the build had needed a fifth
uncertainty kind or a sixth absence reason, the design was wrong. It did
not trigger; both per-cell vocabularies are untouched, asserted by a test.

**`tests/test_mapping_join_defect.py`** — `" ".join(a_mapping)` yields
its **keys**. Caught by hand eight times in this programme and never by a
check.

The broad form was measured and **rejected**: `.join(<bare name>)` occurs
62 times and is almost always a list, so a guard on it would raise 62
alarms for two defects and be switched off within a day. The narrow
property — the joined name is also subscripted by a string literal in the
same function — found exactly two sites, both real, no false positives.
One was mine. The other was worse: a key-join as the first half of an
`or`, unconditionally true, so the real assertion behind it was dead —
and removing it showed that assertion was *also* false.

**`architecture/ecosystem_census.yaml`** and the README — seven
apparatuses, six repositories. Notation Physical Commerce lives inside
this repository and has none of its own, which is why the census
enumerates apparatuses rather than directories. Two repositories with
zero commits present are `UNDETERMINED` rather than named from their
directory names, and a test plants a plausible role on each and watches
it fail.

---

## Guards that fired on this session's own work

Every one was repaired rather than exempted.

- The **doctrine trigger** fired on the SHRINK direction, then on GROW
  when a new record was bound by nothing. Emptying the baseline was not
  free: a `for` loop and a subset assertion both pass trivially over an
  empty set, so both were replaced rather than left to read green over
  nothing. The parked source-list decision was **not** taken.
- The **cohort-identity probe** recorded that zero refusal codes in
  `science/` name a cohort concept — its central finding. Two of mine now
  do, and the premise genuinely lapsed rather than merely matching a
  regex. The basis was re-taken with the old figure kept visible, and the
  probe stays `UNTESTED`, because two refusal codes are not a cohort
  identity.
- The **unverified-window guard** fired three times on modules that read
  the sibling checkout.
- The **register** refused to regenerate mid-merge, because it reads
  `git ls-tree HEAD` and during an unresolved merge HEAD is the pre-merge
  commit. The generator was right and the shortcut it refused was the one
  about to be taken.
- A **`Bent: zero`** written in a phase report moved the register's
  digest until it was re-derived — the register scans the documents for
  that claim form, exactly so a new one cannot go unaccounted.

---

## Corrections to this session's own claims

- The census carried a declaring-count that went stale **three times in
  one session** — 58, then 55/66, then 61/72. The guard caught all three,
  which is the guard working and also the signal the row was the wrong
  shape. It now carries the *relations*, which do not move.
- The first of those numbers came from `grep -rl`, which misses seven
  files because a text search cannot see the canonically-emitted
  `"extends": "core@1.0.0"` form. That is the invariant register's own
  documented finding, committed by hand in the record about it.
- Fixing that exposed a scope bug in the census's own test: it parsed
  `architecture/` and compared to a register that walks the whole
  repository. The relation held by luck.
- A record first said two other-lineage tests were "not edited here" and
  the repair was theirs to take. That was withdrawn: they were red, on
  this machine, because of a merge this session performed, for a reason
  it had already diagnosed. **Leaving a known false alarm standing so as
  not to touch another lineage is not restraint.**
- An assertion was written ending `or True` — the exact vacuous idiom
  filed twice in `architecture/vacuous_evidence.yaml` — in a test whose
  subject is not writing them.

---

## What is still open

Named, not started: per-measurement `data_provenance`, which would let a
guideline reference constant be carried instead of declined; the
granularity of `EVERY_RUN_DIFFERS_IN`, which names the container
`conditions` rather than the offending key; and the **set-level absence**
that P4 left as the remainder.

Three checks now decline when the sibling is stale, where they used to
report a false verdict. That is correct **and it is a reduction in
coverage, not an increase.** What would restore it is fetching the
counterparty's full history rather than a depth-1 fetch of one commit —
a real cost, not taken here.

`commerce/` is correctly parked at its own §4: Phase 0 needs one real
transaction, and its own rule forbids building integrations to avoid
needing it.

---

## Verification

| check | result |
|---|---|
| `python3 -m pytest tests/ -q` | **2418 passed, 9 skipped**, exit code read directly |
| `mypy` (CI scope) | Success, **124 source files** |
| doctrine regenerates identically | clean |
| submodule `vendor/scout-retrieval-agent` | clean, pinned at `5e146d5` |
| detector proofs across the night | 22 planted, 22 fired, all restored |

**Bent: zero.** No core invariant changed. The vendored submodule is
byte-identical.
