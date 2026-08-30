# THIRD ANCHOR — A REAL STUDY OF A TECHNIQUE THIS CONTRACT WAS NOT WRITTEN FOR

Not a chromatogram. The first two anchors were GPC/SEC; this one is a
column-elution water-solubility determination under OECD 105, chosen
before it was found, against criteria recorded in
`architecture/third_anchor_preregistration.yaml`.

## The source

    FINAL REPORT — DETERMINATION OF PHYSICO-CHEMICAL PROPERTIES OF NKK-1304
    WIL Research Europe B.V., 's-Hertogenbosch, The Netherlands
    Study Director K.A. Oudhoff, PhD.  Project 505902, Substance 205674/A
    Sponsor: Nippon Soda Co. Ltd.  Study plan 02 Jul 2014 – 24 Sep 2014
    GLP-compliant, 44 pages

    https://downloads.regulations.gov/EPA-HQ-OPPT-2019-0495-0004/attachment_4.pdf
    sha256 4278fff29d1cf6235131d5ce12552434d7286ecfac989f3984f85a5c235775aa
    retrieved 2026-08-30

This fixture transcribes **section 12, WATER SOLUBILITY** only —
guidelines (12.1), performance (12.3), analytical method (12.4),
Table 8 (12.6.2). The other ten properties in the report are not here.

## Faithfulness — what was checked, not asserted

Two independent extraction passes (`pypdf` default and `layout` mode)
returned the twenty individual concentrations identically.

The report publishes statistics derived from those twenty values, so the
transcription can be checked against the document's own arithmetic:

| statistic        | recomputed from this fixture | printed in Table 8 |
|------------------|------------------------------|--------------------|
| mean, 24 ml/h    | 9.6610                       | 9.66               |
| mean, 12 ml/h    | 9.7410                       | 9.74               |
| mean of means    | 9.7010                       | 9.70               |
| CV, 24 ml/h      | 0.903 %                      | 0.91               |
| CV, 12 ml/h      | 0.271 %                      | 0.28               |
| MD on the means  | 0.825 %                      | 0.83               |

Means and MD reproduce exactly. Both CVs are one unit low in the last
printed digit, which is what computing a CV from concentrations carried
at full precision and printing them rounded to 2 dp produces. That is a
consistency observation, not a proof of method — but the report states
independently (§5.3) that raw data are archived at the test facility, so
values more precise than those printed do exist and were not released.

## WHAT THE SOURCE DOES NOT CONTAIN

- **`data_provenance`.** Absent, as on both GPC anchors. The report does
  not label its own figures as instrument output versus anything else;
  the category is the acquirer's, not the laboratory's.
- **`sample_kind`.** Absent. §6.1.1 describes the substance ("White
  powder", "Purity 99.7% (HPLC)"). A description is not a kind.
- **`sample_id` — absent as a *designated* field, and present three
  times over as candidates.** §6.1.1/§1 carry `NKK-1304` (substance
  designation), `CDC-003` (batch) and `205674/A` (test-facility
  substance number), none labelled as the identity of what was measured.
  This fixture states **none** of them, so that the acquirer's choice
  appears in `acquisition_declared` rather than being baked silently
  into a transcription. That is the same gap `architecture/
  anchor_three_identifiers.yaml` recorded on a GPC export, recurring on
  a different technique and a different vendor.
- **An uncertainty on the reported result.** Table 8 publishes CV
  (n = 10, per flow rate) and MD (between the two flow-rate means).
  Neither is an uncertainty *on* 9.70 mg/l — they are dispersion at a
  level of aggregation below the reported value. No standard deviation,
  standard error, or confidence interval appears anywhere in §12.
- **The individual concentrations at full precision** (see above).
- **Per-injection calibration responses.** §12.4.4 states five
  concentrations with two responses each and r > 0.99; the responses and
  the fitted coefficients are not printed.

## WHAT IT DOES CONTAIN THAT NEITHER GPC ANCHOR DID

- **A method identifier from a published closed vocabulary** — three of
  them: `OECD 105`, `EC A.6`, `OPPTS 830.7840`. Both GPC anchors named
  an instrument and a column; neither cited a guideline. Recorded because
  `third_anchor_preregistration.yaml` Q1 predicted the opposite.
- **Twenty individually reported replicates**, not a collapsed mean.
- **A stated equilibration criterion** (CV ≤ 30 %, MD ≤ 30 %) — an
  acceptance rule the study applies to itself.

## TRANSCRIPTION DECISIONS, STATED SO THEY ARE ARGUABLE

1. The runs carry `eluate_concentration`, not `water_solubility`. What
   Table 8's twenty rows measure is the concentration of test substance
   in a 2 ml eluate fraction. The water solubility (9.70 mg/l, §12.7) is
   the mean of the two flow-rate means — a different quantity, two
   aggregations away. Calling the twenty values twenty measurements of
   water solubility would state something the report does not.
2. **Flow rate and pH sit inside each run's `conditions`, and the fifteen
   report-level keys are restated in every run.** They are conditioning
   variables — the two series differ by flow rate, and the study's
   equilibration criterion (CV ≤ 30 %) is evaluated *per flow rate* — so
   they belong in the comparison context. A run-level `conditions`
   REPLACES the report-level one rather than merging with it, so the
   restatement is not redundancy; dropping it loses the guideline context
   entirely while still passing every gate.

   The first version of this fixture put them under `run_conditions`
   instead. That key is carried by the adapter into the payload and
   silently discarded by the extractor, whose content vocabulary is
   closed. The acquisition then succeeded with zero failures and zero
   refusals, merged the twenty runs into one group, and yielded a pooled
   CV of 0.773 % — a statistic the study never computed and would not
   accept. **The mean was 9.7010 either way**, identical to the report's
   9.70, so the one figure a reader would check agreed exactly while the
   grouping was wrong. Recorded in
   `architecture/third_anchor_result.yaml` as a measured instance rather
   than quietly corrected.
3. The reported result 9.70 mg/l is **not in this fixture**. There is no
   container for it: the adapter's unit of acquisition is a run, and a
   mean of means is not a run. Recorded rather than forced — and the
   substrate recovers 9.7410 and 9.6610 from the replicates, whose mean
   is 9.7010, without being given the aggregate.
