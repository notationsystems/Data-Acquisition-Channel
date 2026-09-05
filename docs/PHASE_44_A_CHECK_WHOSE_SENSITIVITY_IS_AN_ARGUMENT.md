# Phase 44 — A check whose sensitivity is an argument

Two defect classes met in one hour, arriving from opposite directions and
describing the same failure. Both leave the mechanism intact and destroy
the discrimination from outside it. One moves the **bound** under a fixed
sample. The other moves the **sample** under a fixed bound.

## Where the first one came from

Not from this repository. Extracting `science/set_attestation.py` as a
standalone package meant writing down, for a stranger, what `tolerance`
means and why it has no default. The sentence that came out — *a default
would be this layer deciding how close counts as agreement* — invited the
next question, which nobody here had asked: what does a caller-supplied
tolerance of **infinity** decide?

Measured: every attestation `AGREED`, including one off by a factor of
1.7 million.

The general form: **a check takes its sensitivity as a parameter, and for
some values of that parameter it returns the same answer for every
input.** Nothing errors. The mechanism runs correctly. The check has
stopped being a check, and it goes on reporting well-formed verdicts.

This is not the fifth class already filed in
`architecture/vacuous_evidence.yaml`. That one names a checker that never
*reached* the artifact. Here the checker reaches it, reads it, and
computes correctly — the invariance comes from the threshold, and no
amount of confirming the check ran would find it.

## The sweep

AST over the ten product packages, fourteen threshold name fragments,
derived from the tree rather than recalled. **Four** suspect parameters
in the whole product. All four are instances.

| site | degenerate value | what it does |
|---|---|---|
| `check_attestation(tolerance)` | ∞ | AGREED for an attestation off by 1.7M; NaN gives DISAGREED for one that reconciles exactly |
| `covariance_rank(rank_tolerance)` | ≥ 1.0 | rank 0 for **every** matrix; below 0.0, full rank for every matrix |
| `validation_lane_is_discriminating(minimum_…)` | 0.0 | accepts the 0.19% trunk haul it exists to exclude |
| `Calibration.volume_for_mass(tolerance)` | 1e6 | returns **9.0** for a mass whose true volume is 11.0, silently |

## Two dispositions, not one

The repair depends on whether the threshold carries a judgement.

**Three are guarded.** `tolerance` in `check_attestation` encodes a
reader's judgement about how a source rounded its inputs — it stays, with
a stated domain. `rank_tolerance` sits on a **join**: it normally arrives
from the compute layer's published constant, so the guard makes a
degenerate value published *there* loud instead of silent. The lane
minimum is the sharpest of the four, because it does not compute a wrong
answer — it **selects the validation suite**, and a threshold of zero
fills that suite with lanes that agree by construction.

**One is removed.** `volume_for_mass`'s tolerance encoded nothing and no
caller ever supplied it. A parameter that cannot be supplied wrongly
beats one that is checked. Removing it also made the inversion *exact* —
the old default returned `10.999999999999886` where the unbroken
bisection returns `11.0` — so the choice was not a wash.

Their domains are `[0, ∞)`, `[0, 1)`, `(0, ∞)` and none. No two agree, so
a shared validator would take the domain as an argument and be the
defect's own shape. Each site states its own.

## What the pair check found while this was being measured

`tests/test_pair_at_remote.py` was already red before this session's
first edit: `proof_integrity.yaml` DIVERGED at the counterparty's head.

It had not. Twelve lines added on their side, **zero** removed on ours —
the staleness case, resolved by asking which side could have produced its
own copy. What they had added was a class instance,
`a_fixed_oracle_read_against_a_sample_that_moves`, and it named
`tests/test_replicate_pairing.py`.

**The defect was live in this tree, unrepaired**, at line 164:
`seed=hash(str(rho)) % 100000`. Python randomises the hash of a `str` per
interpreter — four consecutive runs here gave 67649, 38988, 88201, 36619
— while the bound it was compared against, `abs=0.05`, did not move. The
green had been saying *the estimator recovered rho on one sample nobody
chose and nobody recorded*.

The record was verified before it was acted on. Pinning the seed at
20260903 gives a worst deviation of **0.016152** against a tolerance of
0.05, a margin of 3.10×. The counterparty's line reads *worst 0.01615 …
a margin of 3.1x*. Reproduced to five significant figures without having
read that line first — which is what establishes the record is about this
code rather than a copy of it.

The seed was not shopped: 20260903 is the value their record prescribes
and the first one tried. The tolerance was not touched.

The binding sweep — `tests/test_no_test_draws_from_a_process_varying_seed.py`
— allows a `hash()` that is **asked about** (read by an assert, or standing
alone as a bare expression, which is what a hashability probe looks like)
and forbids one **carried forward** into data. Measured on this tree: 62
legitimate probes allowed, one site flagged, **no exception list**. A
coarser rule would flag the probes; the module says outright that if it
ever needs an exception, the rule is wrong.

## What this phase did not do

`architecture/proof_integrity.yaml` is still twelve lines behind the
counterparty. Carrying their bytes would be a pure fast-forward and the
content is verified true of this tree — and it is still a write to the
artifact whose entire rule is that neither side writes it alone.

**So two tests remain red, for a true reason, which is what they exist
for.** This phase's suite is not green and nothing here should be read as
saying it is. Whether a verifiable fast-forward is a reissue DAQ may
perform alone is the joint-reissue rule's own question, and it belongs to
the owner.

## Detector proofs

Five defects planted, five detected, reported per guard rather than in
aggregate: the attestation guard removed; the `rank_tolerance` guard
removed; the lane minimum guard removed; the inversion's tolerance
parameter restored; a new unguarded threshold added to the product. Plus
the seed defect replanted, which fires the sweep at the exact line.

Pre-registration `37ce06e67da34a477e37614d8b88a5c1619d342e0c5b84b2da521e8ee231075c`,
written before the repair and unedited after. All six predictions held.
