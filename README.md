# Data Acquisition Fabric

**An acquisition apparatus that refuses rather than guesses.**

DAF takes real external scientific sources to content-addressed
observations under a contract that will not let a number into the
evidence pool without its warrant. It is one of the apparatuses of
[Notation Systems](https://github.com/notationsystems), which builds and
operates provenance-bearing computational corpora.

The property that defines it: **provenance is part of a value's identity,
not metadata beside it.** An observation's id is a hash over
`(record_ids, extraction_method, content)`, and the source class lives
*inside* content. So a fabricated fixture and an instrument measurement
carrying the same number are different objects, and no consumer
downstream — including one that never reads this README — can confuse
them.

---

## What it does

Real sources go in. Nothing is defaulted, and a source that cannot state
what the contract requires is refused rather than completed on its
behalf.

- **Adapters** fetch and decide granularity. One `RawDocument` per *run*,
  never per report — a decision that cannot be made downstream, because
  `run_scout` builds exactly one `Record` per document and an extractor
  handed one record per report has no way to emit five.
- **Extractors** translate a source's vocabulary into the content
  vocabulary, and refuse what they cannot state honestly: a non-numeric
  value, a missing uncertainty posture, an undeclared provenance.
- **Science gates** judge admissibility — typed quantities, structural
  absence, replicate pairing, aligned tables. Membership of a closed
  vocabulary is theirs to decide; presence is the acquisition layer's.
  The split is enforced, not observed.
- **The evidence pool** holds content-addressed observations that name
  the records they came from.

Absence is structural and never a value. A missing cell carries a reason
from a closed vocabulary, and a sentinel encoding one is refused.

## Layers, enforced by AST

```
science/     -> materials, boundary
boundary/    -> evidence
bridge/      -> boundary, daf
daf/         -> evidence ONLY
epistemics/  -> evidence.identity.content_hash ONLY
assertion/   -> daf, science
instrument/  -> imports nothing of the product, and nothing imports it
```

These are checked by parsing the imports, not by convention. `daf`
reaching into `science` to validate vocabulary membership is a real
mistake that was made and caught.

## Where it sits

| apparatus | role |
|---|---|
| [scout-retrieval-agent](https://github.com/notationsystems/scout-retrieval-agent) | **the core.** A canonical-state compiler pipeline. Vendored here read-only and never modified; the pin is the referent 55 records in `architecture/` declare. |
| **data-acquisition-fabric** | this repository. Acquisition. |
| [scientific-compute-layer](https://github.com/notationsystems/scientific-compute-layer-scl-) | the compute apparatus. Two artifacts are held byte-identically by both parties; editing either is a joint reissue, never one party's act. |

`architecture/ecosystem_census.yaml` records all six Notation Systems
repositories, what each stands on, and which of them carry the ecosystem
property — including the two that carry nothing on this machine, recorded
as *undetermined* rather than guessed from their names.

## How it is built

Every phase is a measurement, and the measurement can be wrong. What is
not negotiable is that it is recorded either way.

- **Pre-registration.** Predictions are pinned by digest and committed
  *before* the thing they predict is fetched or run. When one turns out
  wrong the result says so; the record is never edited to match.
  Two of the last five were falsified, and they were the more useful half.
- **Detector proofs.** Plant the defect a check claims to catch and watch
  it fail. A check that has never failed is a check nobody has tested.
- **Discriminating cases.** Name the state in which a test fails before
  writing it. A test with no such state is decoration.
- **Report, not edit.** DAF reports on another party's artifacts and
  never modifies them.
- **No clause is widened so a real document can pass.** If an anchor
  cannot be admitted, that is the result.

Findings that are defects get filed as classes, not incidents —
`architecture/vacuous_evidence.yaml` names six, including the three times
this repository produced a false green by piping a command to `tail` and
reading the pipeline's exit code instead of the command's.

## Anchors

Five fixtures transcribed from three real published documents:

- two GPC/SEC reports (EPA ChemView TSCA P-22-0051; a replicate export);
- two sections of a 44-page GLP physico-chemical study retrieved from
  regulations.gov.

Each carries a provenance sidecar stating what its source **does not**
contain. Where a document publishes statistics derived from its own
values, the transcription is checked against them — on the GLP study the
substrate recovered the laboratory's own two replicate groups and both
published coefficients of variation without being given the aggregate.

## Running it

```bash
python3 -m pytest tests/ -q                       # 1837 tests
python3 -m mypy daf/ science/ boundary/ bridge/ epistemics/ assertion/ session/
python3 architecture/exchange/build_invariant_register.py
```

Read exit codes directly, never through a pipeline. `docs/PHASE_*.md`
are the phase reports in order; `architecture/*.yaml` are the records
they rest on, each bound to an enforcing test.
