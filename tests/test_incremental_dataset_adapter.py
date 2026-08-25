"""Tests for daf.adapters.incremental_dataset.IncrementalDatasetSourceAdapter."""

from __future__ import annotations

import json

import pytest

from daf.adapters.incremental_dataset import (
    IncrementalDatasetFetchError,
    IncrementalDatasetSourceAdapter,
    locator_for,
    sequence_of,
)
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_fetch_from_the_beginning_returns_every_record():
    adapter = IncrementalDatasetSourceAdapter(
        path=FIXTURES / "incremental_dataset_sample.json", source_name="events", retrieved_at="2026-08-24T00:00:00Z"
    )
    documents = adapter.fetch()
    assert [json.loads(d.content)["sequence"] for d in documents] == [1, 2, 3]


def test_fetch_since_a_sequence_returns_only_greater_records():
    adapter = IncrementalDatasetSourceAdapter(
        path=FIXTURES / "incremental_dataset_sample.json",
        source_name="events",
        retrieved_at="2026-08-24T00:00:00Z",
        since_sequence=1,
    )
    documents = adapter.fetch()
    assert [json.loads(d.content)["sequence"] for d in documents] == [2, 3]


def test_fetch_since_the_latest_sequence_returns_nothing():
    adapter = IncrementalDatasetSourceAdapter(
        path=FIXTURES / "incremental_dataset_sample.json",
        source_name="events",
        retrieved_at="2026-08-24T00:00:00Z",
        since_sequence=3,
    )
    assert adapter.fetch() == ()


def test_locator_encodes_sequence_and_round_trips():
    for sequence in (0, 1, 42, 999999):
        assert sequence_of(locator_for(sequence)) == sequence


def test_locators_are_returned_in_ascending_deterministic_order():
    adapter = IncrementalDatasetSourceAdapter(
        path=FIXTURES / "incremental_dataset_sample.json", source_name="events", retrieved_at="2026-08-24T00:00:00Z"
    )
    documents = adapter.fetch()
    assert [d.locator for d in documents] == sorted(d.locator for d in documents)


def test_fetch_rejects_a_record_with_no_integer_sequence(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"id": "x"}]))
    adapter = IncrementalDatasetSourceAdapter(path=path, source_name="events", retrieved_at="2026-08-24T00:00:00Z")
    with pytest.raises(IncrementalDatasetFetchError):
        adapter.fetch()


def test_fetch_rejects_a_boolean_masquerading_as_a_sequence(tmp_path):
    """bool is a subclass of int in Python -- must not be accepted."""
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"sequence": True, "id": "x"}]))
    adapter = IncrementalDatasetSourceAdapter(path=path, source_name="events", retrieved_at="2026-08-24T00:00:00Z")
    with pytest.raises(IncrementalDatasetFetchError):
        adapter.fetch()


def test_fetch_missing_file_raises(tmp_path):
    adapter = IncrementalDatasetSourceAdapter(
        path=tmp_path / "does-not-exist.json", source_name="events", retrieved_at="2026-08-24T00:00:00Z"
    )
    with pytest.raises(IncrementalDatasetFetchError):
        adapter.fetch()
