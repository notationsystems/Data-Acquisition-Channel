"""PC-4 graded, with the two discriminating cases taken from live data
rather than invented.

Both were measured in the CanadaBuys award feed on 2026-08-31:
196 of 3056 awards carry an amount of "0.00" with a blank currency, and
1008 of 3056 carry a per-amendment amount that differs from the cumulative
contract total. The first is null-as-zero; the second is two bases. Each
has a test below that fails if the module would have summed them.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.landed_cost import (AMOUNT_WITHOUT_A_CURRENCY,  # noqa: E402
                                  CURRENCY_WITHOUT_A_PRICING_DATE,
                                  NO_TOTAL_BECAUSE_EVERY_COMPONENT_WAS_REFUSED,
                                  NO_TOTAL_BECAUSE_NO_COMPONENTS_WERE_SUPPLIED,
                                  TOTAL_ACROSS_MIXED_BASES, TOTAL_ACROSS_MIXED_CURRENCIES,
                                  TOTAL_REFUSED_BECAUSE_A_COMPONENT_IS_UNKNOWN, CostRefusal,
                                  Money, assemble, bounded, known, render, unknown)

DDP = "ddp_destination"


def _m(amount: float, currency: str = "CAD", at: str = "2026-08-31") -> Money:
    return Money(amount, currency, at)


# =====================================================================
# The live case: 196 awards reading 0.00 with no currency
# =====================================================================

def test_an_amount_with_no_currency_is_refused_at_construction():
    """Measured on 196 of 3056 live awards, every one reading 0.00. Those
    are undisclosed values, not values of zero, and the column sums
    perfectly while understating the market."""
    with pytest.raises(CostRefusal) as caught:
        Money(0.0, "", "2026-08-31")
    assert caught.value.code == AMOUNT_WITHOUT_A_CURRENCY
    assert "196" in caught.value.detail, "the refusal should carry the measurement that motivates it"


def test_a_currency_with_no_pricing_date_is_refused():
    with pytest.raises(CostRefusal) as caught:
        Money(1000.0, "USD", "")
    assert caught.value.code == CURRENCY_WITHOUT_A_PRICING_DATE


def test_zero_is_a_legitimate_amount_when_it_has_a_currency_and_a_date():
    """The rule is not that zero is forbidden. A genuinely zero brokerage
    fee is a fact. What is forbidden is a zero standing in for an unknown."""
    component = known("brokerage", _m(0.0), basis=DDP)
    assert component.known and component.money is not None
    assert component.money.amount == 0.0


# =====================================================================
# The live case: 1008 awards where two money columns disagree
# =====================================================================

def test_components_on_different_bases_refuse_to_total():
    result = assemble([
        known("goods", _m(10_000.0), basis="fob_origin"),
        known("freight", _m(2_000.0), basis=DDP),
    ])
    assert result.total is None
    assert result.refusal is not None and TOTAL_ACROSS_MIXED_BASES in result.refusal
    assert "1008" in result.refusal


def test_components_in_different_currencies_refuse_to_total():
    result = assemble([
        known("goods", _m(10_000.0, "CAD"), basis=DDP),
        known("freight", _m(2_000.0, "USD"), basis=DDP),
    ])
    assert result.total is None
    assert result.refusal is not None and TOTAL_ACROSS_MIXED_CURRENCIES in result.refusal
    assert "CAD" in result.refusal and "USD" in result.refusal


# =====================================================================
# Unknown produces a refusal or a range. Never a zero.
# =====================================================================

def test_an_unknown_component_refuses_the_total_and_names_itself():
    result = assemble([
        known("goods", _m(10_000.0), basis=DDP),
        unknown("duty", basis=DDP, remedy="the HS classification has not been made; classify to "
                                          "8544.42 or 8536.90 and the rate follows"),
    ])
    assert result.total is None
    assert result.refusal is not None
    assert TOTAL_REFUSED_BECAUSE_A_COMPONENT_IS_UNKNOWN in result.refusal
    assert "duty" in result.refusal
    assert result.missing == ("duty",)


def test_the_bounds_beside_an_unknown_component_are_not_offered_as_a_range():
    """A floor on the known part is not a range for the landed cost. If it
    were read as one, an unknown duty would look like a small uncertainty
    rather than an open question."""
    result = assemble([
        known("goods", _m(10_000.0), basis=DDP),
        unknown("duty", basis=DDP, remedy="classification pending"),
    ])
    assert result.refusal is not None
    assert "NOT a range for the landed cost" in result.refusal


def test_a_bounded_component_yields_bounds_and_never_a_midpoint():
    """Collapsing a range to a midpoint invents precision the missing
    classification has not earned, and the midpoint is indistinguishable
    from a measured number downstream."""
    result = assemble([
        known("goods", _m(10_000.0), basis=DDP),
        bounded("duty", _m(0.0), _m(650.0), basis=DDP,
                remedy="classify the goods; the rate is 0% or 6.5% depending on heading"),
    ])
    assert result.total is None, "a bounded sheet has no single total"
    assert result.total_lower == 10_000.0
    assert result.total_upper == 10_650.0
    assert result.refusal is not None and "midpoint" in result.refusal


def test_a_fully_known_single_basis_sheet_totals():
    result = assemble([
        known("goods", _m(10_000.0), basis=DDP),
        known("freight", _m(2_000.0), basis=DDP),
        known("duty", _m(650.0), basis=DDP),
    ])
    assert result.total == 12_650.0
    assert result.refusal is None
    assert result.currency == "CAD"
    assert result.priced_at == "2026-08-31"


# =====================================================================
# Class 7 on the total, and the component nobody mentioned
# =====================================================================

def test_an_empty_sheet_is_not_a_landed_cost_of_zero():
    result = assemble([])
    assert result.total is None
    assert result.empty_because is not None
    assert NO_TOTAL_BECAUSE_NO_COMPONENTS_WERE_SUPPLIED in result.empty_because
    assert "a spreadsheet cell shows both as 0" in result.empty_because


def test_a_sheet_of_only_unknowns_is_a_different_nothing_from_an_empty_sheet():
    result = assemble([unknown("duty", basis=DDP, remedy="classification pending"),
                       unknown("freight", basis=DDP, remedy="no carrier quoted yet")])
    assert result.empty_because is not None
    assert NO_TOTAL_BECAUSE_EVERY_COMPONENT_WAS_REFUSED in result.empty_because


def test_the_two_empties_are_distinguishable():
    a = assemble([]).empty_because
    b = assemble([unknown("duty", basis=DDP, remedy="pending")]).empty_because
    assert a != b and a is not None and b is not None
    for sentence in (a, b):
        assert len(sentence.split()) > 8


def test_a_component_never_mentioned_is_reported_as_undeclared():
    """Distinct from a component declared unknown. A sheet that omits
    brokerage entirely reads as a sheet with no brokerage cost."""
    result = assemble([known("goods", _m(1.0), basis=DDP)])
    assert "brokerage" in result.undeclared_components
    assert "goods" not in result.undeclared_components
    assert "NOT DECLARED" in render(result)


def test_render_never_prints_a_zero_for_an_unknown():
    text = render(assemble([
        known("goods", _m(10_000.0), basis=DDP),
        unknown("duty", basis=DDP, remedy="the HS classification has not been made"),
    ]))
    duty_line = [line for line in text.splitlines() if "duty" in line][0]
    assert "never 0.00" in duty_line, "the line must say aloud what it is not printing"
    value_column = duty_line.split("—")[0]
    assert "UNKNOWN" in value_column
    assert "0.00" not in value_column, (
        f"an unknown printed as a number is the whole defect: {value_column!r}"
    )
