"""DAQ's workload proposal -- deliberately NOT the joint decision record.

A joint decision is a two-party act. This repository has write access to
itself and READ-ONLY access to the compute layer, so a decision record
authored here would be one party writing both sides -- which destroys the
one property such a record exists to provide. What is committed here is
DAQ's half: its capability measurement, its reading of the compute
layer's PUBLISHED requirements, and a recommendation with rationale.

The proposal still carries both artifact digests, so whoever writes the
decision can verify them against their origin repositories rather than
against this account of them.

The canonicalization itself is tested by `tests/test_exchange_artifact.py`
against the vendored `architecture/exchange/canonical_yaml.py`, which is
byte-identical to the compute layer's copy by agreement. This file tests
the PROPOSAL -- that it binds to real bytes and obeys the joint rule it
claims to follow.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCHANGE = REPO_ROOT / "architecture" / "exchange"
PROPOSAL_PATH = REPO_ROOT / "architecture" / "proposals" / "2026-08-25-daq-workload-proposal.yaml"

CAPABILITIES = EXCHANGE / "daq_capabilities.yaml"
REQUIREMENTS = EXCHANGE / "scl_requirements.yaml"

sys.path.insert(0, str(EXCHANGE))
from canonical_yaml import canonical_dump

PROPOSAL = loads(PROPOSAL_PATH.read_text())


def _digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------- binding


def test_the_recorded_hashes_bind_to_the_bytes_on_disk():
    """The guarantee the proposal carries forward to whoever writes the decision."""
    assert PROPOSAL["capabilities_artifact_hash"] == _digest(CAPABILITIES)
    assert PROPOSAL["requirements_artifact_hash"] == _digest(REQUIREMENTS)


def test_both_artifacts_carry_a_committed_sidecar_digest_that_agrees():
    for artifact in (CAPABILITIES, REQUIREMENTS):
        sidecar = artifact.with_suffix(".sha256")
        assert sidecar.exists(), f"{artifact.name} has no committed digest"
        assert sidecar.read_text().strip() == _digest(artifact)


def test_the_record_is_a_fixed_point_of_the_shared_serializer():
    assert canonical_dump(PROPOSAL) == PROPOSAL_PATH.read_text()


def test_the_record_parses_identically_under_both_parsers():
    """A parser-dependent record would have a parser-dependent hash. This
    is the check that caught a bare ISO date resolving to `datetime.date`
    under PyYAML and `str` under this repository's reader."""
    text = PROPOSAL_PATH.read_text()
    assert loads(text) == yaml.safe_load(text)


def test_no_bare_iso_date_is_used_as_a_value():
    """The shared serializer leaves `2026-08-25` unquoted, so such a value
    is parser-dependent. It is byte-identical across both repositories by
    agreement and must not be edited on one side, so the record avoids the
    shape instead. Locked so it cannot creep back."""

    def walk(node):
        if isinstance(node, dict):
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)
        elif isinstance(node, str):
            yield node

    for value in walk(PROPOSAL):
        parts = value.split("-")
        assert not (len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[0]) == 4), (
            f"{value!r} is a bare ISO date and would hash differently under the two parsers"
        )


# --------------------------------------------------------- the decision


def test_exactly_one_workload_and_one_extension_are_recommended():
    """The recommendation is whatever the CURRENT matrix admits -- not a
    name frozen into this test. Issue 1 recommended fourier_transform_1d
    from a stale matrix; the re-measure moved it, which is what a
    re-measure is for."""
    recommended = PROPOSAL["recommended_workload"]
    assert isinstance(recommended, str) and recommended
    assert PROPOSAL["recommended_daq_extension"] == "none"
    assert recommended not in PROPOSAL["scope"]["do_not_build"]
    assert recommended in PROPOSAL["scope"]["build"]


def test_a_workload_already_built_is_never_recommended():
    """Recommending something that exists is not a decision."""
    built = PROPOSAL["scope"]["already_built_do_not_rebuild"]
    assert PROPOSAL["recommended_workload"] not in built
    assert "fourier_transform_1d" in built
    assert "BUILT" in PROPOSAL["superseded_recommendation"]


def test_the_reissue_chain_is_recorded_rather_than_overwritten():
    """Each issue's basis stays visible, so a reader can see the
    recommendation move and why."""
    reissue = PROPOSAL["reissue"]
    assert reissue["issue"] >= 3
    assert len(reissue["previous_issues"]) == reissue["issue"] - 1
    assert reissue["did_the_decision_move"] is True
    assert "5447df3" in reissue["reason"] and "edfc2dc" in reissue["reason"]


def test_the_recommendation_rests_on_the_remeasured_matrix():
    assert PROPOSAL["matrix_basis"] == "architecture/workload_primitive_matrix.yaml"
    assert (REPO_ROOT / PROPOSAL["matrix_basis"]).exists()


def test_it_is_a_proposal_and_says_so():
    """The correction this file exists to lock: one party with read-only
    access to the other must not author a two-party decision."""
    assert PROPOSAL["status"] == "proposed"
    authority = " ".join(PROPOSAL["authority"]).lower()
    assert "not the joint decision" in authority
    assert "read-only" in authority
    assert "what_would_make_this_a_decision" in PROPOSAL


def test_the_requirements_artifact_is_declared_a_read_only_mirror():
    """It is the compute layer's measured claim about itself. Written
    from here it would be DAQ's account of it instead."""
    authority = " ".join(PROPOSAL["requirements_artifact_authority"]).lower()
    assert "read-only mirror" in authority
    assert "sidecar" in authority, "what makes the mirror trustworthy is the upstream digest"
    assert PROPOSAL["requirements_artifact_hash"] == PROPOSAL["requirements_artifact_upstream_sha256"], (
        "the mirror must hash to the digest recorded in the ORIGIN repository"
    )


def test_the_operation_is_not_named_fft():
    """FFT is an implementation strategy, not the mathematical operation."""
    assert "fft" not in PROPOSAL["recommended_workload"].lower()


def test_the_selected_workload_is_one_daq_actually_satisfies():
    """The joint rule's hard constraint: SCL may not select a workload
    whose observation requirements DAQ marks absent."""
    requirements = loads(REQUIREMENTS.read_text())
    workloads = requirements["workloads"]
    selected = PROPOSAL["recommended_workload"]
    assert selected in workloads, f"{selected!r} is absent from the requirements artifact"

    # An EMPTY blocking list is the ideal case -- fully unblocked on both
    # sides -- not a missing declaration. Asserting it non-empty was a real
    # test bug: it failed exactly the candidate the rule most wants.
    blocking = workloads[selected]["blocking_requirements"] or []
    unmet = [
        entry["requirement"]
        for entry in blocking
        if entry["owner"] == "daq" and entry["status"] != "SATISFIED"
    ]
    assert unmet == [], (
        f"{selected} was selected but SCL marks these DAQ-owned requirements unmet: {unmet}"
    )


def test_every_workload_with_an_unmet_daq_requirement_is_excluded_from_the_build():
    """The other half of the rule, checked against SCL's own artifact
    rather than against this repository's reading of it."""
    requirements = loads(REQUIREMENTS.read_text())
    do_not_build = set(PROPOSAL["scope"]["do_not_build"])
    selected = PROPOSAL["recommended_workload"]

    for name, entry in requirements["workloads"].items():
        unmet = [
            item["requirement"]
            for item in entry.get("blocking_requirements") or []
            if item["owner"] == "daq" and item["status"] != "SATISFIED"
        ]
        if not unmet:
            continue
        assert name != selected, f"{selected} has unmet DAQ requirements {unmet}"
        # Names differ slightly between the two artifacts (SCL says
        # kalman_filter_linear, pca, convolution_1d); match on the stem.
        stem = name.replace("_linear", "").replace("_1d", "")
        assert any(stem in excluded or excluded in name for excluded in do_not_build), (
            f"{name} has unmet DAQ requirements {unmet} but is not excluded from the build"
        )


def test_an_extension_would_have_to_name_its_consuming_workload():
    """`none` is the only value that needs no pairing; the joint rule
    forbids representation work without a named consumer."""
    if PROPOSAL["recommended_daq_extension"] != "none":
        assert PROPOSAL["recommended_workload"], "an extension must be paired with the workload that consumes it"


def test_the_tradeoff_is_recorded_not_only_the_winner():
    tradeoff = PROPOSAL["tradeoff_recorded"]
    assert "reuse_leverage_argument" in tradeoff
    assert "generality_falsification_argument" in tradeoff
    assert "resolution" in tradeoff


def test_the_unselected_workloads_are_explicitly_excluded():
    do_not_build = set(PROPOSAL["scope"]["do_not_build"])
    for excluded in ("least_squares", "pca", "kalman_filter_linear", "viterbi"):
        assert excluded in do_not_build


def test_the_scl_implementation_is_cited_not_claimed():
    """A concurrent SCL session implemented the same workload
    independently. That is corroboration of the selection, and this
    session neither authored nor pushed it -- the record must say so
    rather than absorbing the credit."""
    status = PROPOSAL["implementation_status"]
    blob = " ".join(str(v) for v in status.values()).lower()
    assert "read-only" in blob
    assert "cited, not claimed" in blob


@pytest.mark.parametrize("field", [
    "recommended_workload", "recommended_daq_extension", "rationale",
    "requirements_artifact_hash", "capabilities_artifact_hash", "extends",
])
def test_every_required_field_is_present(field):
    assert field in PROPOSAL and PROPOSAL[field] not in (None, "", [])


def test_it_declares_the_core_version():
    assert PROPOSAL["extends"] == "core@1.0.0"
