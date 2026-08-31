"""PC-1 graded: the three stores reject each other's types, and the
pairing accounts for every commitment.

WHAT THESE TESTS ARE FOR. The store split is the one architecturally
irreversible decision in this programme, and the way it fails is not by
raising -- it is by quietly accepting. A store that admitted a commitment
as evidence would look completely healthy: the counts would be right, the
queries would return rows, and the first thing anyone would notice is a
report in which the firm's own promises were cited as observations about
the world. So the tests below assert the REFUSAL and, where a bucket is
involved, CONSERVATION -- because refusing a thing is not the same as not
double-counting it, which a plant against the session instrument
demonstrated by leaving a green test green.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.stores import (  # noqa: E402
    COMMITMENT_CARRIES_NO_IDEMPOTENCY_KEY, COMMITMENT_ISSUED_OUTSIDE_ITS_AUTHORITY_WINDOW,
    COMMITMENT_KEY_REUSED_WITH_DIFFERENT_CONTENT, COMMITMENT_NAMES_NO_AUTHORITY,
    COMMITMENT_NAMES_NO_ISSUER, DIVERGENCE_ACROSS_UNLIKE_BASIS,
    EVIDENCE_CARRIES_NO_PROVENANCE, EVIDENCE_DECLARES_NO_CLASS,
    EVIDENCE_KNOWN_BEFORE_ITS_PERIOD, NO_PAIRS_BECAUSE_EVERY_COMMITMENT_WAS_REVOKED,
    NO_PAIRS_BECAUSE_EVERY_PAIR_DIFFERED_IN_BASIS, NO_PAIRS_BECAUSE_NO_COMMITMENTS_WERE_ISSUED,
    NO_PAIRS_BECAUSE_NO_OUTCOME_HAS_ARRIVED_YET, OUTCOME_REFERENCES_AN_ABSENT_COMMITMENT,
    OUTCOME_REFERENCES_NO_COMMITMENT, WRONG_TYPE_FOR_THIS_STORE, Authority, Commitment,
    CommitmentStore, Evidence, EvidenceStore, Outcome, OutcomeStore, Provenance, Quantity,
    StoreRefusal, diverge, pair)

AUTH = Authority(holder="ops", instrument="signing_delegation",
                 valid_from="2026-01-01", valid_until="2026-12-31")


def _evidence(**over: object) -> Evidence:
    base = dict(
        subject="lane:YYZ-YVR:transit_days",
        quantity=Quantity(5.0, "days", "door_to_door"),
        provenance=Provenance(source_id="carrier_invoice", retrieved_at="2026-08-31",
                              known_at="2026-08-31"),
        evidence_class="asserted",
    )
    base.update(over)
    return Evidence(**base)  # type: ignore[arg-type]


def _commitment(**over: object) -> Commitment:
    base = dict(
        subject="lane:YYZ-YVR:transit_days",
        quantity=Quantity(4.0, "days", "door_to_door"),
        issuer="ops@firm",
        authority=AUTH,
        idempotency_key="quote-0001",
        issued_at="2026-08-20",
    )
    base.update(over)
    return Commitment(**base)  # type: ignore[arg-type]


# =====================================================================
# The stores reject each other's types
# =====================================================================

def test_the_evidence_store_refuses_a_commitment_by_type():
    """The failure this prevents is silent. A commitment admitted as
    evidence produces a healthy-looking corpus in which the firm's own
    promises are cited as observations about the world."""
    with pytest.raises(StoreRefusal) as caught:
        EvidenceStore().admit(_commitment())
    assert caught.value.code == WRONG_TYPE_FOR_THIS_STORE
    assert "believing its own intentions" in caught.value.detail


def test_the_commitment_store_refuses_evidence_by_type():
    with pytest.raises(StoreRefusal) as caught:
        CommitmentStore().issue(_evidence())
    assert caught.value.code == WRONG_TYPE_FOR_THIS_STORE


def test_the_rejection_is_by_type_and_not_by_field_inspection():
    """A store that checked fields would admit anything shaped right.
    `Outcome` carries an `Evidence`, so a field-inspecting evidence store
    would happily unwrap and accept one."""
    outcome = Outcome(commitment_key="quote-0001", observed=_evidence())
    with pytest.raises(StoreRefusal) as caught:
        EvidenceStore().admit(outcome)
    assert caught.value.code == WRONG_TYPE_FOR_THIS_STORE


# =====================================================================
# Evidence keeps what the earlier programme earned
# =====================================================================

def test_evidence_without_provenance_is_refused():
    with pytest.raises(StoreRefusal) as caught:
        EvidenceStore().admit(_evidence(
            provenance=Provenance(source_id="  ", retrieved_at="2026-08-31",
                                  known_at="2026-08-31")))
    assert caught.value.code == EVIDENCE_CARRIES_NO_PROVENANCE


def test_evidence_declaring_no_class_is_refused_without_naming_the_admissible_set():
    """This layer requires the declaration and does not make it. A local
    copy of a closed vocabulary drifts from the original, and the import
    that would keep them in step is the one the layer rule forbids."""
    with pytest.raises(StoreRefusal) as caught:
        EvidenceStore().admit(_evidence(evidence_class=""))
    assert caught.value.code == EVIDENCE_DECLARES_NO_CLASS
    for owned_elsewhere in ("asserted", "computed", "derived", "measured"):
        assert owned_elsewhere not in caught.value.detail, (
            "the refusal must not restate the admissible set; that vocabulary is owned by "
            "epistemics.evidence_class and a second copy here would drift from it"
        )


def test_known_at_is_separated_from_the_period_and_cannot_precede_it():
    """The separation is what makes a bid post-mortem answer *what did we
    know when we bid* rather than *what do we know now*."""
    with pytest.raises(StoreRefusal) as caught:
        EvidenceStore().admit(_evidence(
            period="2026-09",
            provenance=Provenance(source_id="s", retrieved_at="2026-08-01",
                                  known_at="2026-08-01")))
    assert caught.value.code == EVIDENCE_KNOWN_BEFORE_ITS_PERIOD


# =====================================================================
# Commitments need what evidence never did
# =====================================================================

def test_a_commitment_cannot_be_issued_without_an_issuer():
    with pytest.raises(StoreRefusal) as caught:
        CommitmentStore().issue(_commitment(issuer=""))
    assert caught.value.code == COMMITMENT_NAMES_NO_ISSUER


def test_a_commitment_cannot_be_issued_without_an_authority():
    with pytest.raises(StoreRefusal) as caught:
        CommitmentStore().issue(_commitment(authority=None))
    assert caught.value.code == COMMITMENT_NAMES_NO_AUTHORITY


def test_the_authority_refusal_names_the_empty_field_and_not_a_motive():
    """The refusal codes name OBSERVABLES. `COMMITMENT_NAMES_NO_AUTHORITY`
    says the field is empty; whether the issuer actually held authority is
    a fact about the world that no store can see."""
    with pytest.raises(StoreRefusal) as caught:
        CommitmentStore().issue(_commitment(authority=None))
    assert "does not claim the issuer lacked authority" in caught.value.detail


def test_a_commitment_issued_outside_its_authority_window_is_refused():
    with pytest.raises(StoreRefusal) as caught:
        CommitmentStore().issue(_commitment(issued_at="2027-03-01"))
    assert caught.value.code == COMMITMENT_ISSUED_OUTSIDE_ITS_AUTHORITY_WINDOW
    assert "signing_delegation" in caught.value.detail


def test_a_commitment_without_an_idempotency_key_is_refused():
    with pytest.raises(StoreRefusal) as caught:
        CommitmentStore().issue(_commitment(idempotency_key=""))
    assert caught.value.code == COMMITMENT_CARRIES_NO_IDEMPOTENCY_KEY


def test_the_same_key_with_the_same_content_binds_once():
    """Idempotency is the difference between a retried send and a second
    promise. In an observational system a duplicate wasted a row; here it
    binds the firm twice."""
    store = CommitmentStore()
    store.issue(_commitment())
    store.issue(_commitment())
    assert len(store) == 1


def test_the_same_key_with_different_content_is_refused():
    store = CommitmentStore()
    store.issue(_commitment())
    with pytest.raises(StoreRefusal) as caught:
        store.issue(_commitment(quantity=Quantity(9.0, "days", "door_to_door")))
    assert caught.value.code == COMMITMENT_KEY_REUSED_WITH_DIFFERENT_CONTENT


# =====================================================================
# An outcome is an outcome OF something
# =====================================================================

def test_an_outcome_referencing_no_commitment_is_refused():
    commitments = CommitmentStore()
    with pytest.raises(StoreRefusal) as caught:
        OutcomeStore(commitments).record(Outcome(commitment_key="", observed=_evidence()))
    assert caught.value.code == OUTCOME_REFERENCES_NO_COMMITMENT
    assert "belongs in the evidence store" in caught.value.detail


def test_an_outcome_referencing_an_unissued_commitment_is_refused():
    commitments = CommitmentStore()
    with pytest.raises(StoreRefusal) as caught:
        OutcomeStore(commitments).record(Outcome(commitment_key="ghost", observed=_evidence()))
    assert caught.value.code == OUTCOME_REFERENCES_AN_ABSENT_COMMITMENT


# =====================================================================
# The pairing: the reuse, and the guard the freight domain needs more
# =====================================================================

def test_a_commitment_and_its_outcome_produce_a_residual():
    """Promised 4 days, took 5. This is the whole commercial engine, and
    it needed no new analytics to reach a new domain."""
    result = diverge(_commitment(), Outcome("quote-0001", _evidence()))
    assert result.residual == 1.0
    assert result.refusal is None


def test_two_claims_on_unlike_bases_refuse_rather_than_subtract():
    """Chargeable weight minus gross weight is a number with no referent.
    It looks exactly like a finding, which is why it must not be produced."""
    result = diverge(
        _commitment(quantity=Quantity(1000.0, "kg", "chargeable")),
        Outcome("quote-0001", _evidence(quantity=Quantity(1200.0, "kg", "gross"))))
    assert result.residual is None, "a residual across unlike bases is a unit error"
    assert result.refusal is not None and DIVERGENCE_ACROSS_UNLIKE_BASIS in result.refusal
    assert "chargeable" in result.refusal and "gross" in result.refusal


def test_an_unknown_basis_agrees_with_nothing_including_itself_misspelled():
    result = diverge(
        _commitment(quantity=Quantity(1.0, "kg", "all_in")),
        Outcome("quote-0001", _evidence(quantity=Quantity(1.0, "kg", "all-in"))))
    assert result.residual is None, "spelling is not agreement; the basis must match exactly"


# =====================================================================
# Row accounting on the pairing, and class 7 on the empty one
# =====================================================================

def _settled_pair(key: str, committed: float, realized: float):
    commitments = CommitmentStore()
    commitments.issue(_commitment(idempotency_key=key,
                                  quantity=Quantity(committed, "days", "door_to_door")))
    outcomes = OutcomeStore(commitments)
    outcomes.record(Outcome(key, _evidence(quantity=Quantity(realized, "days", "door_to_door"))))
    return commitments, outcomes


def test_every_commitment_lands_in_exactly_one_bucket_and_they_conserve():
    """The lesson a plant taught the session instrument: refusing a
    conflict is not the same as not double-counting it. Assert
    CONSERVATION, not merely the refusal."""
    commitments = CommitmentStore()
    commitments.issue(_commitment(idempotency_key="settled"))
    commitments.issue(_commitment(idempotency_key="live"))
    commitments.issue(_commitment(idempotency_key="withdrawn", revoked_at="2026-08-25"))
    commitments.issue(_commitment(idempotency_key="mismatched",
                                  quantity=Quantity(1.0, "kg", "chargeable")))
    outcomes = OutcomeStore(commitments)
    outcomes.record(Outcome("settled", _evidence()))
    outcomes.record(Outcome("mismatched", _evidence(quantity=Quantity(1.0, "kg", "gross"))))

    result = pair(commitments, outcomes)
    assert result.accounted == len(commitments) == 4, (
        "every issued commitment must appear in exactly one bucket; a commitment that is "
        "in none of them is a promise the firm has forgotten it made"
    )
    assert [d.subject for d in result.divergences]
    assert result.unsettled == ("live",)
    assert result.revoked == ("withdrawn",)
    assert len(result.basis_refused) == 1
    everything = ([d.subject for d in result.divergences] + list(result.unsettled)
                  + list(result.revoked))
    assert len(everything) == len(set(everything)), "no commitment may appear twice"


def test_no_pairs_because_nothing_was_ever_promised():
    commitments = CommitmentStore()
    result = pair(commitments, OutcomeStore(commitments))
    assert result.empty_because is not None
    assert NO_PAIRS_BECAUSE_NO_COMMITMENTS_WERE_ISSUED in result.empty_because


def test_no_pairs_because_nothing_has_settled_yet():
    commitments = CommitmentStore()
    commitments.issue(_commitment())
    result = pair(commitments, OutcomeStore(commitments))
    assert result.empty_because is not None
    assert NO_PAIRS_BECAUSE_NO_OUTCOME_HAS_ARRIVED_YET in result.empty_because


def test_no_pairs_because_every_commitment_was_revoked():
    commitments = CommitmentStore()
    commitments.issue(_commitment(revoked_at="2026-08-25"))
    result = pair(commitments, OutcomeStore(commitments))
    assert result.empty_because is not None
    assert NO_PAIRS_BECAUSE_EVERY_COMMITMENT_WAS_REVOKED in result.empty_because


def test_no_pairs_because_every_pair_differed_in_basis_is_a_fault_not_a_quiet_quarter():
    """The four empties are four different weeks. This one in particular
    means the measurement pipeline is broken, and reading it as 'nothing
    happened' would hide a fault behind a plausible silence."""
    commitments = CommitmentStore()
    commitments.issue(_commitment(quantity=Quantity(1.0, "kg", "chargeable")))
    outcomes = OutcomeStore(commitments)
    outcomes.record(Outcome("quote-0001", _evidence(quantity=Quantity(1.0, "kg", "gross"))))
    result = pair(commitments, outcomes)
    assert result.empty_because is not None
    assert NO_PAIRS_BECAUSE_EVERY_PAIR_DIFFERED_IN_BASIS in result.empty_because
    assert "not a quiet quarter" in result.empty_because


def test_the_four_empties_are_four_distinct_sentences():
    """Vacuity guard. If two of these produced the same warrant the reader
    could not tell the weeks apart, which is the class this exists to close."""
    commitments = CommitmentStore()
    empties = [pair(commitments, OutcomeStore(commitments)).empty_because]
    for setup in ("unsettled", "revoked", "basis"):
        store = CommitmentStore()
        if setup == "unsettled":
            store.issue(_commitment())
            outs = OutcomeStore(store)
        elif setup == "revoked":
            store.issue(_commitment(revoked_at="2026-08-25"))
            outs = OutcomeStore(store)
        else:
            store.issue(_commitment(quantity=Quantity(1.0, "kg", "chargeable")))
            outs = OutcomeStore(store)
            outs.record(Outcome("quote-0001", _evidence(quantity=Quantity(1.0, "kg", "gross"))))
        empties.append(pair(store, outs).empty_because)
    assert len(set(empties)) == 4, f"the empties must be distinguishable: {empties}"
    for sentence in empties:
        assert sentence is not None and len(sentence.split()) > 6, (
            "a status word is not a warrant; the reader must learn which nothing this is"
        )
