"""ANCHOR 1, transcribed. A real Waters Empower GPC report.

PROVENANCE. EPA ChemView, TSCA premanufacture notice P-22-0051, document
`09022526804d8870_TS-U623EO MW by GPC_Redacted.pdf`, 8 pages, 881836
bytes, PDF 1.6, Author "US EPA", ModDate 2024-04-27. Waters Alliance 2695
with a 2414 RI detector, two Styragel HR1 and one HR2, stabilized THF at
40 C and 1.0 mL/min, 50 uL of ~3 mg/mL, processed by Empower. Test date
19 March 2021. The sample name and chemical name are redacted in the
source; nothing here depends on them.

WHY THIS FILE IS IN `instrument/` AND NOT IN `tests/fixtures/`. These are
real values from a real report, and the layer rule -- asserted by AST in
tests/test_forward_instrument_model.py -- forbids the product from
importing `instrument` at all. So an anchor's numbers living here cannot
reach an adapter, an extractor or the pool. A fixture under
tests/fixtures/ could be ingested; this cannot. That is the difference
between ground truth for a forward model and evidence for acquisition,
and B.1 still has no fixture.

WHAT WAS MACHINE-READ AND WHAT WAS NOT. The slice table below came out of
the PDF's TEXT LAYER and is reproducible by anyone with the file: 100
rows, parsed and checked (indices 1..100 complete, slice area constant,
cumulative percent equal to the index on every row). The calibration
table and the reported moments are RASTER IMAGES with no text layer at
all -- page 4, which carries every headline result, extracts to ZERO
characters -- and were read from the rendered pages. They are transcribed
by reading, not verified by a second party, and the checks in
tests/test_anchor_one.py are what stands behind them: the calibration
transcription is confirmed by a fit that reproduces the report's own
calculated column AND, with no free parameters, the machine-read slice
table's mass column.

At 1.0 mL/min a retention time in minutes is numerically an elution
volume in mL, which is why these times are usable directly as the
`Calibration` volume axis.
"""

from __future__ import annotations

from typing import Tuple

#: (nominal Mol Wt, retention time / min, the report's Calculated Weight,
#: the report's % Residual). Eleven polystyrene standards, each injected
#: twice, American Polymer Standards Corporation, 162-14000 Da.
#: RASTER-READ from page 3.
CALIBRATION_STANDARDS: Tuple[Tuple[int, float, int, float], ...] = (
    (14000, 16.858, 13657, 2.513), (2700, 19.661, 2612, 3.385),
    (14000, 16.879, 13457, 4.034), (2700, 19.685, 2581, 4.591),
    (9400, 17.294, 10139, -7.287), (845, 22.271, 872, -3.145),
    (9400, 17.318, 9977, -5.786), (845, 22.303, 863, -2.029),
    (5450, 18.374, 5184, 5.129), (1925, 20.443, 1813, 6.167),
    (5450, 18.399, 5110, 6.663), (1925, 20.471, 1791, 7.461),
    (4300, 18.620, 4507, -4.586), (4300, 18.649, 4435, -3.053),
    (1470, 20.836, 1529, -3.861), (370, 25.013, 358, 3.376),
    (1470, 20.872, 1506, -2.375), (370, 25.054, 353, 4.689),
    (1080, 21.527, 1154, -6.425), (162, 27.581, 165, -1.847),
    (1080, 21.567, 1136, -4.959), (162, 27.631, 162, -0.290),
)

#: `% Residual` is (nominal - calculated) / CALCULATED, not / nominal.
#: Recovered by arithmetic, checked in the tests.
RESIDUAL_IS_RELATIVE_TO = "calculated"

#: (retention time / min, Slice MW, dwt/d(logM)) for all one hundred rows
#: of the distribution table. TEXT-LAYER read. Every row's Slice Area is
#: SLICE_AREA and every row's Cumulative % equals its index.
SLICE_TABLE: Tuple[Tuple[float, int, float], ...] = (
    (16.078, 24334, 0.228449), (16.178, 22519, 0.355053), (16.25, 21314, 0.469152), (16.307, 20414, 0.577113), (16.355, 19690, 0.678056),
    (16.397, 19083, 0.770321), (16.435, 18556, 0.853361), (16.469, 18087, 0.926664), (16.501, 17661, 0.990563), (16.532, 17268, 1.044937),
    (16.561, 16901, 1.089993), (16.59, 16553, 1.126355), (16.618, 16222, 1.154554), (16.645, 15903, 1.174332), (16.672, 15594, 1.187153),
    (16.699, 15293, 1.19357), (16.727, 14998, 1.193531), (16.754, 14708, 1.188422), (16.781, 14421, 1.178711), (16.81, 14137, 1.164997),
    (16.838, 13855, 1.148381), (16.867, 13574, 1.129563), (16.897, 13293, 1.109388), (16.927, 13013, 1.088528), (16.958, 12734, 1.068007),
    (16.99, 12456, 1.048535), (17.023, 12180, 1.030869), (17.056, 11905, 1.015038), (17.09, 11633, 1.001412), (17.124, 11364, 0.990539),
    (17.159, 11098, 0.982479), (17.194, 10838, 0.976675), (17.23, 10582, 0.973341), (17.265, 10332, 0.972238), (17.301, 10088, 0.972573),
    (17.337, 9850, 0.974399), (17.373, 9618, 0.97689), (17.409, 9393, 0.980181), (17.446, 9173, 0.983585), (17.482, 8959, 0.987103),
    (17.518, 8751, 0.989751), (17.554, 8549, 0.992337), (17.591, 8351, 0.993695), (17.627, 8158, 0.994204), (17.664, 7969, 0.993581),
    (17.701, 7785, 0.991986), (17.739, 7604, 0.988458), (17.776, 7427, 0.983912), (17.814, 7253, 0.97781), (17.853, 7081, 0.970264),
    (17.892, 6912, 0.961487), (17.932, 6746, 0.951226), (17.972, 6582, 0.939765), (18.013, 6420, 0.926976), (18.055, 6259, 0.913019),
    (18.098, 6100, 0.898056), (18.142, 5942, 0.88224), (18.187, 5786, 0.865432), (18.233, 5630, 0.848253), (18.28, 5476, 0.830584),
    (18.329, 5322, 0.812636), (18.379, 5170, 0.79424), (18.43, 5019, 0.775772), (18.483, 4868, 0.757308), (18.538, 4719, 0.738622),
    (18.595, 4570, 0.720242), (18.654, 4423, 0.701866), (18.714, 4276, 0.683629), (18.777, 4131, 0.665434), (18.842, 3986, 0.647476),
    (18.91, 3843, 0.629846), (18.98, 3702, 0.612211), (19.052, 3561, 0.594791), (19.128, 3423, 0.577408), (19.206, 3285, 0.560171),
    (19.288, 3149, 0.543292), (19.373, 3015, 0.526433), (19.463, 2882, 0.509252), (19.556, 2751, 0.492341), (19.654, 2621, 0.475234),
    (19.756, 2494, 0.458264), (19.864, 2368, 0.441508), (19.978, 2244, 0.42455), (20.097, 2121, 0.407991), (20.224, 2001, 0.391724),
    (20.359, 1883, 0.375077), (20.501, 1767, 0.35849), (20.654, 1653, 0.342088), (20.816, 1542, 0.324884), (20.992, 1432, 0.30782),
    (21.182, 1325, 0.289276), (21.389, 1219, 0.270432), (21.616, 1115, 0.25115), (21.87, 1012, 0.231058), (22.155, 910, 0.209398),
    (22.481, 809, 0.187757), (22.862, 709, 0.162327), (23.333, 605, 0.12935), (23.978, 492, 0.098244), (25.667, 294, 0.00051),
)

#: The same value on every one of the hundred rows. Equal-area slicing,
#: confirmed against the reported total area to three parts in ten
#: million.
SLICE_AREA = 122321

#: Table 2, page 4, RASTER-READ. The report's own headline results.
REPORTED = {
    "retention_time": 16.696,
    "percent_area": 100.00,
    "mn": 3466,
    "mw": 8360,
    "mp": 15334,
    "polydispersity": 2.412342,
    "area": 12232104,
    "height": 75284,
    "mz": 12725,
    "mz_plus_1": 15577,
    # `Mv` is an EMPTY CELL in the source, beside populated ones. A blank
    # in a results table is an absence convention, and it is the first
    # this corpus has seen that is not a sentinel, a word, or a zero.
    "mv": None,
}

#: Verbatim column spellings from Table 2. The prose in the same document
#: says "Mw/Mn or polydispersity"; the table says `Polydispersity`. One
#: report, two vocabularies for one quantity, and neither is `PDI`.
REPORTED_SPELLINGS = ("Mn", "Mw", "MP", "Polydispersity", "Mz", "Mz+1", "Mv")

#: Three validity boundaries, of which exactly one is machine-readable
#: per row -- and that one reads `No` on every row of both distribution
#: tables. It tracks the elution window, not either mass limit.
CALIBRATED_RANGE_DA = (162, 14000)
COLUMN_EXCLUSION_LIMIT_DA = 20000
STATED_VALIDITY_LIMIT_DA = 14000
HIGHEST_STANDARD_ELUTES_AT = 16.8
THE_SENTENCE = ("any molecular weight information on the part of the polymer that exceeds "
                "14000 Dalton is not valid")

#: Named but not resolved. The report references the processing method
#: object that holds the baseline and peak limits and does not carry
#: them. A DIFFERENT ABSENCE CLASS from `not reported`: present by
#: reference in a system this artifact does not include.
PROCESSING_METHOD = "GPC_LOWMW_031921"
INTEGRATION_PARAMETERS_ARE = "named_by_reference_not_carried"

#: Acquisition and processing are separate events, nine hours forty
#: minutes apart, each with its own timestamp.
DATE_ACQUIRED = "2021-03-19T05:19:21-04:00"
DATE_PROCESSED = "2021-03-19T14:59:47-04:00"

#: The field exists and reads 1. Single injection established
#: structurally rather than inferred from a missing replicate block, so
#: the aggregate-row question is untestable here rather than answered.
INJECTION_NUMBER = 1
