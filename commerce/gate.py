"""The gate — eligibility, then compliance, then economics — and the
morning view it produces.

THE ORDER IS BY COST, NOT BY IMPORTANCE. Eligibility is a set lookup;
compliance is a credential check; economics needs a carrier cost, which
needs a phone call. Each stage is cheaper than the next, so an
activity-class refusal at stage one saves an hour of pricing that would
have ended in the same refusal.

THREE OUTCOMES AT COMPLIANCE, NOT TWO. Refused, conditional-on-X, and --
the one that matters -- cannot-determine. A boolean collapses the third
into whichever way the code happens to fail, and in this domain that means
either declining good work or moving a load the firm is not authorised to
move. Those are not symmetric errors and neither is acceptable as a
default.

UNPRICEABLE IS A VERDICT, NOT A FAILURE. An opportunity missing a pricing
input is unpriceable and appears in the morning view with the one thing
needed to price it. It is never priced with zeros: zero is a value and
unknown is not, and a contribution computed with an assumed accessorial
exposure is a guess wearing a decision's clothes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

from commerce.opportunity import (ACTIVITY_CLASSES, CROSS_BORDER_BROKERAGE,
                                  CUSTOMS_CLEARANCE, DANGEROUS_GOODS, DOMESTIC_BROKERAGE,
                                  EXPEDITE, FORWARDING, GOVERNMENT_SUPPLY, WAREHOUSING,
                                  Opportunity)

ELIGIBILITY = "eligibility"
COMPLIANCE = "compliance"
ECONOMICS = "economics"

REFUSED = "refused"
CONDITIONAL = "conditional"
CANNOT_DETERMINE = "cannot_determine"
UNPRICEABLE = "unpriceable"
PRICED = "priced"

#: What each activity class requires. The gate keys on activity class
#: because "registered and compliant" is per-activity: a firm authorised
#: to broker domestic freight is not thereby authorised to clear customs.
REQUIRED_CREDENTIALS: Mapping[str, Tuple[str, ...]] = {
    DOMESTIC_BROKERAGE: ("cargo_liability_insurance",),
    CROSS_BORDER_BROKERAGE: ("cargo_liability_insurance", "surety_bond", "us_broker_authority"),
    EXPEDITE: ("cargo_liability_insurance",),
    FORWARDING: ("cargo_liability_insurance", "freight_forwarder_registration"),
    CUSTOMS_CLEARANCE: ("customs_brokerage_licence",),
    DANGEROUS_GOODS: ("cargo_liability_insurance", "dangerous_goods_qualification"),
    WAREHOUSING: ("warehouse_liability_insurance",),
    GOVERNMENT_SUPPLY: ("cargo_liability_insurance", "procurement_supplier_registration"),
}

HELD = "held"
NOT_HELD = "not_held"
UNKNOWN = "unknown"

ACTIVITY_CLASS_NOT_AUTHORISED = "ACTIVITY_CLASS_NOT_AUTHORISED"
OPPORTUNITY_HAS_EXPIRED = "OPPORTUNITY_HAS_EXPIRED"
CREDENTIAL_NOT_HELD = "CREDENTIAL_NOT_HELD"
CREDENTIAL_STATUS_UNKNOWN = "CREDENTIAL_STATUS_UNKNOWN"
PRICING_INPUT_MISSING = "PRICING_INPUT_MISSING"

#: Class 7 on the morning view.
NOTHING_ARRIVED = "NOTHING_ARRIVED"
EVERYTHING_EXPIRED = "EVERYTHING_EXPIRED"
EVERYTHING_REFUSED_AT_ELIGIBILITY = "EVERYTHING_REFUSED_AT_ELIGIBILITY"


@dataclass(frozen=True)
class GateVerdict:
    opportunity: str
    stage: str
    status: str
    clause: Optional[str] = None
    requires: Tuple[str, ...] = ()
    missing: Tuple[str, ...] = ()
    detail: str = ""
    remedy: Optional[str] = None

    @property
    def priced(self) -> bool:
        return self.status == PRICED


@dataclass(frozen=True)
class Authorisations:
    """What the firm may actually do, and what it can prove.

    A credential the firm has not checked is UNKNOWN, not absent. The
    difference is the same three-state rule as carrier vetting, applied to
    the firm itself: "we have not confirmed our bond is current" and "we
    have no bond" are different situations and only one of them is
    solvable this morning.
    """

    activity_classes: FrozenSet[str]
    credentials: Mapping[str, str]

    def status_of(self, credential: str) -> str:
        return self.credentials.get(credential, UNKNOWN)


def check_eligibility(opportunity: Opportunity, authorisations: Authorisations,
                      *, asof: str) -> Optional[GateVerdict]:
    """Stage one: the cheapest check there is."""
    if opportunity.expired_at(asof):
        return GateVerdict(
            opportunity.identifier, ELIGIBILITY, REFUSED, clause=OPPORTUNITY_HAS_EXPIRED,
            detail=f"expired {opportunity.expires_at}, evaluated {asof}. A spot load expires in "
                   "hours; pricing one that has gone is the cheapest waste available.",
        )
    if opportunity.activity_class not in authorisations.activity_classes:
        return GateVerdict(
            opportunity.identifier, ELIGIBILITY, REFUSED, clause=ACTIVITY_CLASS_NOT_AUTHORISED,
            detail=f"this is {opportunity.activity_class!r} work and the firm is authorised for "
                   f"{sorted(authorisations.activity_classes)}. Refused before pricing, because "
                   "the price does not change the answer.",
            remedy=f"obtain authorisation for {opportunity.activity_class}, or decline this "
                   "channel deliberately rather than by silence.",
        )
    return None


def check_compliance(opportunity: Opportunity,
                     authorisations: Authorisations) -> Optional[GateVerdict]:
    """Stage two, with three outcomes.

    Ordering is deliberate: a credential the firm KNOWS it lacks refuses,
    and only an unchecked one is undetermined. A definite failure is not
    made ambiguous by a second credential nobody has looked at.
    """
    required = REQUIRED_CREDENTIALS.get(opportunity.activity_class, ())
    not_held = [c for c in required if authorisations.status_of(c) == NOT_HELD]
    unknown = [c for c in required if authorisations.status_of(c) == UNKNOWN]

    if not_held:
        return GateVerdict(
            opportunity.identifier, COMPLIANCE, REFUSED, clause=CREDENTIAL_NOT_HELD,
            requires=tuple(not_held),
            detail=f"{opportunity.activity_class} requires {list(required)} and the firm does not "
                   f"hold {not_held}.",
            remedy=f"obtain {not_held[0]}, or decline this activity class.",
        )
    if unknown:
        return GateVerdict(
            opportunity.identifier, COMPLIANCE, CANNOT_DETERMINE,
            clause=CREDENTIAL_STATUS_UNKNOWN, requires=tuple(unknown),
            detail=f"{unknown} has not been confirmed. This is not a finding that the firm lacks "
                   "it, and not a finding that it holds it. A boolean here would either decline "
                   "good work or move a load the firm may not be authorised to move.",
            remedy=f"confirm {unknown[0]} and record its expiry; then re-run the gate.",
        )
    return None


def price(opportunity: Opportunity, *, carrier_cost: Optional[float],
          accessorials: Optional[float], financing_cost: Optional[float],
          capital_required: Optional[float],
          risk_reserve: Optional[float]) -> GateVerdict:
    """Stage three. Unpriceable rather than priced-with-zeros.

    Capital required and financing cost are NOT optional inputs with
    sensible defaults. They are the two most likely to be quietly zeroed,
    and a contribution reported without them is the number that looks fine
    right up to the point the facility binds.
    """
    revenue_field = opportunity.fields["revenue"]
    inputs = {
        "revenue": float(revenue_field.value) if revenue_field.present else None,  # type: ignore[arg-type]
        "carrier_cost": carrier_cost,
        "accessorials": accessorials,
        "financing_cost": financing_cost,
        "capital_required": capital_required,
        "risk_reserve": risk_reserve,
    }
    absent = tuple(name for name, value in inputs.items() if value is None)
    gaps = opportunity.gaps
    if absent or gaps:
        return GateVerdict(
            opportunity.identifier, ECONOMICS, UNPRICEABLE, clause=PRICING_INPUT_MISSING,
            missing=tuple(sorted(set(absent) | set(gaps))),
            detail="zero is a value and unknown is not. A contribution computed with an assumed "
                   "accessorial exposure is a guess wearing a decision's clothes.",
            remedy=opportunity.call_to_make or (
                f"obtain {(absent or gaps)[0]}" if (absent or gaps) else None),
        )
    contribution = (inputs["revenue"] - inputs["carrier_cost"]  # type: ignore[operator]
                    - inputs["accessorials"] - inputs["financing_cost"]
                    - inputs["risk_reserve"])
    return GateVerdict(
        opportunity.identifier, ECONOMICS, PRICED,
        detail=f"contribution {contribution:.2f} on capital {capital_required:.2f}",
    )


@dataclass(frozen=True)
class MorningView:
    """Three lists. The middle one is the product."""

    priced: Tuple[GateVerdict, ...]
    blocked: Tuple[GateVerdict, ...]
    refused: Tuple[GateVerdict, ...]
    call_sheet: Tuple[str, ...]
    considered: int
    empty_because: Optional[str] = None

    @property
    def accounted(self) -> int:
        return len(self.priced) + len(self.blocked) + len(self.refused)

    @property
    def conserves(self) -> bool:
        return self.accounted == self.considered


def morning_view(opportunities: Sequence[Opportunity], authorisations: Authorisations,
                 pricing: Mapping[str, Mapping[str, Optional[float]]],
                 *, asof: str) -> MorningView:
    """Run every opportunity through the gate and partition the results.

    EVERY opportunity lands in exactly one of the three lists, asserted.
    An opportunity in none of them is one the operator will never see, and
    the unpriceable ones are the day's work rather than its residue.
    """
    priced: List[GateVerdict] = []
    blocked: List[GateVerdict] = []
    refused: List[GateVerdict] = []
    calls: List[str] = []

    for opportunity in opportunities:
        verdict = check_eligibility(opportunity, authorisations, asof=asof)
        if verdict is not None:
            refused.append(verdict)
            continue
        verdict = check_compliance(opportunity, authorisations)
        if verdict is not None:
            (refused if verdict.status == REFUSED else blocked).append(verdict)
            if verdict.status == CANNOT_DETERMINE and verdict.remedy:
                calls.append(f"{opportunity.identifier} — {verdict.remedy}")
            continue
        inputs = pricing.get(opportunity.identifier, {})
        verdict = price(
            opportunity,
            carrier_cost=inputs.get("carrier_cost"),
            accessorials=inputs.get("accessorials"),
            financing_cost=inputs.get("financing_cost"),
            capital_required=inputs.get("capital_required"),
            risk_reserve=inputs.get("risk_reserve"),
        )
        if verdict.priced:
            priced.append(verdict)
        else:
            blocked.append(verdict)
            call = opportunity.call_to_make
            if call:
                calls.append(f"{opportunity.identifier} — {call}")

    empty_because: Optional[str] = None
    if not opportunities:
        empty_because = (f"{NOTHING_ARRIVED}: no opportunity reached the engine today. That is a "
                         "silent intake, not a market with nothing in it, and the two look "
                         "identical on an empty screen.")
    elif not priced and not blocked and refused:
        if all(v.clause == OPPORTUNITY_HAS_EXPIRED for v in refused):
            empty_because = (f"{EVERYTHING_EXPIRED}: {len(refused)} opportunities arrived and all "
                             "had expired by the time the view was built. The intake is working "
                             "and it is too slow.")
        else:
            empty_because = (f"{EVERYTHING_REFUSED_AT_ELIGIBILITY}: {len(refused)} arrived and "
                             "none is work this firm is authorised to do. That is a channel "
                             "problem, not a quiet day.")

    return MorningView(
        priced=tuple(priced), blocked=tuple(blocked), refused=tuple(refused),
        call_sheet=tuple(calls), considered=len(opportunities), empty_because=empty_because)


def render(view: MorningView, *, sustainable_loads_per_week: Optional[float] = None) -> str:
    """The morning screen.

    The sustainable book size prints beside the margin because exceeding
    it is insolvency at a profit, and it arrives exactly when things are
    going well.
    """
    lines = [f"PRICED   {len(view.priced):>3}",
             f"BLOCKED  {len(view.blocked):>3}   <- the day's work",
             f"REFUSED  {len(view.refused):>3}"]
    if not view.conserves:
        lines.append(f"  ! {view.accounted} accounted for {view.considered} opportunities")
    if view.empty_because:
        lines.append(f"  (empty) {view.empty_because}")
    for verdict in view.priced:
        lines.append(f"  PRICED   {verdict.opportunity}: {verdict.detail}")
    for verdict in view.blocked:
        need = list(verdict.missing or verdict.requires)
        lines.append(f"  BLOCKED  {verdict.opportunity}: needs {need}")
        if verdict.remedy:
            lines.append(f"           -> {verdict.remedy}")
    for verdict in view.refused:
        lines.append(f"  REFUSED  {verdict.opportunity} at {verdict.stage}: {verdict.clause}")
    if view.call_sheet:
        lines.append("CALL SHEET")
        for call in view.call_sheet:
            lines.append(f"  {call}")
    if sustainable_loads_per_week is not None:
        lines.append(f"SUSTAINABLE BOOK  {sustainable_loads_per_week:.1f} loads/week — "
                     "growing past this is insolvency at a profit")
    return "\n".join(lines)
