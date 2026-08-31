"""Opportunity intake — manual entry.

The one channel that needs no integration, and therefore the one that
produces the first fifty opportunities. It writes the SAME `Opportunity`
record a load-board adapter will later write, or the history restarts when
the integration lands.

An email reader was written here and REMOVED unbuilt on the same day; see
the note below `read_value`. It worked. It was out of phase.

THE RULE THAT DOES THE WORK: A HEDGED NUMBER IS NOT A NUMBER.

    "40000 lbs"              -> present
    "about 40,000 lbs"       -> UNPARSED, with the hedge quoted
    "40-45,000 lbs"          -> UNPARSED, with the range quoted
    "~40k"                   -> UNPARSED

A dispatcher writing `about 40,000 lbs` has told you something real and
has not told you the weight. Parsing 40000 out of it produces a number
indistinguishable downstream from a weight someone actually scaled, and
the pricing stage will treat it as one. So the hedge is preserved and the
field is UNPARSED -- which is a different state from missing, because the
remedy is to ask what the actual weight is rather than to ask whether
anyone knows it.

NO PERSON EVER REACHES THE RECORD. An email has a sender address and
usually a signature. `who_knows` carries a ROLE or an organisation --
`the shipper`, `the counterparty` -- never an address and never a
name. The parser has nowhere to put one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from commerce.opportunity import (MANUAL, PRICING_RELEVANT, Field, Opportunity,
                                  missing, present, unparsed)

INTAKE_FIELD_UNKNOWN = "INTAKE_FIELD_UNKNOWN"
INTAKE_NAMES_NO_CHANNEL = "INTAKE_NAMES_NO_CHANNEL"
INTAKE_CARRIES_A_PERSON = "INTAKE_CARRIES_A_PERSON"

#: Hedges that make a number a statement about a number. Matched BEFORE
#: any digit is extracted, so a hedged value never becomes a value.
_HEDGE = re.compile(
    r"(\babout\b|\bapprox\w*|\baround\b|\broughly\b|\bcirca\b|\bballpark\b|"
    r"\bor so\b|\bish\b|\bup to\b|\bat least\b|\bmin\.?\b|\bmax\.?\b|~|\+/-|±)",
    re.IGNORECASE)
#: A range is two numbers, and two numbers are not one number.
_RANGE = re.compile(r"\d[\d,\.]*\s*(?:-|–|—|to)\s*\d[\d,\.]*")
_NUMBER = re.compile(r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)")

#: Fields an email is read for, and who to ask when they are absent. The
#: mapping is per FIELD, because `ask the shipper` is useless advice on a
#: market rate and exactly right on a weight.
WHO_KNOWS: Mapping[str, Tuple[str, bool]] = {
    "origin": ("the counterparty", True),
    "destination": ("the counterparty", True),
    "commodity": ("the counterparty", True),
    "weight": ("the counterparty", True),
    "equipment": ("the counterparty", True),
    "pickup_window": ("the counterparty", True),
    "delivery_req": ("the counterparty", True),
    "revenue": ("the market — no counterparty to ask", False),
}

_NUMERIC_FIELDS = frozenset({"weight", "revenue"})


class IntakeRefusal(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def read_value(text: str, *, numeric: bool) -> Field[object]:
    """One stated value becomes a field, or says why it could not.

    The hedge check runs BEFORE the number is extracted, so a hedged value
    never becomes a value.
    """
    stated = text.strip()
    if not stated:
        return missing("the counterparty")
    if not numeric:
        return present(stated, "stated")
    hedge = _HEDGE.search(stated)
    if hedge:
        return unparsed(f"hedged: {stated!r} contains {hedge.group(0)!r}. A hedged number is a "
                        "statement ABOUT a number and is not one. Parsed, it would be "
                        "indistinguishable downstream from a figure someone actually measured.")
    if _RANGE.search(stated):
        return unparsed(f"a range: {stated!r}. Two numbers are not one number, and picking an "
                        "end or a midpoint invents a precision the sender did not offer.")
    found = _NUMBER.search(stated)
    if not found:
        return unparsed(f"no number in {stated!r}.")
    return present(float(found.group(1).replace(",", "")), "stated")


def _blank_fields() -> Dict[str, Field[object]]:
    out: Dict[str, Field[object]] = {}
    for name in PRICING_RELEVANT:
        who, askable = WHO_KNOWS.get(name, ("the counterparty", True))
        out[name] = missing(who, askable=askable)
    return out


# from_email() WAS WRITTEN HERE AND REMOVED, unbuilt, on 2026-08-31.
#
# It parses a labelled inbound email into this same record and it worked.
# It is removed because the standing plan's Phase 1 must-not is explicit
# and Phase 2 ranks adapters BY THE MISS LOG rather than by a document or
# by reasoning -- and no miss has named inbound email. It was built
# because it was small and adjacent, which is the exact erosion §7 names:
# the most effective way to lose a deliberate decision is a good idea.
#
# validWhile: this stays unbuilt WHILE the miss log names no opportunity
# lost to an unread inbound email. When one entry does, the condition has
# lapsed and this is re-taken rather than re-argued -- the label table and
# the hedge rule below are the whole of it, and `read_value` is already
# here because a person typing `about 40,000 lbs` is the same defect.


def from_manual_form(entry: Mapping[str, Any]) -> Opportunity:
    """One typed form becomes the canonical record.

    An unknown key is refused rather than dropped: a typo'd field is a
    value the operator believes they entered, and it would arrive at the
    gate looking like a field nobody filled in.
    """
    known = set(PRICING_RELEVANT) | {"identifier", "activity_class", "received_at",
                                     "expires_at", "channel"}
    unknown = sorted(set(entry) - known)
    if unknown:
        raise IntakeRefusal(
            INTAKE_FIELD_UNKNOWN,
            f"the form carries {unknown}, which this reader does not understand. Known: "
            f"{sorted(known)}. Refused rather than ignored — a dropped key is a value you "
            "believe you entered.")
    for required in ("identifier", "activity_class", "received_at"):
        if not str(entry.get(required, "")).strip():
            raise IntakeRefusal(INTAKE_NAMES_NO_CHANNEL,
                                f"{required!r} is required and nothing is defaulted.")
    for key, value in entry.items():
        if isinstance(value, str) and "@" in value and "." in value:
            raise IntakeRefusal(
                INTAKE_CARRIES_A_PERSON,
                f"{key!r} looks like an email address. This record has no field for a person, "
                "and the blocked list names a ROLE or an organisation so it stays a call sheet "
                "without carrying anyone's contact details.")

    fields = _blank_fields()
    for name in PRICING_RELEVANT:
        if name in entry and str(entry[name]).strip():
            fields[name] = read_value(str(entry[name]), numeric=name in _NUMERIC_FIELDS)
    return Opportunity(identifier=str(entry["identifier"]), channel=MANUAL,
                       activity_class=str(entry["activity_class"]),
                       received_at=str(entry["received_at"]), fields=fields,
                       expires_at=entry.get("expires_at"))


def blank_form() -> Dict[str, Any]:
    """Every field present and empty, with the hedge rule stated on it."""
    form: Dict[str, Any] = {"identifier": "", "activity_class": "", "received_at": "",
                            "expires_at": ""}
    for name in PRICING_RELEVANT:
        form[name] = ""
    form["how_to_fill_this"] = {
        "numbers": "enter the figure you were GIVEN. If they said `about 40,000 lbs`, type that "
                   "verbatim — the form records it as unparsed and puts the load on the blocked "
                   "list with `ask the weight`. Typing 40000 turns their guess into our number.",
        "blanks": "leave a field blank if nobody told you. Blank means `ask`; a hedge means "
                  "`they answered and the answer is not usable`. Those go to different places.",
        "no_people": "do not enter names, emails or phone numbers anywhere. There is no field "
                     "for them and the form refuses an address.",
    }
    return form
