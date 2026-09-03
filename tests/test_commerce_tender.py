"""PC-3 graded against the real notices, and against what the source
CANNOT carry.

THE ACCEPTANCE THAT MATTERS. It is easy to write an extractor that scores
well by grading itself on the fields it chose to produce. These tests
grade it against the FOUNDING ORDER's list of ten, so a field the source
cannot answer shows up as a refusal rather than as an absence nobody
counted.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from commerce.canadabuys import parse_feed  # noqa: E402
from commerce import tender  # noqa: E402
from commerce.tender import (EMPTY_IN_THIS_NOTICE, NO_COLUMN_IN_THIS_SOURCE,  # noqa: E402
                             REQUESTED_FIELDS, census, extract, render)

FIXTURE = REPO_ROOT / "commerce" / "fixtures" / "canadabuys_open_sample.csv"
RETRIEVAL = parse_feed(FIXTURE.read_text(encoding="utf-8"),
                       source_url="fixture", retrieved_at="2026-08-31")
OPPORTUNITIES = tuple(extract(n) for n in RETRIEVAL.notices)


def test_every_requested_field_is_accounted_for_on_every_notice():
    """A field that is neither present nor refused is a field the reader
    will assume was not asked for."""
    for opportunity in OPPORTUNITIES:
        assert opportunity.accounted, (
            f"{opportunity.reference}: {len(opportunity.present)} present + "
            f"{len(opportunity.refused)} refused != {len(REQUESTED_FIELDS)} requested"
        )


def test_the_five_fields_with_no_column_are_refused_as_structural_not_as_blank():
    """The difference decides whether reading more notices would help.
    NO_COLUMN means no notice will ever have it."""
    for opportunity in OPPORTUNITIES:
        for field in ("quantity", "origin", "incoterms", "equipment"):
            entry = opportunity.fields[field]
            assert entry.code == NO_COLUMN_IN_THIS_SOURCE, (
                f"{field} must say the SOURCE cannot carry it, not that this row was blank"
            )


def test_every_refusal_carries_a_remedy_that_is_a_sentence():
    """`unavailable` is not a remedy. A refusal that does not say what
    would resolve it sends the reader nowhere."""
    for opportunity in OPPORTUNITIES:
        for field in opportunity.refused:
            remedy = opportunity.fields[field].remedy
            assert remedy, f"{field} refuses with no remedy"
            assert len(remedy.split()) > 8, f"{field} remedy is a status word: {remedy!r}"


def test_the_remedy_names_a_document_when_one_exists_and_says_so_when_none_does():
    with_attachment = [o for o in OPPORTUNITIES
                       if "document(s)" in (o.fields["quantity"].remedy or "")]
    without = [o for o in OPPORTUNITIES
               if "links no document" in (o.fields["quantity"].remedy or "")]
    assert with_attachment or without, "the fixture must exercise at least one branch"
    for opportunity in with_attachment:
        assert "http" in (opportunity.fields["quantity"].remedy or ""), (
            "a remedy that names a document must name WHICH document"
        )


def test_no_field_is_inferred_from_another():
    """The closing date is when bids are due; the buyer's address is not
    the destination; a UNSPSC code is not a quantity. Each of those
    substitutions produces a plausible value and a wrong one."""
    for opportunity in OPPORTUNITIES:
        window = opportunity.fields["delivery_window"]
        if not window.present:
            assert "closing" in (window.remedy or "").lower(), (
                "the refusal must name the field a reader would be tempted to substitute"
            )
        destination = opportunity.fields["destination"]
        if destination.present:
            assert destination.from_column == "regionsOfDelivery"


def test_a_duration_needs_both_endpoints_and_is_refused_with_one():
    partial = [o for o in OPPORTUNITIES if not o.fields["duration"].present]
    assert partial, "the fixture was chosen to include a notice missing an expected date"
    for opportunity in partial:
        assert opportunity.fields["duration"].code == EMPTY_IN_THIS_NOTICE


def test_a_closed_vocabulary_is_read_rather_than_refused_as_prose():
    """SELF-CORRECTION, kept as a test. The first draft refused
    `evaluation_criteria` and `compliance` as PROSE_NOT_A_VALUE, assuming
    evaluation rules arrive as paragraphs. Measured over 979 open notices,
    selectionCriteria takes SEVEN distinct values and tradeAgreements
    resolves to SEVENTEEN atoms. Refusing them was the mirror of the
    defect this module guards against -- it under-reported what the source
    answers, and a reader would have concluded the feed cannot say how
    bids are evaluated when it says so on 800 of 979 notices."""
    answered = [o for o in OPPORTUNITIES if o.fields["evaluation_criteria"].present]
    assert answered, "the fixture must include a notice stating its selection criteria"
    for opportunity in answered:
        assert opportunity.fields["evaluation_criteria"].from_column == "selectionCriteria"
    compliant = [o for o in OPPORTUNITIES if o.fields["compliance"].present]
    assert compliant, "the fixture must include a notice naming its trade agreements"
    for value in compliant[0].fields["compliance"].value:  # type: ignore[union-attr]
        assert "\n" not in value and not value.startswith("*")


def test_no_refusal_code_is_defined_that_nothing_can_emit():
    """A refusal nothing can reach is a branch that passes every test by
    never running. PROSE_NOT_A_VALUE was removed rather than left standing
    once both of its call sites turned out to be measurements."""
    assert not hasattr(tender, "PROSE_NOT_A_VALUE"), (
        "the code was removed with its call sites; a vacuous refusal must not linger"
    )
    emitted = {o.fields[f].code for o in OPPORTUNITIES for f in o.refused}
    declared = {NO_COLUMN_IN_THIS_SOURCE, EMPTY_IN_THIS_NOTICE}
    assert emitted <= declared
    assert emitted == declared, f"a declared code was never emitted over the fixture: {declared - emitted}"


def test_the_census_reports_which_fields_the_source_can_never_answer():
    """The finding of PC-2, restated as a measurement over the feed rather
    than as a claim in a document."""
    result = census(OPPORTUNITIES)
    assert result.notices == 4
    for field in ("quantity", "origin", "incoterms", "equipment"):
        assert field in result.never_answered, (
            f"{field} was answered on some notice; the recon claim that it has no column is wrong"
        )
    assert "buyer" not in result.never_answered


def test_an_empty_census_says_it_measured_nothing_rather_than_reporting_no_coverage():
    """Class 7. A census over zero notices that returned zeros for every
    field would read as a source that answers nothing."""
    result = census(())
    assert result.never_answered == (), (
        "a census with no input must not report every field as never-answered"
    )
    assert result.empty_because is not None
    assert "not a finding" in result.empty_because


def test_the_rendered_opportunity_shows_refusals_beside_values():
    text = render(OPPORTUNITIES[0])
    assert "REFUSED" in text and "remedy:" in text
    assert "buyer" in text
