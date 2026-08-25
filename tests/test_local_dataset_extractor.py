"""Tests for daf.extractors.local_dataset.LocalDatasetExtractor."""

from __future__ import annotations

import pytest
from evidence.types import make_record

from daf.extractors.local_dataset import LocalDatasetExtractionError, LocalDatasetExtractor


def test_extract_returns_content_verbatim_with_no_invented_entities():
    record = make_record(
        document_id="doc-1", locator="loc-1", raw_content='{"id": "widget-1", "value": 42.5, "unit": "USD"}'
    )
    candidates = LocalDatasetExtractor().extract(record)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.content == {"id": "widget-1", "value": 42.5, "unit": "USD"}
    assert candidate.entities == ()
    assert candidate.relations == ()
    assert candidate.extraction_method == "json:local_dataset_v1"
    assert candidate.confidence == 1.0


def test_extract_raises_on_invalid_json():
    record = make_record(document_id="doc-1", locator="loc-1", raw_content="not json")
    with pytest.raises(LocalDatasetExtractionError):
        LocalDatasetExtractor().extract(record)


def test_extract_raises_on_non_object_json():
    record = make_record(document_id="doc-1", locator="loc-1", raw_content="[1, 2, 3]")
    with pytest.raises(LocalDatasetExtractionError):
        LocalDatasetExtractor().extract(record)
