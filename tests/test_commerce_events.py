"""PC-6 Part I graded, and its last acceptance criterion made real.

    "The manual adapter writes the same event types as a future API
     adapter; verified by a test asserting the two produce identical
     canonical shapes."

That claim is worth nothing without a second adapter to check against, so
`commerce/tms.py` is a genuinely separate code path over a genuinely
different input shape -- nested vendor JSON with its own field names and
its own units. If the two ever stop agreeing, the residual history stops
being continuous across the day the integration lands, which is the whole
thing Part I is buying.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce import manual  # noqa: E402
from commerce.events import (EVENT_KINDS, PROMISES, SETTLES, WORLD_FACTS,  # noqa: E402
                             EventRefusal, LoadEvent, Source, pair_events)
from commerce.manual import (ENTRY_FIELD_MISSING, KNOWN_AT_DEFAULTED_TO_THE_TYPING_TIME,  # noqa: E402
                             MALFORMED_ENTRY, UNKNOWN_ENTRY_FIELD, UNKNOWN_METHOD,
                             blank_form, from_entry, load_entries)
from commerce.stores import (Authority, Commitment, CommitmentStore, Evidence,  # noqa: E402
                             Outcome, OutcomeStore, Provenance, Quantity, diverge)
from commerce.tms import UNMAPPED_PAYLOAD_FIELD, from_payload  # noqa: E402


def _entry(**over: object) -> dict:
    base = {
        "load": "L-0001", "kind": "transit_estimated", "value": 4.0, "unit": "days",
        "known_at": "2026-08-25", "method": "phone", "recorded_by": "op-7",
        "artifact": "note-114",
    }
    base.update(over)
    return base


# =====================================================================
# THE acceptance criterion: two adapters, one canonical shape
# =====================================================================

def test_the_manual_and_api_adapters_produce_identical_canonical_shapes():
    """The same load, learned two ways. The tuples must match exactly --
    including the basis, which neither adapter is allowed to choose."""
    by_hand = [
        from_entry(_entry(kind="rate_quoted", value=2400.0, unit="CAD")),
        from_entry(_entry(kind="transit_estimated", value=4.0, unit="days")),
        from_entry(_entry(kind="rate_invoiced", value=2400.0, unit="CAD")),
        from_entry(_entry(kind="transit_realized", value=5.0, unit="days")),
    ]
    by_api = from_payload({
        "loadId": "L-0001", "knownAt": "2026-08-25", "system": "reference",
        "observed": {"quotedRate": 2400.0, "estTransitDays": 4.0,
                     "invoicedRate": 2400.0, "actualTransitDays": 5.0},
    })
    assert {e.canonical() for e in by_hand} == {e.canonical() for e in by_api}, (
        "a phone call and an API must write the same event about the world. If these diverge, "
        "the residual history breaks on the day the integration lands."
    )


def test_the_two_adapters_differ_only_in_how_the_event_was_learned():
    """What must NOT match is the provenance -- that is the entire
    difference, and collapsing it would hide that fifty loads were typed."""
    by_hand = from_entry(_entry())
    by_api = from_payload({"loadId": "L-0001", "knownAt": "2026-08-25",
                           "observed": {"estTransitDays": 4.0}})[0]
    assert by_hand.canonical() == by_api.canonical()
    assert by_hand.source.rung == "manual" and by_api.source.rung == "api"
    assert by_hand.source.method == "phone" and by_api.source.method == "api"


def test_a_manually_recorded_pair_scores_through_the_existing_divergence_machinery():
    """A commitment/outcome pair recorded by a person is independent by
    exactly the same construction as one from an API, because the outcome
    came from the world either way -- so PC-1's diverge() takes it with no
    new analytics."""
    promised = from_entry(_entry(kind="transit_estimated", value=4.0))
    realized = from_entry(_entry(kind="transit_realized", value=5.0))
    authority = Authority("ops", "signing_delegation", "2026-01-01", "2026-12-31")
    commitments = CommitmentStore()
    commitment = commitments.issue(Commitment(
        subject=f"{promised.load}:transit", quantity=Quantity(promised.value, promised.unit,
                                                              promised.basis),
        issuer="ops@firm", authority=authority, idempotency_key="L-0001-transit",
        issued_at="2026-08-25"))
    outcomes = OutcomeStore(commitments)
    outcome = outcomes.record(Outcome("L-0001-transit", Evidence(
        subject=f"{realized.load}:transit",
        quantity=Quantity(realized.value, realized.unit, realized.basis),
        provenance=Provenance(source_id=realized.source.source_id,
                              retrieved_at="2026-09-02", known_at=realized.source.known_at),
        evidence_class=realized.source.source_class)))
    result = diverge(commitment, outcome)
    assert result.residual == 1.0 and result.refusal is None


# =====================================================================
# The vocabulary is closed and its pairing is total
# =====================================================================

def test_every_promise_has_exactly_one_settlement():
    """A promise with no counterpart is a number that can never be scored,
    and it would sit in the record looking like data."""
    for promise in PROMISES:
        assert promise in SETTLES
        assert SETTLES[promise] in WORLD_FACTS


def test_the_promise_and_world_fact_sets_do_not_overlap():
    assert not (PROMISES & WORLD_FACTS), "an event cannot be both a promise and its settlement"
    assert PROMISES | WORLD_FACTS == EVENT_KINDS


def test_every_event_kind_has_a_declared_basis():
    """Two adapters writing the same event on different bases is the
    mud-tonnage error arriving through the back door, so the basis is
    fixed per kind and neither adapter may choose it."""
    from commerce.events import BASIS_OF
    assert set(BASIS_OF) == EVENT_KINDS


def test_an_invented_event_kind_is_refused():
    with pytest.raises(EventRefusal) as caught:
        from_entry(_entry(kind="rate_kind_of_agreed"))
    assert "not a canonical event" in caught.value.detail


def test_an_unpaired_promise_stays_visible_rather_than_being_dropped():
    """Dropping it would make an unsettled load look like a load with
    nothing outstanding."""
    events = (from_entry(_entry(kind="transit_estimated", value=4.0)),)
    paired = pair_events(events)
    assert paired["L-0001:transit_estimated"][1] is None


# =====================================================================
# The form refuses what an operator under time pressure will get wrong
# =====================================================================

def test_known_at_equal_to_recorded_at_is_refused_as_a_defaulting_form():
    """The failure this exists to prevent: a form that copies the typing
    time into known_at converts 'the dispatcher told me on Tuesday' into
    'we learned this on Friday', silently, in the one field an
    as-known-then question depends on."""
    with pytest.raises(EventRefusal) as caught:
        from_entry(_entry(known_at="2026-08-28", recorded_at="2026-08-28"))
    assert caught.value.code == KNOWN_AT_DEFAULTED_TO_THE_TYPING_TIME
    assert "far more often a form defaulting" in caught.value.detail


def test_distinct_known_at_and_recorded_at_are_accepted():
    event = from_entry(_entry(known_at="2026-08-25", recorded_at="2026-08-28"))
    assert event.source.known_at == "2026-08-25"


def test_a_missing_field_is_refused_by_name_and_nothing_is_defaulted():
    for field in ("load", "kind", "value", "unit", "known_at", "method", "recorded_by"):
        entry = _entry()
        del entry[field]
        with pytest.raises(EventRefusal) as caught:
            from_entry(entry)
        assert caught.value.code == ENTRY_FIELD_MISSING
        assert field in caught.value.detail


def test_a_typod_field_is_refused_rather_than_dropped():
    with pytest.raises(EventRefusal) as caught:
        from_entry(_entry(known_ats="2026-08-25"))
    assert caught.value.code == UNKNOWN_ENTRY_FIELD


def test_a_method_with_no_declared_class_is_refused():
    with pytest.raises(EventRefusal) as caught:
        from_entry(_entry(method="carrier_pigeon"))
    assert caught.value.code == UNKNOWN_METHOD


def test_an_unreadable_batch_is_not_an_empty_day():
    with pytest.raises(EventRefusal) as caught:
        load_entries("not json")
    assert caught.value.code == MALFORMED_ENTRY
    assert "an empty day are different states" in caught.value.detail


def test_an_empty_batch_is_accepted_as_an_empty_batch():
    assert load_entries("[]") == ()


# =====================================================================
# No natural-person data, structurally
# =====================================================================

def test_the_event_and_source_have_no_field_a_person_could_land_in():
    for cls in (LoadEvent, Source):
        for field in cls.__dataclass_fields__:
            assert "name" not in field.lower(), f"{cls.__name__}.{field}"
            assert "email" not in field.lower() and "phone" not in field.lower()


def test_the_manual_adapter_accepts_no_person_attribute_field():
    """Checked against the ACCEPTED FIELD SET, not the file text. `email`
    appears in this module as a METHOD of learning something, which is
    correct and unrelated; what must not exist is a field that HOLDS a
    person's email. An earlier version of this test grepped the source and
    failed on the method name — a wrong-attribution refusal in a test
    written to guard against exactly that."""
    accepted = manual._KNOWN
    for field in accepted:
        assert field not in {"name", "first_name", "last_name", "contact_name",
                             "email", "phone", "mobile", "address"}, (
            f"the manual adapter accepts {field!r}, which is a person attribute"
        )
    # And the one person-shaped field it does accept is an opaque id.
    assert "recorded_by" in accepted
    assert "NOT your name" in blank_form()["how_to_fill_this"]["recorded_by"]


def test_the_form_tells_the_operator_recorded_by_is_not_a_name():
    notes = blank_form()["how_to_fill_this"]
    assert "NOT your name" in notes["recorded_by"]


# =====================================================================
# The form is a form
# =====================================================================

def test_the_blank_form_ships_every_field_present_and_empty():
    """A form that omits known_at teaches the omission; one that pre-fills
    it teaches the default."""
    form = blank_form()
    for field in ("load", "kind", "value", "unit", "known_at", "recorded_at", "method",
                  "recorded_by"):
        assert field in form and form[field] == ""


def test_the_form_explains_that_known_at_is_when_it_was_said():
    assert "not when you are typing" in blank_form()["how_to_fill_this"]["known_at"].lower()


def test_the_form_does_not_let_the_operator_set_the_basis():
    assert "not yours to set" in blank_form()["how_to_fill_this"]["value_and_unit"]


# =====================================================================
# The API adapter refuses what it does not understand
# =====================================================================

def test_an_unmapped_vendor_measure_is_refused_rather_than_skipped():
    """A vendor adding fuelSurchargeQuoted next quarter would otherwise be
    silently dropped, and the residual history would quietly stop covering
    part of the rate."""
    with pytest.raises(EventRefusal) as caught:
        from_payload({"loadId": "L-9", "knownAt": "2026-08-25",
                      "observed": {"fuelSurchargeQuoted": 120.0}})
    assert caught.value.code == UNMAPPED_PAYLOAD_FIELD
    assert "fuelSurchargeQuoted" in caught.value.detail


def test_a_null_measure_is_omitted_rather_than_written_as_zero():
    events = from_payload({"loadId": "L-9", "knownAt": "2026-08-25",
                           "observed": {"quotedRate": None, "estTransitDays": 3.0}})
    assert [e.kind for e in events] == ["transit_estimated"]
