"""Tests for daf.storage.filesystem_store.FilesystemEvidenceStore."""

from __future__ import annotations

import pytest
from evidence.types import make_document, make_source

from daf.storage.filesystem_store import FilesystemEvidenceStore
from daf.storage.serialization import ArtifactIdentityMismatch


def _store(tmp_path):
    return FilesystemEvidenceStore(tmp_path / "store")


def test_put_and_get_document_recovers_exact_raw_bytes(tmp_path):
    store = _store(tmp_path)
    document = make_document(
        source_id="src-1",
        raw_content="<entry>hello</entry>",
        retrieval_method="http:test",
        retrieved_at="2026-08-24T00:00:00Z",
    )
    store.put_document(document)

    assert store.has_document(document.id)
    retrieved = store.get_document(document.id)
    assert retrieved == document
    assert retrieved.raw_content == "<entry>hello</entry>"


def test_all_documents_deterministic_and_complete(tmp_path):
    store = _store(tmp_path)
    doc_a = make_document(source_id="s", raw_content="A", retrieval_method="m", retrieved_at="t")
    doc_b = make_document(source_id="s", raw_content="B", retrieval_method="m", retrieved_at="t")
    store.put_document(doc_a)
    store.put_document(doc_b)

    assert {d.id for d in store.all_documents()} == {doc_a.id, doc_b.id}
    # deterministic: two independent calls return the same order
    assert [d.id for d in store.all_documents()] == [d.id for d in store.all_documents()]


def test_duplicate_persistence_of_identical_content_is_a_silent_no_op(tmp_path):
    store = _store(tmp_path)
    document = make_document(source_id="s", raw_content="A", retrieval_method="m", retrieved_at="t")
    store.put_document(document)
    store.put_document(document)  # same content, same id -- must not raise or duplicate

    assert len(store.all_documents()) == 1


def test_corrupted_existing_file_is_detected_on_the_next_write(tmp_path):
    """A write to an id that already exists on disk re-verifies the
    EXISTING file's own identity rather than comparing payloads (two
    legitimately-constructed objects sharing an id can only differ in
    non-identity fields like retrieved_at -- see module docstring). If
    the existing file was corrupted/tampered with independent of this
    write, that is what gets caught."""
    store = _store(tmp_path)
    document = make_document(source_id="s", raw_content="A", retrieval_method="m", retrieved_at="t")
    store.put_document(document)

    # Simulate on-disk tampering: rewrite the persisted content without
    # changing its filename/id. Content-addressing makes this impossible
    # via this store's own API -- only direct disk manipulation can do it.
    path = store.root / "documents" / f"{document.id}.json"
    path.write_text(path.read_text().replace('"A"', '"TAMPERED"'))

    with pytest.raises(ArtifactIdentityMismatch):
        store.put_document(document)


def test_re_persisting_identical_content_at_a_different_acquisition_time_is_not_a_conflict(tmp_path):
    """The bug this guards against: Document.id excludes `retrieved_at`
    from its hash, so re-acquiring the SAME content at a later timestamp
    produces an object with the same id but a different retrieved_at --
    that must remain a legitimate, silent duplicate, never an error."""
    store = _store(tmp_path)
    first = make_document(source_id="s", raw_content="A", retrieval_method="m", retrieved_at="2026-01-01T00:00:00Z")
    second = make_document(source_id="s", raw_content="A", retrieval_method="m", retrieved_at="2026-02-01T00:00:00Z")
    assert first.id == second.id  # same identity-relevant content

    store.put_document(first)
    store.put_document(second)  # must NOT raise

    assert len(store.all_documents()) == 1


def test_missing_document_raises_key_error(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.get_document("does-not-exist")


def test_atomic_write_leaves_no_stray_tmp_file(tmp_path):
    store = _store(tmp_path)
    document = make_document(source_id="s", raw_content="A", retrieval_method="m", retrieved_at="t")
    store.put_document(document)

    assert list((store.root / "documents").glob("*.tmp")) == []


def test_persists_across_a_fresh_store_instance_at_the_same_path(tmp_path):
    """No in-memory state is involved in retrieval -- a brand new
    FilesystemEvidenceStore object pointed at the same path sees exactly
    what a prior, unrelated instance wrote."""
    path = tmp_path / "store"
    source = make_source(kind="paper", name="arXiv")
    FilesystemEvidenceStore(path).put_source(source)

    reloaded = FilesystemEvidenceStore(path)
    assert reloaded.get_source(source.id) == source
