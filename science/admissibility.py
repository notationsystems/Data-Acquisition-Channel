"""SYNC_ADDENDUM §6.3 -- a property value is not a scalar.

    no_context_free_property : a property value is inadmissible without
                               method, conditions and a typed quantity
    quantity_is_typed        : every numeric value carries unit,
                               uncertainty and uncertainty_kind

WHY THIS IS A REAL GAP HERE, not an imported requirement. Inspected:
`daf/extractors/graph_dataset.py` passes any record through verbatim, so
`{"property": "tensile_strength", "value": 78, "unit": "MPa"}` is admitted
today with no method, no conditions and no uncertainty. Phase Q's NOAA
extractor does better -- it carries `sigma`, `datum`, `measurement_time`
-- but nothing requires it. Two measurements of "the same" property taken
by different methods or at different rates are two facts, and bare
scalars let the system compare them as one.

"AT INGEST" IS NOT ACHIEVABLE HERE, AND IS NOT FAKED. §6.3 says bare
scalars are "rejected at ingest". Ingest in this repository is
`scout.pipeline.run_scout`, inside the vendored submodule that is never
modified (`daf/_vendor.py`). So these are ADMISSIBILITY validators the
scientific layer applies to already-admitted evidence, not an ingest
gate. The distinction is load-bearing and is stated rather than blurred:
inadmissible evidence still exists in the pool; it is refused for
canonical assertion.

UNCERTAINTY_KIND `absent` IS EXPLICIT ON PURPOSE. §6.3's point: "the
source reported no error" and "we lost it during ingest" are different
facts. `absent` is permitted and must be declared; a missing
`uncertainty_kind` is not the same thing and is refused.

BOUNDARY: pure. No `EvidencePool` access, no `daf` import, no network, no
clock, no mutation. These functions read a `Mapping` and return a
verdict; nothing acts on that verdict automatically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Tuple

# `uncertainty_kind` values. `absent` is a real, declarable answer --
# it says the source reported no error -- and is distinct from the field
# being missing, which says nothing at all.
STATED = "stated"
ESTIMATED = "estimated"
PROPAGATED = "propagated"
ABSENT = "absent"
UNCERTAINTY_KINDS = (STATED, ESTIMATED, PROPAGATED, ABSENT)

MISSING_PROPERTY = "MISSING_PROPERTY"
MISSING_VALUE = "MISSING_VALUE"
MISSING_METHOD = "MISSING_METHOD"
MISSING_CONDITIONS = "MISSING_CONDITIONS"
UNTYPED_QUANTITY = "UNTYPED_QUANTITY"
MISSING_UNIT = "MISSING_UNIT"
MISSING_UNCERTAINTY = "MISSING_UNCERTAINTY"
MISSING_UNCERTAINTY_KIND = "MISSING_UNCERTAINTY_KIND"
UNKNOWN_UNCERTAINTY_KIND = "UNKNOWN_UNCERTAINTY_KIND"
NON_FINITE_QUANTITY = "NON_FINITE_QUANTITY"
NON_FINITE_UNCERTAINTY = "NON_FINITE_UNCERTAINTY"
UNTYPED_UNCERTAINTY = "UNTYPED_UNCERTAINTY"


@dataclass(frozen=True)
class Admissibility:
    """Whether one content mapping may be asserted canonically, and every
    reason it may not. Reasons are sorted so two equal verdicts compare
    equal regardless of check order."""

    admissible: bool
    reasons: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(self.reasons)))


def quantity_is_typed(content: Mapping[str, object]) -> Admissibility:
    """Every numeric value carries `unit`, `uncertainty` and
    `uncertainty_kind`.

    `uncertainty` may be `None` exactly when `uncertainty_kind` is
    `absent`; any other combination is refused, because a null magnitude
    with a substantive kind is a lost value pretending to be a declared
    one."""
    reasons = []

    value = content.get("value")
    if value is None:
        reasons.append(MISSING_VALUE)
    elif not isinstance(value, (int, float)) or isinstance(value, bool):
        reasons.append(UNTYPED_QUANTITY)
    elif not math.isfinite(value):
        # A SENTINEL-ENCODED ABSENCE, refused here rather than downstream.
        # NaN and the infinities are instances of float, so every
        # isinstance check in this file passed them until now: measured,
        # a NaN value was ADMISSIBLE through the full gate. Three things
        # then went wrong quietly. `evidence.identity.content_hash`
        # serialized it as bare `NaN`, which is not valid strict JSON, so
        # the Observation's id was computed over bytes no conformant
        # reader in another language accepts. `FilesystemEvidenceStore`
        # persisted that literal to disk. And `nan != nan`, so the value
        # was not equal to itself after a round trip, which silently
        # breaks any comparison built on it.
        #
        # "Missing" must never be expressible as an in-range value. That
        # is this repository's fourth instance of the same rule --
        # uncertainty_kind's explicit `absent`, the transform's
        # has_sample_spacing flag rather than a defaulted dt, and now
        # this -- and it is the one place the rule was not yet enforced.
        reasons.append(NON_FINITE_QUANTITY)

    if not content.get("unit"):
        reasons.append(MISSING_UNIT)

    kind = content.get("uncertainty_kind")
    if kind is None:
        reasons.append(MISSING_UNCERTAINTY_KIND)
    elif kind not in UNCERTAINTY_KINDS:
        reasons.append(UNKNOWN_UNCERTAINTY_KIND)
    elif kind != ABSENT and content.get("uncertainty") is None:
        reasons.append(MISSING_UNCERTAINTY)

    # An infinite uncertainty is not "unknown". `uncertainty_kind: absent`
    # is how this repository says unknown, and has been since the phase
    # that introduced it. Letting infinity mean it would be a competing,
    # in-range encoding of exactly the fact the explicit vocabulary exists
    # to carry -- so it gets its own reason code rather than being folded
    # into NON_FINITE_QUANTITY, because it is a different claim.
    uncertainty = content.get("uncertainty")
    if isinstance(uncertainty, bool):
        # `isinstance(True, int)` is True, so a bool satisfied every
        # numeric check here and a bool uncertainty was ADMISSIBLE --
        # measured. It is not a magnitude: True is not "one unit of
        # error", and there is no unit in which it would be.
        reasons.append(UNTYPED_UNCERTAINTY)
    elif isinstance(uncertainty, (int, float)) and not math.isfinite(uncertainty):
        reasons.append(NON_FINITE_UNCERTAINTY)

    return Admissibility(admissible=not reasons, reasons=tuple(reasons))


def no_context_free_property(content: Mapping[str, object]) -> Admissibility:
    """A property value is inadmissible without `property`, `method`,
    non-empty `conditions`, and a typed quantity.

    `conditions` must be a non-empty mapping: an empty one asserts that
    the measurement was condition-independent, which is a claim almost no
    real measurement can make, and an absent one asserts nothing at all.
    Both are refused so the difference never has to be guessed."""
    reasons = []

    if not content.get("property"):
        reasons.append(MISSING_PROPERTY)
    if not content.get("method"):
        reasons.append(MISSING_METHOD)

    conditions = content.get("conditions")
    if not isinstance(conditions, Mapping) or not conditions:
        reasons.append(MISSING_CONDITIONS)

    quantity = quantity_is_typed(content)
    return Admissibility(
        admissible=not reasons and quantity.admissible,
        reasons=tuple(reasons) + quantity.reasons,
    )
