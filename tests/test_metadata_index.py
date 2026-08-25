"""Tests for daf.storage.metadata_index.MetadataIndex."""

from __future__ import annotations

import pytest
from evidence.types import make_document, make_record, make_source

from daf.storage.filesystem_store import FilesystemEvidenceStore
from daf.storage.identity import compute_artifact_id
from daf.storage.metadata_index import MetadataIndex


def _index(tmp_path):
    return MetadataIndex(tmp_path / "index.sqlite")


def test_new_index_is_empty(tmp_path):
    assert _index(tmp_path).is_empty() is True


def test_record_document_then_all_ids(tmp_path):
    index = _index(tmp_path)
    index.record_document("doc-1", "source-a", "hash-1", "http", "t1")

    assert index.all_ids("documents") == ("doc-1",)
    assert index.is_empty() is False


def test_all_ids_rejects_a_non_indexed_category(tmp_path):
    index = _index(tmp_path)
    with pytest.raises(ValueError):
        index.all_ids("referents")


def test_list_versions_returns_versions_for_one_artifact_ordered_by_retrieved_at(tmp_path):
    index = _index(tmp_path)
    artifact_id = compute_artifact_id("source-a", "locator-x")
    # Two versions of the SAME artifact (same source_id/locator), plus one
    # version of a DIFFERENT artifact -- list_versions must return only
    # the first two, oldest first.
    index.record_document("doc-old", "source-a", "hash-old", "http", "2026-01-01T00:00:00Z")
    index.record_record("rec-old", "doc-old", "locator-x", "source-a", "hash-old")
    index.record_document("doc-new", "source-a", "hash-new", "http", "2026-01-02T00:00:00Z")
    index.record_record("rec-new", "doc-new", "locator-x", "source-a", "hash-new")
    index.record_document("doc-other", "source-a", "hash-other", "http", "2026-01-01T12:00:00Z")
    index.record_record("rec-other", "doc-other", "locator-y", "source-a", "hash-other")

    assert index.list_versions(artifact_id) == ("doc-old", "doc-new")


def test_list_versions_for_an_unknown_artifact_is_empty(tmp_path):
    index = _index(tmp_path)
    assert index.list_versions("no-such-artifact") == ()


def test_find_by_content_hash(tmp_path):
    index = _index(tmp_path)
    index.record_document("doc-1", "source-a", "shared-hash", "http", "2026-01-01T00:00:00Z")
    index.record_document("doc-2", "source-b", "shared-hash", "http", "2026-01-02T00:00:00Z")
    index.record_document("doc-3", "source-a", "different-hash", "http", "2026-01-03T00:00:00Z")

    assert index.find_by_content_hash("shared-hash") == ("doc-1", "doc-2")


def test_list_source_artifacts_ordered_by_first_observed(tmp_path):
    index = _index(tmp_path)
    index.record_document("doc-1", "source-a", "h1", "http", "2026-01-02T00:00:00Z")
    index.record_record("rec-1", "doc-1", "locator-later", "source-a", "h1")
    index.record_document("doc-2", "source-a", "h2", "http", "2026-01-01T00:00:00Z")
    index.record_record("rec-2", "doc-2", "locator-earlier", "source-a", "h2")
    index.record_document("doc-3", "source-b", "h3", "http", "2026-01-01T00:00:00Z")
    index.record_record("rec-3", "doc-3", "locator-other-source", "source-b", "h3")

    artifacts = index.list_source_artifacts("source-a")
    assert artifacts == (
        compute_artifact_id("source-a", "locator-earlier"),
        compute_artifact_id("source-a", "locator-later"),
    )


def test_locator_for_document(tmp_path):
    index = _index(tmp_path)
    index.record_document("doc-1", "source-a", "h1", "http", "2026-01-01T00:00:00Z")
    index.record_record("rec-1", "doc-1", "the-locator", "source-a", "h1")

    assert index.locator_for_document("doc-1") == "the-locator"
    assert index.locator_for_document("no-such-document") is None


def test_record_is_idempotent(tmp_path):
    index = _index(tmp_path)
    index.record_document("doc-1", "source-a", "h1", "http", "2026-01-01T00:00:00Z")
    index.record_document("doc-1", "source-a", "h1", "http", "2026-01-01T00:00:00Z")  # re-recording is a no-op

    assert index.all_ids("documents") == ("doc-1",)


def test_rebuild_from_an_existing_store_reproduces_the_index(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "store")
    source = make_source(kind="paper", name="Test Source")
    document = make_document(source_id=source.id, raw_content="content", retrieval_method="m", retrieved_at="t")
    record = make_record(document_id=document.id, locator="loc-1", raw_content="content")
    store.put_source(source)
    store.put_document(document)
    store.put_record(record)

    fresh_index = MetadataIndex(tmp_path / "rebuilt.sqlite")
    assert fresh_index.is_empty() is True

    fresh_index.rebuild(store)

    assert fresh_index.all_ids("sources") == (source.id,)
    assert fresh_index.all_ids("documents") == (document.id,)
    artifact_id = compute_artifact_id(source.id, "loc-1")
    assert fresh_index.list_versions(artifact_id) == (document.id,)


def test_rebuild_is_safe_to_call_on_an_already_populated_index(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "store")
    source = make_source(kind="paper", name="Test Source")
    document = make_document(source_id=source.id, raw_content="content", retrieval_method="m", retrieved_at="t")
    store.put_source(source)
    store.put_document(document)

    store.index.rebuild(store)  # already populated incrementally by put_source/put_document above
    store.index.rebuild(store)  # calling again must not duplicate or error

    assert store.index.all_ids("documents") == (document.id,)
