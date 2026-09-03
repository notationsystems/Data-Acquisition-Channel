"""The single path from a proposal to a tendered load.

PC-6's first acceptance criterion is that no tender may be issued against
a carrier that is not `cleared`, asserted STRUCTURALLY rather than by
convention.

WHY A DISTINCT TYPE RATHER THAN A CHECK. The first version of this module
put the gate in front of PC-5's `dispose()` and asserted by source scan
that `dispose()` was called from here only. The scan immediately found a
second door: `ReviewQueue.take()` calls `dispose()` too. That was a real
finding and NOT a test artifact -- but the fix is not to close that door,
because not every commitment is a carrier tender. A quote issued to a
shipper is a commitment and has no carrier to vet, and forcing a vetting
verdict through that path would either block legitimate work or teach
people to pass a dummy verdict.

So the invariant is carried by a TYPE. `CarrierTender` is the only thing a
carrier may be booked against, its constructor is reachable from exactly
one function, and that function takes a `Verdict` as a required argument
and gates on it. A commitment that never passed the gate is still a
perfectly good Commitment -- it simply is not a CarrierTender, and nothing
downstream will accept it as one.

WHY THE VERDICT IS A PARAMETER AND NOT A LOOKUP. If this function fetched
the verdict itself it would choose the as-of date, and a gate that picks
its own clock can always be made to pass by calling it again later. The
caller supplies the verdict it actually relied on, and that verdict is
carried ON the tender so a post-mortem can read what was known at the time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from commerce.authority import Disposal, Proposal, Verdict as ProposalVerdict, dispose
from commerce.stores import Commitment
from commerce.vetting import CLEARED, Verdict, authorise_tender

#: A booking offered something that is not a CarrierTender.
NOT_A_CARRIER_TENDER = "NOT_A_CARRIER_TENDER"


class BookingRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CarrierTender:
    """A commitment to a carrier, carrying the verdict it was issued under.

    Constructed in exactly one place. The vetting verdict is part of the
    record rather than a check that happened somewhere: a post-mortem asks
    what was known when the load was tendered, and an answer that requires
    re-running today's vetting answers a different question.
    """

    commitment: Commitment
    vetting: Verdict

    @property
    def carrier(self) -> str:
        return self.vetting.carrier


def issue_tender(vetting: Verdict, proposal: Proposal, verdict: Optional[ProposalVerdict],
                 disposal: Disposal) -> CarrierTender:
    """Issue a carrier tender. The ONLY path.

    Order matters and is the point: the vetting gate runs FIRST, so a
    proposal a human is willing to dispose of against a blocked carrier
    still cannot become a tender. The human's authority is over the
    commercial judgement, not over whether the carrier is insured.
    """
    authorise_tender(vetting, at=disposal.issued_at)
    return CarrierTender(commitment=dispose(proposal, verdict, disposal), vetting=vetting)


def book(tender: object) -> CarrierTender:
    """Where capacity is actually booked.

    Takes a CarrierTender and nothing else. A caller holding a plain
    Commitment -- however it was produced, and whoever disposed of it --
    has nothing to hand this function.
    """
    if not isinstance(tender, CarrierTender):
        raise BookingRefusal(
            NOT_A_CARRIER_TENDER,
            f"booking was offered {type(tender).__name__}. Only a CarrierTender may book capacity, "
            "and a CarrierTender exists only on the far side of the vetting gate. A Commitment "
            "disposed of through the ordinary review queue is a valid commitment and is not this.",
        )
    if tender.vetting.status != CLEARED:
        raise BookingRefusal(
            NOT_A_CARRIER_TENDER,
            f"the tender carries a {tender.vetting.status} verdict. This cannot be reached through "
            "issue_tender and means a CarrierTender was constructed directly.",
        )
    return tender
