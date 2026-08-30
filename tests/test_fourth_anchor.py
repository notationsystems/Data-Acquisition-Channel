"""Section 13 of the third anchor's report, through the same path.

Every claim in architecture/fourth_anchor_result.yaml is recomputed here
against the live path. The sharp one is comparative: section 12's
replicate sets and section 13's are structurally identical and mean
different things, and this file measures both rather than asserting it.
"""

from __future__ import annotations

import json
import pathlib
import statistics as st
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import GpcReportSourceAdapter  # noqa: E402
from daf.extractors.gpc_report import (GpcReportExtractionError,  # noqa: E402
                                       GpcReportExtractor)
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.replicate_pairing import (pair_replicates,  # noqa: E402
                                       sample_covariance)
from science.table import ABSENCE_REASONS  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
SECTION_13 = FIXTURES / "physchem_study_anchor_wil_505902_partition_coefficient.json"
SECTION_12 = FIXTURES / "physchem_study_anchor_wil_505902_water_solubility.json"
RESULT = loads((REPO_ROOT / "architecture" / "fourth_anchor_result.yaml").read_text())

#: Table 9 as printed, page 39. Toluene is deliberately not here.
TABLE_9 = {
    "formamide_t0":        (0.573, 0.573, None),
    "2-butanone":          (0.732, 0.728, 0.3),
    "benzylalcohol":       (0.957, 0.959, 1.1),
    "nitrobenzene":        (1.423, 1.425, 1.9),
    "bromobenzene":        (3.571, 3.578, 3.0),
    "1,4-dichlorobenzene": (5.358, 5.369, 3.4),
    "biphenyl":            (9.297, 9.314, 4.0),
    "test_substance":      (1.950, 1.950, 2.3),
}


def _acquire(path, **over):
    fields = dict(data_provenance="instrument_measurement", sample_id="CDC-003",
                  sample_kind="sample")
    fields.update(over)
    pool = EvidencePool()
    _, failures = run_scout(
        GpcReportSourceAdapter(path=path, source_name="regulations-gov",
                               retrieved_at="2026-08-30T00:00:00Z", **fields),
        GpcReportExtractor(), pool)
    return list(pool.all_observations()), failures


def _substance(replicate_set):
    return dict(dict(replicate_set.context)["conditions"])["substance"]


# =====================================================================
# The transcription
# =====================================================================

def test_the_fixture_is_table_9_and_toluene_is_not_in_it():
    document = json.loads(SECTION_13.read_text())
    by_substance: dict = {}
    for run in document["runs"]:
        by_substance.setdefault(run["conditions"]["substance"], []).append(run)

    assert set(by_substance) == set(TABLE_9)
    assert "toluene" not in by_substance, (
        "toluene is a reference substance on page 37 and is absent from Table 9; "
        "putting it back would be transcribing the list, not the table"
    )
    for name, (tr1, tr2, log_pow) in TABLE_9.items():
        runs = sorted(by_substance[name], key=lambda r: r["run_id"])
        assert [r["measurements"][0]["value"] for r in runs] == [tr1, tr2]
        has_log_pow = [m for r in runs for m in r["measurements"]
                       if m["variable"] == "log_pow"]
        assert bool(has_log_pow) is (log_pow is not None)
        if log_pow is not None:
            assert {m["value"] for m in has_log_pow} == {log_pow}


def test_injection_is_on_the_locator_and_not_in_the_comparison_context():
    """The error the pairing module caught unplanted, held as a property.

    Fails in the state where the injection number is back in conditions:
    every run becomes its own singleton and EVERY_RUN_DIFFERS_IN fires.
    """
    document = json.loads(SECTION_13.read_text())
    for run in document["runs"]:
        assert "injection" not in run["conditions"]
        assert run["run_id"].endswith(("injection1", "injection2"))


# =====================================================================
# P1, P2 -- what cannot be carried
# =====================================================================

def test_a_guideline_constant_and_a_regression_output_are_refused_alike():
    """P2. Both are not-`measured`, and the path says nothing more."""
    messages = []
    for kind in ("guideline_reference_value", "derived_from_regression_over_other_rows"):
        document = json.loads(SECTION_13.read_text())
        for run in document["runs"]:
            for measurement in run["measurements"]:
                if measurement["variable"] == "log_pow":
                    measurement["kind"] = kind
        tmp = SECTION_13.with_name("tmp_fourth_variant.json")
        tmp.write_text(json.dumps(document))
        try:
            with pytest.raises(GpcReportExtractionError) as caught:
                _acquire(tmp)
            messages.append(str(caught.value).replace(kind, "<KIND>"))
        finally:
            tmp.unlink(missing_ok=True)

    first, second = messages
    assert first.split("reports")[1] == second.split("reports")[1], (
        "the two refusals differ only in the kind they echo; if they have started to "
        "distinguish a literature constant from a regression output, this record is stale"
    )


def test_the_literature_column_can_only_be_declined_never_labelled():
    """P1. One data_provenance per report, so a guideline constant has no
    label of its own and leaves the pool entirely."""
    observations, failures = _acquire(SECTION_13, decline_non_measured=True)
    assert failures == ()
    assert {o.content["property"] for o in observations} == {"retention_time"}
    assert {o.content["data_provenance"] for o in observations} == {"instrument_measurement"}
    declined = {o.content["not_acquired_because_not_measured"] for o in observations}
    assert declined == {"", "log_pow"}, (
        "log_pow is declined on every run that has one, and formamide has none"
    )


def test_no_absence_reason_was_invented_for_toluene():
    """P3's guard. The honest state is unstatable, so the row is absent
    rather than mislabelled -- and the acquisition carries no absence."""
    observations, _ = _acquire(SECTION_13, decline_non_measured=True)
    assert not any("value_absence" in o.content for o in observations)
    document = SECTION_13.read_text()
    for reason in ABSENCE_REASONS:
        assert f'"{reason}"' not in document, (
            f"{reason!r} appears in the fixture; no reason may be chosen to make the "
            "toluene row acquirable"
        )
    assert "NO reason for its absence" in json.loads(document)["_absent_from_this_table"]


# =====================================================================
# P4 -- the comparative measurement, which is the point of this file
# =====================================================================

def test_two_injections_and_twenty_determinations_are_structurally_identical():
    """The sharp one. Section 13's pairs are two injections of one
    prepared solution; section 12's tens are independent determinations.
    Nothing in the content distinguishes them.

    Fails in the state where the substrate acquires a way to tell an
    injection from a determination -- at which point this test is the
    thing to delete.
    """
    thirteen, _ = _acquire(SECTION_13, decline_non_measured=True)
    twelve, _ = _acquire(SECTION_12)

    p13, p12 = pair_replicates(thirteen), pair_replicates(twelve)
    assert p13.refusals == () and p12.refusals == ()
    assert sorted(len(s.run_ids) for s in p13.sets) == [2] * 8
    assert sorted(len(s.run_ids) for s in p12.sets) == [10, 10]

    keys13 = {k for s in p13.sets for k, _ in s.context}
    keys12 = {k for s in p12.sets for k, _ in s.context}
    assert keys13 == keys12, "the two shapes are indistinguishable by their context keys"


def test_the_injection_dispersion_understates_the_determination_dispersion():
    """The harm, in numbers rather than in prose."""
    thirteen, _ = _acquire(SECTION_13, decline_non_measured=True)
    twelve, _ = _acquire(SECTION_12)

    injection_cvs = []
    for replicate_set in pair_replicates(thirteen).sets:
        values = [row[0].value for row in replicate_set.rows]
        mean = st.mean(values)
        if st.stdev(values) > 0:
            injection_cvs.append(100 * st.stdev(values) / mean)

    determination_cvs = []
    for replicate_set in pair_replicates(twelve).sets:
        values = [row[0].value for row in replicate_set.rows]
        determination_cvs.append(100 * st.stdev(values) / st.mean(values))

    assert len(injection_cvs) == 6 and len(determination_cvs) == 2
    assert max(injection_cvs) < max(determination_cvs), (
        "every injection CV is below the largest determination CV, which is the "
        "understatement this records"
    )
    assert st.mean(determination_cvs) / st.mean(injection_cvs) > 2.5


def test_the_degenerate_set_is_caught_and_it_is_the_headline_row():
    """P4's falsified half. Two injections reading 1.950 exactly, on the
    row whose result is section 13's endpoint, and the substrate objects.

    Fails in the state where DEGENERATE_VARIABLE stops firing -- a zero
    dispersion passing silently would license an unbounded confidence.
    """
    observations, _ = _acquire(SECTION_13, decline_non_measured=True)
    degenerate, ordinary = set(), set()
    for replicate_set in pair_replicates(observations).sets:
        reasons = sample_covariance(replicate_set).reasons
        (degenerate if "DEGENERATE_VARIABLE" in reasons else ordinary).add(
            _substance(replicate_set))

    assert degenerate == {"test_substance", "formamide_t0"}
    assert len(ordinary) == 6, "the six understated sets are NOT caught, which is the limit"


# =====================================================================
# P5 -- four set-level quantities, one gap
# =====================================================================

def test_the_regression_quality_travels_as_opaque_text_and_reaches_nothing():
    observations, _ = _acquire(SECTION_13, decline_non_measured=True)
    conditions = dict(observations[0].content["conditions"])
    assert "r = 0.9998, n = 12" in conditions["calibration_regression"]
    # It is a conditions string and nothing else. No content key holds it.
    assert not any(key for key in observations[0].content
                   if "regression" in key or "correlation" in key)
    assert observations[0].content["uncertainty_kind"] == "absent"


def test_the_result_record_names_one_gap_and_not_four():
    unification = RESULT["predictions_scored"][
        "p5_the_regression_r_is_stated_here_and_was_withheld_in_section_10"][
        "the_unification_it_was_written_to_test"]
    assert "ONE gap" in unification
    assert "per-cell contract" in unification
