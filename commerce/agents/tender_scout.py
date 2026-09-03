"""A first agent: rank extracted opportunities by how answerable they are.

It exists to give the structural barrier something real to guard. It reads
opportunities, ranks them, and proposes -- and there is no code path from
here to a commitment, which the source scan asserts rather than assumes.

WHAT IT RANKS ON. Not "attractiveness", which would be the agent grading
its own judgement. It ranks on how much of the founding order's field list
the source could actually answer, which is a measured property of the
notice, and it REFUSES to rank a notice whose quantity has no remedy --
an opportunity nobody can price is not an opportunity, and ranking it
highly because its buyer is large is exactly the inference this layer does
not make.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from commerce.authority import Actor, Proposal, ReviewQueue
from commerce.stores import Quantity
from commerce.tender import Opportunity

#: The notice cannot be priced from this source and links no document.
NOT_RANKABLE_NO_ROUTE_TO_A_QUANTITY = "NOT_RANKABLE_NO_ROUTE_TO_A_QUANTITY"


def rank(opportunities: Sequence[Opportunity]) -> Tuple[List[Opportunity], List[Tuple[str, str]]]:
    """Return (ranked, refused). Every input lands in exactly one."""
    ranked: List[Opportunity] = []
    refused: List[Tuple[str, str]] = []
    for opportunity in opportunities:
        remedy = opportunity.fields["quantity"].remedy or ""
        if "no remedy within this source" in remedy:
            refused.append((opportunity.reference, NOT_RANKABLE_NO_ROUTE_TO_A_QUANTITY))
            continue
        ranked.append(opportunity)
    ranked.sort(key=lambda o: -len(o.present))
    return ranked, refused


def propose(opportunity: Opportunity, queue: ReviewQueue, agent: Actor) -> Proposal:
    """Write a proposal. This is the ceiling of what an agent may do."""
    proposal = Proposal(
        subject=f"pursue:{opportunity.reference}",
        quantity=Quantity(float(len(opportunity.present)), "fields", "answered_from_the_feed"),
        proposed_by=agent,
        evidence_refs=(opportunity.reference,),
        decision_it_would_change="whether to spend an afternoon reading this notice's attachments",
        rationale=f"{len(opportunity.present)} of the order's fields are answerable from the feed.",
    )
    queue.propose(proposal)
    return proposal
