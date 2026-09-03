# Phase 41 — The Ecosystem Measures Itself, and the Instrument Was Wrong Twice

## What this phase was

The ask was to scan everything on the machine and make the parts coherent as
apparatuses of one ecosystem. That is a mapping exercise, and mapping exercises
produce diagrams. This one produced three retractions, one class-record entry,
and a survey of a repository nobody here had opened — and the retractions are
the substance.

The starting move was to ask, of a company that describes itself as building
provenance-bearing computational corpora, **which of its repositories actually
bear provenance.** Nine checkouts sat on this machine under six directories.
A first draft of `architecture/ecosystem_register.yaml` answered from those
checkouts alone, said honestly under `what_this_register_cannot_see` that
remote state had not been measured, and published three findings.

All three were false.

---

## Three for three, and the caveat did not help

The draft reported:

| finding | what is actually true |
| --- | --- |
| three core objects sharing **no** history | one history; the pin is an ancestor of the head |
| the acquisition layer is **two** repositories | one repository, **three** names |
| the corpus substrate is an **empty** member | an empty *clone* of a repository with an active branch |

The register had named its own blind spot in the file and reasoned past it
anyway. That is the lesson worth keeping: **stating a limit does not license
reasoning past it.** Each of the three findings was a claim about the ecosystem
inferred from a sample the caveat had already declared partial. A register that
says "I did not measure the remotes" and then publishes a conclusion about the
remotes has not been careful; it has been transparent about being careless.

The measurement that fixed all three was one command per remote —
`git ls-remote`, which reads refs and touches no object store.

---

## The instrument manufactured a finding

The share-no-objects claim came from running `git cat-file -e <commit>` inside
`ste-clean` for each of three commits and watching all three fail.

`ste-clean` is a **partial clone** — `remote.origin.promisor true`,
`partialclonefilter blob:none`. In a partial clone a presence query is not a
read. On a local miss, git fetches the object from the promisor remote and
answers yes.

Re-running the identical question with **full** shas instead of abbreviated ones
returned `commit` for all three, and two new promisor packs appeared in
`.git/objects/pack` timestamped inside the same minute as the query. The objects
were there *because they had been asked about*.

The difference between the run that produced the finding and the run that
destroyed it was **seven characters**. An abbreviated sha must be resolved
against the local object database before any fetch can be attempted, so it
misses locally and never reaches the lazy path.

This is filed as the twenty-seventh instance in `architecture/proof_integrity.yaml`,
under the class that was already there — a verification with a write side effect
cannot witness what it verifies — and it sharpens it. The existing instance
describes a check that dirtied a tree it was not asking about: an observer
disturbing its surroundings. This one supplied *the very object whose absence was
the finding*: an observer that manufactures what it observes.

The general form now recorded: **ask what obtaining a measurement costs.**
`Is X present` over any lazily-materialising store — a partial clone, a
read-through cache, an ORM with lazy loading, an automounter — is a question
whose asking can make the answer true. That is a write the check does not contain
and cannot be found by reading it.

The repair is `GIT_NO_LAZY_FETCH=1` on every git invocation in
`tests/test_ecosystem_register.py`, set in one helper — plus a test that reads
the test file's own source and fails if any git call is written around that
helper. The guard is not the environment variable. The guard is that the variable
cannot quietly stop being used.

---

## And the same trap sprang again, one file later

The enforcement test verifies a recorded referent by fetching it from its remote.
`git fetch <url> <sha>` also requires the full forty characters, because the
throwaway repository doing the fetch has no object database to resolve an
abbreviation against.

All six members reported *no longer served*. Six false alarms, one cause, the
same cause, inside the artifact whose headline finding was that cause.

The register now records every remote referent unabbreviated, and states the rule
it arrived at from a second direction: **the participating referent is recorded in
full; the abbreviation is a reading aid that may appear in prose and may never be
the thing a check joins on.** That is this pair's own rule, reached again by
walking into it.

---

## Six repositories, ten names

Identity is **equality of the full ref set**, chosen over object-sharing
deliberately: GitHub serves a fork's whole network from one object store, so
"does remote R serve commit C" is true across every fork of anything and
identifies nothing.

- `Notations-Acquisition-Channel.git` ≡ `notations-acquisition-channel` ≡
  `data-acquisition-channel-daq` — one branch, one commit, three names
- `scout-retrieval-agent.git` ≡ `scientific-transformer-engine` — identical ref
  sets, and the *core* is the first of these, vendored at
  `vendor/scout-retrieval-agent`. The draft had classified the second as the core
  on the strength of the acronym.
- `Notations-CUDA-Architecture-`, `scientific-corpus-substrate`,
  `gromacs-molecular-simulation`, `lammps-md`

Whether a shared ref set arises from a rename-with-redirect or a mirror is **not
determined** — both produce exactly this signature, and nothing observed here
separates them. Recorded as undetermined rather than guessed.

Two claims the draft had left open are now measured rather than intended: both
forks have exactly one branch, its head equals the local checkout, and the true
upstream (`gromacs/gromacs`, `lammps/lammps`) serves that commit. `vendored_upstream`
is a description of **state** now, for the refs that exist.

---

## Remote heads move in minutes, and the check had to be redesigned around it

The enforcement test was written asserting recorded heads against live ones. It
failed on its first run: two remotes had moved in the eleven minutes since the
register was written, each by one commit from a concurrent session.

Asserting equality would make the check red on ordinary work, and a check that is
red on ordinary work is a check nobody reads. So the property asserted is the one
that actually carries: **the recorded commit is still served.** A branch advancing
past a reading is expected. A reading the remote can no longer produce is a
rewrite, a force-push or a collection — and it silently voids every claim made
relative to that referent.

---

## The corpus substrate, read

One member was classified `unsurveyed`, and its branch was named
`claude/corpus-graph-polymer-061fbl` — the vertical this repository spent two
phases building. Reading it was not optional.

It is a **counterpart**, not a duplicate and not a contradiction:
`architecture/corpus_substrate_survey.yaml`, read at `cc80f51a…`. It derives Mn,
Mw, Mz, Mp and dispersity from SEC/GPC by an independent route.

**Where the two agree**, having never met: on `dispersity` rather than the
acronym every instrument prints; on a derived quantity never being its own
evidence — this repository refuses it at ingest, the corpus classifies it as a
`claim` at emission; and on knowledge time being separate from the time
described. Each holds *half* of the known-at rule the other does not: the corpus
takes the earliest on merge and has no ordering check, this repository refuses a
`known_at` before its period and has no merge rule.

**Where they diverge**, and it has teeth: `ncg/units.py` carries
`uncertainty: float | None` and nothing else. This repository's
`UNCERTAINTY_KINDS` is a closed four-member vocabulary and
`MISSING_UNCERTAINTY_KIND` is never defaulted. So a molar mass emitted by the
corpus is **refused** at this boundary — and that is not left as prose. The shape
is constructed in `tests/test_corpus_substrate_survey.py` from the corpus's own
field set, run through the real gate, and asserted, with the admissible
counterpart run beside it so a gate that refused everything could not pass.

Which side should move is argued rather than asserted: a standard uncertainty
that does not say whether it was stated, estimated, or propagated is not
interpretable by any consumer, because the three combine differently. The gap is
in the corpus's model. What this repository owes in return is stated too — the
vocabulary lives in a Python tuple and in prose, and nothing exports it in a form
another apparatus can read.

**The sharpest open question** is the second divergence. `DERIVED_VARIABLES` here
is a tuple of five *spellings*, and `architecture/third_anchor_result.yaml`
already records it catching nothing on a different technique. The corpus has no
name list at all: a value is derived because it points at the Signal it came from
through a named, versioned derivation. That is the **derived form of a check this
repository holds in the enumerated form** — the most-instanced class in the record
— and it is the first time another apparatus has been found already holding the
repair. It is not simply adopted, because the two answer different questions: the
corpus knows a value is derived because it derived it, while this repository is
reading a vendor's report and asking whether a printed *column* is derived, with
no derivation to inspect. Recorded as open.

The corpus also declares participation to a **control plane** — an authority it
mirrors vocabularies from and is held to by — referred to only by role, with no
repository or URL anywhere in its tree. That is the shape STE had here before the
core referent was declared: a party with obligations recorded against it and
nothing to join on.

---

## The core has moved six commits and the version did not

`architecture/core.yaml` wrote this failure mode down before it happened:

> it is a submodule bumped to a commit whose pyproject still says 1.0.0. Patch
> commits do not bump versions. Every check passes, the recorded commit is
> silently wrong, and every `extends` still agrees.

Measured: the pin is `5e146d5…`, the remote branch head is `e02cd66…`, six
commits apart, the pin an ancestor of the head, and the package version is
`1.0.0` at both. **Nothing here is currently stale** — the pin has not moved and
the referent join holds. This is a prediction confirmed about the *remote*, not a
defect found in the tree.

What is waiting at that head is
`architecture/exchange/ste_invariant_declaration.yaml`, authored by the core as
owner: the exact path `build_ste_invariants.py` names as what would supersede its
reconstruction. Our `ste_invariants.yaml` carries `RECONSTRUCTION_NOT_DECLARATION`
and a warning never to cite it as the core's own statement. It was right to. The
statement now exists, it answers all three asks in order, and on the cardinality
it answers **neither** eight nor ten — retracting the ten rather than correcting
it, because eight rests on a single citation to a brief that is not in the tree.

It also cites the same rule this record files under `convergence_is_not_evidence`,
reached from the other side: the two readings agree, and both come from the same
documents by the same method, so there is no independence in the agreement.

The core additionally added `materials/replicate_join.py` — a consumer of the same
finding `science/replicate_pairing.py` consumes, on the other substrate, and it
adds the half this repository did not have. The unpairing is not merely an
absence: group values arrive ordered by content-addressed observation id, so two
properties over the same runs give two unrelated permutations. Index pairing
therefore does not fail — it returns **ρ = +0.38 where the true value is −0.98**,
wrong in sign, stably, reproducibly. That is the polymer vertical's stated
question, answered from the other side. And that module declares a dependency on
two properties this layer owns and does not enforce: one Record per run, and the
run identifier out of content.

**The pin was not bumped.** Moving it re-points every `Bent: zero`, every
`core_invariants_modified: 0` and every `extends:` at a different object, and
`core.yaml`'s own rule says those must then be re-measured. That is a phase with a
preregistration, not a line in a register — so
`architecture/core_pin_bump_preregistration.yaml` records six falsifiable
predictions about what a bump will do, before it happens, with the re-measurement
list it obliges.

Its own enforcement caught two gaps in it on the first run: a prediction claiming
a MEASURED basis and citing no path, and a prediction naming nothing that would
falsify it. Both were repaired in the artifact, not the check.

---

## A count typed into prose, three times

`architecture/proof_integrity.yaml` said "the 26 instances below".
`tests/test_condition_provenance_reachability.py` said "records TWENTY-FOUR
instances". Both were right when written, both stale, stale by *different*
amounts — so the repository was simultaneously asserting two different sizes for
one list sitting in the tree.

Bumping them to today's number guarantees a fourth. So the count is not written
down at all any more, and `tests/test_no_prose_states_the_instance_count.py`
asserts that. It found a **third** on its first run —
`architecture/vacuous_evidence.yaml`, `24 instances` — plus one genuine false
positive in the same file, counting occurrences of a different class. The prose
was reworded and the check left alone, following the disposition
`test_cross_repository_claims.py` already argues at length: an exception is a
permanent hole in a check whose entire value is that it has none, and it gets
added by whoever is annoyed rather than by whoever measured.

This is the same repair `core.yaml` already made for the `extends` census. It is
now made for the other census the repository keeps.

---

## Errors of my own, all caught by the machinery

1. **The three false findings**, above. Caught by measuring what the file said it
   had not measured.
2. **A defective plant.** Testing the citation check, the first attempt
   *prepended* text to a claim instead of replacing it, leaving the citation in
   the string. The check correctly passed, and passing was meaningless. The class
   record already carries this operator error under
   `a_mutation_set_is_a_lower_bound_not_a_proof`: a mutation that does not change
   what the check reads reports SURVIVED and means nothing. **A plant that passes
   is a claim about the plant until the plant is inspected.**
3. **`5e146d5` attributed to the wrong repository.** The draft recorded it as a
   third STE object. It is the gitlink for `vendor/scout-retrieval-agent`, and
   `scientific-transformer-engine` is a different name for the same project —
   which is how the acronym produced the error in the first place.

---

## Verification

Twenty-two planted defects across four new checks, each run, each restored:
six against the ecosystem register, four against the corpus survey, three against
the pin-bump preregistration, and the historical prose-count strings against the
count check. Two further failures fired **for real** before any plant, on the
preregistration's first run.

The one plant that could not be re-armed is recorded as such: reproducing the lazy
fetch needs a partial clone holding an object it has not yet fetched, and running
the probe consumes that state. The check measures the **side effect** instead —
pack count before, pack count after, answer discarded — which is the part that
stays checkable after the fact.

**Bent: zero.** No core invariant changed; the pin is unmoved at
`5e146d5924675cd7b6e1d1ed44fb39f5da012610` and the vendored tree is byte-identical.
