"""`diagnose_information_gap(state, candidate, iteration) -> Optional[InformationGap]`
-- the seam between "what this scientific state cannot resolve" and
"what evidence would reduce it".

WHY THIS EXISTS, measured rather than assumed. Walking a real trajectory
S0 -> S1 -> S2 and reading both existing machineries at each state gives:

    state  n  estimate_status     gap_category           expected_information_gain
    S0     0  NOT_DETERMINABLE    MEASUREMENT_CONFLICT   NOT_DETERMINABLE
    S1     1  NOT_DETERMINABLE    MEASUREMENT_CONFLICT   NOT_DETERMINABLE
    S2     2  ESTIMATED (16.0)    MEASUREMENT_CONFLICT   NOT_DETERMINABLE

Two independent axes, with different anchors:

  * `materials.information.estimate_information_value` +
    `ModelStateInformationValueModel` answer whether THE MODEL can resolve
    a cell. That moves with the state (NOT_DETERMINABLE -> ESTIMATED at
    n=2).
  * `materials.value.CandidateInformationValue.gap_category` answers what
    THE EVIDENCE fails to establish against the criteria. It is computed
    from a `MaterialsIteration` at one evidence version, so it does NOT
    move with the model state -- it is constant across the trajectory
    above, still MEASUREMENT_CONFLICT at S2 where the model is already
    determinate.

Nothing joined them, and `InformationValueEstimate` carries the state
only inside `model_name` as the string `"model_state:<id>"` -- so "which
state does this gap belong to?" was answerable only by splitting a
string. Those two facts are the whole justification for this module; it
adds no new mathematics and no new classification vocabulary, reusing
`materials.information`'s own `ESTIMATED`/`NOT_DETERMINABLE` and
`materials.value`'s own categories verbatim.

THE THREE THINGS THIS MODULE KEEPS SEPARATE (Phase T sec.5), because the
table above proves they are not equivalent:

  A. EVIDENCE ABSENCE -- "we have not observed X". Already
     `CandidateInformationValue.gap_category` / `.current_status`, and
     already spelled out as `EvidenceRequirement`s. Surfaced here as
     `ABSENT_EVIDENCE`, never re-derived.
  B. STATE UNCERTAINTY -- "the current model cannot resolve X". Already
     `InformationValueEstimate.estimate_status`. Surfaced here as
     `UNCERTAIN_STATE`.
  C. ACQUISITION REQUIREMENT -- "a future acquisition should try to
     obtain evidence capable of resolving X". NOT produced by this
     module. `InformationGap.requirements` carries the vendored
     `EvidenceRequirement`s, which describe what is needed and never a
     procedure, source, or plan. Translating one into an
     `AcquisitionPlan` is a DAF-side decision this layer must not make,
     and deliberately cannot: nothing here imports `daf`.

WHAT THIS DELIBERATELY DOES NOT CLAIM. `expected_information_gain` is
carried through verbatim and is always `NOT_DETERMINABLE` -- the vendored
`materials.value` hard-codes it, and this module does not estimate,
infer, or substitute for it. In particular an `estimate` of 16.0 at S2 is
OBSERVED information value (the model's current predictive uncertainty),
never the gain an experiment would produce. Carrying the field
explicitly, rather than omitting it, is the point: the refusal stays
visible to whatever future machinery consumes this object.

BOUNDARY: no `EvidencePool`/`RetrievalEngine` access; no mutation of
`state`, `candidate`, or `iteration`; no acquisition side effect; no
`daf` import anywhere in this package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from materials.candidates import ActionCandidate
from materials.information import (
    NOT_DETERMINABLE,
    InformationValueEstimate,
    estimate_information_value,
)
from materials.iteration import MaterialsIteration
from materials.model_state import ModelState, ModelStateInformationValueModel
from materials.specification import EvidenceRequirement

# The two independent reasons a gap can exist. Deliberately not an enum
# and deliberately not extended: each names one of the two existing
# machineries above, and a third would mean a third machinery exists.
UNCERTAIN_STATE = "UNCERTAIN_STATE"
ABSENT_EVIDENCE = "ABSENT_EVIDENCE"

# `CandidateInformationValue.current_status` values that mean the evidence
# does not currently settle the criterion. Read from materials.value's own
# vocabulary rather than redefined; RESOLVED-like statuses are simply
# absent from this set.
_UNSETTLED_STATUSES = ("INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE", "INCOMPARABLE")


@dataclass(frozen=True)
class InformationGap:
    """What ONE `ModelState` fails to resolve about ONE `ActionCandidate`,
    and which already-specified evidence would bear on it.

    `state_id` is a real field, not a substring of `model_name` -- the
    one structural thing that did not exist before. `estimate` is the
    complete, unmodified `InformationValueEstimate`, so the full
    provenance chain (candidate -> information value -> evaluation ->
    targeted requirements -> criterion) stays reachable without being
    duplicated; `estimate_status`/`gap_category`/`current_status` are
    surfaced alongside it purely for ergonomic access, the same
    convention every `materials/` layer already follows.

    `requirements` are the vendored `EvidenceRequirement`s verbatim: what
    is needed, never how to get it."""

    state_id: str
    candidate_id: str
    reasons: Tuple[str, ...]
    estimate: InformationValueEstimate
    estimate_status: str
    gap_category: str
    current_status: str
    requirements: Tuple[EvidenceRequirement, ...]
    expected_information_gain: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "requirements", tuple(self.requirements))


def diagnose_information_gap(
    state: ModelState, candidate: ActionCandidate, iteration: MaterialsIteration
) -> Optional[InformationGap]:
    """Deterministic, side-effect-free, read-only. Returns `None` when
    the state resolves this candidate AND the evidence settles its
    criterion -- an honest "no gap", never an empty gap object, so a
    caller cannot mistake "nothing unresolved" for "something unresolved
    with no reasons".

    `reasons` is sorted so two equal diagnoses compare equal regardless
    of the order the two axes were checked."""
    estimate = estimate_information_value(
        candidate, iteration, ModelStateInformationValueModel(state)
    )
    information_value = estimate.information_value

    reasons = []
    if estimate.estimate_status == NOT_DETERMINABLE:
        reasons.append(UNCERTAIN_STATE)
    if information_value.current_status in _UNSETTLED_STATUSES:
        reasons.append(ABSENT_EVIDENCE)
    if not reasons:
        return None

    return InformationGap(
        state_id=state.id,
        candidate_id=candidate.id,
        reasons=tuple(sorted(reasons)),
        estimate=estimate,
        estimate_status=estimate.estimate_status,
        gap_category=information_value.gap_category,
        current_status=information_value.current_status,
        requirements=tuple(information_value.evaluation.targeted_requirements),
        expected_information_gain=information_value.expected_information_gain,
    )
