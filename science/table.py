"""The aligned observation table: sample identity, variable identity, and
explicit missing-value semantics.

WHAT THIS IS FOR. The joint decision record elected `least_squares` paired
with the DAQ extension that unblocks it. Its two DAQ-owned requirements,
quoted from the compute layer's own exchange artifact:

    stable_sample_and_variable_identity
        "Each observation must carry a sample identity sufficient to align
        a response with its predictors, and a variable identity sufficient
        to know which column is which. Row position is NOT an acceptable
        identity here, because ordering is explicitly not required by this
        modality."

    explicit_missing_value_semantics
        "Missing values must be explicitly represented and their semantics
        stated, not encoded as a sentinel number or elided by dropping
        rows."

WHY NO TABLE OBJECT. A table is not a new evidence type here. It is what a
consumer can BUILD from observations that carry enough identity to be
joined -- one observation per (sample, variable) cell. Introducing a table
artifact would add a second identity system for something the existing
Observation already carries; instead this module states what an
observation must carry to be alignable, and refuses the rest.

THE TWO FAILURE SHAPES THIS GATE EXISTS TO CLOSE, both stated by the
compute layer as the consequence of leaving its requirement unmet:

  * misalignment -- "silently misaligned columns produce a well-formed fit
    of the wrong model; nothing in the numbers reveals it";
  * silent dropping -- "the residuals of a fit over a quietly smaller
    sample look entirely healthy".

Both are invisible in the output. That is why identity is checked here,
before a consumer can join on it, rather than trusted.

ELEMENT TYPES, NOT MERELY PRESENCE. This repository has now measured the
same asymmetry three times: a value admitted at the gate and failing at a
downstream consumer is worse than one refused at the gate, because the
gate refusal is loud and early and the consumer failure is silent and
late. A partially-typed table is exactly that shape -- a sample id that is
an int in one observation and a str in another joins to nothing, and
nothing says so. So this gate checks the TYPE of every identity field, not
its presence.

ABSENCE IS STRUCTURAL, NEVER A VALUE. A missing cell is expressed by the
`value` key being ABSENT together with a stated `value_absence` reason --
never by a sentinel, and NaN is a sentinel. `science.admissibility`
independently refuses non-finite quantities for the same rule, so the two
gates agree: nothing in the numeric range can ever mean "missing".

BOUNDARY: pure. No pool access, no `daf` import, no network, no clock, no
mutation. Reads a Mapping, returns a verdict.
"""

from __future__ import annotations

import math
from typing import List, Mapping, Tuple

from science.admissibility import Admissibility

# Why a cell has no value. Every member states something different about
# the world; none of them is a number, and none is a default.
NOT_MEASURED = "not_measured"  # the instrument was not run for this cell
BELOW_DETECTION = "below_detection"  # run, and the quantity was under the limit
ABOVE_RANGE = "above_range"  # run, and the quantity exceeded the instrument
WITHHELD = "withheld"  # the source has it and did not release it
LOST_IN_ACQUISITION = "lost_in_acquisition"  # DAQ had it and did not keep it
ABSENCE_REASONS = (NOT_MEASURED, BELOW_DETECTION, ABOVE_RANGE, WITHHELD, LOST_IN_ACQUISITION)

MISSING_SAMPLE_IDENTITY = "MISSING_SAMPLE_IDENTITY"
UNTYPED_SAMPLE_IDENTITY = "UNTYPED_SAMPLE_IDENTITY"
MISSING_VARIABLE_IDENTITY = "MISSING_VARIABLE_IDENTITY"
UNTYPED_VARIABLE_IDENTITY = "UNTYPED_VARIABLE_IDENTITY"
MISSING_ABSENCE_REASON = "MISSING_ABSENCE_REASON"
UNKNOWN_ABSENCE_REASON = "UNKNOWN_ABSENCE_REASON"
CONDITION_KEYS_ARE_NOT_IDENTIFIERS = "CONDITION_KEYS_ARE_NOT_IDENTIFIERS"
CONDITION_KEY_SHADOWS_AN_IDENTITY = "CONDITION_KEY_SHADOWS_AN_IDENTITY"
VALUE_AND_ABSENCE_BOTH_PRESENT = "VALUE_AND_ABSENCE_BOTH_PRESENT"
SENTINEL_ENCODED_ABSENCE = "SENTINEL_ENCODED_ABSENCE"
POSITIONAL_IDENTITY_IS_NOT_IDENTITY = "POSITIONAL_IDENTITY_IS_NOT_IDENTITY"

SAMPLE_ID = "sample_id"
VARIABLE = "variable"
VALUE_ABSENCE = "value_absence"
CONDITIONS = "conditions"


def _identity_is_typed(content: Mapping[str, object], key: str, missing: str, untyped: str) -> Tuple[str, ...]:
    """An identity must be a non-empty string. Measured reason for the
    type check rather than a presence check: an int sample id in one
    observation and the str form of the same number in another are
    DIFFERENT join keys, so the table silently splits into two and the
    fit is computed over half the rows it should have been."""
    if key not in content:
        return (missing,)
    value = content[key]
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        return (untyped,)
    return ()


def _conditions_are_recoverable(content: Mapping[str, object]) -> Tuple[str, ...]:
    """The workload's THIRD DAQ-owned requirement, quoted:
    "conditions_that_distinguish_samples_must_be_recoverable_as_predictors
    _or_strata".

    What is and is not DAQ's part of it. Whether a given condition
    becomes a predictor column or a stratum is a MODELLING assertion --
    the same artifact says "the choice of design matrix / basis functions
    is a modelling assertion, not an observation" -- so DAQ must not
    decide it and this function does not. DAQ's part is that the
    conditions are carried, and carried under stable identifiers a
    consumer can join on. A condition keyed by something that is not a
    stable name is not recoverable as anything.

    Conditions are OPTIONAL here. `no_context_free_property` requires
    them for a canonical property assertion and refuses their absence
    loudly; this gate answers a different question and does not restate
    that one."""
    if CONDITIONS not in content:
        return ()
    conditions = content[CONDITIONS]
    if not isinstance(conditions, Mapping):
        return (CONDITION_KEYS_ARE_NOT_IDENTIFIERS,)

    reasons = []
    if any(not isinstance(key, str) or not key.strip() for key in conditions):
        reasons.append(CONDITION_KEYS_ARE_NOT_IDENTIFIERS)
    # A condition named `variable` or `sample_id` collides with the
    # table's own identity columns once it is lifted into a predictor,
    # and the collision is silent -- the consumer joins on one and reads
    # the other. Refused rather than renamed, because renaming a
    # source's own vocabulary is not DAQ's to do.
    if {SAMPLE_ID, VARIABLE, VALUE_ABSENCE} & set(conditions):
        reasons.append(CONDITION_KEY_SHADOWS_AN_IDENTITY)
    return tuple(reasons)


def observation_is_table_alignable(content: Mapping[str, object]) -> Admissibility:
    """Whether one observation carries enough identity to be joined into
    an aligned table, and states its absence explicitly if it has no
    value.

    This does NOT subsume `no_context_free_property`. An observation may
    be alignable and still inadmissible as a canonical property
    assertion, and the reverse. The two gates answer different
    questions and are applied independently."""
    reasons: List[str] = []

    reasons.extend(_identity_is_typed(content, SAMPLE_ID, MISSING_SAMPLE_IDENTITY, UNTYPED_SAMPLE_IDENTITY))
    reasons.extend(_identity_is_typed(content, VARIABLE, MISSING_VARIABLE_IDENTITY, UNTYPED_VARIABLE_IDENTITY))
    reasons.extend(_conditions_are_recoverable(content))

    # Row position is explicitly NOT an identity for this modality --
    # ordering is not required of it, so an index cannot align anything.
    # Refused by name rather than ignored, so a caller that supplies one
    # learns why it does not count.
    if "row_index" in content or "position" in content:
        reasons.append(POSITIONAL_IDENTITY_IS_NOT_IDENTITY)

    has_value = "value" in content and content["value"] is not None
    has_absence = VALUE_ABSENCE in content

    if has_value and has_absence:
        # Both present is not a merge conflict to resolve; it is a claim
        # that the cell simultaneously has and has not been measured.
        reasons.append(VALUE_AND_ABSENCE_BOTH_PRESENT)
    elif has_value:
        value = content["value"]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value):
            # The sentinel the requirement forbids, named as what it is.
            reasons.append(SENTINEL_ENCODED_ABSENCE)
    elif has_absence:
        absence = content[VALUE_ABSENCE]
        if not isinstance(absence, str) or absence not in ABSENCE_REASONS:
            reasons.append(UNKNOWN_ABSENCE_REASON)
    else:
        # Neither a value nor a stated absence. This is the row-dropping
        # case seen from the other side: the cell simply is not here, and
        # a consumer cannot tell a gap from a cell that was never part of
        # the design.
        reasons.append(MISSING_ABSENCE_REASON)

    return Admissibility(admissible=not reasons, reasons=tuple(reasons))


def is_explicitly_absent(content: Mapping[str, object]) -> bool:
    """True when this cell states a reason for having no value. Distinct
    from "has no value", which is what row-dropping produces."""
    return VALUE_ABSENCE in content and content.get("value") is None
