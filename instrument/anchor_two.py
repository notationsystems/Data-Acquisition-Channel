"""ANCHOR 2, transcribed. A real Waters Empower 3 GPC report WITH
REPLICATES -- the structure B.2.4 was written for and could not test.

PROVENANCE. regulations.gov, docket EPA-HQ-OPPT-2019-0271, document 0065,
attachment 2. Impact Analytical report R190048, project P190044, customer
Essential Industries, analyst J. Damaska, report date 2019-02-14. PDF
1.7, 6 pages, 558843 bytes, Producer "Microsoft: Print To PDF", Author
mschwartz. UNREDACTED, where Anchor 1 was heavily redacted.

HOW IT WAS OBTAINED. A plain fetch returns 403; a request carrying a
browser User-Agent and a regulations.gov Referer returns 200. The block
is on the user agent, not on the address, which is worth recording
because "the source is unreachable" was the standing state of this
anchor.

EVERYTHING BELOW IS TEXT-LAYER. Tables I and II, the calibration table,
and every SAMPLE INFORMATION block extract as text -- including the
instrument's own `Injection #` field. That is the opposite of Anchor 1,
whose headline results were raster, and it is why prediction P5 failed.

WHY THIS FILE IS IN `instrument/`. Same reason as anchor_one: the layer
rule forbids the product from importing `instrument`, so real values here
cannot reach an adapter, an extractor or the pool. The fixtures that
exercise DAQ's path against these SHAPES are synthetic and live in
tests/fixtures/.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

#: Table II, page 3. Two injections and an aggregate block.
INJECTIONS: Tuple[Dict[str, float], ...] = (
    {"row_label": 1, "mn": 26459, "mw": 33070, "mz": 41046, "mw_over_mn": 1.25},
    {"row_label": 2, "mn": 23479, "mw": 30985, "mz": 40436, "mw_over_mn": 1.32},
)

#: The aggregate rows exactly as printed.
AGGREGATE = {
    "Average": {"mn": 24969, "mw": 32028, "mz": 40741, "mw_over_mn": 1.29},
    "Standard Deviation": {"mn": 2107, "mw": 1474, "mz": 431, "mw_over_mn": 0.05},
    "% RSD": {"mn": "8.4%", "mw": "4.6%", "mz": "1.1%", "mw_over_mn": "3.9%"},
}

#: Pages 5 and 6. The FIGURE CAPTION, the instrument's own field, and the
#: acquisition timestamp. The caption and the field disagree, and the
#: timestamps settle which is which.
INJECTION_REPORTS: Tuple[Dict[str, object], ...] = (
    {"figure_caption": "injection #1", "instrument_injection_number": 2,
     "date_acquired": "2019-02-14T09:51:01-05:00", "retention_time": 13.167,
     "mn": 26459, "mw": 33070, "mp": 27570, "mz": 41046, "polydispersity": 1.250},
    {"figure_caption": "injection #2", "instrument_injection_number": 1,
     "date_acquired": "2019-02-14T09:24:17-05:00", "retention_time": 13.250,
     "mn": 23479, "mw": 30985, "mp": 25095, "mz": 40436, "polydispersity": 1.320},
)

#: Table I, page 1. The customer-facing summary. `polydispersity` is 9.21
#: and Table I's own numbers give 32000/25000 = 1.28.
SUMMARY_TABLE = {"mn": 25000, "mw": 32000, "mz": 40700, "polydispersity": 9.21,
                 "percent_poly_under_1000": "0.0", "percent_poly_under_500": "0.00"}

#: Page 4. First order, against Anchor 1's third.
CALIBRATION_COEFFICIENTS = (1.089544e+001, -4.902533e-001)
CALIBRATION_FIT_ORDER = 1
CALIBRATION_R = 0.997921
CALIBRATION_R_SQUARED = 0.995846
V0 = 8.716911
VT = 16.799242
CAL_CURVE_ID = 1287
DATE_CALIBRATED = "2019-02-13T16:43:14-05:00"

#: (retention time, nominal Mol Wt, printed Log Mol Wt, printed Calculated
#: Weight, printed % Residual). Ten EasiCal polystyrene standards.
CALIBRATION_STANDARDS: Tuple[Tuple[float, int, float, int, float], ...] = (
    (8.717, 6035000, 6.7807, 4187389, 44.123),
    (9.196, 2698000, 6.4310, 2437198, 10.701),
    (10.340, 597500, 5.7763, 670524, -10.891),
    (10.988, 290300, 5.4628, 322353, -9.944),
    (11.609, 133500, 5.1255, 159966, -16.545),
    (12.171, 70500, 4.8482, 84821, -16.884),
    (12.942, 30230, 4.4804, 35515, -14.880),
    (14.084, 9590, 3.9818, 9789, -2.030),
    (15.195, 2970, 3.4728, 2794, 6.302),
    (16.799, 580, 2.7634, 457, 27.020),
)

#: Same as Anchor 1's. Confirmed independently on a different instrument,
#: a different lab and a different fit order.
RESIDUAL_IS_RELATIVE_TO = "calculated"

#: Named and not resolved, exactly as in Anchor 1. The one thing constant
#: across both anchors.
PROCESSING_METHOD = "P190044 DMF"
INTEGRATION_PARAMETERS_ARE = "named_by_reference_not_carried"

#: The method block describes a preparation that did not produce the
#: reported numbers. Three attempts; the reported result is the third.
METHOD_SAYS_PREPARATION = "dried under a stream of nitrogen"
WHAT_ACTUALLY_PRODUCED_THE_RESULT = "an aliquot of the NON-DRIED portion, diluted with DMF"
THE_NARRATIVE_CARRIES_THE_CORRECTION_NO_FIELD_DOES = True

#: The eluent field is qualified by sample id because it changed mid
#: project: `N, N-dimethylformamide (S190109)`.
ELUENT_AS_PRINTED = "N, N-dimethylformamide (S190109)"

#: Unfilled template fields, verbatim: the prose says "included as
#: Figures 1 through ." and every figure caption reads "Figure ." with no
#: number. Page headers on pages 4-6 read "IA Project P190044 of IA
#: Report R190048" -- the page number is absent too.
UNFILLED_TEMPLATE_FIELDS = ("Figures 1 through .", "Figure .", "P190044 of IA Report")

#: One sample is reported; the summary says four were submitted, and the
#: title and the sample identification disagree on chemistry.
SUMMARY_SAYS = "four polyurethane samples"
SAMPLE_IDENTIFICATION_SAYS = "PA191; Acrylic Polymer"
TITLE_SAYS = "GPC Analysis of Urethane and Acrylic Based Polymers"

#: Header spellings in this one document.
SPELLINGS: Tuple[str, ...] = ("Polydispersity", "Mw/Mn", "MP", "Mn", "Mw", "Mz",
                              "% Poly <1000", "% Poly < MWM4")

#: `% Poly < MWM4` names a marker whose value sits in an adjacent field;
#: Tables I and II print the same quantity resolved as `% Poly <1000`.
MARKER_REFERENCE_FORM = "% Poly < MWM4"
MARKER_RESOLVED_FORM = "% Poly <1000"
MARKER_VALUES: Dict[str, Optional[int]] = {"MWM4": 1000, "MWM5": 500}
