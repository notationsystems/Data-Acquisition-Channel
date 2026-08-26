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
    assert ours["status"] == "represented_unenforced", (
        "DAQ's status changed; the framing's staleness report needs re-measuring")
