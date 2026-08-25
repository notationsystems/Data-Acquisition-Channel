"""Tests for daf.storage.artifact_store.ArtifactStore -- the
artifact-identity / version-identity / content-identity distinction."""

from __future__ import annotations

import pytest
from evidence.types import make_document, make_record

from daf.storage.artifact_store import ArtifactNotFoundError, ArtifactStore
from daf.storage.filesystem_store import FilesystemEvidenceStore


def _store(tmp_path):
    return FilesystemEvidenceStore(tmp_path / "store")


def _doc_and_record(source_id: str, locator: str, raw_content: str):
    document = make_document(
        source_id=source_id,
        raw_content=raw_content,
        retrieval_method="http:test",
        retrieved_at="2026-08-24T00:00:00Z",
    )
    record = make_record(document_id=document.id, locator=locator, raw_content=raw_content)
    return document, record


def test_artifact_id_stable_across_versions_while_version_id_changes(tmp_path):
    artifact_store = ArtifactStore(_store(tmp_path))
    doc_v1, rec_v1 = _doc_and_record("arXiv", "http://arxiv.org/abs/9999.00001v1", "v1 content")
    doc_v2, rec_v2 = _doc_and_record("arXiv", "http://arxiv.org/abs/9999.00001v1", "v2 content")

    artifact_id_1 = artifact_store.put(doc_v1, rec_v1)
    artifact_id_2 = artifact_store.put(doc_v2, rec_v2)

    assert artifact_id_1 == artifact_id_2  # same logical artifact (same source + locator)
    assert doc_v1.id != doc_v2.id  # distinct, distinguishable versions
    assert set(artifact_store.list_versions(artifact_id_1)) == {doc_v1.id, doc_v2.id}


def test_content_hash_is_a_distinct_concept_from_version_id(tmp_path):
    artifact_store = ArtifactStore(_store(tmp_path))
    document, record = _doc_and_record("arXiv", "loc-1", "same bytes")
    artifact_store.put(document, record)

    # content_hash covers ONLY the raw bytes; version_id (Document.id)
    # additionally folds in source_id and retrieval_method -- distinct
    # hashes over distinct payloads, never conflated.
    assert artifact_store.content_hash_of(document) != document.id


def test_deterministic_retrieval_by_artifact_and_version_id(tmp_path):
    artifact_store = ArtifactStore(_store(tmp_path))
    document, record = _doc_and_record("arXiv", "loc-1", "content")
    artifact_id = artifact_store.put(document, record)

    first = artifact_store.get(artifact_id, document.id)
    second = artifact_store.get(artifact_id, document.id)
    assert first == second == document
    assert artifact_store.exists(artifact_id, document.id)


def test_missing_artifact_and_version_raise_and_report_not_existing(tmp_path):
    artifact_store = ArtifactStore(_store(tmp_path))
    with pytest.raises(ArtifactNotFoundError):
        artifact_store.get("nonexistent-artifact", "nonexistent-version")
    assert not artifact_store.exists("nonexistent-artifact", "nonexistent-version")


def test_version_under_the_wrong_artifact_id_is_not_found(tmp_path):
    artifact_store = ArtifactStore(_store(tmp_path))
    document, record = _doc_and_record("arXiv", "loc-1", "content")
    artifact_store.put(document, record)

    wrong_artifact_id = ArtifactStore.artifact_id("arXiv", "a-different-locator")
    with pytest.raises(ArtifactNotFoundError):
        artifact_store.get(wrong_artifact_id, document.id)


def test_list_versions_orders_by_retrieved_at_then_id(tmp_path):
    artifact_store = ArtifactStore(_store(tmp_path))
    doc_later = make_document(
        source_id="arXiv", raw_content="second content", retrieval_method="http:test",
        retrieved_at="2026-02-01T00:00:00Z",
    )
    rec_later = make_record(document_id=doc_later.id, locator="loc-1", raw_content="second content")

    doc_earlier = make_document(
        source_id="arXiv", raw_content="first content", retrieval_method="http:test",
        retrieved_at="2026-01-01T00:00:00Z",
    )
    rec_earlier = make_record(document_id=doc_earlier.id, locator="loc-1", raw_content="first content")

    artifact_store.put(doc_later, rec_later)
    artifact_store.put(doc_earlier, rec_earlier)

    artifact_id = ArtifactStore.artifact_id("arXiv", "loc-1")
    assert artifact_store.list_versions(artifact_id) == (doc_earlier.id, doc_later.id)
