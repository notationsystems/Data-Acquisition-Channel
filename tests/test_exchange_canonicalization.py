"""The Phase-2 exchange artifacts and the joint decision record.

The decision record binds a workload selection to the exact measurements
that produced it by carrying the SHA-256 of each exchange artifact. That
guarantee is only worth anything if the encoding is reproducible, so the
brief pins it and `epistemics/exchange.py` implements it. These tests
assert the properties the guarantee actually rests on:

  * the encoder is deterministic and a fixed point;
  * this repository's dependency-free reader and PyYAML agree on every
    committed artifact -- the cross-parser check that caught an unquoted
    ISO date resolving to `datetime.date` under one parser and `str` under
    the other, which would have made the hash parser-dependent;
  * the recorded hashes match the bytes actually on disk;
  * the decision obeys the joint rule it claims to follow.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads
from epistemics.exchange import (
    ExchangeSerializationError,
    artifact_hash,
    canonical_yaml,
    hash_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCHANGE = REPO_ROOT / "architecture" / "exchange"
DECISIONS = REPO_ROOT / "architecture" / "decisions"

CAPABILITIES = EXCHANGE / "daq_capabilities.yaml"
REQUIREMENTS = EXCHANGE / "scl_requirements.yaml"
DECISION = DECISIONS / "2026-08-25-workload-selection.yaml"

ARTIFACTS = (CAPABILITIES, REQUIREMENTS, DECISION)


def _load(path):
    return loads(path.read_text())


# ------------------------------------------------------ encoder properties


def test_the_encoder_is_deterministic():
    document = {"b": 1, "a": [{"z": 1, "y": 2}], "c": {"n": None, "t": True}}
    assert canonical_yaml(document) == canonical_yaml(document)


def test_keys_are_sorted_at_every_level():
    text = canonical_yaml({"b": {"z": 1, "a": 2}, "a": 3})
    assert text.splitlines()[0] == "a: 3"
    body = text.splitlines()[1:]
    assert body == ["b:", "  a: 2", "  z: 1"]


def test_a_date_like_string_is_quoted_so_both_parsers_agree():
    """The bug this suite caught. PyYAML resolves a bare `2026-08-25` to
    `datetime.date`; the repository reader returns `str`. Unquoted, the
    artifact would parse differently under the two parsers and its hash
    would depend on which one produced it."""
    text = canonical_yaml({"date": "2026-08-25"})
    assert text == 'date: "2026-08-25"\n'
    assert loads(text) == yaml.safe_load(text) == {"date": "2026-08-25"}


def test_numeric_looking_strings_survive_as_strings():
    text = canonical_yaml({"a": "1.0", "b": "42", "c": "true", "d": "null"})
    assert loads(text) == yaml.safe_load(text) == {"a": "1.0", "b": "42", "c": "true", "d": "null"}


def test_empty_collections_use_the_readers_supported_flow_forms():
    text = canonical_yaml({"a": [], "b": {}})
    assert text == "a: []\nb: {}\n"
    assert loads(text) == yaml.safe_load(text) == {"a": [], "b": {}}


def test_a_multi_line_string_is_refused_rather_than_silently_degraded():
    """The reader has no multi-line scalar support. Emitting one anyway
    would produce an artifact it cannot read back, so this raises."""
    with pytest.raises(ExchangeSerializationError, match="multi-line"):
        canonical_yaml({"a": "one\ntwo"})


def test_a_non_finite_float_is_refused():
    with pytest.raises(ExchangeSerializationError, match="non-finite"):
        canonical_yaml({"a": float("inf")})


def test_the_hash_is_over_the_bytes_and_prefixed():
    text = canonical_yaml({"a": 1})
    digest = artifact_hash(text)
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64
    assert artifact_hash(text) == digest


# ------------------------------------------------- committed artifacts


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.name)
def test_every_artifact_parses_identically_under_both_parsers(path):
    text = path.read_text()
    assert loads(text) == yaml.safe_load(text), f"{path.name} parses differently"


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.name)
def test_every_artifact_is_a_fixed_point_of_the_encoder(path):
    """The committed bytes must be exactly what the encoder produces, or
    the recorded hash describes something other than the file."""
    text = path.read_text()
    assert canonical_yaml(loads(text)) == text


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.name)
def test_every_artifact_ends_with_exactly_one_newline(path):
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert b"\r" not in raw, "LF line endings only"


@pytest.mark.parametrize("path", ARTIFACTS, ids=lambda p: p.name)
def test_every_artifact_declares_its_core_version(path):
    assert _load(path)["extends"] == "core@1.0.0"


# ----------------------------------------------------- the decision record


def test_the_decision_hashes_bind_to_the_bytes_on_disk():
    """The single guarantee the record exists to provide: it cannot be
    reconstructed from recollection, because it names the exact
    measurements it was made from."""
    decision = _load(DECISION)
    assert decision["capabilities_artifact_hash"] == hash_file(CAPABILITIES)
    assert decision["requirements_artifact_hash"] == hash_file(REQUIREMENTS)


def test_the_decision_names_exactly_one_workload_and_one_extension():
    decision = _load(DECISION)
    assert decision["workload"] == "fourier_transform_1d"
    assert decision["daq_extension"] == "none"


def test_the_operation_is_not_named_fft():
    """FFT is an implementation strategy, not the mathematical
    operation."""
    decision = _load(DECISION)
    assert decision["workload"] == "fourier_transform_1d"
    assert "fft" not in decision["workload"].lower()


def test_the_selected_workload_is_not_one_daq_marks_absent():
    """The joint rule's hard constraint: SCL may not select a workload
    whose observation requirements DAQ marks absent."""
    requirements = _load(REQUIREMENTS)
    selected = _load(DECISION)["workload"]
    for workload in requirements["workloads"]:
        if workload["workload"] == selected:
            availability = workload["daq_availability_measured"]
            assert availability.startswith("satisfied"), (
                f"{selected} was selected but its DAQ availability is: {availability}"
            )
            return
    raise AssertionError(f"the selected workload {selected!r} is absent from the requirements artifact")


def test_an_extension_would_require_a_named_consuming_workload():
    """`daq_extension: none` is the only value that needs no pairing. Any
    other value must be paired with the workload that consumes it -- the
    joint rule forbids representation work without one."""
    decision = _load(DECISION)
    if decision["daq_extension"] != "none":
        assert decision["workload"], "an extension must name its consuming workload"


def test_every_workload_daq_marks_absent_is_excluded_from_the_build():
    requirements = _load(REQUIREMENTS)
    do_not_build = set(_load(DECISION)["scope"]["do_not_build"])
    for workload in requirements["workloads"]:
        if workload["daq_availability_measured"].startswith("NOT satisfied"):
            assert workload["workload"] in do_not_build, (
                f"{workload['workload']} is unsatisfiable but is not excluded from the build"
            )


def test_the_capability_artifact_marks_the_absent_modalities_absent():
    """The measurement the decision rests on, re-asserted here so a later
    edit to the artifact cannot silently invalidate the decision."""
    statuses = {m["modality"]: m["status"] for m in _load(CAPABILITIES)["modalities"]}
    assert statuses["scalar"] == "supported"
    assert statuses["time_series"] == "partial"
    for absent in ("multivariate_time_series", "spatial_field", "spectrum", "trajectory"):
        assert statuses[absent] == "absent"


def test_the_decision_records_the_tradeoff_rather_than_only_the_winner():
    tradeoff = _load(DECISION)["tradeoff_recorded"]
    assert "reuse_leverage_argument" in tradeoff
    assert "generality_falsification_argument" in tradeoff
    assert "resolution" in tradeoff


def test_daq_never_emits_computed():
    capabilities = _load(CAPABILITIES)
    assert capabilities["identity"]["class_emitted"] == "measured"
    assert capabilities["identity"]["daq_never_emits"] == "computed"
    assert capabilities["re_entry"]["scl_output_as_daq_observation"] == "forbidden"


def test_q_is_recorded_as_outside_daqs_responsibility():
    """R is measurement-side and may derive from DAQ; Q is an asserted
    modelling choice DAQ must never be asked to supply."""
    requirements = _load(REQUIREMENTS)
    assert "Q" in requirements["q_is_not_a_daq_concern"]
    for workload in requirements["workloads"]:
        if workload["workload"] == "kalman_filter":
            assert "Q" in workload["model_parameters_asserted_not_from_daq"]
            return
    raise AssertionError("kalman_filter is missing from the requirements artifact")
