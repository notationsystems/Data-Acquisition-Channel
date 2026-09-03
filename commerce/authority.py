"""PC-5 — the authority model, built before any agent.

INV-4 ("models propose, deterministic code disposes") was written for an
observational system, where a wrong proposal wasted a reader's time. In a
transactional system a wrong proposal creates a liability, so the
invariant needs teeth it never needed before.

    Agents may:     read evidence, propose commitments, rank, refuse
    Agents may not: issue a commitment, bind the firm, contact a
                    counterparty, submit a bid, book capacity, or file
                    anything

THE BARRIER IS STRUCTURAL, NOT DOCUMENTARY. `Proposal` is the only thing
an agent can produce, and the ONLY function that turns one into a
Commitment is `dispose()`, which requires a `Disposal` naming a human or a
deterministic gate AND the authority it acts under. A test
(tests/test_commerce_authority.py) reads every source file under
`commerce/agents/` and fails if any of them names `Commitment`,
`CommitmentStore`, or an issuing verb -- the same shape as this
repository's existing `test_no_interpretive_layer_can_write_evidence`,
which is a text scan over a layer for exactly this reason: a rule that
lives only in a docstring is enforced by whoever last read it.

THE VALIDATOR IS BUILT FIRST, NOT LAST. The round-1 validator contract
already specifies it: judge whether the evidence supports the claim as
stated, and never the same instance that produced the claim. In an
observational system that separation improved a report. Here its verdicts
have prices, so `validate()` refuses when the validating instance is the
proposing instance -- checked by identity, not by an honour system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from commerce.stores import Authority, Commitment, Quantity

#: A proposal with no evidence behind it. An agent's confidence is not
#: evidence, and a proposal that cites nothing cannot be reviewed -- the
#: reviewer would be grading the agent's tone.
PROPOSAL_CITES_NO_EVIDENCE = "PROPOSAL_CITES_NO_EVIDENCE"
#: A proposal that names no decision it would change.
PROPOSAL_CHANGES_NO_DECISION = "PROPOSAL_CHANGES_NO_DECISION"
#: Disposal attempted with no disposer.
DISPOSAL_NAMES_NO_DISPOSER = "DISPOSAL_NAMES_NO_DISPOSER"
#: Disposal attempted with no authority to bind under.
DISPOSAL_NAMES_NO_AUTHORITY = "DISPOSAL_NAMES_NO_AUTHORITY"
#: An agent identity offered as the disposer. The one refusal that carries
#: the whole invariant.
AN_AGENT_MAY_NOT_DISPOSE_OF_ITS_OWN_PROPOSAL = "AN_AGENT_MAY_NOT_DISPOSE_OF_ITS_OWN_PROPOSAL"
#: The validating instance is the proposing instance.
VALIDATOR_IS_THE_PROPOSER = "VALIDATOR_IS_THE_PROPOSER"
#: A rejected proposal reaching disposal.
REJECTED_PROPOSAL_CANNOT_BE_ISSUED = "REJECTED_PROPOSAL_CANNOT_BE_ISSUED"
#: A proposal disposed without ever being validated.
PROPOSAL_DISPOSED_WITHOUT_A_VERDICT = "PROPOSAL_DISPOSED_WITHOUT_A_VERDICT"
#: A verdict with no reason. It cannot be appealed or audited, and a
#: rejection nobody can appeal is indistinguishable from an oversight.
VERDICT_CARRIES_NO_REASON = "VERDICT_CARRIES_NO_REASON"

#: Class 7 on the queue.
QUEUE_EMPTY_BECAUSE_NO_AGENT_HAS_RUN = "QUEUE_EMPTY_BECAUSE_NO_AGENT_HAS_RUN"
QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_WAS_DISPOSED = "QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_WAS_DISPOSED"
QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_FAILED_VALIDATION = (
    "QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_FAILED_VALIDATION")

#: Acts reserved to a disposer. Named so the boundary is a list a reader
#: can check rather than a sentence they must interpret.
RESERVED_ACTS: Tuple[str, ...] = (
    "issue_a_commitment", "bind_the_firm", "contact_a_counterparty",
    "submit_a_bid", "book_capacity", "file_a_declaration",
)


class AuthorityRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Actor:
    """Who is acting, and whether they may dispose.

    `is_agent` is carried on the identity rather than inferred from a
    name, because inferring it from a name means a model called
    `ops_desk` would pass.
    """

    identifier: str
    is_agent: bool


@dataclass(frozen=True)
class Proposal:
    """The only artefact an agent may produce.

    It is not a commitment and cannot become one without passing through
    `dispose()`. It carries the evidence it rests on so a reviewer grades
    the argument rather than the agent.
    """

    subject: str
    quantity: Quantity
    proposed_by: Actor
    #: Identifiers of the evidence this rests on. Not the evidence itself:
    #: an agent that could attach evidence could attach evidence it wrote.
    evidence_refs: Tuple[str, ...]
    decision_it_would_change: str
    counterparty: Optional[str] = None
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_refs:
            raise AuthorityRefusal(
                PROPOSAL_CITES_NO_EVIDENCE,
                f"{self.subject!r} rests on nothing citable. An agent's confidence is not "
                "evidence, and a reviewer handed an uncited proposal is grading its tone.",
            )
        if not self.decision_it_would_change.strip():
            raise AuthorityRefusal(
                PROPOSAL_CHANGES_NO_DECISION,
                f"{self.subject!r} names no decision it would change, so there is no way to say "
                "whether accepting it was right.",
            )


@dataclass(frozen=True)
class Verdict:
    """The validator's judgement: does the evidence support the claim AS
    STATED. Not whether the claim is a good idea."""

    proposal_subject: str
    validated_by: Actor
    supported: bool
    reason: str


def validate(proposal: Proposal, validator: Actor, *, supported: bool, reason: str) -> Verdict:
    """Judge a proposal. The validating instance may not be the proposing
    instance -- checked by identity, not by an honour system."""
    if validator.identifier == proposal.proposed_by.identifier:
        raise AuthorityRefusal(
            VALIDATOR_IS_THE_PROPOSER,
            f"{validator.identifier!r} produced this proposal and cannot judge whether the "
            "evidence supports it. A separate instance is the whole content of the contract; "
            "the same instance asked twice returns the same reasoning with more words.",
        )
    if not reason.strip():
        raise AuthorityRefusal(
            VERDICT_CARRIES_NO_REASON,
            f"{validator.identifier!r} judged {proposal.subject!r} and recorded no reason. A "
            "verdict that cannot be appealed or audited is indistinguishable from an oversight.",
        )
    return Verdict(proposal_subject=proposal.subject, validated_by=validator,
                   supported=supported, reason=reason)


@dataclass(frozen=True)
class Disposal:
    """The act of turning a proposal into a commitment. A human, or a
    deterministic gate -- never a model."""

    disposer: Actor
    authority: Optional[Authority]
    issued_at: str
    idempotency_key: str


def dispose(proposal: Proposal, verdict: Optional[Verdict], disposal: Disposal) -> Commitment:
    """The ONLY path from a proposal to a commitment.

    Every refusal here names an observable. `AN_AGENT_MAY_NOT_DISPOSE...`
    says the disposer's identity is flagged as an agent; it makes no claim
    about the proposal's quality.
    """
    if disposal.disposer.is_agent:
        raise AuthorityRefusal(
            AN_AGENT_MAY_NOT_DISPOSE_OF_ITS_OWN_PROPOSAL,
            f"{disposal.disposer.identifier!r} is an agent identity. Agents propose; disposal is "
            f"a human or a deterministic gate. The reserved acts are {list(RESERVED_ACTS)}.",
        )
    if not disposal.disposer.identifier.strip():
        raise AuthorityRefusal(DISPOSAL_NAMES_NO_DISPOSER,
                               "the firm would be bound by nobody.")
    if disposal.authority is None:
        raise AuthorityRefusal(
            DISPOSAL_NAMES_NO_AUTHORITY,
            "the authority under which a commitment was issued is recorded ON the commitment. "
            "Resolved later it answers what authority exists NOW, which is a different question.",
        )
    if verdict is None:
        raise AuthorityRefusal(
            PROPOSAL_DISPOSED_WITHOUT_A_VERDICT,
            f"{proposal.subject!r} was never validated. The verdict is not paperwork: it is the "
            "separate instance's reading of whether the evidence supports the claim.",
        )
    if not verdict.supported:
        raise AuthorityRefusal(
            REJECTED_PROPOSAL_CANNOT_BE_ISSUED,
            f"{proposal.subject!r} was judged unsupported by {verdict.validated_by.identifier!r}: "
            f"{verdict.reason}",
        )
    return Commitment(
        subject=proposal.subject,
        quantity=proposal.quantity,
        issuer=disposal.disposer.identifier,
        authority=disposal.authority,
        idempotency_key=disposal.idempotency_key,
        issued_at=disposal.issued_at,
        counterparty=proposal.counterparty,
    )


@dataclass
class ReviewQueue:
    """Where proposals wait. An agent writes here and reads nothing back."""

    _pending: List[Proposal] = field(default_factory=list)
    _verdicts: Dict[str, Verdict] = field(default_factory=dict)
    _disposed: List[str] = field(default_factory=list)
    _failed: List[str] = field(default_factory=list)

    def propose(self, proposal: Proposal) -> None:
        self._pending.append(proposal)

    def record(self, verdict: Verdict) -> None:
        self._verdicts[verdict.proposal_subject] = verdict
        if not verdict.supported:
            self._failed.append(verdict.proposal_subject)

    def take(self, proposal: Proposal, disposal: Disposal) -> Commitment:
        commitment = dispose(proposal, self._verdicts.get(proposal.subject), disposal)
        self._pending = [p for p in self._pending if p.subject != proposal.subject]
        self._disposed.append(proposal.subject)
        return commitment

    @property
    def pending(self) -> Tuple[Proposal, ...]:
        return tuple(self._pending)

    @property
    def empty_because(self) -> Optional[str]:
        if self._pending:
            return None
        if not self._disposed and not self._failed:
            return (f"{QUEUE_EMPTY_BECAUSE_NO_AGENT_HAS_RUN}: nothing has been proposed. An empty "
                    "review queue and an agent layer that never started look identical from here.")
        if self._failed and not self._disposed:
            return (f"{QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_FAILED_VALIDATION}: "
                    f"{len(self._failed)} proposal(s) were judged unsupported. The agents ran and "
                    "produced nothing the validator would stand behind, which is a finding about "
                    "the agents rather than a quiet day.")
        return (f"{QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_WAS_DISPOSED}: {len(self._disposed)} "
                f"disposed and {len(self._failed)} rejected; the queue is clear because the work "
                "was done.")
