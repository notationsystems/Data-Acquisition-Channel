"""Tests for daf.extractors.arxiv.ArxivExtractor -- the real Extractor
half of the SCOUT vertical slice, exercised against evidence.types.Record
directly (independent of the adapter), to prove the extractor's own
contract in isolation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from evidence.types import make_record

from daf.extractors.arxiv import ArxivExtractionError, ArxivExtractor

FIXTURES = Path(__file__).parent / "fixtures"
_ENTRY_RE = re.compile(r"<entry>.*?</entry>", re.DOTALL)


def _first_entry(fixture_name: str) -> str:
    text = (FIXTURES / fixture_name).read_text()
    return _ENTRY_RE.findall(text)[0]


def test_extract_returns_extraction_candidate_matching_scout_contract():
    entry_text = _first_entry("arxiv_single_entry_v1.xml")
    record = make_record(document_id="doc-1", locator="loc-1", raw_content=entry_text)

    candidates = ArxivExtractor().extract(record)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.extraction_method == "xml:arxiv_atom_v1"
    assert candidate.confidence == 1.0  # deterministic structural extraction, not a model

    arxiv_id = "http://arxiv.org/abs/9999.00001v1"
    assert candidate.content["arxiv_id"] == arxiv_id
    assert candidate.content["title"] == "A Deterministic Fixture Paper on Test Adhesion"
    assert candidate.content["primary_category"] == "cs.SE"

    assert {e.label for e in candidate.entities} == {arxiv_id, "Ada Example", "Bo Fixture"}
    assert {(e.kind) for e in candidate.entities if e.label == arxiv_id} == {"paper"}
    assert {(r.from_label, r.to_label, r.type) for r in candidate.relations} == {
        (arxiv_id, "Ada Example", "authored_by"),
        (arxiv_id, "Bo Fixture", "authored_by"),
    }


def test_extract_raises_on_malformed_xml():
    record = make_record(document_id="doc-1", locator="loc-1", raw_content="<entry>not valid xml")

    with pytest.raises(ArxivExtractionError):
        ArxivExtractor().extract(record)


def test_extract_raises_when_entry_missing_id():
    entry_text = _first_entry("arxiv_entry_missing_id.xml")
    record = make_record(document_id="doc-1", locator="loc-1", raw_content=entry_text)

    with pytest.raises(ArxivExtractionError):
        ArxivExtractor().extract(record)


def test_extract_rejects_content_that_is_not_an_entry_fragment():
    record = make_record(document_id="doc-1", locator="loc-1", raw_content="<feed></feed>")

    with pytest.raises(ArxivExtractionError):
        ArxivExtractor().extract(record)
