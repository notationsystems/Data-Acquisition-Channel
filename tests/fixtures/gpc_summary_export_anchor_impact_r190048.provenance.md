# Transcription provenance — Anchor 2

Source: regulations.gov docket EPA-HQ-OPPT-2019-0271, document 0065,
attachment 2. Impact Analytical report R190048, Waters Empower 3.
Retrieved directly; a plain fetch returns 403 and a request carrying a
browser User-Agent and a regulations.gov Referer returns 200.

Transcribed from the PDF's TEXT LAYER, which on this document carries
Tables I and II, the calibration table and every SAMPLE INFORMATION
block.

## What this fixture DOES NOT contain, because the report does not state it

- `data_provenance`, `sample_kind`, `method` — not fields of this report.
  They are caller declarations, supplied at acquisition, and the adapter
  for this shape has a channel for them. Anchor 1's adapter does not,
  which is why Anchor 1 cannot be acquired without fabricating.
- a value in the Sample cell of the second injection row. CORRECTED
  2026-08-30 from the source: the cell is not empty, it is MERGED across
  both injection rows. Measured from the text baselines --
  `PA191 (S190109)` sits at y=3644, centred between injection row 1 at
  y=3416 and row 2 at y=3875 -- and corroborated by the one horizontal
  rule on the page that is short across the first column. The blank is
  still kept, because a CSV cannot express cell extent and filling it
  would encode an interpretation as a transcription. What changed is the
  name of the interpretation: not "the document leaves this blank" but
  "the document merges this cell and CSV cannot carry that".
- an injection number on the Average, Standard Deviation and % RSD rows.
  An average has none.
- units for any column. The report states none.

## Why this note is a sidecar and not a comment in the CSV

The adapter carries every `#` line into `conditions` as the report's own
header text. A transcription note written there would become document
content — the fixture would then state something the source does not,
which is precisely the misread this guard exists to catch. The note is
about the fixture; it is not part of the document.
