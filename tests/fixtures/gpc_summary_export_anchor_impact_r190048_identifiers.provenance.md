# Transcription provenance — Anchor 2, all three identifiers

Source: regulations.gov EPA-HQ-OPPT-2019-0271-0065 attachment 2,
sha256 d85d72ab4ff3005de1def3c7722642ba8a30993a12c1d98b8621325b3012ec43.
Table II (page 3) and the SAMPLE INFORMATION blocks (pages 5 and 6), all
from the text layer.

This fixture exists to answer one question: when a document carries three
identifiers for two runs and they disagree, which one does the extractor
take, and can anything downstream tell it took the wrong one.

## The three identifiers, verbatim from the source

| value    | Table II `Injection` | block `Injection #` | block `Date Acquired` |
|----------|----------------------|---------------------|-----------------------|
| Mn 26459 | 1                    | 2                   | 09:51:01              |
| Mn 23479 | 2                    | 1                   | 09:24:17              |

Chronology settles it: 09:24:17 precedes 09:51:01, so the instrument's
first injection produced Mn 23479 — the row Table II labels injection 2.
The table's labels are reversed relative to the instrument's.

## What this fixture DOES NOT contain

- units for any column. The report states none; they are caller-declared.
- `data_provenance`, `sample_kind`, `method`. Not fields of this report.

## STATED INTERPRETATIONS — three, and they are not transcriptions

1. **The merged Sample cell is flattened to a repeated value.** The source
   merges one Sample cell across both injection rows (measured: the label
   sits on its own baseline at y=3644, centred between rows at y=3416 and
   y=3875). CSV cannot express cell extent. The value is repeated on both
   rows, which is what the merge means and not what the file contains.
2. **`Date Acquired` is reduced to minutes past midnight.** The source
   prints `2/14/2019 9:51:01 AM EST`. A timestamp is not a quantity and
   this column is only here because the adapter has no channel for a
   second identifier — see 3. The reduction discards the date and the
   zone.
3. **Two of the three identifiers are declared as QUANTITIES.**
   `_IDENTITY_COLUMNS` is the literal `("Sample", "Inj")`, so only one run
   identifier can be an identifier. `InstrumentInjection` and
   `AcquiredAtMinutes` enter as measured numbers because that is the only
   channel available. This is the finding, not a workaround: the substrate
   has no way to hold a second identifier for the same run.

The aggregate rows are omitted here. They are measured against the other
fixture, and including them would mix two questions.
