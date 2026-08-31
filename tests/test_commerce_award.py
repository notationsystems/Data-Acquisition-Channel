"""The award feed, graded — and the measurement that makes a contract
value not a number.

MEASURED over the 3056 awards in the live 2026-2027 file:

    amount == 0 while total > 0        831   27.2%
    total == 0 while amount > 0         62    2.0%
    both zero                          807   26.4%
    the two columns DISAGREE          1008   33.0%

893 rows — 29.2% — are misread as a contract worth nothing by WHICHEVER
single column is picked. The fixture carries one of each shape, captured
verbatim from the live feed with the thirteen contactInfo columns blanked
in the same pass that wrote it.
"""

from __future__ import annotations

import csv
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.award import (AMENDMENT, AMOUNT_WITHOUT_A_CURRENCY, CUMULATIVE,  # noqa: E402
                            MEASURED_MISREAD_AS_ZERO, MEASURED_ROWS,
                            NO_POSTMORTEMS_BECAUSE_NO_AWARD_HAS_PUBLISHED_YET,
                            NO_POSTMORTEMS_BECAUSE_NO_BIDS_WERE_SUBMITTED,
                            VALUE_ABSENT_ON_THIS_BASIS, VALUE_IS_ZERO_ON_THIS_BASIS_AND_NOT_THE_OTHER,
                            VALUE_REQUESTED_WITHOUT_A_BASIS, Award, AwardRefusal, AwardValue,
                            match_bids, outcome_for, parse_awards, render)
from commerce.canadabuys import LIVE, PUBLISHED_NO_ROWS, UNPARSEABLE  # noqa: E402
from commerce.stores import (Authority, Commitment, CommitmentStore, Outcome,  # noqa: E402
                             OutcomeStore, Quantity, diverge)

FIXTURE = REPO_ROOT / "commerce" / "fixtures" / "canadabuys_award_sample.csv"
RAW = FIXTURE.read_text(encoding="utf-8")
URL = "https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv"
RETRIEVAL = parse_awards(RAW, source_url=URL, retrieved_at="2026-08-31")


# =====================================================================
# The captured bytes parse and the accounting conserves
# =====================================================================

def test_the_real_fixture_parses_and_conserves():
    assert RETRIEVAL.rung == LIVE
    assert RETRIEVAL.rows_in_feed == 4
    assert RETRIEVAL.conserves
    assert len(RETRIEVAL.awards) == 4


def test_the_committed_fixture_carries_no_person_data():
    rows = list(csv.DictReader(FIXTURE.open(encoding="utf-8-sig")))
    for row in rows:
        for column, value in row.items():
            if column.startswith("contactInfo"):
                assert not (value or "").strip(), f"{column} carries person data"


# =====================================================================
# THE FINDING: a contract value is not a number
# =====================================================================

def test_there_is_no_scalar_value_to_ask_for():
    """Every convenience that would let a caller get one number out
    without naming a basis is the defect this class exists to prevent."""
    value = AwardValue(amendment=1.0, cumulative=2.0, currency="CAD")
    assert not hasattr(value, "value")
    assert not hasattr(value, "amount")
    assert not hasattr(value, "__float__")


def test_asking_for_a_value_without_a_basis_is_refused():
    value = AwardValue(amendment=1.0, cumulative=2.0, currency="CAD")
    with pytest.raises(AwardRefusal) as caught:
        value.on("whatever")
    assert caught.value.code == VALUE_REQUESTED_WITHOUT_A_BASIS
    assert str(MEASURED_MISREAD_AS_ZERO) in caught.value.detail
    assert "no default to fall back on" in caught.value.detail


def test_zero_on_one_basis_while_the_other_is_positive_is_refused():
    """The 27.2% case. Taking the zero records a real contract as nothing."""
    value = AwardValue(amendment=0.0, cumulative=102_715.70, currency="USD")
    assert value.on(CUMULATIVE) == 102_715.70
    with pytest.raises(AwardRefusal) as caught:
        value.on(AMENDMENT)
    assert caught.value.code == VALUE_IS_ZERO_ON_THIS_BASIS_AND_NOT_THE_OTHER
    assert "record a real contract as nothing" in caught.value.detail


def test_the_reverse_case_is_refused_symmetrically():
    """The 2.0% case: a $2,000,000 amendment whose cumulative total reads
    zero. Reading `total` alone reports it as worthless."""
    value = AwardValue(amendment=2_000_000.0, cumulative=0.0, currency="CAD")
    assert value.on(AMENDMENT) == 2_000_000.0
    with pytest.raises(AwardRefusal) as caught:
        value.on(CUMULATIVE)
    assert caught.value.code == VALUE_IS_ZERO_ON_THIS_BASIS_AND_NOT_THE_OTHER


def test_the_fixture_contains_both_directions_of_the_defect():
    """Captured from the live feed, not constructed: whichever column an
    implementer picks, one of these rows is misread."""
    zero_on_one = [a for a in RETRIEVAL.awards if a.value.zero_on_exactly_one_basis]
    assert len(zero_on_one) >= 2, "the fixture must exercise both directions"
    directions = {(a.value.amendment == 0.0) for a in zero_on_one}
    assert directions == {True, False}, "both directions must be present"


def test_a_figure_with_no_currency_is_refused_on_either_basis():
    value = AwardValue(amendment=0.0, cumulative=0.0, currency=None)
    for basis in (AMENDMENT, CUMULATIVE):
        with pytest.raises(AwardRefusal) as caught:
            value.on(basis)
        assert caught.value.code == AMOUNT_WITHOUT_A_CURRENCY


def test_a_genuine_zero_on_both_bases_with_a_currency_is_a_value():
    """The rule is not that zero is forbidden. An amendment that changes
    no money is a fact."""
    value = AwardValue(amendment=0.0, cumulative=0.0, currency="CAD")
    assert value.on(AMENDMENT) == 0.0


def test_an_absent_figure_is_distinguished_from_a_zero_one():
    value = AwardValue(amendment=None, cumulative=5.0, currency="CAD")
    with pytest.raises(AwardRefusal) as caught:
        value.on(AMENDMENT)
    assert caught.value.code == VALUE_ABSENT_ON_THIS_BASIS


def test_the_measured_rate_is_pinned():
    assert MEASURED_MISREAD_AS_ZERO == 893 and MEASURED_ROWS == 3056
    assert MEASURED_MISREAD_AS_ZERO / MEASURED_ROWS > 0.29


def test_the_render_flags_the_rows_that_are_zero_on_one_basis():
    text = render(RETRIEVAL)
    assert "ZERO ON ONE BASIS ONLY" in text


# =====================================================================
# The bid post-mortem
# =====================================================================

def test_an_award_becomes_pc1_evidence_on_a_named_basis():
    award = [a for a in RETRIEVAL.awards
             if a.value.cumulative not in (None, 0.0) and a.value.currency][0]
    evidence = outcome_for(award, basis=CUMULATIVE, subject="bid:x",
                           retrieved_at="2026-08-31")
    assert evidence.quantity.basis == f"award:{CUMULATIVE}"
    assert evidence.evidence_class == "measured"


def test_known_at_is_the_publication_date_not_the_award_date():
    """The contract was awarded before the world could read about it, and
    a post-mortem asking what we knew must use the second."""
    award = [a for a in RETRIEVAL.awards
             if a.value.cumulative not in (None, 0.0) and a.value.currency][0]
    evidence = outcome_for(award, basis=CUMULATIVE, subject="bid:x",
                           retrieved_at="2026-08-31")
    assert evidence.provenance.known_at == award.known_at
    assert evidence.period == award.awarded_at


def test_the_basis_has_no_default_so_a_post_mortem_must_state_what_it_bid():
    import inspect
    parameters = inspect.signature(outcome_for).parameters
    assert parameters["basis"].default is inspect.Parameter.empty
    assert parameters["basis"].kind is inspect.Parameter.KEYWORD_ONLY


def test_a_bid_and_its_award_score_through_the_existing_divergence_machinery():
    """This is what the whole feed is for: an outcome the firm did not
    choose, produced by the world, scoring a bid with no new analytics."""
    award = [a for a in RETRIEVAL.awards
             if a.value.cumulative not in (None, 0.0) and a.value.currency][0]
    realized = award.value.on(CUMULATIVE)
    commitments = CommitmentStore()
    commitment = commitments.issue(Commitment(
        subject=f"bid:{award.solicitation}",
        quantity=Quantity(realized - 5_000.0, award.value.currency or "",
                          f"award:{CUMULATIVE}"),
        issuer="ops@firm",
        authority=Authority("ops", "signing_delegation", "2026-01-01", "2026-12-31"),
        idempotency_key=f"bid-{award.solicitation}", issued_at="2026-02-01"))
    outcomes = OutcomeStore(commitments)
    outcome = outcomes.record(Outcome(
        f"bid-{award.solicitation}",
        outcome_for(award, basis=CUMULATIVE, subject=f"bid:{award.solicitation}",
                    retrieved_at="2026-08-31")))
    result = diverge(commitment, outcome)
    assert result.refusal is None
    assert abs(result.residual - 5_000.0) < 1e-6


def test_a_bid_scored_against_the_other_basis_refuses_on_basis():
    """The guard that makes the named basis worth requiring."""
    award = [a for a in RETRIEVAL.awards
             if a.value.cumulative not in (None, 0.0) and a.value.currency][0]
    commitments = CommitmentStore()
    commitment = commitments.issue(Commitment(
        subject="bid:x", quantity=Quantity(1.0, award.value.currency or "",
                                           f"award:{AMENDMENT}"),
        issuer="ops@firm",
        authority=Authority("ops", "signing_delegation", "2026-01-01", "2026-12-31"),
        idempotency_key="bid-x", issued_at="2026-02-01"))
    outcomes = OutcomeStore(commitments)
    outcome = outcomes.record(Outcome("bid-x", outcome_for(
        award, basis=CUMULATIVE, subject="bid:x", retrieved_at="2026-08-31")))
    result = diverge(commitment, outcome)
    assert result.residual is None
    from commerce.stores import DIVERGENCE_ACROSS_UNLIKE_BASIS
    assert result.refusal is not None
    assert DIVERGENCE_ACROSS_UNLIKE_BASIS in result.refusal
    assert "this_amendment" in result.refusal and "cumulative_contract" in result.refusal


# =====================================================================
# The join, and class 7 on it
# =====================================================================

def test_an_unmatched_bid_stays_visible_as_unawarded():
    """Measured live, 966 open solicitations meet 2118 awarded ones at 38.
    That is the right answer: an open tender is mostly not yet awarded, so
    the ground truth arrives with a lag and dropping the unmatched hides it."""
    awarded = RETRIEVAL.awards[0].solicitation
    result = match_bids([awarded, "never-awarded-1", "never-awarded-2"], RETRIEVAL.awards)
    assert len(result.matched) == 1
    assert result.unawarded == ("never-awarded-1", "never-awarded-2")
    assert result.empty_because is None


def test_no_bids_is_not_a_record_of_losing():
    result = match_bids([], RETRIEVAL.awards)
    assert result.empty_because is not None
    assert NO_POSTMORTEMS_BECAUSE_NO_BIDS_WERE_SUBMITTED in result.empty_because
    assert "not a record of losing" in result.empty_because


def test_bids_awaiting_an_award_is_a_wait_not_a_loss():
    result = match_bids(["pending-a", "pending-b"], RETRIEVAL.awards)
    assert result.empty_because is not None
    assert NO_POSTMORTEMS_BECAUSE_NO_AWARD_HAS_PUBLISHED_YET in result.empty_because
    assert "a wait, not a loss" in result.empty_because


def test_the_two_empty_post_mortem_sets_are_distinguishable():
    a = match_bids([], RETRIEVAL.awards).empty_because
    b = match_bids(["pending"], RETRIEVAL.awards).empty_because
    assert a != b and a is not None and b is not None


# =====================================================================
# The ladder, and the hazard that is named rather than solved
# =====================================================================

def test_a_header_with_no_rows_is_its_own_rung():
    header = RAW.split("\n")[0] + "\n"
    result = parse_awards(header, source_url=URL, retrieved_at="2026-08-31")
    assert result.rung == PUBLISHED_NO_ROWS
    assert result.empty_because is not None and "not a filter" in result.empty_because


def test_a_wrong_header_refuses_rather_than_parsing_by_position():
    result = parse_awards("a,b,c\n1,2,3\n", source_url=URL, retrieved_at="2026-08-31")
    assert result.rung == UNPARSEABLE


def test_a_row_with_no_solicitation_is_rejected_because_it_cannot_be_joined():
    header = RAW.split("\n")[0]
    blank = ",".join('""' for _ in header.split(","))
    result = parse_awards(header + "\n" + blank + "\n", source_url=URL,
                          retrieved_at="2026-08-31")
    assert len(result.rejected) == 1
    assert result.conserves


def test_the_supplier_name_hazard_is_flagged_on_every_row_not_guessed_per_row():
    """A sole proprietor's legal name IS a person's name, and this module
    cannot tell a company from a person by inspecting a string. It says
    the hazard exists on every row rather than pretending some are safe."""
    for award in RETRIEVAL.awards:
        assert award.supplier_may_be_a_natural_person is True
