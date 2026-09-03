"""Manual opportunity intake, and the rule that a hedged number is not a
number.

    "40000 lbs"          -> present
    "about 40,000 lbs"   -> UNPARSED, with the hedge quoted
    "40-45,000 lbs"      -> UNPARSED, with the range quoted

A dispatcher writing `about 40,000 lbs` has told you something real and
has not told you the weight. Parsing 40000 out of it produces a number
indistinguishable downstream from a weight someone actually scaled, and
the pricing stage treats it as one.

MISSING AND UNPARSED GO TO DIFFERENT PLACES. Missing means ask whether
anyone knows; unparsed means they answered and the answer is not usable.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce import opportunity_intake as intake  # noqa: E402
from commerce.opportunity import MISSING, PRESENT, UNPARSED  # noqa: E402
from commerce.opportunity_intake import (INTAKE_CARRIES_A_PERSON, INTAKE_FIELD_UNKNOWN,  # noqa: E402
                                         IntakeRefusal, blank_form, from_manual_form,
                                         read_value)

FORM = {"identifier": "O-1", "activity_class": "domestic_brokerage",
        "received_at": "2026-08-31"}


def test_a_plain_number_parses():
    field = read_value("40000 lbs", numeric=True)
    assert field.status == PRESENT and field.value == 40000.0


def test_a_hedged_number_is_unparsed_and_the_hedge_is_quoted():
    for hedged in ("about 40,000 lbs", "~40k", "approx 40000", "roughly 40,000",
                   "up to 40000", "40000 or so"):
        field = read_value(hedged, numeric=True)
        assert field.status == UNPARSED, f"{hedged!r} parsed as a value"
        assert hedged in field.reason
        assert "is not one" in field.reason or "not one number" in field.reason


def test_a_range_is_unparsed_because_two_numbers_are_not_one_number():
    field = read_value("40-45,000 lbs", numeric=True)
    assert field.status == UNPARSED
    assert "invents a precision the sender did not offer" in field.reason


def test_a_blank_is_missing_and_names_who_to_ask():
    field = read_value("", numeric=True)
    assert field.status == MISSING
    assert field.who_knows and field.askable


def test_missing_and_unparsed_are_different_states_with_different_remedies():
    """Missing means ask whether anyone knows; unparsed means they
    answered and the answer is not usable."""
    absent = read_value("", numeric=True)
    hedged = read_value("about 40000", numeric=True)
    assert absent.status != hedged.status
    assert absent.who_knows and not hedged.who_knows
    assert hedged.reason and not absent.reason


def test_a_hedged_weight_makes_the_opportunity_unpriceable_rather_than_priced():
    """The whole point: the hedge survives into the gate instead of
    becoming a number the pricing stage trusts."""
    from commerce.gate import price
    opportunity = from_manual_form({**FORM, "weight": "about 40,000 lbs",
                                    "revenue": "2400"})
    verdict = price(opportunity, carrier_cost=1800.0, accessorials=0.0, financing_cost=0.0,
                    capital_required=1800.0, risk_reserve=0.0)
    assert verdict.status == "unpriceable"
    assert "weight" in verdict.missing


def test_the_same_weight_stated_plainly_prices():
    """Vacuity guard: if the hedged case could never price either, the
    test above would prove nothing about the hedge."""
    from commerce.gate import price
    opportunity = from_manual_form({**FORM, **{name: "1" for name in
                                               ("origin", "destination", "commodity", "weight",
                                                "equipment", "pickup_window", "delivery_req")},
                                    "revenue": "2400"})
    verdict = price(opportunity, carrier_cost=1800.0, accessorials=0.0, financing_cost=0.0,
                    capital_required=1800.0, risk_reserve=0.0)
    assert verdict.status == "priced"


def test_a_typod_field_is_refused_rather_than_dropped():
    with pytest.raises(IntakeRefusal) as caught:
        from_manual_form({**FORM, "weigth": "40000"})
    assert caught.value.code == INTAKE_FIELD_UNKNOWN
    assert "a value you believe you entered" in caught.value.detail


def test_an_email_address_anywhere_in_the_form_is_refused():
    """The record has no field for a person, and the blocked list names a
    ROLE so it stays a call sheet without carrying contact details."""
    with pytest.raises(IntakeRefusal) as caught:
        from_manual_form({**FORM, "commodity": "steel — ask dispatch@acme.com"})
    assert caught.value.code == INTAKE_CARRIES_A_PERSON


def test_every_pricing_field_is_accounted_for_even_on_an_almost_empty_form():
    from commerce.opportunity import PRICING_RELEVANT
    opportunity = from_manual_form(FORM)
    # The constructor enforces it: a field simply absent from the record is
    # one nobody will ever be asked about.
    assert set(opportunity.fields) >= set(PRICING_RELEVANT)
    for name in PRICING_RELEVANT:
        assert opportunity.fields[name].status in (PRESENT, MISSING, UNPARSED)
    assert opportunity.completeness == 0.0
    assert opportunity.blocking_field is not None
    assert opportunity.call_to_make is not None


def test_the_form_states_the_hedge_rule_to_the_operator():
    notes = blank_form()["how_to_fill_this"]
    assert "about 40,000 lbs" in notes["numbers"]
    assert "turns their guess into our number" in notes["numbers"]
    assert "different places" in notes["blanks"]
    assert "no field for them" in notes["no_people"]


def test_the_email_reader_was_removed_and_says_why_in_the_source():
    """§7: an out-of-phase good idea is recorded as unbuilt, not shipped
    because it is small. The removal carries a validWhile condition so it
    is re-taken rather than re-argued."""
    assert not hasattr(intake, "from_email")
    source = (REPO_ROOT / "commerce" / "opportunity_intake.py").read_text()
    assert "REMOVED, unbuilt" in source
    assert "validWhile:" in source
    assert "no miss has named inbound email" in " ".join(source.split())
