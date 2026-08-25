"""Tests for daf.extractors.edgar_daily_index.EdgarDailyIndexExtractor.

Uses only the synthetic fixtures under tests/fixtures/edgar_* -- never
real SEC EDGAR content."""

from __future__ import annotations

from pathlib import Path

import pytest
from evidence.types import make_record

from daf.extractors.edgar_daily_index import EdgarDailyIndexExtractionError, EdgarDailyIndexExtractor

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_parses_every_row_and_counts_form_types():
    raw_content = (FIXTURES / "edgar_daily_index_synthetic_20260701.idx").read_text()
    record = make_record(document_id="doc-1", locator="20260701", raw_content=raw_content)

    candidates = EdgarDailyIndexExtractor().extract(record)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.extraction_method == "text:edgar_daily_index_v1"
    assert candidate.confidence == 1.0
    assert candidate.entities == ()
    assert candidate.relations == ()

    content = candidate.content
    assert content["date_filed"] == "20260701"
    assert content["filing_count"] == 2
    assert content["form_type_counts"] == {"10-K": 1, "8-K": 1}
    assert content["filings"] == [
        {
            "company_name": "SYNTHETIC TEST COMPANY ALPHA",
            "form_type": "10-K",
            "cik": "9999990001",
            "date_filed": "20260701",
            "file_name": "edgar/data/9999990001/0000000000-26-000001.txt",
        },
        {
            "company_name": "SYNTHETIC TEST COMPANY BETA",
            "form_type": "8-K",
            "cik": "9999990002",
            "date_filed": "20260701",
            "file_name": "edgar/data/9999990002/0000000000-26-000002.txt",
        },
    ]


def test_extract_counts_repeated_form_types_correctly():
    raw_content = (FIXTURES / "edgar_daily_index_synthetic_20260702.idx").read_text()
    record = make_record(document_id="doc-1", locator="20260702", raw_content=raw_content)

    candidate = EdgarDailyIndexExtractor().extract(record)[0]
    # 20260702 fixture has one 8-K/A row -- distinct from a plain 8-K, never merged.
    assert candidate.content["form_type_counts"] == {"S-1": 1, "8-K/A": 1, "424B3": 1}
    assert candidate.content["filing_count"] == 3


def test_extract_handles_a_company_name_containing_a_double_space():
    # Discovered against real EDGAR data during the Phase G live demonstration:
    # individual filer names occasionally contain a run of 2+ internal spaces
    # (e.g. "PRICHEP PATRICIA  B"), which a naive split-on-2+-whitespace parser
    # misreads as an extra field. The right-anchored regex must still isolate
    # exactly five fields, keeping the whole free-text prefix as company_name.
    raw_content = (FIXTURES / "edgar_daily_index_synthetic_double_space_name.idx").read_text()
    record = make_record(document_id="doc-1", locator="20260701", raw_content=raw_content)

    candidate = EdgarDailyIndexExtractor().extract(record)[0]

    assert candidate.content["filing_count"] == 1
    assert candidate.content["filings"][0]["company_name"] == "SYNTHETIC TEST PERSON  MIDDLEINITIAL"
    assert candidate.content["filings"][0]["form_type"] == "4"
    assert candidate.content["filings"][0]["cik"] == "9999990003"


def test_extract_raises_when_header_separator_is_missing():
    raw_content = (FIXTURES / "edgar_daily_index_malformed.idx").read_text()
    record = make_record(document_id="doc-1", locator="20260701", raw_content=raw_content)

    with pytest.raises(EdgarDailyIndexExtractionError):
        EdgarDailyIndexExtractor().extract(record)


def test_extract_raises_on_a_malformed_data_row():
    raw_content = "\n".join(
        [
            "Description: test",
            "-" * 20,
            "not enough fields here",
        ]
    )
    record = make_record(document_id="doc-1", locator="20260701", raw_content=raw_content)

    with pytest.raises(EdgarDailyIndexExtractionError):
        EdgarDailyIndexExtractor().extract(record)
