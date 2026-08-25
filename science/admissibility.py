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

    if not content.get("unit"):
        reasons.append(MISSING_UNIT)

    kind = content.get("uncertainty_kind")
    if kind is None:
        reasons.append(MISSING_UNCERTAINTY_KIND)
    elif kind not in UNCERTAINTY_KINDS:
        reasons.append(UNKNOWN_UNCERTAINTY_KIND)
    elif kind != ABSENT and content.get("uncertainty") is None:
        reasons.append(MISSING_UNCERTAINTY)

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
