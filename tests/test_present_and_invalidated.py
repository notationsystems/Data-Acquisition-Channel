"""A value that is present, flagged valid, and invalidated by a sentence
in the same document.

Every claim in architecture/present_and_invalidated.yaml is executed
here against the real acquisition path. Nothing in this module changes
the adapter, the extractor or a gate: the point is what the built path
does, not what a modified one could.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_summary_export import (CONDITIONS_AS_REPORTED,  # noqa: E402
                                             GpcSummaryExportFetchError,
                                             GpcSummaryExportSourceAdapter)
from daf.extractors.gpc_report import GpcReportExtractor  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.admissibility import (no_context_free_property,  # noqa: E402
                                   quantity_is_typed)
from science.table import ABSENCE_REASONS, observation_is_table_alignable  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

RECORD_TEXT = (REPO_ROOT / "architecture" / "present_and_invalidated.yaml").read_text()
RECORD = loads(RECORD_TEXT)
FIXTURE = (REPO_ROOT / "tests" / "fixtures"
           / "gpc_summary_export_synthetic_flag_says_valid.csv")

#: The limit the fixture's own header states, read from the file rather
#: than retyped -- so a fixture edited without editing this module fails
#: rather than quietly measuring something else.
STATED_LIMIT = 12000.0
BENIGN_FLAG = "No"

DECLARED = dict(source_name="synthetic-vendor-sec", retrieved_at="2026-08-27T00:00:00Z",
                data_provenance="fabricated_fixture", sample_kind="sample",
                method="sec_thf_40c_polystyrene_calibrated",
                unit_by_column={"Mw": "g/mol"}, kind_by_column={"Mw": "measured"},
                flag_by_column={"Mw": "Mw_OutsideWindow"})


def acquire(**over):
    pool = EvidencePool()
    adapter = GpcSummaryExportSourceAdapter(
        path=FIXTURE, **{**DECLARED, "measured_flags": (BENIGN_FLAG,), **over})
    _, failures = run_scout(adapter, GpcReportExtractor(), pool)
    return sorted(pool.all_observations(), key=lambda o: o.id), failures


def test_the_fixture_states_its_own_limit_and_exceeds_it():
    """The domain, asserted before the finding. A fixture whose rows all
    sat below the limit would produce the same green and mean nothing."""
    text = FIXTURE.read_text()
    assert f"above {STATED_LIMIT:.0f} g/mol" in text, (
        "the limit this module measures against must be the one the fixture states"
    )
    assert "FABRICATED" in text and "No instrument produced them" in text
    body = [line for line in text.splitlines() if not line.startswith("#")]
    values = [float(line.split(",")[2]) for line in body[1:] if line]
    assert len(values) == 10
    assert len([v for v in values if v > STATED_LIMIT]) == 2, (
        "two of ten must exceed the stated limit, or there is nothing for a gate to miss"
    )
    assert all(line.split(",")[3] == BENIGN_FLAG for line in body[1:] if line), (
        "and the per-row flag must read benign on EVERY row, including those two -- that is "
        "the structure this measures"
    )


# =====================================================================
# Disposition A: the flag is believed
# =====================================================================

def test_every_row_is_admitted_with_no_reason_including_the_invalid_ones():
    """THE FINDING. Ten observations, no failure, no admissibility reason,
    and the two values the document invalidates are indistinguishable
    from the eight it does not."""
    observations, failures = acquire()
    assert failures == ()
    assert len(observations) == 10

    values = sorted(o.content["value"] for o in observations)
    invalid = [v for v in values if v > STATED_LIMIT]
    assert len(invalid) == 2

    for observation in observations:
        for gate in (no_context_free_property, quantity_is_typed,
                     observation_is_table_alignable):
            verdict = gate(observation.content)
            assert not verdict.reasons, (
                f"{gate.__name__} gave reasons {verdict.reasons} -- if a gate does catch this, "
                "the record's central claim is false and must be rewritten"
            )

    fields = {key for observation in observations for key in observation.content}
    above = [o for o in observations if o.content["value"] > STATED_LIMIT]
    below = [o for o in observations if o.content["value"] <= STATED_LIMIT]
    for key in fields - {"value"}:
        assert {o.content.get(key) for o in above} <= {o.content.get(key) for o in below}, (
            f"{key} distinguishes the invalid rows from the valid ones, so the substrate DOES "
            "carry the distinction and this record is wrong about its own subject"
        )


def test_the_invalidating_sentence_is_carried_into_the_observation_and_still_unreachable():
    """STRONGER THAN THE PREDICTION IT CAME FROM. The prediction said the
    context is present in the DOCUMENT and unreachable from the data.
    Measured, it is present in the OBSERVATION."""
    observations, _ = acquire()
    for observation in observations:
        conditions = observation.content["conditions"]
        carried = conditions[CONDITIONS_AS_REPORTED]
        assert "not valid" in carried and f"{STATED_LIMIT:.0f} g/mol" in carried, (
            "the sentence that invalidates the value must travel WITH the value, or the finding "
            "is ordinary information loss rather than unreachability"
        )

    invalid = next(o for o in observations if o.content["value"] > STATED_LIMIT)
    assert not no_context_free_property(invalid.content).reasons, (
        "and the gate whose subject is context passes on an observation whose context says the "
        "value is not valid. Its bar is that conditions EXIST."
    )


# =====================================================================
# Disposition B: the flag is mapped onto an absence
# =====================================================================

def test_mapping_the_benign_flag_onto_an_absence_discards_the_valid_rows_too():
    """THE OTHER AVAILABLE REPRESENTATION, executed. The flag channel is
    keyed on the FLAG VALUE, and every row carries the same flag, so it
    cannot partition rows by their VALUES."""
    observations, failures = acquire(measured_flags=(),
                                     absence_reason_by_flag={BENIGN_FLAG: "above_range"})
    assert failures == ()
    assert len(observations) == 10
    assert all(o.content["value"] is None for o in observations), (
        "every value is discarded, including the eight the document does not invalidate"
    )
    assert {o.content["value_absence"] for o in observations} == {"above_range"}


def test_the_two_dispositions_are_the_only_ones_the_channel_offers():
    """DETECTOR PROOF that the silence is specific rather than a dead
    path. The same adapter DOES refuse an unmapped flag and DOES carry a
    reasoned absence -- so the channel is live, and what it cannot do is
    key on a value."""
    with pytest.raises(GpcSummaryExportFetchError, match="no absence reason is declared"):
        acquire(measured_flags=("OK",))

    reasoned = REPO_ROOT / "tests" / "fixtures" / "gpc_summary_export_synthetic_absences.csv"
    pool = EvidencePool()
    adapter = GpcSummaryExportSourceAdapter(
        path=reasoned, source_name="synthetic-vendor-sec",
        retrieved_at="2026-08-27T00:00:00Z", data_provenance="fabricated_fixture",
        sample_kind="sample", method="sec_thf_35c_polystyrene_calibrated",
        unit_by_column={"Mw": "g/mol", "Mn": "g/mol"},
        kind_by_column={"Mw": "measured", "Mn": "measured"},
        flag_by_column={"Mw": "Mw_Flag", "Mn": "Mn_Flag"}, measured_flags=("OK",),
        absence_reason_by_flag={"DETECTOR_SATURATED": "lost_in_acquisition",
                                "RUN_FAILED": "lost_in_acquisition",
                                "MISSING": "not_measured",
                                "BELOW_QUANT_LIMIT": "below_detection"})
    run_scout(adapter, GpcReportExtractor(), pool)
    carried = {o.content.get("value_absence") for o in pool.all_observations()}
    assert carried & set(ABSENCE_REASONS), (
        "the absence channel must demonstrably work on a fixture that uses it, or `it cannot "
        "express this state` is indistinguishable from `it does not work`"
    )


# =====================================================================
# The record's own claims
# =====================================================================

def test_the_record_refuses_the_repairs_rather_than_deferring_them():
    """A record proposing a fix it did not build is a plan. This one says
    why each available fix is wrong."""
    refused = RECORD["what_is_deliberately_not_built"]
    assert "The value is present" in refused["a_new_absence_reason"]
    assert "category error" in refused["a_new_absence_reason"]
    assert "would be answering a question the pair has not been asked" in \
        refused["a_validity_qualifier_on_a_present_value"]
    assert "a parser wearing a gate's name" in refused["a_gate_that_reads_prose"]


def test_the_record_does_not_call_the_acquisition_path_defective():
    disclaimer = RECORD["what_this_record_does_not_claim"]
    assert "not" in disclaimer and "defective" in disclaimer
    assert "refuses to invent what it does not" in disclaimer


def test_the_record_says_what_it_took_from_the_anchor_and_what_it_did_not():
    header = " ".join(line.lstrip("#").strip()
                      for line in RECORD_TEXT.split("extends:")[0].splitlines())
    assert "reproduces that SHAPE and nothing else" in header
    assert "no transcribed value" in header
    assert "the fixture is still synthetic" in header, (
        "the anchor's tables have since been recovered; this record must say that its own "
        "fixture did not change with them"
    )
