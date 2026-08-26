"""A measurement covariance R, admitted into an observation.

WHAT THIS CLOSES. `structured_measurement_uncertainty`, quoted from the
compute layer's exchange artifact:

    "DAQ must be able to express a measurement covariance R, not only a
    scalar uncertainty per observation. A scalar is sufficient ONLY when
    the measurement is genuinely 1-D and uncorrelated."

Two halves, and the second is the one with teeth. Expressing R is a
representation change. Enforcing "a scalar is sufficient ONLY when the
measurement is 1-D" is a CORRESPONDENCE rule between the value and its
uncertainty, and it is the rule that makes a scalar sigma on a
three-component measurement refusable instead of merely unfortunate.

WHAT DAQ OWNS HERE, AND WHAT IT DOES NOT. The compute layer's covariance
contract states five rules it owns outright: numeric entry, rectangular,
square, symmetric, positive-semidefinite. None of them is checked here,
and their absence is DECLARED rather than accidental -- see
architecture/kalman_framing.yaml shape_rules_the_gate_formally_declines.
The split is not arbitrary:

    DAQ  -- is this OBSERVATION internally coherent? Does its uncertainty
            correspond to its value, do its units correspond to its
            components, is every number it carries a number?
    SCL  -- is this MATRIX a covariance? Shape, symmetry, spectrum.

A matrix that is ragged, asymmetric or indefinite is a perfectly coherent
OBSERVATION of something that is not a covariance. That distinction is
why the rules divide where they do, and why nothing here computes a
spectrum.

THE LEAF RULE IS IMPORTED, NOT RESTATED. `science.table.leaf_is_a_quantity`
is the same function the aligned-observation gate uses, called here rather
than reimplemented. The ordering caveat from the Kalman framing is that
the leaf rule is reusable and the gate around it is not -- that gate
refuses positional identity by name because its modality forbids ordering,
and Kalman requires it. Two gates, one definition of what a quantity is.

ONE DELIBERATE DIVERGENCE from the table gate's leaf semantics, stated
because it is a divergence: a categorical string is an admissible table
CELL and is not an admissible UNCERTAINTY. That is not this module
pre-empting the compute layer's numeric-entry rule; it is DAQ's own
long-standing semantics, the same one under which `quantity_is_typed`
already refuses a boolean uncertainty. An uncertainty is a magnitude.

BOUNDARY: pure. No pool access, no `daf` import, no network, no clock, no
mutation.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Sequence, Tuple

from science.admissibility import Admissibility
from science.table import leaf_is_a_quantity

UNCERTAINTY_SHAPE_DOES_NOT_MATCH_VALUE = "UNCERTAINTY_SHAPE_DOES_NOT_MATCH_VALUE"
SCALAR_UNCERTAINTY_ON_A_MULTIVARIATE_VALUE = "SCALAR_UNCERTAINTY_ON_A_MULTIVARIATE_VALUE"
STRUCTURED_UNCERTAINTY_ON_A_SCALAR_VALUE = "STRUCTURED_UNCERTAINTY_ON_A_SCALAR_VALUE"
UNCERTAINTY_LEAF_IS_NOT_A_MAGNITUDE = "UNCERTAINTY_LEAF_IS_NOT_A_MAGNITUDE"
UNITS_DO_NOT_MATCH_COMPONENTS = "UNITS_DO_NOT_MATCH_COMPONENTS"
UNTYPED_COMPONENT_UNIT = "UNTYPED_COMPONENT_UNIT"
VALUE_LEAF_IS_NOT_A_QUANTITY = "VALUE_LEAF_IS_NOT_A_QUANTITY"


def _is_sequence(value: Any) -> bool:
    """A list or tuple, and deliberately not a str or bytes -- both are
    sequences in Python and neither is a measurement vector."""
    return isinstance(value, (list, tuple))


def measurement_dimension(value: Any) -> int:
    """1 for a scalar, n for an n-component vector.

    A scalar measurement has dimension one rather than dimension zero, so
    the correspondence rule below reads the same way for both: an
    uncertainty describes as many components as the value has."""
    return len(value) if _is_sequence(value) else 1


def _leaf_reasons(node: Any, refuse_categorical: bool, code: str) -> Tuple[str, ...]:
    """Every leaf of a possibly-nested structure, held to the leaf rule.

    Depth is unbounded on purpose. A covariance is two levels, but DAQ
    does not decide how many levels a structure has -- that is a shape
    question -- so the traversal asks the question at whatever depth it
    finds a leaf."""
    if _is_sequence(node) or isinstance(node, Mapping):
        items: Sequence[Any] = list(node.values()) if isinstance(node, Mapping) else list(node)
        reasons: List[str] = []
        for item in items:
            reasons.extend(_leaf_reasons(item, refuse_categorical, code))
        return tuple(dict.fromkeys(reasons))

    reason = leaf_is_a_quantity(node)
    if reason:
        return (code, reason)
    if refuse_categorical and isinstance(node, str):
        # The stated divergence: the shared leaf rule admits a categorical
        # because a categorical COLUMN is a real column. An uncertainty is
        # a magnitude, and DAQ has refused non-magnitude uncertainties
        # since the phase that added UNTYPED_UNCERTAINTY.
        return (code, UNCERTAINTY_LEAF_IS_NOT_A_MAGNITUDE)
    return ()


def uncertainty_corresponds_to_value(content: Mapping[str, object]) -> Admissibility:
    """Whether an observation's uncertainty and units correspond to its
    value, and whether every number it carries is one.

    Checks nothing about whether the uncertainty is a valid covariance.
    A ragged, asymmetric or indefinite matrix passes here and is refused
    by the compute layer, which owns that contract."""
    reasons: List[str] = []

    if "value" not in content:
        return Admissibility(admissible=True, reasons=())
    value = content["value"]
    uncertainty = content.get("uncertainty")

    reasons.extend(_leaf_reasons(value, False, VALUE_LEAF_IS_NOT_A_QUANTITY))
    if uncertainty is not None:
        reasons.extend(_leaf_reasons(uncertainty, True, UNCERTAINTY_LEAF_IS_NOT_A_MAGNITUDE))

    dimension = measurement_dimension(value)
    structured = _is_sequence(uncertainty)

    if uncertainty is None:
        pass
    elif dimension > 1 and not structured:
        # THE RULE WITH TEETH. "A scalar is sufficient ONLY when the
        # measurement is genuinely 1-D and uncorrelated." A single sigma
        # over a three-component measurement does not merely lose the
        # off-diagonals; it asserts an independence nobody stated.
        reasons.append(SCALAR_UNCERTAINTY_ON_A_MULTIVARIATE_VALUE)
    elif dimension == 1 and structured:
        # The mirror, and it is a real error rather than harmless
        # generosity: a 1-by-1 matrix on a scalar measurement invites a
        # consumer to read a covariance where none was measured.
        reasons.append(STRUCTURED_UNCERTAINTY_ON_A_SCALAR_VALUE)
    elif structured and len(list(uncertainty)) != dimension:  # type: ignore[call-overload]
        # OUTER length only. Whether the rows are equal-length, square,
        # symmetric or PSD is the compute layer's contract; that R
        # describes as many components as the value HAS is this
        # observation's own coherence.
        reasons.append(UNCERTAINTY_SHAPE_DOES_NOT_MATCH_VALUE)

    reasons.extend(_unit_reasons(content, dimension))
    return Admissibility(admissible=not reasons, reasons=tuple(dict.fromkeys(reasons)))


def _unit_reasons(content: Mapping[str, object], dimension: int) -> Tuple[str, ...]:
    """`units_per_measurement_component`, which the compute layer records
    as required metadata for this workload.

    A single unit string on a multivariate measurement is the same shape
    of error as a single sigma: position and velocity do not share a unit,
    and one string cannot say so."""
    unit = content.get("unit")
    if unit is None:
        return ()

    units: List[Any] = list(unit) if _is_sequence(unit) else [unit]  # type: ignore[call-overload]
    if _is_sequence(unit) and len(units) != dimension:
        return (UNITS_DO_NOT_MATCH_COMPONENTS,)
    if not _is_sequence(unit) and dimension > 1:
        return (UNITS_DO_NOT_MATCH_COMPONENTS,)
    for entry in units:
        if not isinstance(entry, str) or not entry.strip():
            return (UNTYPED_COMPONENT_UNIT,)
    return ()
