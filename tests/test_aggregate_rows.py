"""B.2.4, EXECUTED. What DAQ's acquisition path does with an aggregate
block.

The question was pre-registered in architecture/corpus_anchor_preregistration.yaml
before any anchor existed and was UNTESTABLE until a replicate report
arrived: does a table of injections followed by Average / Standard
Deviation / % RSD enter the pool as measurements?

The pre-registration's sharper form asked WHERE it breaks, not whether.
The answer is that it does not break.

THE FIXTURE IS SYNTHETIC. It carries the SHAPE a real replicate report
was measured to have; no value is transcribed from one.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_summary_export import (GpcSummaryExportFetchError,  # noqa: E402
                                             GpcSummaryExportSourceAdapter)
from daf.extractors.gpc_report import GpcReportExtractor  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.admissibility import (no_context_free_property,  # noqa: E402
                                   quantity_is_typed)
from science.table import observation_is_table_alignable  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

FIXTURE = (REPO_ROOT / "tests" / "fixtures"
           / "gpc_summary_export_synthetic_aggregate_block.csv")
PREREG = loads((REPO_ROOT / "architecture"
                / "corpus_anchor_preregistration.yaml").read_text())

DECLARED = dict(source_name="synthetic-vendor-sec", retrieved_at="2026-08-27T00:00:00Z",
                data_provenance="fabricated_fixture", sample_kind="sample",
                method="sec_dmf_50c_polystyrene_calibrated",
                unit_by_column={"Mn": "g/mol", "Mw": "g/mol"},
                kind_by_column={"Mn": "measured", "Mw": "measured"})


def acquire(path=FIXTURE, **over):
    pool = EvidencePool()
    adapter = GpcSummaryExportSourceAdapter(path=path, **{**DECLARED, **over})
    _, failures = run_scout(adapter, GpcReportExtractor(), pool)
    return sorted(pool.all_observations(), key=lambda o: o.id), failures


def test_the_fixture_carries_two_injections_and_a_three_row_aggregate_block():
    """The domain, before the finding."""
    body = [line for line in FIXTURE.read_text().splitlines() if not line.startswith("#")]
    labels = [line.split(",")[1] for line in body[1:] if line]
    assert labels == ["1", "2", "Average", "Standard Deviation", "% RSD"]
    assert "FABRICATED" in FIXTURE.read_text()


def test_the_aggregate_rows_enter_the_pool_as_measurements():
    """THE ANSWER, and it is worse than the pre-registration predicted.

    Two injections carry four measured values. TEN observations enter,
    with no acquisition failure and no admissibility reason. A standard
    deviation of 2121 g/mol is in the pool as a measured Mn, in the same
    column as 26000, and a per-cent RSD of 8.7 is in the pool as a
    measured Mn of 8.7 g/mol."""
    observations, failures = acquire()
    assert failures == ()
    assert len(observations) == 10, "four real values and six derived ones"

    values = sorted(o.content["value"] for o in observations
                    if o.content["property"] == "Mn")
    assert values == [8.7, 2121.0, 23000.0, 24500.0, 26000.0]

    for observation in observations:
        for gate in (no_context_free_property, quantity_is_typed,
                     observation_is_table_alignable):
            assert not gate(observation.content).reasons, (
                f"{gate.__name__} caught it; the finding would then be false"
            )
        assert observation.content.get("value_absence") is None


def test_nothing_distinguishes_a_standard_deviation_from_a_measurement():
    """Not the kind, not a flag, not a field. The adapter's declared kind
    is per COLUMN and an aggregate block is a set of ROWS."""
    observations, _ = acquire()
    deviation = next(o for o in observations if o.content["value"] == 2121.0)
    measurement = next(o for o in observations if o.content["value"] == 26000.0)
    differing = {key for key in set(deviation.content) | set(measurement.content)
                 if deviation.content.get(key) != measurement.content.get(key)}
    assert differing == {"value"}, (
        f"only the value differs; {differing} would mean the substrate does carry the "
        "distinction and this finding is wrong"
    )


def test_an_mn_of_eight_point_seven_grams_per_mole_is_admissible():
    """No gate here judges plausibility, and this is the sharpest form of
    that: a per-cent RSD admitted as a molar mass three orders of
    magnitude below any monomer."""
    observations, _ = acquire()
    rsd = next(o for o in observations if o.content["value"] == 8.7)
    assert rsd.content["unit"] == "g/mol"
    assert not quantity_is_typed(rsd.content).reasons


def test_the_only_thing_that_ever_refuses_is_a_percent_sign():
    """DETECTOR PROOF, and it is what makes the result a finding rather
    than a near miss. A real report prints `8.4%`. That is refused -- for
    not being numeric, not for being derived. Strip the character and the
    row walks through."""
    with_sign = FIXTURE.with_name("tmp_percent_sign.csv")
    with_sign.write_text(FIXTURE.read_text().replace(",8.7,4.4", ",8.7%,4.4%"))
    try:
        with pytest.raises(GpcSummaryExportFetchError, match="is not numeric"):
            acquire(path=with_sign)
    finally:
        with_sign.unlink()

    observations, failures = acquire()
    assert failures == () and len(observations) == 10, (
        "without the character the same row is a measurement, so the refusal is an accident "
        "of formatting and not a judgement about the row"
    )


def test_the_instruments_own_run_identifier_cannot_be_carried_as_an_identifier():
    """THE SECOND FINDING, and it is the one-Record-per-run precondition
    meeting a real report.

    A replicate report was measured to carry THREE identifiers for two
    runs -- a figure caption, a table row label, and the instrument's own
    `Injection #` field -- with the third disagreeing with the first two.
    DAQ builds run identity from the table's label. Handed the
    instrument's field as a second column, the adapter demands a UNIT for
    it: the identity vocabulary is a two-element literal, so the one
    field that would resolve the disagreement can only enter as a
    measured quantity or not at all."""
    from daf.adapters.gpc_summary_export import _IDENTITY_COLUMNS

    assert _IDENTITY_COLUMNS == ("Sample", "Inj"), (
        "a literal, which is why a third identifier has nowhere to go"
    )

    two_identities = FIXTURE.with_name("tmp_two_identities.csv")
    text = FIXTURE.read_text().replace("Sample,Inj,Mn,Mw", "Sample,Inj,InstrumentInj,Mn,Mw")
    text = text.replace("SYN-0001,1,26000", "SYN-0001,1,2,26000")
    text = text.replace("SYN-0001,2,23000", "SYN-0001,2,1,23000")
    for label in ("Average", "Standard Deviation", "% RSD"):
        text = text.replace(f"SYN-0001,{label},", f"SYN-0001,{label},,")
    two_identities.write_text(text)
    try:
        with pytest.raises(GpcSummaryExportFetchError, match="no unit declared"):
            acquire(path=two_identities)
    finally:
        two_identities.unlink()


def test_the_preregistration_asked_where_and_the_answer_is_nowhere():
    """The pre-registration is pinned and is not edited. Its prediction is
    quoted here and scored against what was measured."""
    row = PREREG["predictions"]["the_aggregate_block_is_read_as_measurements"]
    assert "ingests SIX measurements rather than three" in row["prediction"]
    assert "WHERE" in row["the_sharper_form"]
    assert "refuses because a flag column is unmapped" in row["the_sharper_form"], (
        "the pre-registration offered a refusal as the alternative outcome; measured, there is "
        "no refusal at all except on a percent sign"
    )
