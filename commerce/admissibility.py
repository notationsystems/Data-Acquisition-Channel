"""Admissibility — what a result derived from fixture rows may claim.

THE RULE, AND WHY IT IS COMPUTED RATHER THAN DECLARED. A residual over
four hundred fabricated loads is a test of the machinery and a claim about
nothing. A residual over four hundred real loads is the asset. The same
function computes both, so the difference cannot live in the code path —
it lives in the INPUTS, and this module reads it off them.

WEAKEST INPUT WINS. A result over 399 real events and one fixture event is
inadmissible, because the one fabricated row is inside the mean and cannot
be subtracted back out. Admissibility is not a proportion.

WHEN THE FIRST REAL LOAD ARRIVES nothing here changes. Its events carry a
real source instead of a fixture stamp, results derived only from it come
back admissible, and results mixing it with fixture rows stay
inadmissible with the count of each — which is the honest description of a
book in transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from commerce.events import LoadEvent

#: The stamps a fabricated row carries inside its own content. Both are
#: recognised because both conventions exist in this tree; a stamp added
#: later joins the tuple rather than a new scan.
FIXTURE_STAMPS: Tuple[str, ...] = ("fabricated_fixture", "representative_fixture",
                                   "fabricated_example")

INADMISSIBLE_EVERY_INPUT_IS_FIXTURE = "INADMISSIBLE_EVERY_INPUT_IS_FIXTURE"
INADMISSIBLE_MIXED_INPUTS = "INADMISSIBLE_MIXED_INPUTS"
INADMISSIBLE_NO_INPUTS = "INADMISSIBLE_NO_INPUTS"


def _is_fixture(event: LoadEvent) -> bool:
    marks = (event.source.artifact or "", event.source.source_id or "")
    return any(stamp in mark for stamp in FIXTURE_STAMPS for mark in marks)


@dataclass(frozen=True)
class Admissibility:
    admissible: bool
    because: str
    fixture_inputs: int
    real_inputs: int

    @property
    def sentence(self) -> str:
        """Rendered onto every quantitative surface, so the number never
        travels without its standing."""
        if self.admissible:
            return (f"ADMISSIBLE — derived from {self.real_inputs} event(s), none fabricated.")
        return f"INADMISSIBLE — {self.because}"


def derived_from(events: Sequence[LoadEvent]) -> Admissibility:
    """The admissibility of anything computed from these events."""
    fixture = sum(1 for e in events if _is_fixture(e))
    real = len(events) - fixture
    if not events:
        return Admissibility(False, (
            f"{INADMISSIBLE_NO_INPUTS}: computed from nothing. An empty derivation is not "
            "admissible by vacuity; it is a claim with no inputs to warrant it."),
            0, 0)
    if fixture and real:
        return Admissibility(False, (
            f"{INADMISSIBLE_MIXED_INPUTS}: {real} real event(s) mixed with {fixture} fabricated. "
            "The fabricated rows are inside the figure and cannot be subtracted back out; "
            "admissibility is not a proportion. This is the honest state of a book in "
            "transition, and it resolves load by load as real records land."),
            fixture, real)
    if fixture:
        return Admissibility(False, (
            f"{INADMISSIBLE_EVERY_INPUT_IS_FIXTURE}: all {fixture} input event(s) are "
            "fabricated. The result exercises the machinery and claims nothing about any "
            "carrier, lane, receiver or rate."),
            fixture, 0)
    return Admissibility(True, "", 0, real)
