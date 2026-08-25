"""Tests for daf.extractors.usgs_earthquakes.UsgsEarthquakeExtractor.

Uses only the synthetic fixtures under tests/fixtures/usgs_* -- never
real USGS Earthquake Catalog content."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evidence.types import make_record

from daf.extractors.usgs_earthquakes import UsgsEarthquakeExtractionError, UsgsEarthquakeExtractor

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_projects_every_documented_field():
    raw_content = (FIXTURES / "usgs_event_detail_synth00000001.json").read_text()
    record = make_record(document_id="doc-1", locator="synth00000001", raw_content=raw_content)

    candidates = UsgsEarthquakeExtractor().extract(record)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.extraction_method == "json:usgs_earthquake_v1"
    assert candidate.confidence == 1.0
    assert candidate.entities == ()
    assert candidate.relations == ()

    content = candidate.content
    assert content["event_id"] == "synth00000001"
    assert content["magnitude"] == 4.1
    assert content["magnitude_type"] == "mb"
    assert content["place"] == "SYNTHETIC TEST PLACE ALPHA"
    assert content["origin_time"] == 1700000001000
    assert content["updated"] == 1700000101000
    assert content["status"] == "reviewed"
    assert content["longitude"] == -100.0001
    assert content["latitude"] == 10.0001
    assert content["depth_km"] == 12.3
    # Phase 31: property-admissibility keys, additive.
    assert content["property"] == "earthquake_magnitude"
    assert content["value"] == content["magnitude"]
    assert content["unit"] == "dimensionless"
    assert content["method"] == content["magnitude_type"]


def test_extract_of_a_revised_event_reflects_the_revised_content():
    # Same event id as the fixture above -- a real revision, not a
    # different event -- proving extraction is purely a function of
    # whatever content it is given, with no memory of prior revisions.
    raw_content = (FIXTURES / "usgs_event_detail_synth00000001_revised.json").read_text()
    record = make_record(document_id="doc-2", locator="synth00000001", raw_content=raw_content)

    content = UsgsEarthquakeExtractor().extract(record)[0].content

    assert content["event_id"] == "synth00000001"
    assert content["magnitude"] == 4.4  # revised from 4.1
    assert content["updated"] == 1700000901000  # revised from 1700000101000


def test_extract_raises_on_invalid_json():
    record = make_record(document_id="doc-1", locator="synth00000001", raw_content="not json at all")

    with pytest.raises(UsgsEarthquakeExtractionError):
        UsgsEarthquakeExtractor().extract(record)


def test_extract_raises_when_a_required_field_is_missing():
    raw_content = (FIXTURES / "usgs_event_detail_malformed.json").read_text()
    record = make_record(document_id="doc-1", locator="synth00000099", raw_content=raw_content)

    with pytest.raises(UsgsEarthquakeExtractionError):
        UsgsEarthquakeExtractor().extract(record)


def test_a_missing_magtype_produces_no_method_rather_than_a_default():
    """The honesty check: a real event lacking a magnitude-type field
    must not silently receive one. `method` is None, exactly like
    `magnitude_type`, so `no_context_free_property` still refuses it for
    MISSING_METHOD -- see tests/test_usgs_property_admission_integration.py
    for that gate-level assertion. This is the extractor-level half: the
    content itself carries no fabricated value."""
    raw_content = json.dumps(
        {
            "type": "Feature",
            "id": "synth-no-magtype",
            "properties": {"mag": 3.0, "time": 1, "updated": 2, "place": "p"},
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0, 1.0]},
        }
    )
    record = make_record(document_id="doc-1", locator="synth-no-magtype", raw_content=raw_content)

    content = UsgsEarthquakeExtractor().extract(record)[0].content
    assert content["magnitude_type"] is None
    assert content["method"] is None
