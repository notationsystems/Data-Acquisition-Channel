"""The sheet as intake, and the boundary at the wire.

Two directives, both in-phase: a spreadsheet is the right store for the
first twenty loads, and the outbound gate belongs at the channel rather
than at the record type — because a dispatcher reading `can you cover
Toronto-Detroit Thursday at $2,400` treats it as an offer whatever our
schema calls it, and cannot see the type system.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.authority import Actor  # noqa: E402
from commerce.events import EventRefusal  # noqa: E402
from commerce.outbound import (AN_AGENT_MAY_NOT_SEND_TO_A_COUNTERPARTY,  # noqa: E402
                               BINDING_DRAFT_WAS_NOT_REVIEWED, BINDING_KINDS,
                               DRAFT_NAMES_NO_COUNTERPARTY,
                               QUEUE_EMPTY_BECAUSE_EVERYTHING_WAS_SENT,
                               QUEUE_EMPTY_BECAUSE_NOTHING_WAS_DRAFTED, Draft, OutboundQueue,
                               OutboundRefusal, check_in, render as render_outbound, send)
from commerce.sheet import (SHEET_CARRIES_A_COMPUTED_COLUMN, SHEET_IS_NOT_A_SHEET,  # noqa: E402
                            SHEET_LACKS_A_REQUIRED_COLUMN, blank_sheet, read_sheet,
                            render as render_sheet)

HEADER = blank_sheet().strip()
GOOD = "L-001,rate_quoted,2400,CAD,2026-08-25,phone,op-7,2026-08-28,note-1,,,"


def _sheet(*rows: str) -> str:
    return HEADER + "\n" + "\n".join(rows) + "\n"


# =====================================================================
# The sheet is an intake surface, never the record
# =====================================================================

def test_a_typed_sheet_becomes_canonical_events():
    read = read_sheet(_sheet(GOOD))
    assert len(read.events) == 1
    assert read.events[0].kind == "rate_quoted"
    assert read.events[0].source.known_at == "2026-08-25"
    assert read.conserves


def test_a_computed_column_is_refused_because_the_sheet_is_becoming_the_record():
    """A sheet that is both the input and the report becomes the record by
    accident, after which the residual history is whatever someone last
    typed over."""
    with pytest.raises(EventRefusal) as caught:
        read_sheet(HEADER + ",residual\n" + GOOD + ",150\n")
    assert caught.value.code == SHEET_CARRIES_A_COMPUTED_COLUMN
    assert "becomes the record by accident" in caught.value.detail


def test_a_sheet_missing_a_required_column_is_refused_by_name():
    with pytest.raises(EventRefusal) as caught:
        read_sheet("load,kind,value\nL-1,rate_quoted,1\n")
    assert caught.value.code == SHEET_LACKS_A_REQUIRED_COLUMN
    assert "known_at" in caught.value.detail


def test_an_export_with_no_header_is_unreadable_not_empty():
    with pytest.raises(EventRefusal) as caught:
        read_sheet("")
    assert caught.value.code == SHEET_IS_NOT_A_SHEET
    assert "different states" in caught.value.detail


def test_one_bad_row_does_not_lose_the_other_nineteen():
    """An operator who typed twenty loads and made one mistake needs the
    other nineteen and a named reason for the twentieth."""
    bad = "L-002,rate_quoted,not-a-number,CAD,2026-08-25,phone,op-7,,,,,"
    read = read_sheet(_sheet(GOOD, bad))
    assert len(read.events) == 1
    assert len(read.refused) == 1
    assert read.refused[0].row == 3, "the row number must be the one the operator sees"
    assert read.conserves


def test_a_refused_row_carries_the_reason_the_underlying_rule_gave():
    """The sheet is a TRANSPORT. Validation stays in `manual`, so a second
    copy of the rules cannot drift from the first."""
    same_day = "L-003,rate_quoted,2400,CAD,2026-08-25,phone,op-7,2026-08-25,,,,"
    read = read_sheet(_sheet(same_day))
    assert len(read.refused) == 1
    assert read.refused[0].code == "KNOWN_AT_DEFAULTED_TO_THE_TYPING_TIME"


def test_a_header_only_sheet_is_not_a_day_with_no_loads():
    read = read_sheet(HEADER + "\n")
    assert read.empty_because is not None
    assert "nobody has typed into" in read.empty_because


def test_every_row_refused_is_a_different_nothing_from_an_empty_sheet():
    bad = "L-002,rate_quoted,nope,CAD,2026-08-25,phone,op-7,,,,,"
    empty = read_sheet(HEADER + "\n").empty_because
    all_bad = read_sheet(_sheet(bad)).empty_because
    assert empty != all_bad
    assert all_bad is not None and "is being used and this reader cannot read it" in all_bad


def test_blank_spacer_rows_are_not_counted_as_rows():
    read = read_sheet(_sheet(GOOD, ",,,,,,,,,,,"))
    assert read.rows_in_sheet == 1 and read.conserves


def test_the_blank_sheet_ships_with_no_example_row():
    """A template with an example in it becomes the example, and the first
    real load gets typed underneath a fiction."""
    assert blank_sheet().count("\n") == 1
    assert "L-001" not in blank_sheet()


def test_the_render_shows_every_refused_row():
    bad = "L-002,rate_quoted,nope,CAD,2026-08-25,phone,op-7,,,,,"
    text = render_sheet(read_sheet(_sheet(GOOD, bad)))
    assert "ROW 3" in text and "refused 1" in text


# =====================================================================
# The boundary is the wire
# =====================================================================

AGENT = Actor("scout.a", is_agent=True)
HUMAN = Actor("ops@firm", is_agent=False)


def _draft(**over):
    base = dict(kind="quote", counterparty="Acme Carriers",
                body="can you cover Toronto-Detroit Thursday at $2,400",
                drafted_by=AGENT)
    base.update(over)
    return Draft(**base)


def test_an_agent_may_not_put_anything_on_the_wire():
    with pytest.raises(OutboundRefusal) as caught:
        send(_draft(reviewed_by=HUMAN), AGENT, at="2026-08-31")
    assert caught.value.code == AN_AGENT_MAY_NOT_SEND_TO_A_COUNTERPARTY
    assert "cannot see the type system" in caught.value.detail


def test_the_refusal_names_the_wire_rather_than_the_record_type():
    """PC-5 already stops an agent constructing a Commitment. That is
    necessary and not sufficient."""
    with pytest.raises(OutboundRefusal) as caught:
        send(_draft(), AGENT, at="2026-08-31")
    assert "boundary is the WIRE" in caught.value.detail


def test_a_binding_draft_with_no_reviewer_is_refused_even_from_a_person():
    with pytest.raises(OutboundRefusal) as caught:
        send(_draft(), HUMAN, at="2026-08-31")
    assert caught.value.code == BINDING_DRAFT_WAS_NOT_REVIEWED


def test_a_reviewed_binding_draft_sends():
    sent = send(_draft(reviewed_by=HUMAN), HUMAN, at="2026-08-31")
    assert sent.sender is HUMAN and sent.sent_at == "2026-08-31"


def test_a_check_in_is_the_safe_case_and_needs_no_review():
    """Inbound status carries no offer and no acceptance."""
    draft = check_in("Acme Carriers", "any update on L-001?", AGENT)
    assert not draft.binding
    assert send(draft, HUMAN, at="2026-08-31").draft.kind == "check_in"


def test_an_agent_still_cannot_send_even_the_safe_case():
    """Automating the drafting is not automating the wire."""
    draft = check_in("Acme Carriers", "any update?", AGENT)
    with pytest.raises(OutboundRefusal):
        send(draft, AGENT, at="2026-08-31")


def test_offer_shaped_content_is_flagged_with_the_reason_not_silently_blocked():
    """The reviewer is told WHY their hand is required rather than being
    asked to notice."""
    flags = _draft().offer_shaped
    assert any("price" in f for f in flags)
    assert any("committing language" in f for f in flags)


def test_the_detector_reports_candidates_rather_than_deciding():
    """A price in a sentence about last month's invoice is not an offer,
    and this cannot tell the difference. Deciding would commit class 8 one
    level up."""
    innocent = _draft(kind="acknowledgement",
                      body="thanks — your invoice for $2,400 was received and is in the queue")
    assert innocent.offer_shaped, "it still flags, because it cannot tell"
    assert not innocent.binding, "but the KIND is what gates, not the flag"
    assert send(innocent, HUMAN, at="2026-08-31") is not None


def test_a_draft_with_no_counterparty_cannot_be_reviewed():
    with pytest.raises(OutboundRefusal) as caught:
        _draft(counterparty="  ")
    assert caught.value.code == DRAFT_NAMES_NO_COUNTERPARTY


def test_the_binding_kinds_are_a_list_a_reader_can_check():
    for kind in ("quote", "tender", "rate_confirmation", "booking", "customs_filing"):
        assert kind in BINDING_KINDS


def test_an_empty_queue_says_whether_any_agent_drafted():
    queue = OutboundQueue()
    assert queue.empty_because is not None
    assert QUEUE_EMPTY_BECAUSE_NOTHING_WAS_DRAFTED in queue.empty_because


def test_a_queue_emptied_by_sending_is_a_different_nothing():
    queue = OutboundQueue()
    draft = _draft(reviewed_by=HUMAN)
    queue.draft(draft)
    queue.release(draft, HUMAN, at="2026-08-31")
    assert queue.empty_because is not None
    assert QUEUE_EMPTY_BECAUSE_EVERYTHING_WAS_SENT in queue.empty_because


def test_the_queue_render_marks_binding_drafts_and_their_flags():
    queue = OutboundQueue()
    queue.draft(_draft())
    text = render_outbound(queue)
    assert "[BINDING]" in text
    assert "reads as an offer to the recipient" in text
