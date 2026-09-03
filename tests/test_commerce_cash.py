"""Cash conversion graded.

The claim under test is that the capital requirement is a PRECONDITION and
not a field. A field that may be omitted is a field that will be omitted,
and a capital requirement defaulted to zero makes every opportunity look
fundable and the whole portfolio look solvent — while summing perfectly.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.cash import (CYCLE_IS_NEGATIVE_CONFIRM_THE_TERMS,  # noqa: E402
                           CYCLE_STATES_NO_PAYMENT_TERMS, NO_FACILITY_STATED,
                           NO_RATE_BECAUSE_NO_OPPORTUNITIES_WERE_SUPPLIED,
                           OPPORTUNITY_STATES_NO_CAPITAL_REQUIREMENT, CashCycle, CashRefusal,
                           Opportunity, portfolio, sustainable_rate)

CYCLE = CashCycle(carrier_paid_in_days=15, shipper_pays_in_days=45)


def _opportunity(**over: object) -> Opportunity:
    base = dict(identifier="load-1", contribution=300.0, currency="CAD",
                capital_required=2000.0, cycle=CYCLE)
    base.update(over)
    return Opportunity(**base)  # type: ignore[arg-type]


def test_an_opportunity_that_cannot_state_its_capital_is_refused_not_defaulted():
    with pytest.raises(CashRefusal) as caught:
        _opportunity(capital_required=None)
    assert caught.value.code == OPPORTUNITY_STATES_NO_CAPITAL_REQUIREMENT
    assert "sums perfectly" in caught.value.detail


def test_an_opportunity_with_no_payment_terms_is_refused():
    with pytest.raises(CashRefusal) as caught:
        _opportunity(cycle=None)
    assert caught.value.code == CYCLE_STATES_NO_PAYMENT_TERMS


def test_a_cycle_missing_one_side_is_unknown_and_not_short():
    """Defaulting the missing side to zero produces the most optimistic
    cycle available, which is the one that hides the constraint."""
    with pytest.raises(CashRefusal) as caught:
        CashCycle(carrier_paid_in_days=15, shipper_pays_in_days=None)
    assert caught.value.code == CYCLE_STATES_NO_PAYMENT_TERMS
    assert "most optimistic" in caught.value.detail


def test_the_gap_is_the_days_of_carrier_cost_outstanding():
    assert CYCLE.gap_days == 30


def test_factoring_enters_the_contribution_rather_than_arriving_later():
    """It converts a capital constraint into a rate, so the rate belongs
    in the margin from load one."""
    opportunity = _opportunity()
    after = opportunity.contribution_after_factoring(rate_per_annum=0.18)
    expected = 300.0 - (2000.0 * 0.18 * 30 / 365.0)
    assert abs(after - expected) < 1e-9
    assert after < opportunity.contribution


def test_the_sustainable_rate_is_computed_from_the_facility_and_the_cycle():
    """Exceeding it is insolvency at a profit, which is why it belongs
    beside the margin rather than in a separate spreadsheet."""
    result = sustainable_rate(facility=500_000.0, carrier_cost_per_load=2000.0, cycle=CYCLE)
    assert result.loads_per_week is not None
    # 2000 * 30/7 = 8571.43 outstanding per weekly load; 500k / that = 58.3
    assert abs(result.loads_per_week - 500_000.0 / (2000.0 * 30 / 7.0)) < 1e-9
    assert 58.0 < result.loads_per_week < 59.0
    assert result.outstanding_at_that_rate is not None
    assert abs(result.outstanding_at_that_rate - 500_000.0) < 1e-6


def test_the_worked_illustration_from_the_brief_reproduces():
    """50 loads/week at $2,000 carrier cost on a 30-day gap needs roughly
    $430k outstanding — inside the $400-600k the brief estimates."""
    outstanding = 50 * 2000.0 * 30 / 7.0
    assert 400_000 < outstanding < 600_000
    result = sustainable_rate(facility=outstanding, carrier_cost_per_load=2000.0, cycle=CYCLE)
    assert result.loads_per_week is not None
    assert abs(result.loads_per_week - 50.0) < 1e-9


def test_an_unstated_facility_is_not_a_facility_of_zero():
    """A facility of zero means the sustainable rate is zero, which is a
    finding. An unstated one means there is no finding at all."""
    result = sustainable_rate(facility=None, carrier_cost_per_load=2000.0, cycle=CYCLE)
    assert result.loads_per_week is None
    assert result.refusal is not None and NO_FACILITY_STATED in result.refusal
    assert "which is a finding" in result.refusal and "no finding at all" in result.refusal


def test_a_facility_of_zero_yields_a_rate_of_zero_rather_than_a_refusal():
    result = sustainable_rate(facility=0.0, carrier_cost_per_load=2000.0, cycle=CYCLE)
    assert result.loads_per_week == 0.0
    assert result.refusal is None


def test_an_inverted_cycle_refuses_rather_than_reporting_an_unbounded_rate():
    inverted = CashCycle(carrier_paid_in_days=45, shipper_pays_in_days=15)
    result = sustainable_rate(facility=500_000.0, carrier_cost_per_load=2000.0, cycle=inverted)
    assert result.loads_per_week is None
    assert result.refusal is not None and CYCLE_IS_NEGATIVE_CONFIRM_THE_TERMS in result.refusal


def test_a_zero_cycle_refuses_because_it_reads_like_two_dates_entered_the_same():
    zero = CashCycle(carrier_paid_in_days=30, shipper_pays_in_days=30)
    result = sustainable_rate(facility=500_000.0, carrier_cost_per_load=2000.0, cycle=zero)
    assert result.loads_per_week is None
    assert result.refusal is not None and "entered the same" in result.refusal


def test_an_empty_book_is_not_a_book_with_nothing_worth_doing():
    result = portfolio([])
    assert result.total_contribution is None
    assert result.empty_because is not None
    assert NO_RATE_BECAUSE_NO_OPPORTUNITIES_WERE_SUPPLIED in result.empty_because


def test_a_portfolio_totals_contribution_and_capital_together():
    result = portfolio([_opportunity(), _opportunity(identifier="load-2")])
    assert result.total_contribution == 600.0
    assert result.total_capital == 4000.0, (
        "capital must be totalled beside contribution; a margin total without a capital total is "
        "the number that looks fine right up to the point the facility binds"
    )


def test_a_portfolio_across_currencies_refuses_to_total():
    result = portfolio([_opportunity(), _opportunity(identifier="load-2", currency="USD")])
    assert result.total_contribution is None
    assert result.refusal is not None and "MIXED_CURRENCIES" in result.refusal
