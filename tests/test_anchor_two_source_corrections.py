"""Three corrections, verified from the source rather than accepted.

The arithmetic is re-derived here. The geometry is not -- the source PDF
is not in this repository, so the measurements taken from it are recorded
with what they rest on, and the parts this session could not close are
marked rather than smoothed over.
"""

from __future__ import annotations

import pathlib
import statistics
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402
from instrument import anchor_two as A  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture"
                / "anchor_two_source_corrections.yaml").read_text())
PRINTED_RATIOS = [injection["mw_over_mn"] for injection in A.INJECTIONS]


def test_only_the_mean_of_the_PRINTED_ratios_reproduces_the_aggregate():
    """CORRECTION ONE, re-derived. Three candidate computations, one
    match -- and the two that fail differ from the report in the printed
    decimal, so the discrimination is real rather than a rounding
    coincidence."""
    full = [injection["mw"] / injection["mn"] for injection in A.INJECTIONS]
    printed_mean = statistics.mean(PRINTED_RATIOS)
    full_mean = statistics.mean(full)
    ratio_of_means = (statistics.mean(i["mw"] for i in A.INJECTIONS)
                      / statistics.mean(i["mn"] for i in A.INJECTIONS))

    assert f"{printed_mean:.2f}" == "1.29" == f"{A.AGGREGATE['Average']['mw_over_mn']:.2f}"
    assert f"{full_mean:.2f}" == "1.28"
    assert f"{ratio_of_means:.2f}" == "1.28"
    assert full_mean != printed_mean, "if these agreed the finding would be untestable"


def test_the_percent_rsd_row_agrees_independently():
    """The second field. Same two numbers, a different statistic, and it
    picks the same computation -- which is what makes this a measurement
    of the report's method rather than a fit to one number."""
    full = [injection["mw"] / injection["mn"] for injection in A.INJECTIONS]

    def rsd(values):
        return statistics.stdev(values) / statistics.mean(values) * 100

    assert f"{rsd(PRINTED_RATIOS):.1f}" == "3.9"
    assert f"{rsd(full):.1f}" == "3.8"
    assert A.AGGREGATE["% RSD"]["mw_over_mn"] == "3.9%"
    assert f"{statistics.stdev(PRINTED_RATIOS):.2f}" == "0.05"


def test_the_record_states_the_stronger_form_rather_than_the_number():
    correction = RECORD["correction_one_the_aggregate_is_computed_from_the_DISPLAYED_values"]
    assert "PROJECTION of the measurements" in correction["the_stronger_statement"]
    assert "bounded by the display precision" in correction["the_stronger_statement"]
    assert "rounding step that appears nowhere in the record" in \
        correction["what_it_means_for_a_consumer"]


def test_the_merge_correction_names_what_settles_it_and_what_does_not():
    """CORRECTION TWO. A text layer records absence and cannot
    distinguish absence from span, so the token counts do not settle it.
    The centred baseline does, and the drawn rule corroborates without
    closing."""
    correction = RECORD["correction_two_the_sample_cell_is_merged_not_blank"]
    assert "cannot distinguish absence from span" in \
        correction["what_the_text_layer_shows_and_why_it_is_not_enough"]
    assert "vertically CENTRED across both rows" in correction["what_settles_it"]
    assert "NO vertical rules" in correction["the_drawn_rules_agree_in_part"]
    assert correction["what_is_NOT_established"].startswith("WHICH boundary")
    assert "did not reconcile them" in correction["what_is_NOT_established"], (
        "the unclosed half must say why it is unclosed, not merely that it is"
    )


def test_the_merge_revises_two_earlier_findings_rather_than_adding_one():
    correction = RECORD["correction_two_the_sample_cell_is_merged_not_blank"]
    assert "the transcription lost structure the document had" in correction["what_it_revises"]
    assert "TOPOLOGICAL" in correction["and_it_revises_the_lineage_finding"]
    assert "row order is a shadow of that" in correction["and_it_revises_the_lineage_finding"]

    earlier = loads((REPO_ROOT / "architecture"
                     / "anchor_two_ingest_result.yaml").read_text())
    assert "POSITIONAL IN THE DOCUMENT" in earlier["the_three_questions_answered"][
        "is_the_aggregates_lineage_to_the_two_injections_recoverable"], (
        "the earlier record must still say what it said; a revision that edits the original "
        "leaves nothing to revise"
    )


def test_the_fixture_still_keeps_the_blank_and_says_why():
    """The decision the correction did NOT change, and the reason it
    changed the NAME of the interpretation rather than the interpretation."""
    decision = RECORD["what_the_fixture_does_about_the_merge"]
    assert "KEEPS the blank" in decision["the_decision"]
    assert "CSV cannot express geometry" in decision["why_not_fill_it"]
    assert "measured the need rather than designed the answer" in \
        decision["what_would_actually_carry_it"]

    sidecar = (REPO_ROOT / "tests" / "fixtures"
               / "gpc_summary_export_anchor_impact_r190048.provenance.md")
    assert "merged" in sidecar.read_text().lower(), (
        "the sidecar must now say the source merges the cell, not that it leaves it blank"
    )


def test_the_403_correction_had_already_been_measured_here():
    correction = RECORD["correction_three_the_403_was_a_user_agent_block"]
    assert "ALREADY MEASURED HERE" in correction["verdict"]
    assert "stale rather than wrong" in correction["the_check_that_closes_it"]


def test_daq_three_is_named_as_not_done_and_why():
    """A record that listed corrections and left the next item implicit
    would read as though the phase were finished."""
    outstanding = RECORD["what_is_not_done"]
    assert outstanding.startswith("DAQ-3")
    assert "which identifier the extractor takes" in outstanding
    assert "a CSV cannot faithfully be" in outstanding
