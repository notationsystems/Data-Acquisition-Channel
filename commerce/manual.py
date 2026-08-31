"""PC-6 Part I — the manual adapter. A phone call is a source.

The first fifty loads are phone calls and emails. That is fine, and it is
fully expressible: a call has a `known_at` (when it was said, not when it
was typed), a method, a person who recorded it, and an artifact. What it
does NOT have is an integration, and that is the only difference.

WHAT THIS REFUSES, AND WHY EACH REFUSAL IS HERE RATHER THAN DOWNSTREAM.
An operator typing at the end of a day will happily leave `known_at`
blank, and a form that defaults it to `now` silently converts "the
dispatcher told me this on Tuesday" into "we learned this on Friday" --
which is the one field an as-known-then question depends on. So the two
timestamps are separate fields and neither defaults to the other.

NO NATURAL-PERSON DATA. `recorded_by` is an opaque identifier. There is no
field for a name, an email or a phone number anywhere in this module, and
a test asserts it -- the same structural rule as the CanadaBuys
projection, which has nowhere to put a contact name rather than a filter
that strips one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from commerce.events import (BASIS_OF, EVENT_KINDS, LoadEvent, Source, EventRefusal)

#: The entry is not the format it claims.
MALFORMED_ENTRY = "MALFORMED_ENTRY"
#: A required field is absent. Named with the field AND the load.
ENTRY_FIELD_MISSING = "ENTRY_FIELD_MISSING"
#: A field this reader does not understand, refused rather than dropped.
UNKNOWN_ENTRY_FIELD = "UNKNOWN_ENTRY_FIELD"
#: `known_at` and `recorded_at` collapsed into one value by the form.
KNOWN_AT_DEFAULTED_TO_THE_TYPING_TIME = "KNOWN_AT_DEFAULTED_TO_THE_TYPING_TIME"
#: A method this adapter has no source class for.
UNKNOWN_METHOD = "UNKNOWN_METHOD"

#: How a thing was learned, and what class that makes it. A dispatcher's
#: phone call is an assertion by an interested party; a signed document is
#: too, and neither becomes measured by being written down carefully.
CLASS_OF_METHOD: Mapping[str, str] = {
    "phone": "asserted",
    "email": "asserted",
    "portal": "asserted",
    "document": "asserted",
    "observed": "measured",
}

_REQUIRED = ("load", "kind", "value", "unit", "known_at", "method", "recorded_by")
_OPTIONAL = ("period_start", "period_end", "supersedes", "artifact", "recorded_at")
_KNOWN = set(_REQUIRED) | set(_OPTIONAL)


def _refuse(code: str, detail: str) -> EventRefusal:
    return EventRefusal(code, detail)


def from_entry(entry: Mapping[str, Any]) -> LoadEvent:
    """One form submission becomes one canonical event.

    Nothing is defaulted. A value invented at the form reaches the
    residual history wearing the operator's authority, and by the time it
    is questioned the call it came from is months old.
    """
    unknown = sorted(set(entry) - _KNOWN)
    if unknown:
        raise _refuse(
            UNKNOWN_ENTRY_FIELD,
            f"the entry carries {unknown}, which this reader does not understand. Known fields: "
            f"{sorted(_KNOWN)}. Refused rather than ignored — a dropped key is a value the "
            "operator believes they recorded.",
        )
    for field in _REQUIRED:
        if entry.get(field) in (None, ""):
            raise _refuse(
                ENTRY_FIELD_MISSING,
                f"{field!r} is absent from an entry for load {entry.get('load', '<unknown>')!r}. "
                "Nothing is defaulted here: this is the record a post-mortem reads, and a field "
                "invented at intake is indistinguishable from one a person actually knew.",
            )

    method = str(entry["method"])
    if method not in CLASS_OF_METHOD:
        raise _refuse(
            UNKNOWN_METHOD,
            f"{method!r} has no declared source class. Known methods: "
            f"{sorted(CLASS_OF_METHOD)}. A method with no class would let an event into the "
            "record without saying how strongly it is held.",
        )

    known_at = str(entry["known_at"])
    recorded_at = entry.get("recorded_at")
    if recorded_at is not None and str(recorded_at) == known_at:
        raise _refuse(
            KNOWN_AT_DEFAULTED_TO_THE_TYPING_TIME,
            f"known_at and recorded_at are both {known_at!r} on load {entry['load']!r}. That is "
            "possible and it is far more often a form defaulting one to the other. When the "
            "dispatcher said it and when it was typed are different facts, and only the first "
            "answers what we knew at the time. Enter both, or omit recorded_at.",
        )

    source = Source(
        source_id=f"manual:{method}",
        source_class=CLASS_OF_METHOD[method],
        method=method,
        known_at=known_at,
        recorded_by=str(entry["recorded_by"]),
        artifact=entry.get("artifact"),
        rung="manual",
    )
    return LoadEvent(
        load=str(entry["load"]),
        kind=str(entry["kind"]),
        value=float(entry["value"]),
        unit=str(entry["unit"]),
        source=source,
        period_start=entry.get("period_start"),
        period_end=entry.get("period_end"),
        supersedes=entry.get("supersedes"),
    )


def load_entries(raw: str) -> Tuple[LoadEvent, ...]:
    """Parse a batch of form submissions.

    Unparseable and empty are DIFFERENT states, and this reader will not
    return the second for the first.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _refuse(
            MALFORMED_ENTRY,
            f"the entry file is not JSON ({exc.msg} at line {exc.lineno}). An unreadable form and "
            "an empty day are different states.",
        ) from None
    if not isinstance(payload, list):
        raise _refuse(MALFORMED_ENTRY, "the entry file must be a JSON array of entries.")
    return tuple(from_entry(entry) for entry in payload)


def blank_form() -> Dict[str, Any]:
    """The form an operator fills in.

    It ships with every field present and EMPTY. A form that omits
    `known_at` teaches the omission, and a form that pre-fills it teaches
    the default -- which is the failure this module exists to prevent.
    """
    return {
        "load": "",
        "kind": "",
        "value": "",
        "unit": "",
        "known_at": "",
        "recorded_at": "",
        "method": "",
        "recorded_by": "",
        "period_start": "",
        "period_end": "",
        "artifact": "",
        "how_to_fill_this": {
            "kind": f"one of {sorted(EVENT_KINDS)}",
            "known_at": "WHEN IT WAS SAID, not when you are typing. If the dispatcher told you "
                        "on Tuesday and you are entering it on Friday, this is Tuesday.",
            "recorded_at": "when you are typing. Leave blank if it is the same day as known_at; "
                           "entering the same value in both is refused, because a form that "
                           "copies one into the other destroys the distinction.",
            "recorded_by": "your operator id. NOT your name — this system carries no personal "
                           "data and has no field to put one in.",
            "method": f"one of {sorted(CLASS_OF_METHOD)}",
            "artifact": "the note, email or document id this came from, so someone can go back "
                        "to it.",
            "value_and_unit": "the number and what it is measured in. The BASIS is not yours to "
                              f"set — it is fixed per event kind: {dict(BASIS_OF)}",
        },
    }
