"""DAQ-3: three identifiers, two runs, and nothing compares them."""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_summary_export import (_IDENTITY_COLUMNS,  # noqa: E402
                                             GpcSummaryExportSourceAdapter)
from daf.extractors.gpc_report import GpcReportExtractor  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

FIXTURE = (REPO_ROOT / "tests" / "fixtures"
           / "gpc_summary_export_anchor_impact_r190048_identifiers.csv")
RECORD = loads((REPO_ROOT / "architecture"
                / "anchor_three_identifiers.yaml").read_text())


def _acquire():
    pool = EvidencePool()
    _, failures = run_scout(GpcSummaryExportSourceAdapter(
        path=FIXTURE, source_name="regulations-gov",
        retrieved_at="2026-08-30T00:00:00Z",
        data_provenance="instrument_measurement", sample_kind="sample",
        method="sec_dmf_50c",
        unit_by_column={"Mn": "g/mol", "Mw": "g/mol", "Mz": "g/mol",
                        "InstrumentInjection": "dimensionless",
                        "AcquiredAtMinutes": "min"},
        kind_by_column={"Mn": "measured", "Mw": "measured", "Mz": "measured",
                        "InstrumentInjection": "measured",
                        "AcquiredAtMinutes": "measured"}),
        GpcReportExtractor(), pool)
    records = {record.id: record for record in pool._records.values()}
    runs = {}
    for observation in pool.all_observations():
        locator = str(records[observation.record_ids[0]].locator).split("#")[-1]
        runs.setdefault(locator, {})[observation.content["property"]] = \
            observation.content["value"]
    return runs, failures


def test_run_identity_comes_from_the_table_label_and_not_the_instrument():
    runs, failures = _acquire()
    assert failures == ()
    assert set(runs) == {"PA191 (S190109)/1", "PA191 (S190109)/2"}
    assert runs["PA191 (S190109)/1"]["Mn"] == 26459.0, (
        "Table II labels Mn 26459 as injection 1, and that is the identity DAQ took"
    )


def test_the_contradiction_is_inside_each_record_and_nothing_compares_it():
    """THE FINDING. The Record's identity says run 1; a measurement the
    same Record holds says the instrument called it 2."""
    runs, _ = _acquire()
    for locator, values in runs.items():
        label = float(locator.rsplit("/", 1)[1])
        assert values["InstrumentInjection"] != label, (
            "the two identifiers must disagree in this document, or the fixture no longer "
            "carries the case DAQ-3 is about"
        )
    earlier = runs["PA191 (S190109)/2"]["AcquiredAtMinutes"]
    later = runs["PA191 (S190109)/1"]["AcquiredAtMinutes"]
    assert earlier < later, "chronology must agree with the instrument's numbering"
    assert runs["PA191 (S190109)/2"]["InstrumentInjection"] == 1.0


def test_the_substrate_has_no_channel_for_a_second_identifier():
    """Why they cannot be compared: only one of the three is an
    identifier and the others are measurements."""
    assert _IDENTITY_COLUMNS == ("Sample", "Inj")
    assert len(_IDENTITY_COLUMNS) == 2, (
        "one name for the sample and one for the run; a document offering a second run "
        "identifier has nowhere to put it that is not a quantity"
    )
    runs, _ = _acquire()
    assert "InstrumentInjection" in runs["PA191 (S190109)/1"], (
        "it entered as a measured quantity, which is the measurement DAQ-3 asked for"
    )


def test_the_fixture_names_its_interpretations_rather_than_hiding_them():
    sidecar = FIXTURE.with_suffix(".provenance.md")
    text = sidecar.read_text()
    assert "STATED INTERPRETATIONS" in text
    for interpretation in ("merged Sample cell is flattened",
                           "reduced to minutes past midnight",
                           "declared as QUANTITIES"):
        assert interpretation in text, f"the sidecar does not name: {interpretation}"
    forced = RECORD["the_fixture_decision"]["why_the_third_is_not_a_workaround"]
    assert "what the substrate forces" in forced, (
        "the third interpretation is the finding: the substrate leaves no other channel"
    )


def test_the_record_declines_the_two_other_options_with_reasons():
    declined = RECORD["the_fixture_decision"]["what_was_declined_and_why"]
    assert "invents a representation from one document" in declined["a_format_carrying_cell_extent"]
    assert "changing the subject" in declined["a_different_ingest_path_against_the_rendered_document"]


def test_the_record_does_not_claim_the_extractor_chose_wrongly():
    disclaimer = RECORD["what_is_not_claimed"]
    assert "not that the extractor chose wrongly" in disclaimer
    assert "the report disagrees with itself" in disclaimer
    assert "wrong, and silently" in disclaimer
