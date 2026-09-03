# Phase 41 — The Ecosystem Has a Census

## What this phase was

A scan of everything under the Notation Systems name, and the first
artifact that says what each apparatus is, what it stands on, and which
of them carry the property the name claims.

Six repositories exist. Three exchange artifacts under a contract and had
machinery joining them; three participate in nothing. Until this phase
nothing said which was which, and the most developed of the six had no
README at all.

---

## What was found

**Six apparatuses, and they are not alike.**

| apparatus | role | carries the property |
|---|---|---|
| scout-retrieval-agent | the core — a canonical-state compiler pipeline | it *is* the determinism the rest rests on |
| **data-acquisition-fabric** | acquisition; provenance inside identity | yes, and it is where the property was worked out |
| scientific-compute-layer | the compute contract | partially, by a different route |
| morphohdl | growing circuits by structural recursion | no, and no sign it was meant to |
| network-scout-signal-miner | **undetermined** | zero commits present |
| information-systems-archive | **undetermined** | zero commits, no remote reachable |

Two roles are `UNDETERMINED` rather than inferred from their directory
names. An empty local clone is evidence about this machine and nothing
else, and naming a repository's purpose from its name would be the
fabrication the census exists to refuse. A test plants a plausible role
on each and watches it fail.

**`core@1.0.0` does not identify the core.**

The pin this repository vendors is `5e146d5`, committed 2026-08-27,
declaring `version = "1.0.0"`. A second working checkout of the same
repository sits beside it at `d43a569`, committed 2026-08-24, declaring
`version = "1.0.0"`. Two different core commits wearing one label, three
days apart.

Phase 39 already closed this *inside* this repository — the submodule
commit is the participating field, the version string is bound as
annotating, and no check here joins on the label. What Phase 39 could not
do is say anything about the other parties. There is no artifact anywhere
recording which core commit each member of the ecosystem stands on.

Whether the pin is ahead of, behind, or divergent from `d43a569` **cannot
be answered from this machine**: the sibling checkout is grafted, so
`git cat-file -t 5e146d5` in it fails and the commit is not in its object
database. Recorded as undeterminable rather than guessed.

**Why it is reported and not repaired.** A fix means either editing
another party's repository — which this apparatus must never do — or
building a second generator beside the invariant register, which
`tests/test_invariant_register.py` names in as many words as the parallel
architecture this pair has refused everywhere else. What would close it
is one field in an artifact each party already emits. That is a joint
decision and is not taken here.

**The shared pair was verified rather than assumed.** Both
jointly-held artifacts hash identically on both sides. Recorded because
an earlier claim in this repository that the pair was byte-identical was
made by running the verifier with no arguments and piping it to `tail` —
a false green, already filed as a class instance. The verification is
cheap; the assertion was the error.

---

## BOUND and OBSERVED, held to different standards

The census carries two kinds of claim and labels every row with which it
is:

- **BOUND** — derivable from inside this repository, and re-measured by
  the enforcing test against the tree. The core pin, the version string
  at that pin, the declared-core count, the layer rule, the shared-pair
  digests, the phase and record counts.
- **OBSERVED** — seen once, on one machine, in sibling checkouts this
  repository does not own. **Not checked**, and not pretended to be: a
  test that verified them would pass on a machine where the siblings are
  absent, which is precisely the vacuous shape
  `architecture/vacuous_evidence.yaml` files three times. What *is*
  checked is that they are declared unverifiable and dated.

A census that mixed them would be reproducible in half its claims and
machine-dependent in the other half, with nothing saying which half a
reader was looking at.

---

## The count I got wrong, in the record about getting counts wrong

The census's first draft said 58 records declare the core. That number
came from `grep -rl` — which finds 59 files today and misses seven,
because a text search cannot see the canonically-emitted
`"extends": "core@1.0.0"` form the exchange emitter writes.

That is the invariant register's own finding, stated in its own
generator's docstring, committed here by hand in the record about it.
Corrected by measurement: 55 at the top of `architecture/`, 66 across it
by parse.

Then the register reported 65 for the same tree. Both are right — the
register excludes *itself*, because a census whose value includes its own
row reports a number depending on whether it has been run before. Rather
than record two numbers that read as a contradiction, the enforcement now
asserts the *relation*: `register == parse − 1`, so the two cannot drift
apart in silence.

---

## Two guards fired, and both were right

Adding the census tripped two of this repository's deferred-premise
guards. Neither was worked around.

**The doctrine coverage trigger fired on the SHRINK direction.**
`tests/test_ecosystem_census.py` reads
`kalman_validation_preregistration.yaml` *and asserts a pinned digest of
its content* — a binding, not the inert mention the record's own
`naming_is_not_reading` note warns about. So the unbound set went from
one artifact to none, and the trigger's message says what to do: bind the
baseline down, because a stale allowance is how a gap becomes permanent.

Emptying it was not free. Two constructs consumed that set — a `for`
loop and a `KNOWN_UNBOUND <= shared` subset assertion — and **both pass
trivially over an empty set**. Emptying the baseline and leaving them
would have manufactured two vacuous assertions in the same edit that
closed a real gap. Both were replaced: the empty case now asserts what
the loop's silence cannot, and the subset check was replaced by the thing
it was actually protecting — that the two jointly-held artifacts stay in
the intersection, because an artifact that leaves it becomes one this
repository could bind unilaterally, which the joint-reissue rule forbids.

The parked doctrine-source-list decision was **not** taken. Binding a
baseline down is not deciding the source list, and the deferral's own
lapse condition — a *third* unbound artifact — moved further away, not
closer.

**The unverified-window guard fired on a module it did not account for.**
The census test reads the sibling checkout, making four such modules
where the record named three. Added, with the difference stated: the
fourth reads the sibling *conditionally* and degrades to a weaker
measurement rather than to a skip.

---

## What was not done

No other repository was read into, written to, or asserted about beyond
what was observed on disk. No parked decision was resolved. No clause was
widened. The two `UNDETERMINED` roles stay undetermined.

---

## Verification

| check | result |
|---|---|
| `python3 -m pytest tests/ -q` | **1848 passed, 1 skipped**, exit code read directly |
| `mypy daf/ science/ boundary/ bridge/ epistemics/ assertion/ session/` | Success, **91 source files** |
| submodule `vendor/scout-retrieval-agent` | clean, pinned at `5e146d5` |
| `build_invariant_register.py` | regenerated; 65 `extends` agreeing, 0 disagreeing |
| detector proofs | 8 planted, 8 fired, all restored to green |

**Bent: zero.** No core invariant changed. The vendored submodule is
byte-identical.
