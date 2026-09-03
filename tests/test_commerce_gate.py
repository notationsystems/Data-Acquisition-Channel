"""The Opportunity Acquisition Engine, graded on the thing it sells.

THE MIDDLE LIST IS THE PRODUCT, so the tests that matter most are the ones
asserting a blocked opportunity survives to the screen with the one thing
needed to price it. An engine that drops the unpriceable and shows four
clean items has thrown away most of the day's work, and it looks better
doing it -- which is why the conservation assertion is here rather than
the count of priced items.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.gate import (ACTIVITY_CLASS_NOT_AUTHORISED, CANNOT_DETERMINE,  # noqa: E402
                           COMPLIANCE, CREDENTIAL_NOT_HELD, CREDENTIAL_STATUS_UNKNOWN,
                           ECONOMICS, ELIGIBILITY, EVERYTHING_EXPIRED,
                           EVERYTHING_REFUSED_AT_ELIGIBILITY, HELD, NOT_HELD, NOTHING_ARRIVED,
                           OPPORTUNITY_HAS_EXPIRED, PRICED, PRICING_INPUT_MISSING, REFUSED,
                           UNKNOWN, UNPRICEABLE, Authorisations, check_compliance,
                           check_eligibility, morning_view, price, render)
from commerce.opportunity import (CROSS_BORDER_BROKERAGE, DANGEROUS_GOODS,  # noqa: E402
                                  DOMESTIC_BROKERAGE, PRICING_RELEVANT, SHIPPER_DIRECT,
                                  Opportunity, OpportunityRefusal, missing, present, unparsed)

FULL_CREDENTIALS = {"cargo_liability_insurance": HELD, "surety_bond": HELD,
                    "us_broker_authority": HELD, "dangerous_goods_qualification": HELD}
AUTH = Authorisations(frozenset({DOMESTIC_BROKERAGE, CROSS_BORDER_BROKERAGE}), FULL_CREDENTIALS)


def _fields(**over):
    base = {name: present(1.0, "manual") for name in PRICING_RELEVANT}
    base.update(over)
    return base


def _opportunity(**over):
    base = dict(identifier="O-1", channel=SHIPPER_DIRECT, activity_class=DOMESTIC_BROKERAGE,
                received_at="2026-08-31", fields=_fields())
    base.update(over)
    return Opportunity(**base)


PRICING = {"carrier_cost": 1800.0, "accessorials": 120.0, "financing_cost": 30.0,
           "capital_required": 1800.0, "risk_reserve": 50.0}


# =====================================================================
# The record: every pricing field explicitly present, missing or unparsed
# =====================================================================

def test_a_missing_field_must_name_who_knows_it():
    """Without that, the blocked list is a backlog rather than a call
    sheet, and the engine's most valuable output becomes a list of regrets."""
    with pytest.raises(OpportunityRefusal) as caught:
        missing("")
    assert "call sheet" in caught.value.detail


def test_missing_and_unparsed_are_different_situations():
    """Nobody told us, versus somebody told us and this reader could not
    read it. Collapsing them sends an operator to make a call that has
    already been made."""
    gap = missing("the shipper")
    unreadable = unparsed("the weight is in a scanned PDF")
    assert gap.status != unreadable.status
    assert gap.who_knows and not unreadable.who_knows
    assert unreadable.reason and not gap.reason


def test_a_field_absent_from_the_record_entirely_is_refused():
    fields = _fields()
    del fields["weight"]
    with pytest.raises(OpportunityRefusal) as caught:
        _opportunity(fields=fields)
    assert "nobody will ever be asked about" in caught.value.detail


def test_completeness_is_measured_against_what_pricing_needs():
    """Not against the record's own field count — otherwise adding an
    optional field makes every opportunity less complete overnight."""
    full = _opportunity()
    assert full.completeness == 1.0
    partial = _opportunity(fields=_fields(weight=missing("the shipper"),
                                          revenue=missing("the shipper")))
    assert partial.completeness == (len(PRICING_RELEVANT) - 2) / len(PRICING_RELEVANT)


def test_the_blocking_field_prefers_a_gap_someone_can_be_asked_about():
    """The point of the list is the call to make this morning, and an
    unaskable gap cannot be closed by making one."""
    opportunity = _opportunity(fields=_fields(
        revenue=missing("the market — no one to ask", askable=False),
        weight=missing("the shipper")))
    assert opportunity.blocking_field == "weight"
    assert opportunity.call_to_make == "weight: ask the shipper"


def test_an_opportunity_with_only_unaskable_gaps_still_names_one():
    opportunity = _opportunity(fields=_fields(
        revenue=missing("the market", askable=False)))
    assert opportunity.blocking_field == "revenue"
    assert opportunity.call_to_make is None


def test_an_unknown_activity_class_is_refused_because_the_gate_keys_on_it():
    with pytest.raises(OpportunityRefusal) as caught:
        _opportunity(activity_class="vibes_haulage")
    assert "evaluated against no requirement at all and pass" in caught.value.detail


# =====================================================================
# The gate is ordered by cost
# =====================================================================

def test_an_unauthorised_activity_class_is_refused_before_any_pricing():
    verdict = check_eligibility(_opportunity(activity_class=DANGEROUS_GOODS), AUTH,
                                asof="2026-08-31")
    assert verdict is not None
    assert verdict.stage == ELIGIBILITY and verdict.clause == ACTIVITY_CLASS_NOT_AUTHORISED
    assert "the price does not change the answer" in verdict.detail


def test_an_expired_opportunity_is_refused_at_the_cheapest_stage():
    verdict = check_eligibility(_opportunity(expires_at="2026-08-30"), AUTH, asof="2026-08-31")
    assert verdict is not None and verdict.clause == OPPORTUNITY_HAS_EXPIRED


def test_an_eligible_opportunity_passes_stage_one_silently():
    assert check_eligibility(_opportunity(), AUTH, asof="2026-08-31") is None


# =====================================================================
# Three outcomes at compliance, and the third is the one that matters
# =====================================================================

def test_a_credential_the_firm_knows_it_lacks_refuses():
    auth = Authorisations(frozenset({CROSS_BORDER_BROKERAGE}),
                          {**FULL_CREDENTIALS, "surety_bond": NOT_HELD})
    verdict = check_compliance(_opportunity(activity_class=CROSS_BORDER_BROKERAGE), auth)
    assert verdict is not None
    assert verdict.status == REFUSED and verdict.clause == CREDENTIAL_NOT_HELD
    assert "surety_bond" in verdict.requires


def test_an_unchecked_credential_is_cannot_determine_and_not_a_refusal():
    """A boolean here would either decline good work or move a load the
    firm may not be authorised to move. Those are not symmetric errors and
    neither is acceptable as a default."""
    auth = Authorisations(frozenset({CROSS_BORDER_BROKERAGE}),
                          {"cargo_liability_insurance": HELD, "surety_bond": HELD})
    verdict = check_compliance(_opportunity(activity_class=CROSS_BORDER_BROKERAGE), auth)
    assert verdict is not None
    assert verdict.status == CANNOT_DETERMINE
    assert verdict.clause == CREDENTIAL_STATUS_UNKNOWN
    assert "us_broker_authority" in verdict.requires
    assert "not a finding that the firm lacks it" in verdict.detail
    assert verdict.remedy is not None


def test_a_definite_failure_outranks_an_unchecked_credential():
    auth = Authorisations(frozenset({CROSS_BORDER_BROKERAGE}),
                          {"cargo_liability_insurance": NOT_HELD})
    verdict = check_compliance(_opportunity(activity_class=CROSS_BORDER_BROKERAGE), auth)
    assert verdict is not None and verdict.status == REFUSED


def test_the_three_compliance_outcomes_are_all_reachable_and_distinct():
    ok = check_compliance(_opportunity(), AUTH)
    refused = check_compliance(_opportunity(),
                               Authorisations(frozenset({DOMESTIC_BROKERAGE}),
                                              {"cargo_liability_insurance": NOT_HELD}))
    unknown = check_compliance(_opportunity(),
                               Authorisations(frozenset({DOMESTIC_BROKERAGE}), {}))
    assert ok is None
    assert refused is not None and unknown is not None
    assert refused.status != unknown.status


# =====================================================================
# Economics: unpriceable, never priced-with-zeros
# =====================================================================

def test_a_missing_pricing_input_is_unpriceable_rather_than_zeroed():
    verdict = price(_opportunity(), **{**PRICING, "accessorials": None})
    assert verdict.status == UNPRICEABLE
    assert "accessorials" in verdict.missing
    assert "guess wearing a decision's clothes" in verdict.detail


def test_capital_required_is_never_optional():
    verdict = price(_opportunity(), **{**PRICING, "capital_required": None})
    assert verdict.status == UNPRICEABLE and "capital_required" in verdict.missing


def test_financing_cost_is_never_optional():
    verdict = price(_opportunity(), **{**PRICING, "financing_cost": None})
    assert verdict.status == UNPRICEABLE and "financing_cost" in verdict.missing


def test_a_missing_record_field_also_makes_it_unpriceable():
    verdict = price(_opportunity(fields=_fields(weight=missing("the shipper"))), **PRICING)
    assert verdict.status == UNPRICEABLE
    assert "weight" in verdict.missing
    assert verdict.remedy == "weight: ask the shipper"


def test_a_zero_input_is_a_value_and_prices():
    """The rule is not that zero is forbidden. A genuinely zero accessorial
    is a fact; a zero standing in for an unknown is not."""
    verdict = price(_opportunity(), **{**PRICING, "accessorials": 0.0})
    assert verdict.status == PRICED


def test_a_complete_opportunity_prices():
    opportunity = _opportunity(fields=_fields(revenue=present(2400.0, "shipper")))
    verdict = price(opportunity, **PRICING)
    assert verdict.status == PRICED
    assert "contribution 400.00" in verdict.detail


# =====================================================================
# The morning view: three lists, and every opportunity in exactly one
# =====================================================================

def _view(opportunities, pricing=None, auth=AUTH, asof="2026-08-31"):
    return morning_view(opportunities, auth,
                        pricing if pricing is not None else
                        {o.identifier: PRICING for o in opportunities}, asof=asof)


def test_every_opportunity_lands_in_exactly_one_list():
    opportunities = [
        _opportunity(identifier="priced", fields=_fields(revenue=present(2400.0, "s"))),
        _opportunity(identifier="blocked", fields=_fields(weight=missing("the shipper"))),
        _opportunity(identifier="refused", activity_class=DANGEROUS_GOODS),
        _opportunity(identifier="expired", expires_at="2026-08-01"),
    ]
    view = _view(opportunities)
    assert view.conserves, f"{view.accounted} accounted for {view.considered}"
    assert [v.opportunity for v in view.priced] == ["priced"]
    assert [v.opportunity for v in view.blocked] == ["blocked"]
    assert {v.opportunity for v in view.refused} == {"refused", "expired"}


def test_the_unpriceable_survive_to_the_screen_with_the_call_to_make():
    """The middle list is the product. An engine that drops these and
    shows four clean items has thrown away most of the day's work."""
    view = _view([_opportunity(identifier="O-9",
                               fields=_fields(weight=missing("the shipper")))])
    assert len(view.blocked) == 1
    assert view.call_sheet == ("O-9 — weight: ask the shipper",)
    assert "O-9 — weight: ask the shipper" in render(view)


def test_an_undetermined_compliance_verdict_reaches_the_call_sheet_too():
    view = morning_view([_opportunity(activity_class=CROSS_BORDER_BROKERAGE)],
                        Authorisations(frozenset({CROSS_BORDER_BROKERAGE}), {}),
                        {"O-1": PRICING}, asof="2026-08-31")
    assert len(view.blocked) == 1
    assert view.call_sheet and "confirm" in view.call_sheet[0]


def test_the_rendered_view_labels_the_middle_list_as_the_work():
    assert "<- the day's work" in render(_view([_opportunity()]))


def test_the_sustainable_book_prints_beside_the_margin():
    text = render(_view([_opportunity()]), sustainable_loads_per_week=58.3)
    assert "insolvency at a profit" in text


# =====================================================================
# Class 7 on the morning view: three ways to see an empty screen
# =====================================================================

def test_an_empty_intake_is_not_a_market_with_nothing_in_it():
    view = _view([])
    assert view.empty_because is not None and NOTHING_ARRIVED in view.empty_because
    assert "silent intake" in view.empty_because


def test_everything_expired_says_the_intake_is_too_slow():
    view = _view([_opportunity(identifier="a", expires_at="2026-08-01"),
                  _opportunity(identifier="b", expires_at="2026-08-02")])
    assert view.empty_because is not None and EVERYTHING_EXPIRED in view.empty_because
    assert "too slow" in view.empty_because


def test_everything_refused_at_eligibility_is_a_channel_problem():
    view = _view([_opportunity(identifier="a", activity_class=DANGEROUS_GOODS)])
    assert view.empty_because is not None
    assert EVERYTHING_REFUSED_AT_ELIGIBILITY in view.empty_because
    assert "not a quiet day" in view.empty_because


def test_the_three_empty_screens_are_distinguishable():
    empties = {
        _view([]).empty_because,
        _view([_opportunity(identifier="a", expires_at="2026-08-01")]).empty_because,
        _view([_opportunity(identifier="b", activity_class=DANGEROUS_GOODS)]).empty_because,
    }
    assert len(empties) == 3
