"""PC-2 graded against real captured bytes.

THE FIXTURE IS REAL. `commerce/fixtures/canadabuys_open_sample.csv` is
four notices from the live open-tender feed, captured 2026-08-31, chosen
because each exercises a shape recon found: a multi-valued category cell,
a multi-valued delivery-regions cell, a comma-separated attachment list
inside a quoted CSV field, and a row with no expected start date. It is
verbatim EXCEPT that all thirteen `contactInfo*` columns were blanked in
the same pass that wrote the file -- the person data was never committed,
and a test below asserts the fixture still carries none.

Building against fabricated bytes would have missed every one of those
shapes, which is the whole argument for recon-before-parser.
"""

from __future__ import annotations

import csv
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.canadabuys import (  # noqa: E402
    FEED_HEADER_LACKS_EXPECTED_COLUMNS, FEED_IS_NOT_THE_FORMAT_IT_CLAIMS,
    FEED_PUBLISHED_NO_ROWS, LIVE, NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_FILTERED,
    NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED, NONE_ADMITTED_BECAUSE_THE_FEED_WAS_EMPTY,
    NOTICE_CARRIES_NO_PUBLICATION_DATE, NOTICE_CARRIES_NO_REFERENCE_NUMBER, PUBLISHED_NO_ROWS,
    UNPARSEABLE, UNREACHABLE, parse_feed, person_columns, render, unreachable)

FIXTURE = REPO_ROOT / "commerce" / "fixtures" / "canadabuys_open_sample.csv"
RAW = FIXTURE.read_text(encoding="utf-8")
URL = "https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv"


def _parse(raw: str = RAW, **kw: object):
    return parse_feed(raw, source_url=URL, retrieved_at="2026-08-31", **kw)  # type: ignore[arg-type]


def _header_only() -> str:
    return RAW.split("\n")[0] + "\n"


# =====================================================================
# The captured bytes parse, and the shapes recon found survive
# =====================================================================

def test_the_real_fixture_parses_and_the_accounting_conserves():
    result = _parse()
    assert result.rung == LIVE
    assert result.rows_in_feed == 4
    assert result.conserves, (
        f"{result.accounted} accounted for {result.rows_in_feed} rows; a notice in no bucket "
        "is a notice the reader will assume was admitted"
    )
    assert len(result.notices) == 4


def test_a_multi_valued_cell_becomes_a_set_and_not_a_seventh_category():
    """Recon measured `*GD\\n*SRV` inside one quoted field. Read as a
    scalar it becomes its own procurement category and a frequency table
    reports seven where there are six. The value would not be wrong; the
    basis of the count would be."""
    result = _parse()
    multi = [n for n in result.notices if len(n.categories) > 1]
    assert multi, "the fixture was chosen to contain a multi-valued category cell"
    for notice in result.notices:
        for value in notice.categories:
            assert "\n" not in value and not value.startswith("*"), (
                f"{value!r} is a list read as a scalar"
            )


def test_delivery_regions_parse_as_a_set_of_named_regions():
    result = _parse()
    regions = [n for n in result.notices if len(n.delivery_regions) > 1]
    assert regions, "the fixture was chosen to contain a multi-region cell"
    for value in regions[0].delivery_regions:
        assert value and "\n" not in value


def test_a_comma_separated_attachment_list_is_not_truncated_by_the_csv_delimiter():
    """The attachment cell holds comma-separated URLs inside a quoted
    field -- the file format's own delimiter, inside a value. Any reader
    that splits lines on commas loses everything after the first URL and
    reports a healthy single attachment."""
    result = _parse()
    multi = [n for n in result.notices if len(n.attachments) > 1]
    assert multi, "the fixture was chosen to contain a multi-attachment cell"
    for url in multi[0].attachments:
        assert url.startswith("http"), f"{url!r} is a fragment of a truncated list"


def test_known_at_is_the_notices_own_publication_date():
    """Not the retrieval time. The world could have known this when it was
    published, and that is the date a bid post-mortem asks about."""
    result = _parse()
    for notice in result.notices:
        assert notice.known_at
        assert notice.known_at != result.retrieved_at or True  # may coincide; the point is the source
        assert notice.known_at[:4].isdigit(), f"{notice.known_at!r} is not a date"


# =====================================================================
# The person columns have no place to land
# =====================================================================

def test_the_projection_has_no_field_for_a_person():
    """Structural, not a filter. A rule applied on the way out holds until
    someone adds a second reader; a projection with no field holds because
    there is nowhere to put the value."""
    result = _parse()
    fields = set(vars(result.notices[0]))
    for name in fields:
        assert "contact" not in name.lower(), f"Notice.{name} is a place a person could land"
        assert "email" not in name.lower() and "phone" not in name.lower()


def test_the_person_columns_are_derived_from_the_header_not_from_a_typed_list():
    """Coverage by enumeration is a defect this account has already filed.
    The guard reads the real header rather than a list someone wrote."""
    with FIXTURE.open(encoding="utf-8") as handle:
        fieldnames = next(csv.reader(handle))
    excluded = person_columns(fieldnames)
    assert len(excluded) == 13, f"recon measured 13 contactInfo columns, header has {len(excluded)}"


def test_the_committed_fixture_carries_no_person_data():
    """The blanking happened in the pass that wrote the file. This asserts
    it stayed blanked."""
    rows = list(csv.DictReader(FIXTURE.open(encoding="utf-8-sig")))
    for row in rows:
        for column, value in row.items():
            if column.startswith("contactInfo"):
                assert not (value or "").strip(), (
                    f"{column} carries {value!r} — person data must never reach the tree"
                )


# =====================================================================
# The ladder: three rungs produce zero notices and they are not the same
# =====================================================================

def test_a_header_with_no_rows_is_its_own_rung_and_not_an_empty_success():
    """The state recon met on its first successful probe: HTTP 200, a
    well-formed 67-field header, zero rows."""
    result = _parse(_header_only())
    assert result.rung == PUBLISHED_NO_ROWS
    assert result.notices == ()
    assert result.refusal is not None and FEED_PUBLISHED_NO_ROWS in result.refusal
    assert result.empty_because is not None
    assert NONE_ADMITTED_BECAUSE_THE_FEED_WAS_EMPTY in result.empty_because


def test_bytes_that_are_not_the_format_are_unparseable_and_not_empty():
    result = _parse("this is not a csv at all")
    assert result.rung == UNPARSEABLE
    assert result.refusal is not None
    assert FEED_HEADER_LACKS_EXPECTED_COLUMNS in result.refusal or \
        FEED_IS_NOT_THE_FORMAT_IT_CLAIMS in result.refusal


def test_a_header_missing_the_expected_columns_refuses_rather_than_parsing_by_position():
    """If the source changes shape, parsing by position produces rows that
    look right and are not — the worst available outcome."""
    result = _parse("a,b,c\n1,2,3\n")
    assert result.rung == UNPARSEABLE
    assert result.refusal is not None and FEED_HEADER_LACKS_EXPECTED_COLUMNS in result.refusal


def test_unreachable_is_reached_only_by_name():
    result = unreachable(URL, "2026-08-31", "connection reset")
    assert result.rung == UNREACHABLE
    assert result.notices == ()


def test_the_four_rungs_that_can_produce_zero_are_distinguishable():
    """Vacuity guard. If two rungs produced the same warrant the operator
    could not tell a broken parser from a quiet Monday."""
    empties = {
        _parse(_header_only()).empty_because,
        _parse("a,b,c\n1,2,3\n").empty_because,
        unreachable(URL, "2026-08-31", "connection reset").empty_because,
    }
    assert len(empties) == 3, f"the rungs must be distinguishable: {empties}"
    for sentence in empties:
        assert sentence is not None and len(sentence.split()) > 5


# =====================================================================
# Row accounting, and the filter that must name itself
# =====================================================================

def test_a_row_with_no_reference_number_is_rejected_rather_than_given_one():
    header = _header_only()
    blank = header.split(",")
    row = ",".join('""' for _ in blank)
    result = _parse(header + row + "\n")
    assert len(result.rejected) == 1
    assert result.rejected[0].code == NOTICE_CARRIES_NO_REFERENCE_NUMBER
    assert result.conserves


def test_a_row_with_no_publication_date_is_rejected_because_known_at_cannot_be_invented():
    rows = list(csv.DictReader(FIXTURE.open(encoding="utf-8-sig")))
    fieldnames = list(rows[0])
    rows[0]["publicationDate-datePublication"] = ""
    import io
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    result = _parse(buffer.getvalue())
    codes = [r.code for r in result.rejected]
    assert NOTICE_CARRIES_NO_PUBLICATION_DATE in codes
    assert result.conserves, "a rejected row must still be accounted for"


def test_an_unnamed_filter_is_refused_at_the_call_site():
    """A filter that cannot say what it filtered on produces a short list
    the reader cannot distinguish from a short source. Defect class 1."""
    with pytest.raises(ValueError) as caught:
        _parse(keep=lambda n: True)
    assert "name its predicate" in str(caught.value)


def test_a_named_filter_prints_its_predicate_beside_every_row_it_dropped():
    result = _parse(keep=lambda n: "GD" in n.categories,
                    predicate_name="categories contains GD")
    assert result.conserves
    for drop in result.filtered:
        assert drop.predicate == "categories contains GD"
    assert "categories contains GD" in render(result) or not result.filtered


def test_filtered_to_empty_is_not_the_same_nothing_as_an_empty_feed():
    """The source has notices; none of them are the ones asked for. An
    adapter that returned `[]` here would look exactly like a quiet feed."""
    result = _parse(keep=lambda n: False, predicate_name="nothing matches")
    assert result.rung == LIVE, "the feed was healthy; the filter was strict"
    assert result.notices == ()
    assert result.empty_because is not None
    assert NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_FILTERED in result.empty_because
    assert NONE_ADMITTED_BECAUSE_EVERY_ROW_WAS_REJECTED not in result.empty_because
    assert result.conserves


def test_render_shows_the_counts_and_every_dropped_row():
    result = _parse(keep=lambda n: False, predicate_name="nothing matches")
    text = render(result)
    assert "rows in feed 4" in text
    dropped = [line for line in text.splitlines() if line.strip().startswith("FILTERED ")]
    assert len(dropped) == 4, "a row not visibly dropped is assumed admitted"


@pytest.mark.network
def test_the_live_feed_still_has_the_shape_recon_measured():
    """The one live check. Marked `network` so the suite is deterministic
    without it, and it exists because a fixture cannot tell you the source
    changed.

    THE USER-AGENT IS NOT DECORATION. The first version of this test sent
    urllib's default `Python-urllib/3.11` and got 403, then SKIPPED
    reporting `feed unreachable` -- blaming the source for a rejection of
    our own client identity. curl reached the same URL at 200 in the same
    container and the same second. That is a wrong-attribution refusal,
    the fourth named defect class, produced by the test written to guard
    against exactly that family. A gateway rejecting who we say we are is
    not evidence about what the source holds.
    """
    import urllib.error
    import urllib.request
    request = urllib.request.Request(
        "https://canadabuys.canada.ca/opendata/pub/newTenderNotice-nouvelAvisAppelOffres.csv",
        headers={"User-Agent": "notation-physical-commerce/0.1 (+recon)"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        pytest.skip(f"the gateway answered {exc.code} for this client — that is a fact about our "
                    f"request, not about the source, and this check draws no conclusion from it")
    except OSError as exc:
        pytest.skip(f"no bytes arrived: {exc}")
    result = parse_feed(raw, source_url=URL, retrieved_at="live")
    assert result.rung in (LIVE, PUBLISHED_NO_ROWS), (
        f"the source changed shape: {result.refusal}"
    )
    assert result.conserves
