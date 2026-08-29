"""The sea_dog_session instrument: a queue becomes a work order, and a
session becomes a record that can be graded.

WHAT THIS IS FOR. A half-day of researcher time is the scarcest input in
the program and the only one no engineering substitutes for. This module
converts that half-day into the largest number of DISCRIMINATING answers
by doing three things a person under time pressure reliably does not:

    it ranks on yield PER UNIT TIME rather than on interest, so a large
        answer cannot crowd out three small ones
    it refuses to rank a question whose acceptance test was written
        after the question was worked, so an answer is not graded by the
        person who produced it after seeing it
    it distinguishes a session that met its stopping rule from one that
        ran out of energy, because those are different evidence

WHY THE ORDER IS BY DISCRIMINATION AND NOT BY OPENNESS. An open question
is not automatically worth an hour: the test is whether the answer could
CHANGE A DOWNSTREAM DECISION. A question that cannot is not ranked low,
it is dropped -- and it is dropped IN WRITING, with its reason, because a
question that disappears from a queue without a record is indistinguishable
from one that was answered.

WHY "BEFORE" IS A SEQUENCE AND NOT A CLOCK. The property is an ORDER:
the acceptance test exists before the item is worked. A wall-clock stamp
invites an argument about skew and about whose machine; a caller-supplied
monotonic position can be compared. Equal positions are NOT before --
written at the same moment as the work is not written ahead of it, and
treating it as ahead would give the invariant a hole exactly where a
hurried session would land in it.

WHAT AN EMPTY ORDER MEANS. Two different states produce an order with no
items -- every question was dropped, or no question was asked -- and an
empty tuple states neither. The order carries `empty_because` when it is
empty and carries nothing when it is not, because a warrant attached to
every result is a warrant on none.

AUTHORITY BOUNDARY, ENFORCED STRUCTURALLY. Findings are OBSERVATIONS.
This module imports nothing from an acquisition, admission or state
layer, so it cannot promote one to canonical state even by accident; the
import list is asserted in tests/test_session_instrument.py rather than
promised here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

#: A question that names no decision its answer could change. Dropped,
#: with its reason recorded -- never removed silently.
NO_DECISION_IT_COULD_CHANGE = "NO_DECISION_IT_COULD_CHANGE"
#: An item carrying no acceptance test cannot be ranked: ranking it would
#: leave the test to be written after the answer is in hand.
NO_ACCEPTANCE_TEST = "NO_ACCEPTANCE_TEST"
#: An item with no per-item box cannot overrun, so it cannot be abandoned
#: deliberately -- only by exhaustion, which is the thing being prevented.
NO_TIME_BOX = "NO_TIME_BOX"
#: The acceptance test was recorded at or after the position at which the
#: item was worked. The observable, not a motive.
ACCEPTANCE_TEST_POSTDATES_WORK = "ACCEPTANCE_TEST_POSTDATES_WORK"
#: A findings record with no source. An uncited finding cannot be
#: re-derived or rejected, which is the provenance rule this layer owns.
FINDING_CITES_NO_SOURCE = "FINDING_CITES_NO_SOURCE"
#: A finding naming an item the work order does not contain: there is no
#: acceptance test to grade it against.
FINDING_FOR_NO_ITEM = "FINDING_FOR_NO_ITEM"
#: A finding that declares no evidence class. The doctrine requires
#: findings to conform to "the research finding schema"; MEASURED, no such
#: schema exists anywhere in this repository, the vendored substrate at the
#: pin, or the instrument this session studies -- recorded in
#: architecture/sea_dog_session_instrument.yaml. What this layer can assert
#: without one is that the finding said SOMETHING about its class rather
#: than nothing. Which classes are admissible is owned by
#: `epistemics.evidence_class` and is NOT restated here: a second copy of a
#: closed vocabulary drifts from the first, and the layer test forbids the
#: import that would keep them in step. This is the same resolution the GPC
#: extractor reached when it tried to import UNCERTAINTY_KINDS.
FINDING_DECLARES_NO_EVIDENCE_CLASS = "FINDING_DECLARES_NO_EVIDENCE_CLASS"
#: The residue list was not supplied. DISTINCT from a list explicitly
#: stated as empty: `nothing was raised` and `nobody recorded what was
#: raised` are different sessions.
RESIDUE_OMITTED = "RESIDUE_OMITTED"
#: The session ended without its stopping rule being met. It says the
#: rule was not met; it does not claim to know why.
STOPPED_WITHOUT_THE_STOPPING_RULE = "STOPPED_WITHOUT_THE_STOPPING_RULE"
#: The whole queue was dropped for want of a decision it could change.
EMPTY_BECAUSE_EVERY_ITEM_WAS_DROPPED = "EMPTY_BECAUSE_EVERY_ITEM_WAS_DROPPED"
#: No question was supplied. Not the same fact as the one above.
EMPTY_BECAUSE_THE_QUEUE_WAS_EMPTY = "EMPTY_BECAUSE_THE_QUEUE_WAS_EMPTY"


@dataclass(frozen=True)
class QueueItem:
    """One question, with everything needed to rank and grade it.

    `expected_yield` is the operator's own estimate of how much the
    answer discriminates, on whatever scale they keep it in; only its
    ORDER matters here, and it is divided by `minutes` so the ranking is
    per unit of the scarce input rather than per question.
    """

    identifier: str
    question: str
    #: The downstream decision this answer could change. None means the
    #: item is dropped: see NO_DECISION_IT_COULD_CHANGE.
    decision_it_could_change: Optional[str]
    #: How the answer will be graded, written before the item is worked.
    acceptance_test: Optional[str]
    expected_yield: float
    #: The per-item box. An item that overruns it is abandoned as a
    #: decision rather than by exhaustion.
    minutes: Optional[int]
    #: Monotonic position at which the acceptance test was recorded.
    acceptance_test_at: Optional[int] = None
    #: Monotonic position at which the item was worked. None = not yet.
    worked_at: Optional[int] = None

    @property
    def yield_per_minute(self) -> float:
        return self.expected_yield / float(self.minutes or 1)


@dataclass(frozen=True)
class Drop:
    """A question removed from the queue, with the reason in writing."""

    identifier: str
    code: str
    reason: str


@dataclass(frozen=True)
class Finding:
    """An observation from the session. Never a fact about the world by
    itself: it cites what it rests on, and it is graded against the
    acceptance test its item carried before the work began."""

    item_id: str
    statement: str
    sources: Tuple[str, ...]
    #: The class the finding is claimed under, from the vocabulary
    #: `epistemics.evidence_class` owns. Unset is refused rather than
    #: defaulted: a session finding is almost always `asserted` -- a
    #: person's account of what they did -- and defaulting to it would
    #: silently promote the occasional counter reading to the same class
    #: without anyone choosing.
    evidence_class: Optional[str] = None


@dataclass(frozen=True)
class WorkOrder:
    items: Tuple[QueueItem, ...]
    drops: Tuple[Drop, ...]
    refusals: Tuple[Tuple[str, str], ...]
    box_minutes: int
    #: Set only when `items` is empty, and it says WHICH empty.
    empty_because: Optional[str] = None

    @property
    def planned_minutes(self) -> int:
        return sum(item.minutes or 0 for item in self.items)

    @property
    def overruns_the_box(self) -> bool:
        """The plan asks for more than the session has. Reported rather
        than silently truncated: which items to cut is the operator's
        call, and a plan quietly trimmed to fit reads as a plan that fits."""
        return self.planned_minutes > self.box_minutes


@dataclass(frozen=True)
class Session:
    order: WorkOrder
    findings: Tuple[Finding, ...]
    residue: Tuple[str, ...]
    residue_was_stated: bool
    stopping_rule_met: bool
    refusals: Tuple[Tuple[str, str], ...]

    @property
    def complete(self) -> bool:
        """A session is complete when it met its stopping rule and
        nothing about its record is refused. Both, because a record that
        cannot be graded is not finished either."""
        return self.stopping_rule_met and not self.refusals


def plan(queue: Sequence[QueueItem], *, box_minutes: int) -> WorkOrder:
    """Order the queue by expected yield per unit time.

    Dropped first, then refused, then ranked -- in that sequence, because
    a question that changes no decision should not be refused for
    lacking an acceptance test it was never going to need.
    """
    drops = []
    refusals = []
    rankable = []

    for item in queue:
        if item.decision_it_could_change is None:
            drops.append(Drop(
                identifier=item.identifier,
                code=NO_DECISION_IT_COULD_CHANGE,
                reason=(f"{item.identifier!r} names no downstream decision its answer could "
                        "change, so an answer would not discriminate between actions. Dropped "
                        "here rather than ranked low: a low-ranked item still consumes the "
                        "queue's attention."),
            ))
            continue
        if item.acceptance_test is None:
            refusals.append((NO_ACCEPTANCE_TEST, item.identifier))
            continue
        if item.minutes is None:
            refusals.append((NO_TIME_BOX, item.identifier))
            continue
        if (item.worked_at is not None
                and (item.acceptance_test_at is None
                     or item.acceptance_test_at >= item.worked_at)):
            refusals.append((ACCEPTANCE_TEST_POSTDATES_WORK, item.identifier))
            continue
        rankable.append(item)

    rankable.sort(key=lambda i: (-i.yield_per_minute, i.identifier))

    empty_because = None
    if not rankable:
        empty_because = (EMPTY_BECAUSE_THE_QUEUE_WAS_EMPTY if not queue
                         else EMPTY_BECAUSE_EVERY_ITEM_WAS_DROPPED)

    return WorkOrder(
        items=tuple(rankable),
        drops=tuple(drops),
        refusals=tuple(refusals),
        box_minutes=box_minutes,
        empty_because=empty_because,
    )


def close_session(
    order: WorkOrder,
    *,
    findings: Sequence[Finding],
    residue: Optional[Sequence[str]],
    stopping_rule_met: bool,
) -> Session:
    """Close a session against its work order.

    `residue=None` is an OMISSION and is refused; `residue=()` is a
    statement that nothing was raised, and is accepted. The two are not
    the same evidence and the signature does not let them collapse.
    """
    refusals = list(order.refusals)
    known = {item.identifier for item in order.items}

    for finding in findings:
        if finding.item_id not in known:
            refusals.append((FINDING_FOR_NO_ITEM, finding.item_id))
            continue
        if not finding.sources:
            refusals.append((FINDING_CITES_NO_SOURCE, finding.item_id))
        if not finding.evidence_class:
            refusals.append((FINDING_DECLARES_NO_EVIDENCE_CLASS, finding.item_id))

    if residue is None:
        refusals.append((RESIDUE_OMITTED, "session"))
    if not stopping_rule_met:
        refusals.append((STOPPED_WITHOUT_THE_STOPPING_RULE, "session"))

    return Session(
        order=order,
        findings=tuple(findings),
        residue=tuple(residue or ()),
        residue_was_stated=residue is not None,
        stopping_rule_met=stopping_rule_met,
        refusals=tuple(refusals),
    )
