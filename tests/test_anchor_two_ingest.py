"""The replicate anchor against the unchanged path, and the guard the
Anchor 1 misread showed was missing.

EVERY GUARD IN THIS REPOSITORY WATCHES CODE. A fixture is data, and the
Anchor 1 misread -- four fields transcribed into a document that states
none of them -- was caught by scoring a prediction, not by any check.
`test_an_anchor_fixture_states_only_what_its_source_states` is the check
that was missing.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_summary_export import (_IDENTITY_COLUMNS,  # noqa: E402
                                             GpcSummaryExportFetchError,
                                             GpcSummaryExportSourceAdapter)
from daf.extractors.gpc_report import GpcReportExtractor  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

ANCHOR = (REPO_ROOT / "tests" / "fixtures"
          / "gpc_summary_export_anchor_impact_r190048.csv")
RESULT = loads((REPO_ROOT / "architecture"
                / "anchor_two_ingest_result.yaml").read_text())

DECLARED = dict(source_name="regulations-gov-EPA-HQ-OPPT-2019-0271-0065",
                retrieved_at="2026-08-28T00:00:00Z",
                data_provenance="instrument_measurement", sample_kind="sample",
                method="sec_dmf_50c_polystyrene_calibrated")
UNITS = {"Mn": "g/mol", "Mw": "g/mol", "Mz": "g/mol", "Mw/Mn": "dimensionless",
         "% Poly <1000": "percent", "% Poly <500": "percent"}
KINDS = {"Mn": "measured", "Mw": "measured", "Mz": "measured", "Mw/Mn": "derived",
         "% Poly <1000": "derived", "% Poly <500": "derived"}

#: The obstacles a FAITHFUL transcription hits, in the order they fire.
#: Removing them is done in memory to measure what lies behind; none is
#: removed in the fixture.
CONTINUATION = (",2,23479", "PA191 (S190109),2,23479")
IDENTITY_SPELLING = ("Sample,Injection,", "Sample,Inj,")
PERCENT_SIGNS = (("8.4%", "8.4"), ("4.6%", "4.6"), ("1.1%", "1.1"), ("3.9%", "3.9"))


def _acquire(text, units=None, kinds=None):
    path = ANCHOR.with_name("tmp_anchor_two_variant.csv")
    path.write_text(text)
    pool = EvidencePool()
    try:
        _, failures = run_scout(
            GpcSummaryExportSourceAdapter(
                path=path, unit_by_column=units or UNITS,
                kind_by_column=kinds or KINDS, **DECLARED),
            GpcReportExtractor(), pool)
        records = {record.id: record for record in pool._records.values()}
        by_run = {}
        for observation in pool.all_observations():
            locator = str(records[observation.record_ids[0]].locator).split("#")[-1]
            by_run.setdefault(locator, []).append(
                (observation.content["property"], observation.content["value"]))
        return by_run, failures
    finally:
        path.unlink(missing_ok=True)


# =====================================================================
# The guard the Anchor 1 misread showed was missing
# =====================================================================

def test_an_anchor_fixture_states_only_what_its_source_states():
    """THE CHECK THAT WAS NOT THERE.

    Anchor 1's fixture invented `data_provenance`, `sample_kind`, `method`
    and `sample_id`, the ingest succeeded because of it, and nothing in
    the repository could have caught it -- every guard watches code and a
    fixture is data.

    A fixture declared A_GPC_ANCHOR must carry a transcription note that
    names its source and states what it does NOT contain. That is not a
    proof of faithfulness; it is the minimum that makes an invented field
    a visible claim rather than a silent one."""
    from test_corpus_anchor_preregistration import (A_GPC_ANCHOR,  # noqa: E402
                                                    FIXTURE_PROVENANCE)

    anchors = [name for name, kind in FIXTURE_PROVENANCE.items() if kind == A_GPC_ANCHOR]
    assert anchors, "no anchor is declared, so this guard is vacuous"
    for name in anchors:
        path = REPO_ROOT / "tests" / "fixtures" / name
        sidecar = path.with_suffix(".provenance.md")
        # THE NOTE MAY LIVE IN THE DOCUMENT ONLY WHERE THE ADAPTER IGNORES
        # IT. A JSON fixture can carry `_transcription_note`; a CSV cannot,
        # because every `#` line is carried into `conditions` as the
        # report's own header text -- a note written there would BECOME
        # document content, which is the misread this guard exists to
        # catch. So a sidecar is the general answer and an ignored key is
        # the special case.
        note = sidecar.read_text() if sidecar.exists() else path.read_text()
        assert "transcription" in note.lower(), (
            f"{name} has no transcription note, in the fixture or in {sidecar.name}. An anchor "
            "fixture is a CLAIM ABOUT A DOCUMENT and must say where it came from and what it "
            "does not contain."
        )
        assert "does not" in note.lower(), (
            f"{name}'s note does not say what the source omits, which is the half that catches "
            "an invented field"
        )
        if path.suffix == ".csv":
            assert sidecar.exists(), (
                f"{name} is a CSV, so its note must be a sidecar -- a `#` line would be read as "
                "the report's own header text"
            )


def test_the_faithful_fixture_keeps_every_obstacle_the_document_has():
    """The fixture is not repaired to make the path work."""
    text = ANCHOR.read_text()
    assert "\n,2,23479" in text, "the blank continuation cell must stay blank"
    assert "Sample,Injection," in text, "the report's own column spelling must stay"
    assert "8.4%" in text, "the percent signs are what the report prints"


# =====================================================================
# Three refusals, none of them about the aggregate
# =====================================================================

AS_QUANTITY = (dict(UNITS, **{"Injection": "dimensionless"}),
               dict(KINDS, **{"Injection": "measured"}))


def test_refusal_one_the_run_identifier_column_is_not_recognised():
    """FIRST, and before any row is read. The report's column is
    `Injection`; the literal says `Inj`; so a run number is a quantity and
    needs a unit it cannot have."""
    assert _IDENTITY_COLUMNS == ("Sample", "Inj")
    assert "Injection" not in _IDENTITY_COLUMNS
    with pytest.raises(GpcSummaryExportFetchError, match=r"no unit declared.*Injection"):
        _acquire(ANCHOR.read_text())


def test_refusal_two_the_blank_sample_cell_on_the_continuation_row():
    with pytest.raises(GpcSummaryExportFetchError, match="names no Sample"):
        _acquire(ANCHOR.read_text(), *AS_QUANTITY)


def test_refusal_three_the_aggregate_rows_have_no_injection_number():
    text = ANCHOR.read_text().replace(*CONTINUATION)
    with pytest.raises(GpcSummaryExportFetchError, match="'Injection' is blank"):
        _acquire(text, *AS_QUANTITY)


def test_refusal_four_the_percent_sign():
    text = ANCHOR.read_text().replace(*CONTINUATION).replace(*IDENTITY_SPELLING)
    with pytest.raises(GpcSummaryExportFetchError, match="not numeric"):
        _acquire(text)


def test_none_of_the_four_refusals_is_about_the_row_being_an_aggregate():
    """The point. Four correct refusals, every one incidental."""
    refusals = RESULT["the_four_refusals_in_the_order_they_actually_fire"]
    assert "the_order_was_recorded_wrong_first" in refusals
    for name, body in refusals.items():
        if name == "the_order_was_recorded_wrong_first":
            continue
        assert "code" in body, f"{name} names no code"
    assert "incidental" in RESULT["status"]


# =====================================================================
# What lies behind them
# =====================================================================

def _all_obstacles_removed():
    text = ANCHOR.read_text().replace(*CONTINUATION).replace(*IDENTITY_SPELLING)
    for sign, plain in PERCENT_SIGNS:
        text = text.replace(sign, plain)
    return text


def test_the_aggregate_rows_become_three_more_records_and_nine_more_observations():
    by_run, failures = _acquire(_all_obstacles_removed())
    assert failures == ()
    assert set(by_run) == {"PA191 (S190109)/1", "PA191 (S190109)/2",
                           "Average/row-2", "Standard Deviation/row-3", "% RSD/row-4"}
    assert sum(len(rows) for rows in by_run.values()) == 15

    every_mn = sorted(value for rows in by_run.values() for name, value in rows
                      if name == "Mn")
    assert every_mn == [8.4, 2107.0, 23479.0, 24969.0, 26459.0], (
        "a per-cent RSD, a standard deviation, an average and two measurements, in one column"
    )


def test_the_aggregates_lineage_is_positional_in_the_document_and_absent_from_the_pool():
    """The third of DAQ-2's questions, and the one with no repair
    available inside acquisition."""
    by_run, _ = _acquire(_all_obstacles_removed())
    average = by_run["Average/row-2"]
    injections = by_run["PA191 (S190109)/1"] + by_run["PA191 (S190109)/2"]
    assert average and injections
    assert "Average/row-2".startswith("Average"), "identity comes from the LABEL"
    lineage = RESULT["the_three_questions_answered"][
        "is_the_aggregates_lineage_to_the_two_injections_recoverable"]
    assert lineage.startswith("NO")
    assert "POSITIONAL IN THE DOCUMENT" in lineage


def test_the_declared_kind_declines_the_dispersity_so_the_mean_of_ratios_never_lands():
    """What the requirement DID catch -- and the per-column limit that
    makes it insufficient for the rest."""
    by_run, _ = _acquire(_all_obstacles_removed())
    assert all(name != "Mw/Mn" for rows in by_run.values() for name, _ in rows), (
        "the derived dispersity must not enter, so the Average row's 1.29 cannot reach a consumer"
    )
    caught = RESULT["what_the_declared_kind_requirement_did_catch"]
    assert "per COLUMN" in caught["and_what_it_did_not"]
    assert "no per-ROW channel" in caught["and_what_it_did_not"]


def test_the_two_adapters_differ_and_the_record_says_which_is_right():
    contrast = RESULT["the_contrast_with_anchor_one_is_the_result"]
    assert "no caller-declaration channel" in contrast["anchor_one"]
    assert "caller declarations" in contrast["anchor_two"]
    assert "never propagated back" in contrast["what_that_says_about_the_contract"]
