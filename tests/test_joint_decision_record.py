"""The joint DAQ/SCL decision record.

`architecture/decisions/2026-08-25-workload-selection.yaml` owns the
workload selection and any paired DAQ extension. Its whole value is that
it cannot be reconstructed from an agent's recollection: it carries the
SHA-256 of the exact two exchange artifacts it was made from.

The canonicalization itself is tested by `tests/test_exchange_artifact.py`
against the vendored `architecture/exchange/canonical_yaml.py`, which is
byte-identical to the compute layer's copy by agreement. This file tests
the DECISION -- that it binds to real bytes and obeys the joint rule it
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
DECISION_PATH = REPO_ROOT / "architecture" / "decisions" / "2026-08-25-workload-selection.yaml"

CAPABILITIES = EXCHANGE / "daq_capabilities.yaml"
REQUIREMENTS = EXCHANGE / "scl_requirements.yaml"

sys.path.insert(0, str(EXCHANGE))
from canonical_yaml import canonical_dump

DECISION = loads(DECISION_PATH.read_text())


def _digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------- binding


def test_the_recorded_hashes_bind_to_the_bytes_on_disk():
    """The single guarantee the record exists to provide."""
    assert DECISION["capabilities_artifact_hash"] == _digest(CAPABILITIES)
    assert DECISION["requirements_artifact_hash"] == _digest(REQUIREMENTS)


def test_both_artifacts_carry_a_committed_sidecar_digest_that_agrees():
    for artifact in (CAPABILITIES, REQUIREMENTS):
        sidecar = artifact.with_suffix(".sha256")
        assert sidecar.exists(), f"{artifact.name} has no committed digest"
        assert sidecar.read_text().strip() == _digest(artifact)


def test_the_record_is_a_fixed_point_of_the_shared_serializer():
    assert canonical_dump(DECISION) == DECISION_PATH.read_text()


def test_the_record_parses_identically_under_both_parsers():
    """A parser-dependent record would have a parser-dependent hash. This
    is the check that caught a bare ISO date resolving to `datetime.date`
    under PyYAML and `str` under this repository's reader."""
    text = DECISION_PATH.read_text()
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

    for value in walk(DECISION):
        parts = value.split("-")
        assert not (len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[0]) == 4), (
            f"{value!r} is a bare ISO date and would hash differently under the two parsers"
        )


# --------------------------------------------------------- the decision


def test_exactly_one_workload_and_one_extension_are_named():
    assert DECISION["workload"] == "fourier_transform_1d"
    assert DECISION["daq_extension"] == "none"


def test_the_operation_is_not_named_fft():
    """FFT is an implementation strategy, not the mathematical
    operation."""
    assert "fft" not in DECISION["workload"].lower()


def test_the_selected_workload_is_one_daq_actually_satisfies():
    """The joint rule's hard constraint: SCL may not select a workload
    whose observation requirements DAQ marks absent."""
    requirements = loads(REQUIREMENTS.read_text())
    workloads = requirements["workloads"]
    selected = DECISION["workload"]
    assert selected in workloads, f"{selected!r} is absent from the requirements artifact"

    blocking = workloads[selected]["blocking_requirements"]
    assert blocking, f"{selected} declares no blocking requirements at all"
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
    do_not_build = set(DECISION["scope"]["do_not_build"])
    selected = DECISION["workload"]

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
    if DECISION["daq_extension"] != "none":
        assert DECISION["workload"], "an extension must be paired with the workload that consumes it"


def test_the_tradeoff_is_recorded_not_only_the_winner():
    tradeoff = DECISION["tradeoff_recorded"]
    assert "reuse_leverage_argument" in tradeoff
    assert "generality_falsification_argument" in tradeoff
    assert "resolution" in tradeoff


def test_the_unselected_workloads_are_explicitly_excluded():
    do_not_build = set(DECISION["scope"]["do_not_build"])
    for excluded in ("least_squares", "pca", "kalman_filter_linear", "viterbi"):
        assert excluded in do_not_build


def test_the_scl_implementation_is_cited_not_claimed():
    """A concurrent SCL session implemented the same workload
    independently. That is corroboration of the selection, and this
    session neither authored nor pushed it -- the record must say so
    rather than absorbing the credit."""
    status = DECISION["implementation_status"]
    blob = " ".join(str(v) for v in status.values()).lower()
    assert "read-only" in blob
    assert "cited, not claimed" in blob


@pytest.mark.parametrize("field", [
    "workload", "daq_extension", "rationale",
    "requirements_artifact_hash", "capabilities_artifact_hash", "extends",
])
def test_every_required_field_is_present(field):
    assert field in DECISION and DECISION[field] not in (None, "", [])


def test_it_declares_the_core_version():
    assert DECISION["extends"] == "core@1.0.0"
