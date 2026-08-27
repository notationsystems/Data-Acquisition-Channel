"""architecture/selection_rule_defect.yaml, bound.

It was bound by NOTHING -- not a doctrine source, and named by no test --
so nothing anywhere would have noticed it going stale. It had, in four
places, one of them its own headline evidence. A defect record whose
symptom names an outcome that did not occur is worse than no record,
because it is read as a measurement.

WHAT THIS FILE DOES AND DOES NOT ASSERT. Every claim here is re-measured
against the joint decision record, the requirements artifact at its
pinned hash, and architecture/invariants.yaml -- never restated from the
record under test. The rule CRITIQUE (`why_it_is_backwards`) is an
argument, not a measurement, and nothing here tries to certify it: an
argument bound by a test asserting it is true would be exactly the
self-consistent-and-wrong shape this repository keeps refusing.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARCHITECTURE = REPO_ROOT / "architecture"
RECORD = loads((ARCHITECTURE / "selection_rule_defect.yaml").read_text())
REMEASURED = RECORD["re_measured_2026_08_27"]
DECISION = loads((ARCHITECTURE / "decisions" / "2026-08-26-joint-workload-decision.yaml").read_text())
REQUIREMENTS_PATH = ARCHITECTURE / "exchange" / "scl_requirements.yaml"
REQUIREMENTS = loads(REQUIREMENTS_PATH.read_text())
INVARIANTS = loads((ARCHITECTURE / "invariants.yaml").read_text())


def _daq_blockers(workload: str) -> dict:
    entry = REQUIREMENTS["workloads"][workload]
    return {row["requirement"]: row["status"]
            for row in entry["blocking_requirements"] if row["owner"] == "daq"}


def _invariant(name: str) -> dict:
    return next(row for row in INVARIANTS["invariants"] if row["id"] == name)


def test_the_requirements_artifact_is_at_its_pinned_hash():
    """Everything below reads it. A measurement against a drifted artifact
    is not a measurement -- and the pin is what this pair already uses to
    say so."""
    live = "sha256:" + hashlib.sha256(REQUIREMENTS_PATH.read_bytes()).hexdigest()
    pinned = (ARCHITECTURE / "exchange" / "scl_requirements.sha256").read_text().strip()
    assert live == pinned, (
        "the requirements artifact has moved off its pin; re-measure the claims below against the "
        "new content before trusting any of them"
    )


def test_the_record_never_selected_fourier_which_is_what_it_claimed():
    """STALENESS ONE, and the sharpest: the record's own observable
    symptom names a selection that did not happen."""
    assert DECISION["the_actual_choice"]["elected"] == "option_b"
    assert "least_squares" in DECISION["the_actual_choice"]["option_b"]
    assert "fourier" not in DECISION["the_actual_choice"]["option_b"]

    dated = RECORD["process_finding"]["observable_symptom"]
    assert "selects fourier_transform_1d" in dated, (
        "the dated sentence is kept in place; if it is ever rewritten, this correction loses its "
        "subject and should be retired rather than left pointing at nothing"
    )
    correction = REMEASURED["one_the_observable_symptom_names_an_outcome_that_did_not_occur"]
    assert "did not occur" in correction["measured"] or "never selected" in correction["measured"]
    assert "withdrawn ON COMPLETION" in DECISION["the_rule_defect"]["how_it_surfaced"]


def test_the_process_finding_survives_the_correction():
    """The durable half. A gate slower than the work it gates was
    overtaken -- that is unchanged, and the correction must not be read as
    retracting it."""
    assert "what_survives" in REMEASURED["one_the_observable_symptom_names_an_outcome_that_did_not_occur"]
    assert "latency" in RECORD["process_finding"]["why_this_is_a_process_defect_not_an_accident"]
    assert RECORD["process_finding"]["summary"] == "the workload did not lose; the phase did"


def test_the_correction_was_applied_rather_than_left_pending():
    """STALENESS TWO. `not_yet_applied` sat beside a joint record that had
    already decided a workload under the corrected reading."""
    assert "SECOND CLAUSE" in DECISION["the_actual_choice"]["option_b"]
    assert "is the repair" in DECISION["the_rule_defect"]["the_correction"]
    assert DECISION["status"] == "decided"

    applied = REMEASURED["two_the_proposed_correction_is_applied_not_pending"]
    assert "not_yet_applied" in applied["the_dated_claim"]
    assert "has not been reissued" in applied["what_is_still_open"], (
        "applied in a decision is not repaired in the rule, and the record must keep the two apart"
    )


def test_kalman_has_no_remaining_daq_blocker():
    """STALENESS THREE. The sharpest_case_against_the_rule rests on Kalman
    having a small remaining extension. Both of its DAQ blockers are now
    SATISFIED, so it cannot be read as a live example."""
    blockers = _daq_blockers("kalman_filter_linear")
    assert set(blockers) == {"structured_measurement_uncertainty", "recursive_generation_depth"}
    assert set(blockers.values()) == {"SATISFIED"}, f"kalman DAQ blockers moved: {blockers}"
    assert _invariant("generation_depth_bounded")["status"] == "enforced"

    correction = REMEASURED["three_kalman_has_no_remaining_daq_blocker"]
    assert "BOTH" in correction["measured"]
    assert "correct when made" in correction["what_it_does_to_the_argument"], (
        "the case was right when written and its extension was built; the correction must say that "
        "rather than reading as a retraction"
    )


def test_the_least_squares_and_pca_blocker_sets_are_still_exactly_as_recorded():
    """STALENESS FOUR, measured and NOT stale. The half of the record that
    still holds, asserted so that its holding is a fact rather than an
    assumption carried forward."""
    assert _daq_blockers("least_squares") == {
        "stable_sample_and_variable_identity": "UNSATISFIED",
        "explicit_missing_value_semantics": "UNSATISFIED",
    }
    assert _daq_blockers("pca") == {
        "stable_sample_and_variable_identity": "UNSATISFIED",
        "commensurable_units_or_explicit_scaling": "UNSATISFIED",
    }
    recorded = RECORD["corrected_in_the_same_phase"]["measured"]
    assert any("stable_sample_and_variable_identity" in line and "least_squares" in line
               for line in recorded)


def test_daq_has_not_reported_the_table_against_the_requirement_it_answers():
    """Named by the record, and measured here rather than left as a
    sentence. The status is SCL's to set; whether DAQ has SAID anything is
    DAQ's, and it has not."""
    assert (REPO_ROOT / "science" / "table.py").exists()
    assert _daq_blockers("least_squares")["stable_sample_and_variable_identity"] == "UNSATISFIED"
    assert "not having reported" in REMEASURED["and_one_thing_daq_has_not_reported"]

    # DISCHARGED 2026-08-27, and this assertion INVERTED rather than
    # deleted. It previously asserted the requirement was ABSENT from the
    # response artifact, and it fired the moment DAQ reported -- which is
    # what it was for. The dated sentence stays; what changed is that the
    # obligation it names is now met, and the check moved to asserting the
    # discharge is real rather than that the gap persists.
    response = loads((ARCHITECTURE / "exchange" / "daq_requirement_response.yaml").read_text())
    answered = set(response["responses"])
    assert "least_squares::stable_sample_and_variable_identity" in answered, (
        "the discharge recorded below is not in the artifact"
    )
    assert "pca::stable_sample_and_variable_identity" in answered, (
        "the pca row carries DIFFERENT statement text and is a different row; answering only the "
        "least_squares one leaves it looking unanswered"
    )
    assert "discharged_2026_08_27" in REMEASURED["and_one_thing_daq_has_not_reported"] or \
        "discharged_2026_08_27" in REMEASURED, "the discharge must be recorded beside the claim"

    # And DAQ still asserts no status for a row it does not own.
    for key in ("least_squares::stable_sample_and_variable_identity",
                "pca::stable_sample_and_variable_identity"):
        blob = " ".join(str(v) for v in response["responses"][key].values())
        assert "SATISFIED" not in blob, f"{key} asserts a status that is SCL's to set"


def test_the_record_does_not_certify_its_own_argument():
    """The critique is an argument. Binding a test that asserts an
    argument is true is the self-consistent-and-wrong shape, so this
    asserts only that the argument is still PRESENT and unretracted."""
    assert isinstance(RECORD["why_it_is_backwards"], list)
    assert len(RECORD["why_it_is_backwards"]) == 3
    assert RECORD["status"] == "corrected_in_the_joint_decision_record"


def test_the_record_says_why_it_went_stale_unnoticed():
    """The reason this file exists at all, kept with the record rather
    than only in a phase report."""
    why = REMEASURED["why_this_section_exists"]
    assert "bound by NOTHING" in why
    assert "not a doctrine source" in why
    assert "left in place beside the corrections" in why
