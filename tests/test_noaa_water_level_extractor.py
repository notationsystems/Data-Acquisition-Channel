"""Tests for daf.extractors.noaa_water_level.NoaaWaterLevelExtractor.

Uses only the synthetic fixtures under tests/fixtures/noaa_window_* --
never real NOAA CO-OPS content."""

from __future__ import annotations

from pathlib import Path

import pytest
from evidence.types import make_record

from daf.extractors.noaa_water_level import NoaaWaterLevelExtractionError, NoaaWaterLevelExtractor

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_projects_metadata_and_counts_quality_flags():
    raw_content = (FIXTURES / "noaa_window_synthetic_20260101_20260103.json").read_text()
    record = make_record(
        document_id="doc-1", locator="9999999:water_level:MLLW:metric:20260101:20260103", raw_content=raw_content
    )

    candidates = NoaaWaterLevelExtractor().extract(record)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.extraction_method == "json:noaa_water_level_v1"
    assert candidate.confidence == 1.0
    assert candidate.entities == ()
    assert candidate.relations == ()

    content = candidate.content
    assert content["station_id"] == "9999999"
    assert content["station_name"] == "SYNTHETIC TEST STATION -- NOT A REAL NOAA STATION"
    assert content["reading_count"] == 4
    assert content["quality_counts"] == {"v": 3, "p": 1}
    assert content["readings"][0] == {
        "time": "2026-01-01 00:00", "value": "1.100", "sigma": "0.010", "flags": "0,0,0,0", "quality": "v",
    }


def test_extract_of_a_revised_window_reflects_the_revised_readings():
    # Same window (same station/product/dates -- same locator) as the
    # fixture above, but the last reading has moved from preliminary to
    # verified with a corrected value -- proving extraction is purely a
    # function of whatever content it is given, with no memory of a
    # prior revision.
    raw_content = (FIXTURES / "noaa_window_synthetic_20260101_20260103_revised.json").read_text()
    record = make_record(
        document_id="doc-2", locator="9999999:water_level:MLLW:metric:20260101:20260103", raw_content=raw_content
    )

    content = NoaaWaterLevelExtractor().extract(record)[0].content

    assert content["quality_counts"] == {"v": 4}  # all four now verified, was {"v": 3, "p": 1}
    assert content["readings"][-1]["value"] == "1.207"  # revised from "1.200"
    assert content["readings"][-1]["quality"] == "v"  # revised from "p"


def test_extract_raises_on_invalid_json():
    record = make_record(document_id="doc-1", locator="9999999:water_level:MLLW:metric:20260101:20260103", raw_content="not json")

    with pytest.raises(NoaaWaterLevelExtractionError):
        NoaaWaterLevelExtractor().extract(record)


def test_extract_raises_when_metadata_or_data_is_missing():
    record = make_record(document_id="doc-1", locator="9999999:water_level:MLLW:metric:20260101:20260103", raw_content="{}")

    with pytest.raises(NoaaWaterLevelExtractionError):
        NoaaWaterLevelExtractor().extract(record)


def test_extract_raises_when_a_reading_is_missing_required_fields():
    raw_content = (FIXTURES / "noaa_window_malformed.json").read_text()
    record = make_record(document_id="doc-1", locator="9999999:water_level:MLLW:metric:20260101:20260101", raw_content=raw_content)

    with pytest.raises(NoaaWaterLevelExtractionError):
        NoaaWaterLevelExtractor().extract(record)
