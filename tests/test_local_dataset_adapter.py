"""Tests for daf.adapters.local_dataset.LocalDatasetSourceAdapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from daf.adapters.local_dataset import LocalDatasetFetchError, LocalDatasetSourceAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def test_fetch_parses_one_document_per_record():
    adapter = LocalDatasetSourceAdapter(
        path=FIXTURES / "local_dataset_sample.json",
        source_name="widget-dataset",
        retrieved_at="2026-08-24T00:00:00Z",
    )
    documents = adapter.fetch()

    assert len(documents) == 2
    assert {json.loads(d.content)["id"] for d in documents} == {"widget-1", "widget-2"}
    assert all(d.source_name == "widget-dataset" for d in documents)
    assert all(d.source_kind == "dataset" for d in documents)
    assert all(d.retrieval_method == "file:local_json_v1" for d in documents)
    assert all(d.retrieved_at == "2026-08-24T00:00:00Z" for d in documents)


def test_fetch_missing_file_raises(tmp_path):
    adapter = LocalDatasetSourceAdapter(
        path=tmp_path / "does-not-exist.json", source_name="x", retrieved_at="2026-08-24T00:00:00Z"
    )
    with pytest.raises(LocalDatasetFetchError):
        adapter.fetch()


def test_fetch_invalid_json_raises(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("not json")
    adapter = LocalDatasetSourceAdapter(path=path, source_name="x", retrieved_at="2026-08-24T00:00:00Z")
    with pytest.raises(LocalDatasetFetchError):
        adapter.fetch()


def test_fetch_non_array_json_raises(tmp_path):
    path = tmp_path / "not_a_list.json"
    path.write_text(json.dumps({"id": "solo"}))
    adapter = LocalDatasetSourceAdapter(path=path, source_name="x", retrieved_at="2026-08-24T00:00:00Z")
    with pytest.raises(LocalDatasetFetchError):
        adapter.fetch()


def test_fetch_record_missing_id_raises(tmp_path):
    path = tmp_path / "missing_id.json"
    path.write_text(json.dumps([{"value": 1}]))
    adapter = LocalDatasetSourceAdapter(path=path, source_name="x", retrieved_at="2026-08-24T00:00:00Z")
    with pytest.raises(LocalDatasetFetchError):
        adapter.fetch()
