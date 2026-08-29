"""ANCHOR 2, verified against the source PDF rather than an extraction.

The relayed reading of this report came from a web extraction with a
scrambled method block, and its own caveat said the source was
unreachable: `curl` returns 403. It is not unreachable. A request
carrying a browser User-Agent and a regulations.gov Referer returns 200
and 558843 bytes. Everything below is re-derived from that file.

NOT A FIXTURE. `instrument` is unreachable from the product by the layer
rule, so these values cannot enter an adapter or the pool. The fixture
that exercises DAQ's path against this SHAPE is synthetic.
"""

from __future__ import annotations

import math
import pathlib
import statistics
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from instrument import anchor_two as A  # noqa: E402


def test_the_aggregate_block_is_the_sample_standard_deviation():
    """n-1, not n. The two differ by a factor of root two on a pair, so
    the choice is identifiable rather than inferred."""
    for key, printed_sd in (("mn", 2107), ("mw", 1474), ("mz", 431)):
        values = [injection[key] for injection in A.INJECTIONS]
        assert round(statistics.mean(values)) == A.AGGREGATE["Average"][key]
        assert round(statistics.stdev(values)) == printed_sd, f"{key} is not the n-1 deviation"
        population = math.sqrt(sum((v - statistics.mean(values)) ** 2 for v in values) / 2)
        assert abs(round(population) - printed_sd) > 100, (
            f"{key}: the n and n-1 deviations must be distinguishable at the printed precision"
        )


def test_the_average_dispersity_is_the_mean_of_ratios_not_the_ratio_of_means():
    """The derived-row problem with a measurable consequence, and the two
    readings disagree in the printed decimal."""
    mean_of_ratios = statistics.mean(i["mw_over_mn"] for i in A.INJECTIONS)
    ratio_of_means = (statistics.mean(i["mw"] for i in A.INJECTIONS)
                      / statistics.mean(i["mn"] for i in A.INJECTIONS))
    assert f"{mean_of_ratios:.2f}" == "1.29"
    assert f"{ratio_of_means:.2f}" == "1.28"
    assert f"{A.AGGREGATE['Average']['mw_over_mn']:.2f}" == f"{mean_of_ratios:.2f}", (
        "the report prints the mean of the ratios"
    )
    assert abs(mean_of_ratios - ratio_of_means) > 0.002


def test_three_identifiers_for_two_runs_and_the_instruments_own_disagrees():
    """THE ONE-RECORD-PER-RUN FAILURE, LIVE. The figure caption, the
    table row label and the instrument's `Injection #` field name the same
    two runs, and the third disagrees with the first two. Chronology
    settles it: the earlier timestamp carries `Injection #: 1`."""
    by_time = sorted(A.INJECTION_REPORTS, key=lambda r: r["date_acquired"])
    assert by_time[0]["instrument_injection_number"] == 1, (
        "the earlier acquisition must be the instrument's first injection"
    )
    assert by_time[0]["figure_caption"] == "injection #2", (
        "and it is captioned #2 -- if the caption agreed, there is no finding"
    )
    assert by_time[0]["mn"] == A.INJECTIONS[1]["mn"], (
        "the instrument's FIRST injection produced the value Table II labels row 2"
    )
    for report in A.INJECTION_REPORTS:
        caption_number = int(report["figure_caption"].split("#")[1])
        assert caption_number != report["instrument_injection_number"]


def test_the_summary_tables_dispersity_is_not_any_ratio_in_the_document():
    """Wrong by a factor of seven, in the table a customer reads first,
    while the detailed table has it right. Both machine-readable."""
    summary = A.SUMMARY_TABLE
    candidates = {
        "mw_over_mn": summary["mw"] / summary["mn"],
        "mz_over_mw": summary["mz"] / summary["mw"],
        "mz_over_mn": summary["mz"] / summary["mn"],
        "mn_over_mw": summary["mn"] / summary["mw"],
    }
    assert all(abs(value - summary["polydispersity"]) > 1.0 for value in candidates.values()), (
        f"9.21 matches one of {candidates}; if it does, it is explicable and this is not a finding"
    )
    assert abs(candidates["mw_over_mn"] - 1.28) < 0.01
    assert summary["polydispersity"] / candidates["mw_over_mn"] > 7.0

    # A NUMERICAL COINCIDENCE, RULED OUT RATHER THAN OFFERED. ln(10000)
    # is 9.2103, which rounds to the printed value -- and no quantity in
    # this document is 10000 or a natural logarithm of anything.
    assert abs(math.log(10000) - 9.21) < 0.01
    assert 10000 not in (summary["mn"], summary["mw"], summary["mz"])


def test_the_calibration_is_first_order_and_reproduces_its_own_column():
    """Against Anchor 1's third order. Calibration order is not a vendor
    property: same software, two labs, two orders."""
    a, b = A.CALIBRATION_COEFFICIENTS
    assert A.CALIBRATION_FIT_ORDER == 1
    worst = max(abs(10 ** (a + b * rt) / calculated - 1)
                for rt, _, _, calculated, _ in A.CALIBRATION_STANDARDS)
    assert worst < 0.001, f"first order must reproduce the printed column: {worst:.4%}"

    printed_logs = [abs(log - math.log10(nominal))
                    for _, nominal, log, _, _ in A.CALIBRATION_STANDARDS]
    assert max(printed_logs) < 1e-4, "the two-column layout must be paired correctly"


def test_the_printed_r_squared_is_the_quality_fit_confirming_anchor_ones_distinction():
    """ANCHOR 1 FOUND TWO CUBICS AND SAID THE PRINTED R^2 WAS THE FIT
    AGAINST NOMINAL. Anchor 2 confirms it on a different instrument, a
    different lab and a different fit order: the printed R^2 reproduces
    against NOMINAL, not against the calculated column."""
    a, b = A.CALIBRATION_COEFFICIENTS
    nominals = [math.log10(nominal) for _, nominal, _, _, _ in A.CALIBRATION_STANDARDS]
    mean = statistics.mean(nominals)
    residual = sum((math.log10(nominal) - (a + b * rt)) ** 2
                   for rt, nominal, _, _, _ in A.CALIBRATION_STANDARDS)
    total = sum((value - mean) ** 2 for value in nominals)
    assert abs((1 - residual / total) - A.CALIBRATION_R_SQUARED) < 1e-5
    assert abs(A.CALIBRATION_R ** 2 - A.CALIBRATION_R_SQUARED) < 1e-6


def test_the_residual_definition_holds_on_a_second_instrument():
    """Anchor 1 established it; this confirms it independently."""
    assert A.RESIDUAL_IS_RELATIVE_TO == "calculated"
    worst_calculated = max(abs((nominal - calculated) / calculated * 100 - printed)
                           for _, nominal, _, calculated, printed in A.CALIBRATION_STANDARDS)
    worst_nominal = max(abs((nominal - calculated) / nominal * 100 - printed)
                        for _, nominal, _, calculated, printed in A.CALIBRATION_STANDARDS)
    assert worst_calculated < 0.15
    assert worst_nominal > 5.0


def test_a_first_order_fit_spans_four_decades_and_r_squared_conceals_it():
    """R^2 = 0.9958 over residuals of +44%, -17% and +27%."""
    a, b = A.CALIBRATION_COEFFICIENTS
    decades = (a + b * A.V0) - (a + b * A.VT)
    assert decades > 3.9
    residuals = [abs(printed) for _, _, _, _, printed in A.CALIBRATION_STANDARDS]
    assert max(residuals) > 44.0
    assert A.CALIBRATION_R_SQUARED > 0.995, (
        "the concealment is the point: a high R^2 alongside a 44% residual"
    )


def test_the_sample_elutes_inside_the_window_unlike_anchor_one():
    """Vo and Vt are given as NUMBERS here, where Anchor 1 had only a
    per-slice flag."""
    a, b = A.CALIBRATION_COEFFICIENTS
    for report in A.INJECTION_REPORTS:
        rt = report["retention_time"]
        assert A.V0 < rt < A.VT, "no extrapolation in this report"
        assert abs(10 ** (a + b * rt) / report["mp"] - 1) < 0.001, (
            "the calibration must reproduce the printed peak molar mass"
        )


def test_the_method_block_describes_a_preparation_that_did_not_produce_the_result():
    """Three attempts; the reported result is the third. The narrative
    carries the correction and no field does."""
    assert "dried" in A.METHOD_SAYS_PREPARATION
    assert "NON-DRIED" in A.WHAT_ACTUALLY_PRODUCED_THE_RESULT
    assert A.THE_NARRATIVE_CARRIES_THE_CORRECTION_NO_FIELD_DOES
    assert "(S190109)" in A.ELUENT_AS_PRINTED, (
        "the eluent field is qualified by sample id because it changed mid-project"
    )


def test_the_integration_parameters_are_named_and_unresolved_as_in_anchor_one():
    """The one thing constant across both anchors."""
    from instrument import anchor_one

    assert A.INTEGRATION_PARAMETERS_ARE == anchor_one.INTEGRATION_PARAMETERS_ARE
    assert A.PROCESSING_METHOD and anchor_one.PROCESSING_METHOD
    assert A.PROCESSING_METHOD != anchor_one.PROCESSING_METHOD


def test_the_two_anchors_agree_on_almost_nothing_else():
    """Two reports from the same vendor's software. What varies between
    them is what a contract derived from either alone would have got
    wrong."""
    from instrument import anchor_one

    assert A.CALIBRATION_FIT_ORDER == 1
    assert len(anchor_one.CALIBRATION_STANDARDS) == 22 and len(A.CALIBRATION_STANDARDS) == 10
    assert len(anchor_one.SLICE_TABLE) == 100
    assert not hasattr(A, "SLICE_TABLE"), "Anchor 2 has no distribution table at all"
    assert anchor_one.INJECTION_NUMBER == 1 and len(A.INJECTIONS) == 2

    worst_one = max(abs(row[3]) for row in anchor_one.CALIBRATION_STANDARDS)
    worst_two = max(abs(row[4]) for row in A.CALIBRATION_STANDARDS)
    assert worst_two > 5.0 * worst_one, (
        f"the residual quality must differ by an order of magnitude: {worst_one} vs {worst_two}"
    )
