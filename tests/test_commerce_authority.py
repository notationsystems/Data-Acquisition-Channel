"""PC-5 graded, with the barrier asserted structurally.

THE TEST THAT CARRIES THE INVARIANT is
`test_no_agent_module_can_construct_a_commitment`. It is a source scan
over `commerce/agents/`, in the same shape as this repository's existing
`test_no_interpretive_layer_can_write_evidence`, and for the same reason:
a boundary that lives in a docstring is enforced by whoever last read the
docstring. Everything else here checks a runtime refusal; that one checks
that the refusal cannot be reached around.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.agents import tender_scout  # noqa: E402
from commerce.authority import (AN_AGENT_MAY_NOT_DISPOSE_OF_ITS_OWN_PROPOSAL,  # noqa: E402
                                DISPOSAL_NAMES_NO_AUTHORITY, PROPOSAL_CHANGES_NO_DECISION,
                                PROPOSAL_CITES_NO_EVIDENCE, PROPOSAL_DISPOSED_WITHOUT_A_VERDICT,
                                QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_FAILED_VALIDATION,
                                QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_WAS_DISPOSED,
                                QUEUE_EMPTY_BECAUSE_NO_AGENT_HAS_RUN,
                                REJECTED_PROPOSAL_CANNOT_BE_ISSUED, RESERVED_ACTS,
                                VALIDATOR_IS_THE_PROPOSER, VERDICT_CARRIES_NO_REASON,
                                Actor, AuthorityRefusal, Disposal, Proposal, ReviewQueue,
                                dispose, validate)
from commerce.canadabuys import parse_feed  # noqa: E402
from commerce.stores import Authority, Commitment, CommitmentStore, Quantity  # noqa: E402
from commerce.tender import extract  # noqa: E402

AGENT = Actor("scout.instance.a", is_agent=True)
OTHER_AGENT = Actor("validator.instance.b", is_agent=True)
HUMAN = Actor("ops@firm", is_agent=False)
AUTH = Authority("ops", "signing_delegation", "2026-01-01", "2026-12-31")


def _proposal(**over: object) -> Proposal:
    base = dict(subject="tender:ABC-123", quantity=Quantity(1.0, "loads", "per_week"),
                proposed_by=AGENT, evidence_refs=("notice:ABC-123",),
                decision_it_would_change="whether to bid")
    base.update(over)
    return Proposal(**base)  # type: ignore[arg-type]


def _disposal(**over: object) -> Disposal:
    base = dict(disposer=HUMAN, authority=AUTH, issued_at="2026-08-31",
                idempotency_key="bid-0001")
    base.update(over)
    return Disposal(**base)  # type: ignore[arg-type]


# =====================================================================
# The structural barrier
# =====================================================================

def test_no_agent_module_can_construct_a_commitment():
    """The invariant with teeth. In an observational system a wrong
    proposal wasted a reader's time; here it creates a liability, so the
    barrier is a fact about the source rather than a promise in prose."""
    forbidden = re.compile(
        r"\bCommitment\b|\bCommitmentStore\b|\bdispose\s*\(|\bissue\s*\(", re.MULTILINE)
    agents = sorted((REPO_ROOT / "commerce" / "agents").glob("*.py"))
    assert agents, "the scan must have something to scan; a vacuous guard passes forever"
    assert any(p.name != "__init__.py" for p in agents), (
        "at least one real agent module must exist, or this test proves nothing"
    )
    for path in agents:
        source = path.read_text()
        # The package docstring is allowed to NAME the rule it states.
        body = re.sub(r'^"""(?:.|\n)*?"""', "", source, count=1)
        match = forbidden.search(body)
        assert match is None, (
            f"{path.relative_to(REPO_ROOT)} names {match.group(0)!r} outside its docstring. "
            "Agents propose; only dispose() issues."
        )


def test_the_reserved_acts_are_a_list_a_reader_can_check():
    for act in ("issue_a_commitment", "bind_the_firm", "contact_a_counterparty",
                "submit_a_bid", "book_capacity", "file_a_declaration"):
        assert act in RESERVED_ACTS


def test_an_agent_identity_cannot_dispose():
    """The one refusal that carries the whole invariant."""
    verdict = validate(_proposal(), OTHER_AGENT, supported=True, reason="evidence cited and read")
    with pytest.raises(AuthorityRefusal) as caught:
        dispose(_proposal(), verdict, _disposal(disposer=AGENT))
    assert caught.value.code == AN_AGENT_MAY_NOT_DISPOSE_OF_ITS_OWN_PROPOSAL


def test_agent_status_is_carried_on_the_identity_and_not_inferred_from_its_name():
    """A model named `ops_desk` would pass a name check."""
    disguised = Actor("ops_desk", is_agent=True)
    verdict = validate(_proposal(), OTHER_AGENT, supported=True, reason="read")
    with pytest.raises(AuthorityRefusal) as caught:
        dispose(_proposal(), verdict, _disposal(disposer=disguised))
    assert caught.value.code == AN_AGENT_MAY_NOT_DISPOSE_OF_ITS_OWN_PROPOSAL


# =====================================================================
# A proposal must be reviewable
# =====================================================================

def test_a_proposal_with_no_evidence_is_refused():
    with pytest.raises(AuthorityRefusal) as caught:
        _proposal(evidence_refs=())
    assert caught.value.code == PROPOSAL_CITES_NO_EVIDENCE
    assert "confidence is not" in caught.value.detail


def test_a_proposal_that_changes_no_decision_is_refused():
    with pytest.raises(AuthorityRefusal) as caught:
        _proposal(decision_it_would_change="  ")
    assert caught.value.code == PROPOSAL_CHANGES_NO_DECISION


# =====================================================================
# The validator is a separate instance, checked by identity
# =====================================================================

def test_the_proposing_instance_cannot_validate_its_own_proposal():
    with pytest.raises(AuthorityRefusal) as caught:
        validate(_proposal(), AGENT, supported=True, reason="looks right to me")
    assert caught.value.code == VALIDATOR_IS_THE_PROPOSER
    assert "same instance asked twice" in caught.value.detail


def test_a_verdict_with_no_reason_is_refused():
    with pytest.raises(AuthorityRefusal) as caught:
        validate(_proposal(), OTHER_AGENT, supported=False, reason="")
    assert caught.value.code == VERDICT_CARRIES_NO_REASON


def test_a_second_agent_instance_may_validate():
    """The separation is between INSTANCES, not between humans and models.
    A validating agent is legitimate; a self-validating one is not."""
    verdict = validate(_proposal(), OTHER_AGENT, supported=True, reason="the notice says so")
    assert verdict.supported and verdict.validated_by is OTHER_AGENT


# =====================================================================
# Disposal
# =====================================================================

def test_disposal_without_a_verdict_is_refused():
    with pytest.raises(AuthorityRefusal) as caught:
        dispose(_proposal(), None, _disposal())
    assert caught.value.code == PROPOSAL_DISPOSED_WITHOUT_A_VERDICT


def test_disposal_of_a_rejected_proposal_is_refused_and_quotes_the_reason():
    verdict = validate(_proposal(), OTHER_AGENT, supported=False,
                       reason="the cited notice does not state a quantity")
    with pytest.raises(AuthorityRefusal) as caught:
        dispose(_proposal(), verdict, _disposal())
    assert caught.value.code == REJECTED_PROPOSAL_CANNOT_BE_ISSUED
    assert "does not state a quantity" in caught.value.detail


def test_disposal_without_an_authority_is_refused():
    verdict = validate(_proposal(), OTHER_AGENT, supported=True, reason="read")
    with pytest.raises(AuthorityRefusal) as caught:
        dispose(_proposal(), verdict, _disposal(authority=None))
    assert caught.value.code == DISPOSAL_NAMES_NO_AUTHORITY


def test_a_disposed_proposal_becomes_a_commitment_the_store_accepts():
    """End to end: the only path from a model's output to a bound firm,
    and it passes through a human and a store that checks the authority."""
    verdict = validate(_proposal(), OTHER_AGENT, supported=True, reason="notice read and cited")
    commitment = dispose(_proposal(), verdict, _disposal())
    assert isinstance(commitment, Commitment)
    assert commitment.issuer == "ops@firm"
    assert commitment.authority is AUTH
    assert CommitmentStore().issue(commitment) is commitment


# =====================================================================
# The queue, and class 7 on it
# =====================================================================

def test_an_empty_queue_says_whether_any_agent_ran():
    queue = ReviewQueue()
    assert queue.empty_because is not None
    assert QUEUE_EMPTY_BECAUSE_NO_AGENT_HAS_RUN in queue.empty_because


def test_a_queue_emptied_by_rejection_is_a_finding_about_the_agents():
    queue = ReviewQueue()
    proposal = _proposal()
    queue.propose(proposal)
    queue.record(validate(proposal, OTHER_AGENT, supported=False, reason="uncited"))
    queue._pending = []  # the reviewer cleared it
    assert queue.empty_because is not None
    assert QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_FAILED_VALIDATION in queue.empty_because
    assert "rather than a quiet day" in queue.empty_because


def test_a_queue_emptied_by_disposal_is_a_different_nothing():
    queue = ReviewQueue()
    proposal = _proposal()
    queue.propose(proposal)
    queue.record(validate(proposal, OTHER_AGENT, supported=True, reason="read"))
    queue.take(proposal, _disposal())
    assert queue.empty_because is not None
    assert QUEUE_EMPTY_BECAUSE_EVERY_PROPOSAL_WAS_DISPOSED in queue.empty_because


def test_the_three_empty_queues_are_distinguishable():
    sentences = set()
    queue = ReviewQueue()
    sentences.add(queue.empty_because)
    for supported in (False, True):
        q = ReviewQueue()
        p = _proposal()
        q.propose(p)
        q.record(validate(p, OTHER_AGENT, supported=supported, reason="read"))
        if supported:
            q.take(p, _disposal())
        else:
            q._pending = []
        sentences.add(q.empty_because)
    assert len(sentences) == 3, f"the empties must be distinguishable: {sentences}"


# =====================================================================
# The agent itself, over real notices
# =====================================================================

def test_the_scout_ranks_and_refuses_and_every_input_lands_in_one_of_them():
    fixture = REPO_ROOT / "commerce" / "fixtures" / "canadabuys_open_sample.csv"
    retrieval = parse_feed(fixture.read_text(encoding="utf-8"),
                           source_url="fixture", retrieved_at="2026-08-31")
    opportunities = tuple(extract(n) for n in retrieval.notices)
    ranked, refused = tender_scout.rank(opportunities)
    assert len(ranked) + len(refused) == len(opportunities), (
        "an opportunity in neither list is one the operator will assume was ranked"
    )


def test_the_scout_writes_a_proposal_and_can_reach_nothing_further():
    queue = ReviewQueue()
    fixture = REPO_ROOT / "commerce" / "fixtures" / "canadabuys_open_sample.csv"
    retrieval = parse_feed(fixture.read_text(encoding="utf-8"),
                           source_url="fixture", retrieved_at="2026-08-31")
    opportunity = extract(retrieval.notices[0])
    proposal = tender_scout.propose(opportunity, queue, AGENT)
    assert proposal in queue.pending
    assert queue.empty_because is None
    assert not hasattr(tender_scout, "issue")
