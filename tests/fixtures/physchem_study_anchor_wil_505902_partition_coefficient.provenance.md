# FOURTH ANCHOR — SECTION 13 OF THE THIRD ANCHOR'S REPORT

Same source document as
`physchem_study_anchor_wil_505902_water_solubility.provenance.md`:

    FINAL REPORT — DETERMINATION OF PHYSICO-CHEMICAL PROPERTIES OF NKK-1304
    WIL Research Europe B.V., Project 505902, Substance 205674/A
    https://downloads.regulations.gov/EPA-HQ-OPPT-2019-0495-0004/attachment_4.pdf
    sha256 4278fff29d1cf6235131d5ce12552434d7286ecfac989f3984f85a5c235775aa
    retrieved 2026-08-30

This fixture transcribes **section 13, PARTITION COEFFICIENT** — Table 9
(page 39), the analytical conditions (13.5), the reference substance
list (page 37) and the regression (13.7.2). Chosen because it carries
three things section 12 could not test: duplicate injections, reference
literature values beside measured ones in the same rows, and a headline
result derived from a regression over the other rows of the same table.

## WHAT THE SOURCE DOES NOT CONTAIN

- **`data_provenance`, `sample_kind`, a designated `sample_id`** — as in
  section 12, and for the same reasons.
- **An uncertainty on any retention time.** Table 9 gives tr,1, tr,2 and
  a mean. No dispersion figure of any kind is attached to a row.
- **Toluene's retention times.** Toluene is listed as a reference
  substance on page 37 with log Pow 2.7, and does not appear in Table 9.
  The regression states n = 12, which is the six tabulated reference
  substances at two injections each — so toluene is genuinely excluded
  from the calibration, not merely omitted from the printing. **The
  report gives no reason.** No absence reason is declared here: see
  `architecture/fourth_anchor_preregistration.yaml` P3.
- **The section 10 correlation coefficient**, which the report states was
  obtained and archived in the raw data rather than released. Not part of
  this fixture; recorded because it is the report's own withholding.

## TRANSCRIPTION DECISIONS

1. **`injection` is on `run_id`, not in `conditions`.** The first version
   of this fixture put it in conditions; every run then became its own
   singleton group and `pair_replicates` returned `EVERY_RUN_DIFFERS_IN`.
   That is the Phase 16 error — an acquisition locator in the comparison
   context — committed by hand and caught by the detector rather than by
   review. Recorded in `architecture/fourth_anchor_result.yaml`.
2. **`substance` IS in `conditions`.** Different substances under one
   method are different measurements, not replicates of one.
3. **The log Pow column is declared for what each value is**:
   `guideline_reference_value` for the six calibration standards (the
   page 37 footnote reads "values according to the OECD 117 guideline")
   and `derived_from_regression_over_other_rows` for the test substance.
   The path refuses both identically. Declaring them and being refused
   is the measurement; omitting them would have hidden it.
4. **Formamide carries no log Pow.** It is the unretained compound (t0),
   and Table 9 gives it none.
