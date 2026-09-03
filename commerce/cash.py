"""Cash conversion — the binding constraint, modelled beside the margin.

WHY THIS IS NOT A FINANCE APPENDIX. Contribution is the easy constraint.
The binding one is timing: the carrier is paid in 7-30 days and the
shipper pays in 30-60, so roughly a month of carrier cost is permanently
outstanding. Brokerages fail on cash rather than on margin, and the
failure arrives precisely when volume is GROWING, because every additional
load widens the gap before it narrows it.

So the capital requirement lives in the same object as the contribution,
and an opportunity that cannot state it is REFUSED rather than defaulted
to zero. A zero capital requirement is the most dangerous default
available here: it makes every opportunity look fundable and the
portfolio look solvent, and it sums perfectly.

GROWTH RATE IS A COMPUTED CONSTRAINT, NOT AN AMBITION. Given a facility
size and a cycle length there is a maximum sustainable loads-per-week, and
exceeding it is insolvency at a profit. `sustainable_rate()` computes it;
it belongs on the dashboard beside the margin rather than in a
spreadsheet someone maintains separately.

FACTORING IS A MARGIN DECISION. It converts a capital constraint into a
rate, so the rate enters the contribution from load one rather than
arriving later as a financing line that surprises the margin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

#: The one refusal this module exists for.
OPPORTUNITY_STATES_NO_CAPITAL_REQUIREMENT = "OPPORTUNITY_STATES_NO_CAPITAL_REQUIREMENT"
#: A cycle with no payment terms on one side.
CYCLE_STATES_NO_PAYMENT_TERMS = "CYCLE_STATES_NO_PAYMENT_TERMS"
#: Terms that imply the shipper pays before the carrier does. Possible,
#: and rare enough that it is far more often a data-entry inversion.
CYCLE_IS_NEGATIVE_CONFIRM_THE_TERMS = "CYCLE_IS_NEGATIVE_CONFIRM_THE_TERMS"
#: A facility size of zero. Distinct from no facility having been stated.
NO_FACILITY_STATED = "NO_FACILITY_STATED"

#: Class 7 on a portfolio.
NO_RATE_BECAUSE_NO_OPPORTUNITIES_WERE_SUPPLIED = "NO_RATE_BECAUSE_NO_OPPORTUNITIES_WERE_SUPPLIED"


class CashRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CashCycle:
    """How long money is out.

    Both terms are required. A cycle with one side missing is not a short
    cycle; it is an unknown one, and defaulting the missing side to zero
    produces the most optimistic cycle available.
    """

    carrier_paid_in_days: Optional[int]
    shipper_pays_in_days: Optional[int]

    def __post_init__(self) -> None:
        if self.carrier_paid_in_days is None or self.shipper_pays_in_days is None:
            missing = ("carrier_paid_in_days" if self.carrier_paid_in_days is None
                       else "shipper_pays_in_days")
            raise CashRefusal(
                CYCLE_STATES_NO_PAYMENT_TERMS,
                f"{missing} is not stated. Defaulting it to zero produces the most optimistic "
                "cycle available, and the optimistic cycle is the one that hides the constraint.",
            )

    @property
    def gap_days(self) -> int:
        """Days of carrier cost outstanding per load."""
        return self.shipper_pays_in_days - self.carrier_paid_in_days  # type: ignore[operator]

    @property
    def inverted(self) -> bool:
        return self.gap_days < 0


@dataclass(frozen=True)
class Opportunity:
    """An opportunity priced with its capital requirement, not without it.

    `capital_required` and `cycle` are mandatory. The founding order's
    schema had capital as a field; this makes it a precondition, because a
    field that may be omitted is a field that will be.
    """

    identifier: str
    contribution: float
    currency: str
    capital_required: Optional[float]
    cycle: Optional[CashCycle]

    def __post_init__(self) -> None:
        if self.capital_required is None:
            raise CashRefusal(
                OPPORTUNITY_STATES_NO_CAPITAL_REQUIREMENT,
                f"{self.identifier!r} states a contribution of {self.contribution} "
                f"{self.currency} and no capital requirement. Defaulted to zero it makes every "
                "opportunity look fundable and the portfolio look solvent, and it sums perfectly.",
            )
        if self.cycle is None:
            raise CashRefusal(
                CYCLE_STATES_NO_PAYMENT_TERMS,
                f"{self.identifier!r} states no payment terms, so how long its capital is "
                "outstanding is unknown. Contribution per load without days outstanding is half "
                "a number.",
            )

    def contribution_after_factoring(self, *, rate_per_annum: float) -> float:
        """Factoring converts a capital constraint into a rate, so the rate
        belongs in the contribution rather than in a later financing line."""
        assert self.capital_required is not None and self.cycle is not None
        days = max(self.cycle.gap_days, 0)
        cost = self.capital_required * rate_per_annum * days / 365.0
        return self.contribution - cost


@dataclass(frozen=True)
class SustainableRate:
    loads_per_week: Optional[float]
    outstanding_at_that_rate: Optional[float]
    refusal: Optional[str] = None
    empty_because: Optional[str] = None


def sustainable_rate(*, facility: Optional[float], carrier_cost_per_load: float,
                     cycle: CashCycle) -> SustainableRate:
    """The maximum loads per week a given facility can carry.

    At steady state the outstanding balance is
    `loads_per_week * carrier_cost * gap_days / 7`. Setting that equal to
    the facility gives the ceiling. Exceeding it is insolvency at a
    profit, which is why this number belongs beside the margin rather than
    in a separate spreadsheet.
    """
    if facility is None:
        return SustainableRate(None, None, refusal=(
            f"{NO_FACILITY_STATED}: no working-capital facility was stated, so no sustainable "
            "rate can be computed. This is NOT a facility of zero — a facility of zero would mean "
            "the sustainable rate is zero, which is a finding; an unstated one means there is no "
            "finding at all."))
    if cycle.inverted:
        return SustainableRate(None, None, refusal=(
            f"{CYCLE_IS_NEGATIVE_CONFIRM_THE_TERMS}: the terms as entered have the shipper paying "
            f"{-cycle.gap_days} days before the carrier. That is possible and it is far more often "
            "an inversion at data entry, so it refuses rather than reporting an unbounded rate."))
    if cycle.gap_days == 0:
        return SustainableRate(None, None, refusal=(
            "CYCLE_IS_ZERO_SO_NO_RATE_BINDS: the terms as entered leave nothing outstanding, so "
            "the facility never binds. Confirm the terms — a genuinely zero cycle is unusual in "
            "this business and reads identically to two dates entered the same."))
    weekly_outstanding_per_load = carrier_cost_per_load * cycle.gap_days / 7.0
    loads = facility / weekly_outstanding_per_load
    return SustainableRate(loads_per_week=loads,
                           outstanding_at_that_rate=loads * weekly_outstanding_per_load)


@dataclass(frozen=True)
class Portfolio:
    opportunities: Tuple[Opportunity, ...]
    total_contribution: Optional[float]
    total_capital: Optional[float]
    currency: Optional[str]
    refusal: Optional[str] = None
    empty_because: Optional[str] = None


def portfolio(opportunities: Sequence[Opportunity]) -> Portfolio:
    opportunities = tuple(opportunities)
    if not opportunities:
        return Portfolio((), None, None, None, empty_because=(
            f"{NO_RATE_BECAUSE_NO_OPPORTUNITIES_WERE_SUPPLIED}: the book is empty. That is a "
            "book with nothing in it, not a book with nothing worth doing in it, and a zero "
            "contribution renders both the same."))
    currencies = {o.currency for o in opportunities}
    if len(currencies) > 1:
        return Portfolio(opportunities, None, None, None, refusal=(
            f"TOTAL_ACROSS_MIXED_CURRENCIES: {sorted(currencies)}. Summing needs a rate and a "
            "date to take it at."))
    return Portfolio(
        opportunities,
        total_contribution=sum(o.contribution for o in opportunities),
        total_capital=sum(o.capital_required or 0.0 for o in opportunities),
        currency=next(iter(currencies)),
    )
