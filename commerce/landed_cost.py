"""PC-4 — a landed cost that states its axes and refuses when one is unknown.

WHY THE REFUSALS HERE ARE NOT HYPOTHETICAL. Two of them were measured in
the live CanadaBuys award feed while this module was being written
(architecture/canadabuys_recon.yaml):

  * 196 of 3056 awards carry `contractAmount = "0.00"` with the currency
    column BLANK. Those are not contracts worth nothing -- they are
    contracts whose value was not disclosed: standing offers, supply
    arrangements, task-authorisation contracts. Summing the column treats
    all 196 as zero and understates the market with no error anywhere.
    That is the null-is-not-zero rule, in production, with money attached.

  * 1008 of 3056 carry a `contractAmount` that DIFFERS from
    `totalContractValue`. Both are money, both are plausible readings of
    "the price", and they are measured on different bases -- this
    amendment versus the cumulative contract. Adding one to the other, or
    comparing a bid against whichever happens to be populated, is the
    mud-tonnage error in a commercial document.

So: every component carries basis, currency AND the date its currency was
priced at, and a completeness. An unknown component produces a range or a
refusal. It never produces a zero.

WHY A RANGE IS A LEGITIMATE ANSWER AND A POINT ESTIMATE IS NOT. A duty
rate that depends on an HS classification not yet made has a knowable
floor and ceiling; collapsing that to a midpoint invents precision the
classification has not earned. The range says what is known. The midpoint
says more than is known and looks the same as a measured number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

#: An amount with no currency is not a quantity of money. Measured on 196
#: of 3056 live awards, every one of them reading "0.00".
AMOUNT_WITHOUT_A_CURRENCY = "AMOUNT_WITHOUT_A_CURRENCY"
#: A currency with no date. Cross-currency arithmetic needs an FX date and
#: "today" is not one: a bid post-mortem asks what the rate was when the
#: bid was priced, not what it is now.
CURRENCY_WITHOUT_A_PRICING_DATE = "CURRENCY_WITHOUT_A_PRICING_DATE"
#: A component whose value is genuinely not known.
COMPONENT_NOT_KNOWN = "COMPONENT_NOT_KNOWN"
#: A component whose value is known only within bounds.
COMPONENT_KNOWN_ONLY_AS_A_RANGE = "COMPONENT_KNOWN_ONLY_AS_A_RANGE"
#: Summing across currencies without a conversion.
TOTAL_ACROSS_MIXED_CURRENCIES = "TOTAL_ACROSS_MIXED_CURRENCIES"
#: Summing across bases -- an amendment value added to a cumulative total.
TOTAL_ACROSS_MIXED_BASES = "TOTAL_ACROSS_MIXED_BASES"
#: One or more components are unknown, so the total is not a total.
TOTAL_REFUSED_BECAUSE_A_COMPONENT_IS_UNKNOWN = "TOTAL_REFUSED_BECAUSE_A_COMPONENT_IS_UNKNOWN"

#: Class 7 on the total. A zero total and an empty cost sheet look the
#: same in a spreadsheet cell and are entirely different situations.
NO_TOTAL_BECAUSE_NO_COMPONENTS_WERE_SUPPLIED = "NO_TOTAL_BECAUSE_NO_COMPONENTS_WERE_SUPPLIED"
NO_TOTAL_BECAUSE_EVERY_COMPONENT_WAS_REFUSED = "NO_TOTAL_BECAUSE_EVERY_COMPONENT_WAS_REFUSED"

#: Completeness, carried per component and never averaged away.
STATED = "stated"
ESTIMATED = "estimated"
BOUNDED = "bounded"
UNKNOWN = "unknown"

#: The components a landed cost is made of. Named as a tuple so a cost
#: sheet missing one is visibly missing it rather than quietly shorter.
COMPONENTS: Tuple[str, ...] = (
    "goods", "freight", "insurance", "duty", "tax", "brokerage", "financing",
)


class CostRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Money:
    """An amount, its currency, and the date that currency was priced at.

    All three or none. `Money(0.0, "", "")` is refused at construction
    rather than admitted and dealt with later, because a zero with no
    currency is precisely the value that sums correctly and means nothing.
    """

    amount: float
    currency: str
    priced_at: str

    def __post_init__(self) -> None:
        if not self.currency.strip():
            raise CostRefusal(
                AMOUNT_WITHOUT_A_CURRENCY,
                f"{self.amount} of what? Measured on 196 of 3056 live award notices, all reading "
                "0.00 with a blank currency -- values that were not disclosed, not values of zero. "
                "Summing them understates the total and reports no error.",
            )
        if not self.priced_at.strip():
            raise CostRefusal(
                CURRENCY_WITHOUT_A_PRICING_DATE,
                f"{self.amount} {self.currency} with no pricing date. A post-mortem asks what the "
                "rate was when the bid was priced; 'today' answers a different question.",
            )


@dataclass(frozen=True)
class Component:
    """One line of the cost sheet: a value, or the reason there isn't one."""

    name: str
    basis: str
    completeness: str
    money: Optional[Money] = None
    lower: Optional[Money] = None
    upper: Optional[Money] = None
    code: Optional[str] = None
    remedy: Optional[str] = None

    @property
    def known(self) -> bool:
        return self.money is not None

    @property
    def bounded(self) -> bool:
        return self.money is None and self.lower is not None and self.upper is not None


def known(name: str, money: Money, *, basis: str, completeness: str = STATED) -> Component:
    return Component(name=name, basis=basis, completeness=completeness, money=money)


def bounded(name: str, lower: Money, upper: Money, *, basis: str, remedy: str) -> Component:
    """A component known only within bounds.

    A range is a legitimate answer. Collapsing it to a midpoint invents
    precision that the missing classification has not earned, and the
    midpoint is indistinguishable from a measured number downstream.
    """
    if lower.currency != upper.currency:
        raise CostRefusal(TOTAL_ACROSS_MIXED_CURRENCIES,
                          f"{name} bounded in {lower.currency} and {upper.currency}.")
    return Component(name=name, basis=basis, completeness=BOUNDED, lower=lower, upper=upper,
                     code=COMPONENT_KNOWN_ONLY_AS_A_RANGE, remedy=remedy)


def unknown(name: str, *, basis: str, remedy: str) -> Component:
    """A component whose value is not known. NOT zero, and not omitted:
    an omitted component makes a short cost sheet look complete."""
    return Component(name=name, basis=basis, completeness=UNKNOWN,
                     code=COMPONENT_NOT_KNOWN, remedy=remedy)


@dataclass(frozen=True)
class LandedCost:
    components: Tuple[Component, ...]
    currency: Optional[str]
    priced_at: Optional[str]
    #: Present only when every component is known and shares one currency.
    total: Optional[float] = None
    #: Present when some components are bounded: the floor and ceiling of
    #: what the sheet can support.
    total_lower: Optional[float] = None
    total_upper: Optional[float] = None
    refusal: Optional[str] = None
    empty_because: Optional[str] = None

    @property
    def missing(self) -> Tuple[str, ...]:
        return tuple(c.name for c in self.components if not c.known and not c.bounded)

    @property
    def declared_components(self) -> Tuple[str, ...]:
        return tuple(c.name for c in self.components)

    @property
    def undeclared_components(self) -> Tuple[str, ...]:
        """Components of the standard sheet that were never mentioned.

        Distinct from a component declared UNKNOWN. A sheet that omits
        brokerage entirely reads as a sheet with no brokerage cost; a sheet
        that declares brokerage unknown reads correctly.
        """
        return tuple(name for name in COMPONENTS if name not in self.declared_components)


def assemble(components: Sequence[Component], *, priced_at: Optional[str] = None) -> LandedCost:
    """Assemble a landed cost, refusing rather than defaulting.

    The total is produced ONLY when every declared component is known, in
    one currency, on one basis. Otherwise the sheet reports bounds if it
    can and a refusal naming the components that stopped it.
    """
    components = tuple(components)
    if not components:
        return LandedCost(
            components=(), currency=None, priced_at=priced_at,
            empty_because=(f"{NO_TOTAL_BECAUSE_NO_COMPONENTS_WERE_SUPPLIED}: no cost sheet was "
                           "built. This is not a landed cost of zero; it is the absence of a "
                           "landed cost, and a spreadsheet cell shows both as 0."),
        )

    valued = [c for c in components if c.known or c.bounded]
    if not valued:
        return LandedCost(
            components=components, currency=None, priced_at=priced_at,
            empty_because=(f"{NO_TOTAL_BECAUSE_EVERY_COMPONENT_WAS_REFUSED}: "
                           f"{len(components)} component(s) were declared and none carries a "
                           "value. The sheet exists and is empty of numbers, which is a different "
                           "state from no sheet at all."),
        )

    currencies = {(c.money or c.lower).currency for c in valued}  # type: ignore[union-attr]
    if len(currencies) > 1:
        return LandedCost(
            components=components, currency=None, priced_at=priced_at,
            refusal=(f"{TOTAL_ACROSS_MIXED_CURRENCIES}: {sorted(currencies)}. Converting needs a "
                     "rate AND the date to take it at, and this sheet was not given one. A total "
                     "produced by ignoring the currencies would be a number with no unit."),
        )
    currency = next(iter(currencies))

    bases = {c.basis for c in valued}
    if len(bases) > 1:
        return LandedCost(
            components=components, currency=currency, priced_at=priced_at,
            refusal=(f"{TOTAL_ACROSS_MIXED_BASES}: {sorted(bases)}. Measured live: 1008 of 3056 "
                     "award notices carry a per-amendment amount and a cumulative total that "
                     "differ. Both are money; adding them is not addition."),
        )

    dates = {(c.money or c.lower).priced_at for c in valued}  # type: ignore[union-attr]
    resolved_date = priced_at or (next(iter(dates)) if len(dates) == 1 else None)

    unresolved = [c.name for c in components if not c.known and not c.bounded]

    def _floor(component: Component) -> float:
        edge = component.money or component.lower
        assert edge is not None  # `valued` admits only known-or-bounded components
        return edge.amount

    def _ceiling(component: Component) -> float:
        edge = component.money or component.upper
        assert edge is not None
        return edge.amount

    lower = math.fsum(_floor(c) for c in valued)
    upper = math.fsum(_ceiling(c) for c in valued)

    if unresolved:
        return LandedCost(
            components=components, currency=currency, priced_at=resolved_date,
            total_lower=lower, total_upper=upper,
            refusal=(f"{TOTAL_REFUSED_BECAUSE_A_COMPONENT_IS_UNKNOWN}: {unresolved}. The bounds "
                     "below cover only the components that carry a value, so they are a floor on "
                     "the known part and NOT a range for the landed cost."),
        )

    if lower == upper:
        return LandedCost(components=components, currency=currency, priced_at=resolved_date,
                          total=lower, total_lower=lower, total_upper=upper)
    return LandedCost(
        components=components, currency=currency, priced_at=resolved_date,
        total_lower=lower, total_upper=upper,
        refusal=(f"{COMPONENT_KNOWN_ONLY_AS_A_RANGE}: the sheet supports "
                 f"{lower}..{upper} {currency} and no single number. A midpoint would invent "
                 "precision the missing classification has not earned."),
    )


def render(cost: LandedCost) -> str:
    lines = ["LANDED COST"]
    for component in cost.components:
        if component.known and component.money is not None:
            lines.append(f"  {component.name:<12} {component.money.amount:>12,.2f} "
                         f"{component.money.currency} @ {component.money.priced_at}  "
                         f"[{component.basis} / {component.completeness}]")
        elif component.bounded and component.lower is not None and component.upper is not None:
            lines.append(f"  {component.name:<12} {component.lower.amount:>12,.2f}.."
                         f"{component.upper.amount:,.2f} {component.lower.currency}  "
                         f"[{component.basis} / {component.completeness}]")
            lines.append(f"  {'':<12} remedy: {component.remedy}")
        else:
            lines.append(f"  {component.name:<12} {'UNKNOWN':>12}  [{component.basis}] "
                         f"— never 0.00")
            lines.append(f"  {'':<12} remedy: {component.remedy}")
    for name in cost.undeclared_components:
        lines.append(f"  {name:<12} {'NOT DECLARED':>12}  — this sheet never mentioned it, which "
                     "reads as no cost")
    if cost.total is not None:
        lines.append(f"  TOTAL        {cost.total:>12,.2f} {cost.currency} @ {cost.priced_at}")
    if cost.refusal:
        lines.append(f"  NO TOTAL — {cost.refusal}")
    if cost.empty_because:
        lines.append(f"  (empty) {cost.empty_because}")
    return "\n".join(lines)
