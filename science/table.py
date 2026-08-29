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
BOOLEAN_IS_NOT_A_QUANTITY = "BOOLEAN_IS_NOT_A_QUANTITY"
NUMERIC_LOOKING_STRING_CELL = "NUMERIC_LOOKING_STRING_CELL"
COMPOSITE_CELL_LEAF_IS_NOT_A_QUANTITY = "COMPOSITE_CELL_LEAF_IS_NOT_A_QUANTITY"
CELL_TYPE_IS_NOT_A_QUANTITY = "CELL_TYPE_IS_NOT_A_QUANTITY"
POSITIONAL_IDENTITY_IS_NOT_IDENTITY = "POSITIONAL_IDENTITY_IS_NOT_IDENTITY"

SAMPLE_ID = "sample_id"

# THE VARIABLE IDENTITY IS `property`, AND IT IS NOT THIS GATE'S TO NAME.
#
# `variable identity` is this module's term and `column` is deliberately
# avoided in every DEFINED NAME here: naming things after a table's
# columns would be this gate taking a position on predictor-versus-stratum,
# which it must not. That rule is asserted by
# test_the_gate_does_not_decide_predictor_versus_stratum -- and it caught
# this very reconciliation, whose first draft defined RETIRED_COLUMN_KEYS
# and COLUMN_IDENTITY_UNDER_A_RETIRED_NAME.
#
# This gate originally read `variable` while science/admissibility.py's
# no_context_free_property read `property`. Both gates were correct and
# neither read the other's key, so an extractor satisfied both by writing
# the key TWICE -- and content declaring `variable: mn` alongside
# `property: mw` passed BOTH GATES with nothing anywhere owning the
# relation between two names for one concept.
#
# The direction of the reconciliation was not a preference. Measured:
#
#   * materials.analysis.analyze FILTERS on content["property"]
#     (_matches_property) before grouping, and _comparison_context
#     excludes `property` precisely BECAUSE that filter already fixed it.
#     That code is inside the unmodifiable core. An observation without
#     `property` is not merely inconvenient to find; analyze cannot see it.
#   * DAQ's own published capability artifact already states the key:
#     "A single Observation carries one `property` name and one scalar
#     `value`". No published artifact ever named `variable` as a KEY --
#     every occurrence is the English word for the concept.
#   * four extractors already emit `property`; `variable` existed only in
#     this module, in replicate_pairing, and in the GPC extractor.
#
# So `property` is the column identity and `variable` was a synonym this
# module introduced. Retired here.
#
# WHY THIS IS NOT ONE GATE REACHING INTO ANOTHER'S SUBJECT. Joinability is
# this gate's subject; interpretability is the other's. WHICH QUANTITY is
# a referent BOTH need and neither owns -- so unifying the name does not
# move a subject, it removes a second name for a shared referent. And it
# dissolves the unowned relation rather than assigning it an owner: with
# one key there is no relation between two keys to own, so no third gate
# is needed. A third gate would have been the repair if the two keys had
# meant DIFFERENT things.
VARIABLE = "property"

# A retired synonym still PRESENT in content is the two-encodings shape,
# and it is silent: `variable` would simply become an ordinary content
# key, entering the comparison context as though it were a condition.
# Refused by name so the migration cannot half-happen.
RETIRED_IDENTITY_KEYS = ("variable",)
VARIABLE_IDENTITY_UNDER_A_RETIRED_NAME = "VARIABLE_IDENTITY_UNDER_A_RETIRED_NAME"

VALUE_ABSENCE = "value_absence"
CONDITIONS = "conditions"


def _looks_numeric(text: str) -> bool:
    """Whether a string cell would coerce to a number silently.

    The test is `float()` itself rather than a pattern, because `float()`
    is what a consumer actually calls -- so this asks the real question
    ("would this coerce without complaint?") instead of approximating it.
    Non-finite spellings are included deliberately: `"nan"` and `"inf"`
    coerce, and a sentinel absence smuggled in as a string is the same
    forbidden encoding wearing a different type."""
    try:
        float(text)
    except (TypeError, ValueError):
        return False
    return True



def leaf_is_a_quantity(value: object) -> str:
    """A leaf inside a composite cell must BE a finite real number.

    PUBLIC, deliberately, and it is the only part of this module the
    covariance extension reuses. The ordering caveat that came out of the
    Kalman framing is that THE LEAF RULE IS REUSABLE AND THE GATE AROUND
    IT IS NOT -- this gate refuses positional identity by name because
    least_squares forbids ordering, and Kalman requires it. So a second
    gate written for the covariance modality must import THIS function
    rather than restate its rule, or the two drift and the pair ends up
    with two definitions of what a quantity is.

    STATED AS THE PROPERTY, NOT AS A LIST OF WHAT IS FORBIDDEN, and the
    rewrite is the point. This function used to name three bad things --
    bool, numeric-looking string, non-finite -- and return "" for
    everything else. Measured against fifteen leaf types, that admitted
    None, a plain string, bytes, a complex number, a Decimal, a Fraction,
    an empty list, an empty dict and a set, every one of them inside what
    a covariance extension would read as a matrix entry.

    That is coverage-by-enumeration (architecture/proof_integrity.yaml):
    the check named what it looked for instead of asserting the property,
    so it was correct exactly until a type nobody listed arrived, and
    silent at that moment. The bool repair itself was an instance -- it
    added one name to the list and left the class open.

    The specific reasons are still returned where they apply, because
    "this is a bool" and "this is a numeric-looking string" tell a caller
    more than "wrong type". They are now the SPECIALISATIONS of a refusal
    that has already been decided, rather than the conditions for one.

    Scope, deliberately narrow: this says a matrix entry must be a
    number. It says nothing about shape -- raggedness, dimensionality,
    symmetry and positive-semidefiniteness remain the covariance
    extension's contract to define, and deciding them here would pre-empt
    the joint record."""
    if isinstance(value, bool):
        # before the int check: isinstance(True, int) is True
        return BOOLEAN_IS_NOT_A_QUANTITY
    if isinstance(value, str):
        # A CATEGORICAL string stays admitted, here as in the scalar
        # branch. THIS WAS TRIED THE OTHER WAY AND REVERTED, and the
        # reason is worth keeping: refusing it as a leaf would say a
        # matrix entry must be numeric, which is a COVARIANCE rule, and
        # this gate answers alignability rather than fittability. The
        # existing property test -- that the scalar and composite paths
        # apply ONE rule set -- caught the over-reach immediately.
        #
        # So "a matrix entry must be a number" is NOT a rule this gate
        # holds, and the covariance extension cannot assume it does. That
        # obligation is the extension's, and it is recorded rather than
        # quietly satisfied here.
        return NUMERIC_LOOKING_STRING_CELL if _looks_numeric(value) else ""
    if not isinstance(value, (int, float)):
        return CELL_TYPE_IS_NOT_A_QUANTITY
    if not math.isfinite(value):
        return SENTINEL_ENCODED_ABSENCE
    return ""


def _composite_cell_reasons(value: object) -> Tuple[str, ...]:
    """MEASURED HOLE, closed here. Every cell rule this gate enforces --
    no bool, no sentinel, no numeric-looking string -- ran only when the
    cell was a SCALAR. The moment a cell was a list or a mapping, none of
    them ran: a vector carrying NaN, a vector carrying a bool, and a
    MATRIX carrying a bool were all admissible.

    That last one is the exact case the covariance work was warned about
    -- a covariance is a matrix of cells, and a bool in one passes a
    positive-semidefiniteness check while meaning nothing. Refusing a
    bool AS the cell did nothing about a bool INSIDE it, so the rule was
    closed on one axis and open on the other.

    WHAT THIS DOES NOT DECIDE. Shape is not touched: raggedness,
    dimensionality, symmetry and positive-semidefiniteness are the
    covariance extension's contract to define, and inventing them here
    would pre-empt a decision that belongs in the joint record. This
    applies only the rules already decided, at every depth."""
    if isinstance(value, Mapping):
        items: Tuple[object, ...] = tuple(value.values())
    elif isinstance(value, (list, tuple)):
        items = tuple(value)
    else:
        return ()

    if not items:
        # AN EMPTY COMPOSITE PASSES, at any depth, for the reason a scan
        # over an empty domain passes: there is nothing to find a fault
        # in. THIS WAS TRIED AS A REFUSAL AND REVERTED. `value: []` is a
        # zero-length quantity, and length is SHAPE, which this gate
        # deliberately does not decide (see
        # test_shape_is_deliberately_not_decided_here). Refusing `[]`
        # nested but not bare would have been a depth rule, which is shape
        # by another name.
        #
        # Recorded rather than closed: an empty row inside a covariance is
        # admissible here and means nothing, and that is the covariance
        # extension's obligation, not this gate's.
        return ()

    reasons: List[str] = []
    for item in items:
        if isinstance(item, (Mapping, list, tuple)):
            reasons.extend(_composite_cell_reasons(item))
            continue
        leaf = leaf_is_a_quantity(item)
        if leaf:
            reasons.append(COMPOSITE_CELL_LEAF_IS_NOT_A_QUANTITY)
            reasons.append(leaf)
    # Deduplicated, order-preserving: one bad leaf and fifty bad leaves are
    # the same verdict, and a fifty-entry reason list is unreadable.
    seen = []
    for reason in reasons:
        if reason not in seen:
            seen.append(reason)
    return tuple(seen)


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

    reasons: List[str] = []
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

    # The reconciled key is `property`; a retired synonym alongside it is
    # two encodings of one meaning and is refused at the reader that can
    # still see both. Named separately from the missing/untyped codes
    # because it is a different fault: the identity is present, under a
    # name that no longer denotes it.
    if any(key in content for key in RETIRED_IDENTITY_KEYS):
        reasons.append(VARIABLE_IDENTITY_UNDER_A_RETIRED_NAME)

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
        if isinstance(value, (Mapping, list, tuple)):
            reasons.extend(_composite_cell_reasons(value))
        elif isinstance(value, bool):
            # MEASURED: a bool cell was admissible here. `isinstance(True,
            # int)` is True in Python, so a bool passes every numeric check
            # that does not exclude it by name -- and downstream it means
            # something nobody asserted: `sum([True, True, False])` is 2, so
            # a bool column silently becomes a count.
            #
            # Refusing it is also the modelling boundary, not just a type
            # check. If the source means an indicator, encoding it as 0/1 is
            # a DESIGN MATRIX decision, and the requirements artifact says
            # the choice of design matrix is a modelling assertion rather
            # than an observation. DAQ must not make it silently by letting
            # `True` arrive where a number is read.
            #
            # This is the surface a covariance inherits directly: a
            # covariance is a matrix of cells, and a bool cell passes a
            # positive-semidefiniteness check while meaning nothing.
            reasons.append(BOOLEAN_IS_NOT_A_QUANTITY)
        elif isinstance(value, str) and _looks_numeric(value):
            # THE DECISION a concurrent session left to this gate's author,
            # made here rather than inherited. The question was whether a
            # STRING cell is alignable, given that this gate answers
            # alignability and not fittability.
            #
            # Answer: a categorical string cell IS alignable and is
            # admitted -- a categorical column is a real column and the
            # workload's own requirement asks for identity, not for
            # numerics. But a NUMERIC-LOOKING string is refused, and the
            # dividing line is measured rather than chosen by taste:
            #
            #     True     float() -> 1.0   SILENT   sum -> 2   SILENT
            #     "1.5"    float() -> 1.5   SILENT   sum RAISES LOUD
            #     "B7"     float() RAISES   LOUD     sum RAISES LOUD
            #
            # `True` is silent on both paths and is refused above. "B7" is
            # loud on both and is admitted. "1.5" coerces silently under
            # float() -- so a column holding 1.5 in one observation and
            # "1.5" in another MERGES under a coercing consumer and SPLITS
            # under a strict one, and neither says anything.
            #
            # That is the implicit-typing defect one layer in: the same
            # class the canonical YAML rule closed by always-quoting, where
            # a value's type depended on who read it. Refusing it here is
            # the same repair applied to a cell.
            reasons.append(NUMERIC_LOOKING_STRING_CELL)
        elif isinstance(value, (int, float)) and not math.isfinite(value):
            # The sentinel the requirement forbids, named as what it is.
            reasons.append(SENTINEL_ENCODED_ABSENCE)
        elif not isinstance(value, (int, float, str)):
            # THE SAME ENUMERATION DEFECT THE LEAF RULE HAD, on this axis.
            # The branches above name bool, numeric-looking string and
            # non-finite; everything unnamed fell through as admissible.
            # Measured: bytes, a complex number, a Decimal, a Fraction and
            # a set were all admissible as CELLS.
            #
            # The categorical-string decision above is PRESERVED, not
            # reversed: `str` is listed here precisely so a non-numeric
            # string keeps reaching the admitted path. That decision was
            # made deliberately, with the coercion table that justifies
            # it, and this repair is about the types nobody decided
            # anything about.
            reasons.append(CELL_TYPE_IS_NOT_A_QUANTITY)
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
