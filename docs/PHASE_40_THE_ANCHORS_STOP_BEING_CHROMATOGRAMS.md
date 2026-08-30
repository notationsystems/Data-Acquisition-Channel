# Phase 40 — The Anchors Stop Being Chromatograms

## What this phase was

Two anchors had met the acquisition path and both were GPC/SEC. The contract
survived them — one refused, one ingested end to end — and neither could test the
claim that actually mattered: that this is a contract about **measurements**
rather than a contract about **chromatograms**. A third chromatogram would have
tightened the comparisons and answered nothing.

So the third anchor was deliberately a different technique, and the predictions
about what it would do were pinned and committed **before any candidate was
fetched**. That commit order is the whole content of the claim; the digest only
makes a later edit a visible second act.

The document that arrived is a 44-page GLP final report from WIL Research Europe
(project 505902, sponsored by Nippon Soda), retrieved from regulations.gov under
`EPA-HQ-OPPT-2019-0495-0004`, `sha256 4278fff2…`. Eleven physico-chemical
properties. Two of its sections became fixtures.

---

## The verdict: the contract is not GPC-shaped

Every clause that survived two chromatograms survived a column-elution water
solubility determination under OECD 105, on a document none of them was written
for. What *was* technique-shaped turned out to be smaller than predicted, and is
now named.

**Q1 was wrong about `method`.** It predicted that no report of any technique
states `data_provenance`, `sample_kind`, a machine-readable `sample_id`, or a
method identifier. Three hold. The fourth fails hard: the report cites `OECD 105`,
`EC A.6` and `OPPTS 830.7840` — three identifiers from published closed
vocabularies, more machine-readable than anything either GPC anchor carried.
Declaring `method` at the adapter alongside the document's own is refused as a
conflict, which is both correct and the proof the field is genuinely stated.

The prediction generalised from two chromatograms. A chromatogram names an
instrument and a column; a guideline study cites the guideline it was performed
under, because that citation is what makes it a guideline study. So the four
"caller-declarable" fields were never one class: three are the acquirer's
categories, and `method` was in the list only because chromatograms happen not to
state it.

**Q4 was wrong about run identity.** It predicted a study might satisfy the
one-Record-per-run precondition vacuously by collapsing replicates before
acquisition. Table 8 prints all twenty individual concentrations. Twenty runs,
twenty distinct Records, zero failures — and **twelve of the twenty share a value
with another replicate**, all staying distinct. The adapter's claim that run
identity on the locator keeps two runs reporting the same number two Records had
never been tested: both GPC anchors had all-distinct values.

The prediction was wrong about this report and right about the shape. §12.7 states
the result as a single figure, so a transcriber reading the conclusion rather than
the table would produce exactly the collapsed document it describes, and nothing
downstream could tell the two readings apart.

---

## The transcription could be checked, which no previous anchor allowed

The report publishes statistics derived from the twenty values, so a misread is
arithmetic rather than a matter of opinion:

| statistic | recomputed from the fixture | printed |
|---|---|---|
| mean, 24 ml/h | 9.6610 | 9.66 |
| mean, 12 ml/h | 9.7410 | 9.74 |
| mean of means | 9.7010 | 9.70 |
| CV, 24 ml/h | 0.903 % | 0.91 |
| CV, 12 ml/h | 0.271 % | 0.28 |
| MD on the means | 0.825 % | 0.83 |

Both means reproduce exactly. MD lands on 0.825 against a printed 0.83 — half-up
rounding of a value sitting exactly on the boundary, which a first draft of the
result record called "exact" and does not deserve. Both CVs are one unit low in
the last printed digit, which is what a CV computed from concentrations carried at
full precision and printed to 2 dp produces.

---

## The best result: the substrate reproduced the laboratory's own analysis

Given the twenty replicates and **no aggregate**, `science/replicate_pairing.py`
recovered two replicate sets of ten — means 9.6610 and 9.7410, CVs 0.903 % and
0.271 % — against a printed 9.66/0.91 and 9.74/0.28, with the mean of means at
9.7010 against a stated 9.70 mg/l.

The pairing machinery had only ever been checked against synthetic runs and this
repository's own fixtures. This is the first time it has been checked against an
external laboratory's published analysis, and its grouping rule — *conditions are
the group* — picks the same grouping a GLP study picks for itself. One agreement
on one study is one agreement, and it is more than there was.

---

## The defect that agreement exposed

The first transcription put flow rate and pH under a run-level key
`run_conditions`. The adapter copies every non-`run_id` run key into the payload,
so it travelled. The extractor's content vocabulary is closed, so it was
**discarded without a word**.

Acquisition succeeded: twenty observations, zero failures, zero pairing refusals.
The twenty runs merged into one comparison group instead of two, and the pooled CV
came out at 0.773 % — a statistic the study never computed, sitting between its two
acceptance figures, derived by pooling across the very variable its acceptance
criterion is evaluated within.

**And the mean is invariant.** 9.7010 either way, matching the report exactly. The
one figure a reader would check against the source agrees perfectly while the
grouping is wrong. The check a reader would actually run is blind to the defect.

The correct key exists — a run-level `conditions` is carried, and
`architecture/acquisition_reachability.yaml` was right that per-run conditions are
expressible. Filed as a measured asymmetry rather than a proposal: an adapter
accepts a key the extractor discards in silence, and an author who guesses the
wrong name gets a clean green.

A second cost sits beside it. A run-level `conditions` **replaces** the
report-level one rather than merging, so adding one per-run key means restating
all fifteen. A transcription that states only the run's own two keys also passes
every gate — and loses all three guideline citations, the temperature, the column
and the whole method context. The correct transcription and the context-destroying
one differ in verbosity, not in verdict.

---

## Section 13: two injections and twenty determinations look the same

The fourth anchor is the same report's partition-coefficient section, chosen
because Table 9 carries three things §12 could not test. Predictions pinned
before the run; all five confirmed, one with half falsified.

The path acquires **eight replicate sets of two**, zero refusals, with the same
seven context keys as §12's two sets of ten. But §12's tens are twenty independent
determinations and §13's pairs are two injections of one prepared solution.
Injection CVs run 0.099 %–0.388 % against determination CVs of 0.271 % and
0.903 %: a consumer computing dispersion from §13 gets injection repeatability and
reads it as determination repeatability, understating it about threefold. Nothing
in the content says which it is.

The falsified half: something *does* object. `sample_covariance` returns
`DEGENERATE_VARIABLE` on the test substance — whose two injections read 1.950 min
exactly, on the row carrying the report's headline endpoint — and on formamide.
Unplanted, on a real document. It does not fire on the other six. **A zero
dispersion is caught; a threefold understatement is not, and is the more likely
error.**

---

## One gap, met four times

§13 prints `r = 0.9998, n = 12`. §10 says a curve with r > 0.99 could not be
obtained and that the results are archived in the raw data — released when it
supports the conclusion, archived when it does not. Neither is expressible.

That joins §12's CV and MD. Four set-level quantities in one report, and the
content vocabulary is per-cell in all four cases. This is not an uncertainty gap
and an absence gap. It is **one gap**: a per-cell contract meeting a document whose
statistics are about sets. `uncertainty_kind` cannot hold a dispersion across
runs; `value_absence` cannot hold a withholding of a fit statistic; and neither
failure is really about its own vocabulary.

Naming it once rather than four times is the phase's most useful piece of
bookkeeping.

---

## Four absences, and the vocabulary fits none of them

`science/table.py` offers `not_measured`, `below_detection`, `above_range`,
`withheld`, `lost_in_acquisition`. This one report produced four absences and no
reason fits any:

1. **Vapour pressure `< 1.5 × 10⁻³ Pa`** (§10). The intended determination failed —
   no log p vs 1/T curve with r > 0.99 — so the bound was set by comparing weight
   loss against hexachlorobenzene. It was measured, so not `not_measured`. Weight
   loss *was* detected, so not `below_detection`. The true statement is an upper
   bound established by comparison with a reference substance, and the bound
   `1.5e-3` has nowhere to live even if a reason fitted, because an absence carries
   a reason and not a number. `< 1.5e-3 Pa` is strictly more informative than
   `not_measured` and the substrate flattens them.
2. **The §10 correlation coefficient**, stated to exist and archived rather than
   released. Genuinely `withheld` — and set-level, so unattachable.
3. **Toluene's retention times** (§13). Listed as a reference substance on page 37
   with log Pow 2.7, absent from Table 9, with n = 12 confirming six substances.
   The report gives no reason. None was chosen: the row is simply not there, and a
   test asserts no `ABSENCE_REASONS` string appears in the fixture.
4. **Self-ignition temperature: "not required."** An absence because the test was
   inapplicable.

`withheld` therefore remains unexercised, and now for a stated reason rather than
for want of a document.

---

## Two errors of my own, both caught by the machinery

**`injection` in `conditions`.** The first §13 fixture put the injection number in
the comparison context. Every run became its own singleton and `pair_replicates`
returned `EVERY_RUN_DIFFERS_IN` — the Phase 16 error the module's own docstring
documents, committed by hand and caught by the detector rather than by review. The
injection number was already on `run_id`, hence on the locator, which is where it
belongs.

Its limit is recorded too: the refusal names `conditions`, the **container**, not
`injection`, the **culprit**, and there are eighteen keys inside.

**A tautology.** An assertion in the pre-registration test ended `or True` — the
exact vacuous idiom filed twice in `architecture/vacuous_evidence.yaml`, written
by me, in a test whose subject is not writing them. Replaced with three real
assertions, with the edit that makes them fire planted and watched.

---

## The guard's own vocabulary was technique-shaped

`tests/test_corpus_anchor_preregistration.py` declared every fixture as
`A_GPC_ANCHOR` or `NOT_A_GPC_ANCHOR`. A real GLP water-solubility determination is
not a GPC anchor, so the binary offered only `NOT_A_GPC_ANCHOR` — true by the
letter, and precisely the case the guard's own docstring names as beyond any
check: *"a fixture transcribed from a real report and declared NOT_A_GPC_ANCHOR is
a false statement by a person, and no check reaches it."*

The repair is a third value and an `ANCHOR_KINDS` set — the **vocabulary** widened,
not a clause. What the guard is really asking is whether a fixture came from a real
document; the GPC in the name was always incidental. The misfiling now fails two
assertions, planted and watched.

The finding this phase exists to test — that a name encoded a technique where the
substance was general — recurred inside the check written to police the anchors.

---

## What was not done

No clause was widened so a real anchor could pass. `UNCERTAINTY_KINDS` and
`ABSENCE_REASONS` are unchanged and a test asserts it. No product change was made
in response to any finding above: the dropped-key asymmetry, the per-cell/set-level
gap, per-measurement provenance and the granularity of `EVERY_RUN_DIFFERS_IN` are
all recorded as measurements, not proposals.

Forward-model steps 5–6 remain unbuilt, per the standing decision that they wait
until a real report has gone end to end *for that purpose*.

---

## Verification

| check | result |
|---|---|
| `python3 -m pytest tests/ -q` | **1836 passed, 1 skipped**, exit code read directly |
| `mypy daf/ science/ boundary/ bridge/ epistemics/ assertion/ session/` | Success, **91 source files** |
| submodule `vendor/scout-retrieval-agent` | clean, pinned at `5e146d5` |
| `architecture/exchange/build_invariant_register.py` | regenerated; 64 `extends` agreeing, 0 disagreeing |
| detector proofs | 8 planted, 8 fired, all restored to green |

Two notes on process. Exit codes are read directly and never through a pipeline —
a `PYTEST_EXIT=0` early in this phase was the exit code of `tail`, not of pytest,
which is the failure mode that rule exists for. And twice a `__pycache__` entry
survived a same-second, same-length edit and reported a stale result; both times
the phantom was chased before being recognised.
