"""Phase 37: what actually blocks Kalman, measured rather than inherited.

DAQ FRAMES; IT DOES NOT ELECT. This file checks that the framing record
says what was measured, and re-runs the measurements so the record cannot
drift away from the substrate it describes.

THE CLAIM THIS CHECKED. That Kalman's remaining blocker is only the
covariance extension, on three supports: cell typing resolved on both
axes, recursive depth supplied, and a working reissue discipline. Two
hold. The third did not, and reading the workload entry WHOLE turns up
four DAQ-owned requirements outside `blocking_requirements` -- the same
place the least_squares third requirement was nearly missed.

That repetition is the reason this file exists: an undercount arrived
twice from the same cause, which makes it a reading rule rather than an
incident.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads
from evidence.types import Observation
from science.admissibility import UNTYPED_QUANTITY, quantity_is_typed
from science.table import observation_is_table_alignable

REPO_ROOT = Path(__file__).resolve().parent.parent
FRAMING = loads((REPO_ROOT / "architecture" / "kalman_framing.yaml").read_text())
REQUIREMENTS = loads(
    (REPO_ROOT / "architecture" / "exchange" / "scl_requirements.yaml").read_text())
KALMAN = REQUIREMENTS["workloads"]["kalman_filter_linear"]


# ------------------------------------- the record frames and does not elect


def test_the_record_frames_and_does_not_elect():
    assert FRAMING["status"] == "framing_only"
    assert FRAMING["owner"] == "daf"
    assert "does not" in FRAMING["framing_for_the_next_decision"]["is_it_still_the_right_next_decision"]
    assert FRAMING["framing_for_the_next_decision"]["deliberately_not_started"].startswith("none")


def test_the_record_does_not_answer_its_counterpartys_question():
    """`recursive_generation_depth` is the compute layer's requirement.
    DAQ states what it supplied and what it did not; declaring the
    requirement met would be DAQ answering for the other side."""
    row = FRAMING["blocking_requirements_as_recorded"]["recursive_generation_depth"]
    assert row["verdict"] == "PARTIALLY_CLOSED_AND_NOT_DAQS_TO_DECLARE_CLOSED"
    assert "theirs to make" in row["why_not_declared_closed_here"]


# ------------------------------------- the measurements, re-run not quoted


def test_structured_uncertainty_is_still_unrepresented():
    verdict = quantity_is_typed(
        {"value": [1.0, 2.0], "unit": ["m", "m/s"], "uncertainty": 0.1,
         "uncertainty_kind": "stated"})
    assert not verdict.admissible
    assert UNTYPED_QUANTITY in verdict.reasons
    assert FRAMING["blocking_requirements_as_recorded"][
        "structured_measurement_uncertainty"]["verdict"] == "OPEN"


def test_observation_carries_no_order_and_no_stream_identity():
    fields = set(Observation.__dataclass_fields__)
    assert not (fields & {"index", "sequence", "order", "position"})
    assert not any("stream" in field for field in fields)
    outside = FRAMING["requirements_outside_the_blocking_list"]
    assert outside["ordering_is_required_and_significant"]["verdict"] == "OPEN"
    assert outside["stream_identity"]["verdict"] == "OPEN"


def test_the_table_gate_refuses_exactly_what_kalman_requires():
    """The sharp part of the framing, and it is not a defect in either
    gate: the two modalities genuinely differ. least_squares states that
    ordering is NOT required, so the table gate refuses positional
    identity by name. Kalman's modality is ordered and significant. The
    extension built for one does not carry to the other."""
    assert KALMAN["ordering_requirements"] == "required_and_significant"
    assert KALMAN["modality"] == "ordered_multivariate_time_series"

    positional = {"sample_id": "s1", "variable": "x", "value": 1.0, "row_index": 3}
    assert not observation_is_table_alignable(positional).admissible

    least_squares = REQUIREMENTS["workloads"]["least_squares"]
    ordering_row = next(r for r in least_squares["blocking_requirements"]
                        if r["requirement"] == "stable_sample_and_variable_identity")
    assert "ordering is explicitly not required" in ordering_row["statement"]


def test_per_component_units_have_no_representation():
    assert "units_per_measurement_component" in KALMAN["required_metadata"]
    assert not quantity_is_typed(
        {"value": [1.0, 2.0], "unit": ["m", "m/s"]}).admissible


# --------------------------- the reading rule, which is the real deliverable


def test_the_blocking_list_is_not_the_requirement_list():
    """Both undercounts came from reading `blocking_requirements` as if it
    were the requirements. Measured here so the rule rests on the artifact
    rather than on a claim about it."""
    blocking = {row["requirement"] for row in KALMAN["blocking_requirements"]}
    daq_blocking = {row["requirement"] for row in KALMAN["blocking_requirements"]
                    if row["owner"] == "daq"}
    assert daq_blocking == {"structured_measurement_uncertainty", "recursive_generation_depth"}, (
        f"the artifact's DAQ-owned blocking rows changed: {sorted(daq_blocking)}")
    assert len(daq_blocking) == 2, "two blocking rows -- and five open DAQ requirements in total"

    # The entry carries requirement-bearing keys OUTSIDE that list, which is
    # where the other three live.
    assert blocking
    outside = {"observation_requirements", "ordering_requirements", "required_metadata",
               "condition_requirements", "structured_data_requirements",
               "uncertainty_requirements", "minimum_observation_fields"}
    assert outside <= set(KALMAN), (
        f"the workload entry lost keys the framing depends on: {sorted(outside - set(KALMAN))}")

    assert "read the workload entry WHOLE" in FRAMING[
        "framing_for_the_next_decision"]["why_the_undercount_happened_twice"]


def test_every_daq_owned_requirement_the_framing_names_is_in_the_artifact():
    """The framing must not invent a requirement, and must not paraphrase
    one. Each named requirement is checked back against the artifact's own
    text."""
    outside = FRAMING["requirements_outside_the_blocking_list"]
    blob = " ".join(
        str(KALMAN[key]) for key in
        ("observation_requirements", "ordering_requirements", "required_metadata",
         "condition_requirements", "modality")
    )
    for name, entry in outside.items():
        stated = entry["stated_as"]
        # the framing quotes a fragment; the fragment must appear upstream
        fragment = stated.split(";")[0].split(":")[-1].strip()
        assert fragment[:30] in blob, f"{name}: {fragment[:60]!r} is not in the artifact"


def test_the_count_is_five_and_the_record_says_so_plainly():
    correction = FRAMING["framing_for_the_next_decision"]["the_correction"]
    assert "NOT only the covariance extension" in correction
    open_rows = [
        name for name, entry in FRAMING["requirements_outside_the_blocking_list"].items()
        if entry["verdict"] == "OPEN"
    ] + [
        name for name, entry in FRAMING["blocking_requirements_as_recorded"].items()
        if entry["verdict"] == "OPEN"
    ]
    assert len(open_rows) == 5, open_rows
    assert "at least five" in correction
    # plus the partially-closed one, which is open until its owner says otherwise
    assert FRAMING["blocking_requirements_as_recorded"][
        "recursive_generation_depth"]["verdict"].startswith("PARTIALLY")


def test_the_upstream_staleness_is_reported_and_not_edited():
    """The requirements artifact describes DAQ's invariant with a status
    DAQ has since corrected. It is the compute layer's artifact, mirrored
    read-only here, so the framing reports it."""
    row = FRAMING["blocking_requirements_as_recorded"]["recursive_generation_depth"]
    assert "reported rather than edited" in row["a_staleness_to_surface_not_fix"]

    upstream = next(r for r in KALMAN["blocking_requirements"]
                    if r["requirement"] == "recursive_generation_depth")
    assert "vacuously_enforced" in upstream["statement"]

    invariants = loads((REPO_ROOT / "architecture" / "invariants.yaml").read_text())
    ours = next(e for e in invariants["invariants"] if e["id"] == "generation_depth_bounded")
    assert ours["status"] == "enforced", (
        "DAQ's status changed again; the framing's staleness report needs re-measuring")
    assert "TWO corrections behind" in row["a_staleness_to_surface_not_fix"], (
        "the gap between what the upstream artifact says and what DAQ's invariant says has "
        "widened; the report must say how far behind it is, not merely that it is behind")


# ------------------ the shape rules the gate declines, measured not asserted


@pytest.mark.parametrize("cell", [
    [[1.0, 2.0], [3.0]],            # ragged
    [[1.0, 0.9], [0.1, 1.0]],       # asymmetric
    [[1.0, 2.0], [2.0, 1.0]],       # not positive-semidefinite
    [1.0, 2.0],                     # 1-D where 2-D expected
    [[], []],                       # empty
    [["low", "high"], ["high", "low"]],  # categorical entries
])
def test_the_gate_admits_every_shape_it_declines_to_rule_on(cell):
    """A declared boundary, re-measured rather than quoted. If one of
    these starts being refused, the gate has begun defining the covariance
    contract, and that decision belongs in the joint record."""
    assert observation_is_table_alignable(
        {"sample_id": "s1", "variable": "x", "value": cell}).admissible, cell


def test_the_leaf_rule_holds_at_every_depth_so_the_boundary_is_clean():
    """What the compute layer gets is a CLEAN boundary rather than a
    partial one: shape is entirely unclaimed, and leaf type is entirely
    claimed. A half-enforced leaf rule would be worse than none, because
    a consumer could not tell which half it had."""
    from science.table import COMPOSITE_CELL_LEAF_IS_NOT_A_QUANTITY

    for bad in (True, float("nan"), float("inf"), "1.5", None):
        deep = {"sample_id": "s1", "variable": "x", "value": [[1.0, [bad]]]}
        verdict = observation_is_table_alignable(deep)
        assert not verdict.admissible, bad
        assert COMPOSITE_CELL_LEAF_IS_NOT_A_QUANTITY in verdict.reasons


def test_the_declined_rules_are_recorded_where_the_other_half_will_read_them():
    declined = FRAMING["shape_rules_the_gate_formally_declines"]
    owned = declined["therefore_owned_outright_by_the_covariance_extension"]
    assert set(owned) == {"numeric_entry", "dimensionality", "raggedness", "symmetry",
                          "positive_semidefiniteness"}
    assert "electing-by-momentum" in declined["why_daq_declined_them_rather_than_supplying_them"]
    assert "ordering" in declined["the_ordering_caveat_still_applies"]

    # the PSD entry must carry why the bool finding does not close it
    assert "does not close this" in owned["positive_semidefiniteness"]


# ------------- the requirements artifact, re-measured rather than quoted


def test_the_requirements_artifact_has_not_moved_during_the_reissues():
    """Walks committed history in BOTH repositories rather than comparing
    current bytes to the current sidecar -- which would agree even if both
    had moved together, and is the proxy this repository keeps catching."""
    import hashlib
    import subprocess

    relative = "architecture/exchange/scl_requirements.yaml"
    log = subprocess.run(["git", "log", "--format=%H", "--", relative],
                         cwd=str(REPO_ROOT), capture_output=True, text=True)
    if log.returncode != 0 or not log.stdout.strip():
        pytest.skip("no git history (shallow clone)")

    versions = []
    for commit in log.stdout.split():
        blob = subprocess.run(["git", "show", f"{commit}:{relative}"],
                              cwd=str(REPO_ROOT), capture_output=True)
        if blob.returncode:
            continue
        digest = "sha256:" + hashlib.sha256(blob.stdout).hexdigest()
        if not versions or versions[-1] != digest:
            versions.append(digest)

    stability = FRAMING["requirements_artifact_stability"]
    assert stability["verdict"] == "CONFIRMED_STABLE"
    assert versions[0] == stability["current_in_both"].split(",")[0], (
        "the requirements artifact moved since the stability check was recorded; the joint record "
        "no longer binds the set the decision was reasoned over")

    decision = loads((REPO_ROOT / "architecture" / "decisions"
                      / "2026-08-26-joint-workload-decision.yaml").read_text())
    assert decision["requirements_artifact_hash"] == versions[0]


def test_the_artifact_lists_TWO_daq_owned_blocking_rows_not_one():
    """The correction the stability check surfaced. Re-measured from the
    artifact, because a claim about how many rows block a workload is
    exactly the kind that gets carried forward without checking."""
    daq_rows = [r for r in KALMAN["blocking_requirements"] if r["owner"] == "daq"]
    assert len(daq_rows) == 2
    assert {r["requirement"] for r in daq_rows} == {
        "structured_measurement_uncertainty", "recursive_generation_depth"}
    assert all(r["status"] == "UNSATISFIED" for r in daq_rows)

    stability = FRAMING["requirements_artifact_stability"]
    assert "NOT the last row" in stability["and_what_it_immediately_showed"]
    assert "read the workload entry whole" in stability["the_undercount_has_now_happened_three_times"]
    assert "the_undercount_has_now_happened_three_times" in stability
