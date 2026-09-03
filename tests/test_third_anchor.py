"""The third anchor: a real GLP study of a technique this contract was
never written for, run through the unchanged acquisition path.

Every number in architecture/third_anchor_result.yaml is recomputed here
from the fixture and the live path. A result record that restated what a
reading claimed, rather than what the code does, would be the stale
mirror this repository has already filed twice.
"""

from __future__ import annotations

import copy
import json
import pathlib
import statistics as st
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from daf.adapters.gpc_report import (GpcReportFetchError,  # noqa: E402
                                     GpcReportSourceAdapter)
from daf.extractors.gpc_report import GpcReportExtractor  # noqa: E402
from epistemics._yaml import loads  # noqa: E402
from evidence.pool import EvidencePool  # noqa: E402
from science.admissibility import (UNCERTAINTY_KINDS,  # noqa: E402
                                   no_context_free_property, quantity_is_typed)
from science.replicate_pairing import pair_replicates  # noqa: E402
from science.table import ABSENCE_REASONS, observation_is_table_alignable  # noqa: E402
from scout.pipeline import run_scout  # noqa: E402

ANCHOR = (REPO_ROOT / "tests" / "fixtures"
          / "physchem_study_anchor_wil_505902_water_solubility.json")
SIDECAR = ANCHOR.with_name(ANCHOR.name.replace(".json", ".provenance.md"))
RESULT = loads((REPO_ROOT / "architecture" / "third_anchor_result.yaml").read_text())

#: Table 8, as printed. Held here so a fixture edit is a test failure.
PRINTED = {
    24: {"individual": (9.43, 9.61, 9.66, 9.70, 9.69, 9.68, 9.71, 9.71, 9.70, 9.72),
         "mean": 9.66, "cv": 0.91, "ph": "7.8"},
    12: {"individual": (9.70, 9.72, 9.73, 9.74, 9.76, 9.74, 9.75, 9.80, 9.73, 9.74),
         "mean": 9.74, "cv": 0.28, "ph": "7.7"},
}
PRINTED_RESULT = 9.70   # section 12.7
PRINTED_MD = 0.83


def _acquire(document=None, **declared):
    """The UNCHANGED path. `document` overrides the fixture in place."""
    path = ANCHOR
    tmp = None
    if document is not None:
        tmp = ANCHOR.with_name("tmp_third_anchor_variant.json")
        tmp.write_text(json.dumps(document))
        path = tmp
    fields = dict(data_provenance="instrument_measurement", sample_id="CDC-003",
                  sample_kind="sample")
    fields.update(declared)
    try:
        pool = EvidencePool()
        _, failures = run_scout(
            GpcReportSourceAdapter(path=path, source_name="regulations-gov",
                                   retrieved_at="2026-08-30T00:00:00Z", **fields),
            GpcReportExtractor(), pool)
        return list(pool.all_observations()), failures
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


# =====================================================================
# The fixture is faithful, and faithful is checkable here
# =====================================================================

def test_the_fixture_states_nothing_the_report_does_not():
    document = json.loads(ANCHOR.read_text())
    for absent in ("data_provenance", "sample_kind", "sample_id"):
        assert absent not in document, (
            f"{absent!r} is back in the fixture. The report states it nowhere, and a fixture "
            "that supplies it widens a clause one layer earlier than any test looks."
        )
    # `method` is the one the report DOES state -- Q1's falsification.
    assert "OECD 105" in document["method"]


def test_the_transcription_reproduces_the_report_s_own_arithmetic():
    """The check the GPC anchors could not offer: the document publishes
    statistics derived from the values, so a misread is arithmetic.

    Fails in the state where any individual concentration is mistyped --
    a single digit moves a mean or a CV off the printed figure.
    """
    document = json.loads(ANCHOR.read_text())
    by_flow: dict = {}
    for run in document["runs"]:
        flow = int(run["conditions"]["flow_rate_ml_per_hour"])
        by_flow.setdefault(flow, []).append(run["measurements"][0]["value"])

    assert set(by_flow) == set(PRINTED)
    means = []
    for flow, printed in PRINTED.items():
        values = by_flow[flow]
        assert tuple(values) == printed["individual"]
        mean = st.mean(values)
        means.append(mean)
        assert round(mean, 2) == printed["mean"]
        cv = 100 * st.stdev(values) / mean
        # One unit low in the last printed digit: the laboratory computed
        # its CV from concentrations it did not print at full precision.
        assert abs(cv - printed["cv"]) < 0.01, (flow, cv, printed["cv"])

    assert round(st.mean(means), 2) == PRINTED_RESULT
    hi, lo = max(means), min(means)
    # CORRECTED 2026-09-03. This read `< 0.01` and passed, and the
    # comment above it said 0.825 against a printed 0.83 was half-up
    # rounding of a value on the boundary. Both were wrong. The report's
    # own formula (page 33: divide by the mean of the highest and lowest)
    # gives 0.824657, which prints as 0.82, not 0.83 -- it is not on any
    # boundary, and the tolerance was wide enough to absorb the very
    # discrepancy it was checking. Recorded in
    # architecture/third_anchor_result.yaml under faithfulness.
    by_the_reports_formula = 100 * (hi - lo) / ((hi + lo) / 2)
    assert abs(by_the_reports_formula - 0.824657251829709) < 1e-12
    assert round(by_the_reports_formula, 2) == 0.82 != PRINTED_MD, (
        "the printed MD no longer disagrees with the report's own formula; the finding "
        "in third_anchor_result.yaml needs re-measuring rather than editing"
    )


def test_the_sidecar_states_what_the_source_lacks():
    text = SIDECAR.read_text()
    assert "WHAT THE SOURCE DOES NOT CONTAIN" in text
    assert "4278fff29d1cf6235131d5ce12552434d7286ecfac989f3984f85a5c235775aa" in text


# =====================================================================
# Q1 -- FALSIFIED IN PART. The report states its method.
# =====================================================================

def test_three_of_the_four_declarable_fields_are_absent_and_each_is_refused_alone():
    document = json.loads(ANCHOR.read_text())
    for field in ("data_provenance", "sample_id", "sample_kind"):
        supplied = {k: v for k, v in
                    dict(data_provenance="instrument_measurement", sample_id="CDC-003",
                         sample_kind="sample").items() if k != field}
        with pytest.raises(GpcReportFetchError, match=field):
            _acquire(document, **{**{k: None for k in ("data_provenance", "sample_id",
                                                       "sample_kind")}, **supplied})


def test_the_fourth_is_stated_by_the_document_and_declaring_it_is_a_conflict():
    """Q1's falsification, and its proof. A guideline study cites the
    guideline it was run under; that citation IS a method identifier.

    Fails in the state where the adapter silently prefers one source over
    the other instead of refusing.
    """
    with pytest.raises(GpcReportFetchError, match="method"):
        _acquire(method="oecd_105")

    observations, _ = _acquire()
    method = observations[0].content["method"]
    for citation in ("OECD 105", "EC A.6", "OPPTS 830.7840"):
        assert citation in method
    assert RESULT["predictions_scored"][
        "q1_the_four_declarable_fields_are_still_absent"]["verdict"] == "FALSIFIED_IN_PART"


# =====================================================================
# Q4 -- FALSIFIED. Twenty runs, and twelve of them share a value.
# =====================================================================

def test_twenty_replicates_become_twenty_distinct_records():
    observations, failures = _acquire()
    assert failures == ()
    assert len(observations) == 20
    assert len({o.id for o in observations}) == 20
    assert len({o.record_ids for o in observations}) == 20


def test_replicates_sharing_a_value_stay_distinct():
    """The adapter's locator claim, tested on real data for the first
    time -- both GPC anchors had all-distinct values.

    Fails in the state where run identity leaves the locator: two runs
    reporting the same number would hash to one Record and one
    Observation, silently halving the replicate count.
    """
    observations, _ = _acquire()
    values = [o.content["value"] for o in observations]
    repeated = [v for v in set(values) if values.count(v) > 1]
    shared = sum(values.count(v) for v in repeated)
    assert shared == 12, f"the report has twelve replicates sharing a value, found {shared}"
    for value in repeated:
        same = [o for o in observations if o.content["value"] == value]
        assert len({o.id for o in same}) == len(same)


# =====================================================================
# The unpredicted result: the substrate recovers the study's own analysis
# =====================================================================

def test_the_pairing_recovers_the_studys_own_groups_and_its_published_dispersions():
    """Given twenty replicates and no aggregate, the grouping rule picks
    the same two groups the laboratory picked, and the same CVs.

    Fails in the state where flow rate stops conditioning the group --
    which is exactly what the dropped-key defect below produces.
    """
    observations, _ = _acquire()
    pairing = pair_replicates(observations)
    assert pairing.refusals == ()
    assert len(pairing.sets) == 2

    seen = {}
    for replicate_set in pairing.sets:
        conditions = dict(dict(replicate_set.context)["conditions"])
        flow = int(conditions["flow_rate_ml_per_hour"])
        values = [row[0].value for row in replicate_set.rows]
        assert len(values) == 10
        seen[flow] = st.mean(values)
        assert round(seen[flow], 2) == PRINTED[flow]["mean"]
        assert abs(100 * st.stdev(values) / seen[flow] - PRINTED[flow]["cv"]) < 0.01
        assert conditions["ph"] == PRINTED[flow]["ph"]

    assert round(st.mean(list(seen.values())), 2) == PRINTED_RESULT


def test_a_conditioning_variable_under_an_unrecognised_key_is_dropped_in_silence():
    """The adapter carries every run key into the payload; the
    extractor's content vocabulary is closed and discards what it does
    not name. Nothing reports the difference.

    Fails in the state where the extractor either carries the key or
    refuses it -- either would end the silence, and this test would then
    be the thing to delete.
    """
    document = json.loads(ANCHOR.read_text())
    base = json.loads(ANCHOR.read_text())["conditions"]
    for run in document["runs"]:
        conditions = run.pop("conditions")
        run["run_conditions"] = {"flow_rate_ml_per_hour": conditions["flow_rate_ml_per_hour"],
                                 "ph": conditions["ph"]}
        run["conditions"] = dict(base)

    observations, failures = _acquire(document)
    assert failures == (), "the dropped key is not reported as a failure"
    assert len(observations) == 20
    assert all("run_conditions" not in o.content for o in observations), (
        "the key reached content; the silent drop no longer happens and this test is stale"
    )

    pairing = pair_replicates(observations)
    assert pairing.refusals == (), "the merge is not reported as a refusal either"
    assert len(pairing.sets) == 1, "twenty runs merged into one group"

    values = [row[0].value for row in pairing.sets[0].rows]
    pooled_mean = st.mean(values)
    pooled_cv = 100 * st.stdev(values) / pooled_mean

    # THE DANGEROUS HALF. The mean is invariant to the defect, so the
    # figure a reader would check against the report agrees exactly.
    assert round(pooled_mean, 2) == PRINTED_RESULT
    # The dispersion is not, and lands between the study's two acceptance
    # figures -- a number the study never computed.
    assert abs(pooled_cv - 0.773) < 0.005
    assert PRINTED[12]["cv"] < pooled_cv < PRINTED[24]["cv"]


def test_run_conditions_replace_the_reports_and_losing_the_method_context_is_green():
    """Both the correct transcription and the context-destroying one pass
    every gate. They differ in verbosity, not in verdict."""
    document = json.loads(ANCHOR.read_text())
    for run in document["runs"]:
        conditions = run["conditions"]
        run["conditions"] = {"flow_rate_ml_per_hour": conditions["flow_rate_ml_per_hour"],
                             "ph": conditions["ph"]}

    observations, failures = _acquire(document)
    assert failures == ()
    assert len(pair_replicates(observations).sets) == 2
    carried = dict(observations[0].content["conditions"])
    assert set(carried) == {"flow_rate_ml_per_hour", "ph"}
    assert not any("OECD" in str(v) for v in carried.values()), (
        "all three guideline citations are gone and nothing objected"
    )
    for gate in (quantity_is_typed, no_context_free_property,
                 observation_is_table_alignable):
        assert gate(observations[0].content).admissible


# =====================================================================
# Q2 and the vapour-pressure bound: what the vocabularies cannot hold
# =====================================================================

def test_absent_is_the_only_true_posture_and_it_discards_two_published_numbers():
    observations, _ = _acquire()
    assert {o.content["uncertainty_kind"] for o in observations} == {"absent"}
    assert {o.content["uncertainty"] for o in observations} == {None}
    # The report publishes CV and MD. Neither has anywhere to go.
    carried = set()
    for observation in observations:
        carried.update(str(v) for v in observation.content.values())
        carried.update(str(v) for v in dict(observation.content["conditions"]).values())
    for published in ("0.91", "0.28", "0.83"):
        assert not any(published == c for c in carried), (
            f"{published} is being carried somewhere; the gap this records has closed"
        )


def test_the_vapour_pressure_bound_fits_no_absence_reason():
    """Section 10: `< 1.5e-3 Pa`, after the intended method failed and the
    bound was set by comparison with hexachlorobenzene.

    A structural check, not a transcription: the claim is that the five
    reasons cannot express a bound, and the five reasons are read from
    the module rather than restated.
    """
    assert set(ABSENCE_REASONS) == {"not_measured", "below_detection", "above_range",
                                    "withheld", "lost_in_acquisition"}
    finding = RESULT["unpredicted"]["a_result_that_is_neither_a_value_nor_any_absence_reason"]
    assert finding["status"] == "OPEN_AND_NOT_RESOLVED_HERE"
    # An absence carries a reason and not a number, so even a fitting
    # reason could not hold 1.5e-3. That is the structural half.
    from science.table import VALUE_ABSENCE
    assert VALUE_ABSENCE == "value_absence"


def test_the_uncertainty_vocabulary_is_unchanged_by_this_anchor():
    """No clause was widened so a real anchor could pass."""
    assert UNCERTAINTY_KINDS == ("stated", "estimated", "propagated", "absent")


# =====================================================================
# The record says what the code does
# =====================================================================

def test_every_scored_prediction_carries_a_verdict_from_the_closed_set():
    allowed = {"CONFIRMED", "FALSIFIED", "FALSIFIED_IN_PART",
               "CONFIRMED_IN_A_SHARPER_FORM"}
    verdicts = {name: body["verdict"]
                for name, body in RESULT["predictions_scored"].items()}
    assert len(verdicts) == 5
    assert set(verdicts.values()) <= allowed
    assert sum(1 for v in verdicts.values() if v.startswith("FALSIFIED")) == 2
