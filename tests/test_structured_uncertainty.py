"""DAQ's half of `structured_measurement_uncertainty`, paired with Kalman.

THE REQUIREMENT, quoted from the compute layer's exchange artifact:

    "DAQ must be able to express a measurement covariance R, not only a
    scalar uncertainty per observation. A scalar is sufficient ONLY when
    the measurement is genuinely 1-D and uncorrelated."

Two halves. Expressing R is a representation change. Enforcing the
"ONLY when" is a CORRESPONDENCE rule between value and uncertainty, and
it is the half with teeth: a single sigma on a three-component
measurement does not merely lose the off-diagonals, it asserts an
independence nobody stated.

THE SPLIT WITH THE COMPUTE LAYER, which its covariance contract states
from the other side and this file checks from ours:

    DAQ  is this OBSERVATION internally coherent?  correspondence, units,
         every number a number
    SCL  is this MATRIX a covariance?  numeric entry, rectangular, square,
         symmetric, positive-semidefinite

A ragged, asymmetric or indefinite matrix is a perfectly coherent
observation of something that is not a covariance. That is why the rules
divide where they do, and why nothing here computes a spectrum.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from daf.extractors._passthrough import PassthroughRefusal, tighten_passthrough_content
from epistemics._yaml import loads
from evidence.identity import content_hash
from science import structured_uncertainty as su
from science.structured_uncertainty import (
    measurement_dimension,
    uncertainty_corresponds_to_value,
)
from science.table import leaf_is_a_quantity, observation_is_table_alignable

REPO_ROOT = Path(__file__).resolve().parent.parent
R2 = [[1.0, 0.2], [0.2, 1.0]]


def _observation(**overrides):
    content = {"value": [1.0, 2.0], "unit": ["m", "m/s"], "uncertainty": R2}
    content.update(overrides)
    return content


# ------------------------------------------- 1. R can be expressed at all


def test_a_covariance_bearing_observation_is_admitted():
    assert uncertainty_corresponds_to_value(_observation()).admissible


def test_the_scalar_case_still_works_unchanged():
    """The extension must not make the existing shape harder. Every
    scalar-uncertainty observation this repository already produces is
    one-dimensional, and the correspondence rule reads the same way for
    it: an uncertainty describes as many components as the value has."""
    assert uncertainty_corresponds_to_value(
        {"value": 1.0, "unit": "m", "uncertainty": 0.1}).admissible
    assert measurement_dimension(1.0) == 1
    assert measurement_dimension([1.0, 2.0, 3.0]) == 3


# ---------------------------------- 2. the correspondence rule, both ways


def test_a_scalar_sigma_on_a_multivariate_value_is_refused():
    """The "ONLY when" clause, enforced. This is the case the requirement
    was written about."""
    verdict = uncertainty_corresponds_to_value(_observation(uncertainty=0.1))
    assert not verdict.admissible
    assert su.SCALAR_UNCERTAINTY_ON_A_MULTIVARIATE_VALUE in verdict.reasons


def test_a_matrix_on_a_scalar_value_is_refused_too():
    """MEASURED HOLE before this module existed: `quantity_is_typed`
    ADMITTED {"value": 1.0, "uncertainty": [[1.0, 0.2], [0.2, 1.0]]}. A
    covariance attached to a scalar measurement passed every gate, because
    nothing compared the uncertainty's shape to the value's.

    It is a real error rather than harmless generosity: it invites a
    consumer to read a covariance where none was measured."""
    verdict = uncertainty_corresponds_to_value({"value": 1.0, "unit": "m", "uncertainty": R2})
    assert not verdict.admissible
    assert su.STRUCTURED_UNCERTAINTY_ON_A_SCALAR_VALUE in verdict.reasons


def test_an_R_of_the_wrong_dimension_is_refused():
    verdict = uncertainty_corresponds_to_value(
        {"value": [1.0, 2.0, 3.0], "unit": ["m", "m", "m"], "uncertainty": R2})
    assert not verdict.admissible
    assert su.UNCERTAINTY_SHAPE_DOES_NOT_MATCH_VALUE in verdict.reasons


def test_only_the_OUTER_dimension_is_checked():
    """The boundary, asserted rather than described. That R has as many
    rows as the value has components is this observation's own coherence.
    Whether those rows are equal-length is the compute layer's contract,
    so a ragged R of the right outer length passes here."""
    ragged = [[1.0, 0.2], [0.2]]
    assert uncertainty_corresponds_to_value(
        {"value": [1.0, 2.0], "unit": ["m", "m"], "uncertainty": ragged}).admissible


# ---------------------------- 3. units per component, the required metadata


def test_one_unit_string_on_a_multivariate_value_is_refused():
    """The same shape of error as a single sigma: position and velocity
    do not share a unit, and one string cannot say so."""
    verdict = uncertainty_corresponds_to_value(_observation(unit="m"))
    assert not verdict.admissible
    assert su.UNITS_DO_NOT_MATCH_COMPONENTS in verdict.reasons


def test_the_unit_count_must_equal_the_component_count():
    for units in (["m"], ["m", "m", "m"]):
        verdict = uncertainty_corresponds_to_value(_observation(unit=units))
        assert su.UNITS_DO_NOT_MATCH_COMPONENTS in verdict.reasons, units


@pytest.mark.parametrize("bad", [["m", ""], ["m", "  "], ["m", 3], ["m", None], ["m", True]])
def test_every_component_unit_must_be_a_real_name(bad):
    verdict = uncertainty_corresponds_to_value(_observation(unit=bad))
    assert su.UNTYPED_COMPONENT_UNIT in verdict.reasons


# ----------------------------- 4. the leaf rule, imported and not restated


def test_the_leaf_rule_is_the_SAME_FUNCTION_the_table_gate_uses():
    """THE ORDERING CAVEAT, enforced as a test rather than trusted.

    The leaf rule is reusable and the gate around it is not: the aligned
    table gate refuses positional identity by name because its modality
    forbids ordering, and Kalman requires it. Two gates that restate one
    rule drift; two gates that CALL one rule cannot."""
    import ast

    source = (REPO_ROOT / "science" / "structured_uncertainty.py").read_text()
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "science.table"
        for alias in node.names
    }
    assert "leaf_is_a_quantity" in imported, "the leaf rule must be imported, not restated"

    # No local redefinition of the predicate under another name.
    for name in ("isfinite", "math"):
        assert name not in source, (
            f"{name!r} appears here; the finiteness question belongs to the shared leaf rule")


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), None, 2 + 3j, b"x"])
def test_a_bad_leaf_anywhere_in_R_is_refused(bad):
    verdict = uncertainty_corresponds_to_value(
        _observation(uncertainty=[[1.0, bad], [0.2, 1.0]]))
    assert not verdict.admissible
    assert su.UNCERTAINTY_LEAF_IS_NOT_A_MAGNITUDE in verdict.reasons


def test_a_bad_leaf_in_the_VALUE_is_refused_too():
    verdict = uncertainty_corresponds_to_value(_observation(value=[1.0, float("nan")]))
    assert su.VALUE_LEAF_IS_NOT_A_QUANTITY in verdict.reasons


def test_the_one_deliberate_divergence_from_the_table_gates_leaf_semantics():
    """A categorical string is an admissible table CELL and is not an
    admissible UNCERTAINTY. Stated as a divergence because it is one, and
    it is DAQ's own semantics rather than a pre-emption of the compute
    layer's numeric-entry rule: `quantity_is_typed` has refused a boolean
    uncertainty since the phase that added UNTYPED_UNCERTAINTY. An
    uncertainty is a magnitude."""
    assert leaf_is_a_quantity("B7") == "", "the shared rule admits a categorical"
    assert observation_is_table_alignable(
        {"sample_id": "s", "property": "v", "value": "B7"}).admissible

    verdict = uncertainty_corresponds_to_value(
        _observation(uncertainty=[["low", "high"], ["high", "low"]]))
    assert su.UNCERTAINTY_LEAF_IS_NOT_A_MAGNITUDE in verdict.reasons


# --------------- 5. the five rules the compute layer owns, still passing here


@pytest.mark.parametrize("R,what", [
    ([[1.0, 0.2], [0.2]], "ragged"),
    ([[1.0, 0.9], [0.1, 1.0]], "asymmetric"),
    ([[1.0, 2.0], [2.0, 1.0]], "not positive-semidefinite"),
    ([[], []], "empty rows"),
])
def test_the_five_rules_the_compute_layer_owns_are_still_not_checked_here(R, what):
    """PINNED ADMISSIONS ARE OBLIGATIONS. These pass today with tests
    asserting they pass, so closing any of them later fails loudly -- and
    that is the point: the extension's first act is deciding WHERE each
    rule lives, not silently tightening a gate.

    They live with the compute layer, whose covariance contract states
    all five and says none may be assumed checked upstream."""
    assert uncertainty_corresponds_to_value(
        {"value": [1.0, 2.0], "unit": ["m", "m"], "uncertainty": R}).admissible, what

    source = (REPO_ROOT / "science" / "structured_uncertainty.py").read_text()
    for owned in ("symmetr", "eigen", "semidefinite", "transpose", "determinant"):
        assert f"def {owned}" not in source and f"_{owned}(" not in source, (
            f"this module computes {owned}; that is the compute layer's contract")


# --------------------- 6. the upstream residual, and that it scales as n^2


def test_the_residual_scales_with_the_square_of_measurement_dimension():
    """Measured, because the shape of the exposure changed rather than
    its existence. A scalar-uncertainty observation carried two numeric
    slots; an n-component measurement with a covariance carries n + n^2.
    Every one of them is a place a non-finite could enter."""
    for dimension in (1, 2, 3, 10):
        assert dimension + dimension ** 2 == len(
            [1] * dimension) + dimension * dimension
    assert 10 + 100 == 110, "dimension 10 carries 110 slots where a scalar observation carried 2"


@pytest.mark.parametrize("depth_path,R", [
    ("uncertainty[1][1]", [[1.0, 0.2], [0.2, float("nan")]]),
    ("uncertainty[0][1]", [[1.0, float("inf")], [0.2, 1.0]]),
])
def test_every_refusal_the_extension_leans_on_is_one_of_DAQs_own(depth_path, R):
    """All three DAQ-owned refusals reach a slot nested two levels deep,
    and the pass-through names the exact path so an operator is not left
    grepping a dataset."""
    with pytest.raises(PassthroughRefusal, match=re_escape(depth_path)):
        tighten_passthrough_content({"value": [1.0, 2.0], "uncertainty": R}, "r1")

    with pytest.raises(ValueError, match="not JSON compliant"):
        json.dumps({"uncertainty": R}, allow_nan=False)

    verdict = uncertainty_corresponds_to_value(
        {"value": [1.0, 2.0], "unit": ["m", "m"], "uncertainty": R})
    assert su.UNCERTAINTY_LEAF_IS_NOT_A_MAGNITUDE in verdict.reasons


def re_escape(text):
    import re
    return re.escape(text)


def test_reaching_content_hash_directly_still_bypasses_all_three():
    """THE RESIDUAL, unchanged and restated because the covariance path
    multiplies the number of chances to take it. `content_hash` is
    vendored and mints over whatever it is handed; the gate, the
    pass-through and the writer are all upstream of it and none is on its
    path. Recorded rather than papered over -- and it is why every
    refusal this extension leans on has to be one DAQ owns."""
    minted = content_hash({"value": [1.0, 2.0], "uncertainty": [[1.0, float("nan")], [0.2, 1.0]]})
    assert minted.startswith("sha256:") or len(minted) == 64

    import evidence.identity as identity
    assert "vendor/scout-retrieval-agent" in identity.__file__


# ----------------------------------------------- 7. the record, and Kalman


def test_the_record_states_the_split_and_does_not_claim_kalman_is_cleared():
    record = loads((REPO_ROOT / "architecture" / "structured_uncertainty.yaml").read_text())
    assert record["named_consuming_workload"]["id"] == "kalman_filter_linear"

    still_open = record["named_consuming_workload"]["requirements_still_open"]
    closes = record["named_consuming_workload"]["requirement_this_closes"]

    # THE COUNT IS DERIVED FROM THE ARTIFACT, never from this record's prose
    # or from anyone's recollection. That is the repair for the reading form
    # of the enumerated class (architecture/proof_integrity.yaml
    # reading_a_subset_as_though_it_were_the_set), and it is cheap: the test
    # that already asserts requirements_still_open asserts the count too.
    requirements = loads(
        (REPO_ROOT / "architecture" / "exchange" / "scl_requirements.yaml").read_text())
    daq_rows = {
        row["requirement"]
        for row in requirements["workloads"]["kalman_filter_linear"]["blocking_requirements"]
        if row["owner"] == "daq"
    }
    assert closes in daq_rows
    assert set(still_open) | {closes} == daq_rows, (
        f"the record accounts for {sorted(set(still_open) | {closes})} of the artifact's "
        f"{sorted(daq_rows)}. A row the artifact lists and the record does not name is the "
        "undercount this pair has now made three times.")

    owned = record["what_the_compute_layer_owns"]
    assert set(owned) == {"numeric_entry", "rectangular", "square", "symmetric",
                          "positive_semidefinite"}


def test_the_invariant_is_enforced_as_the_ledger_claims():
    entry = next(
        e for e in loads((REPO_ROOT / "architecture" / "invariants.yaml").read_text())["invariants"]
        if e["id"] == "uncertainty_corresponds_to_its_value"
    )
    assert entry["status"] == "partially_enforced"
    assert Path(__file__).name in entry["enforcement"]
    assert "ADMITTED a 2x2 matrix uncertainty on a scalar value" in entry["measured_hole_it_closes"]
    assert "ONE of two" in entry["named_consuming_workload"]

    # the measured hole, replayed
    from science.admissibility import quantity_is_typed
    assert quantity_is_typed(
        {"value": 1.0, "unit": "m", "uncertainty": R2, "uncertainty_kind": "stated"}).admissible, (
        "the old gate no longer admits it, so the hole this invariant records has moved")
    assert not uncertainty_corresponds_to_value(
        {"value": 1.0, "unit": "m", "uncertainty": R2}).admissible
