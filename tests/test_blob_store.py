"""Tests for daf.storage.blob_store.BlobStore."""

from __future__ import annotations

from evidence.identity import content_hash
import pytest

from daf.storage.blob_store import BlobCorruptionError, BlobNotFoundError, BlobStore


def _store(tmp_path):
    return BlobStore(tmp_path / "blobs")


def test_put_then_get_recovers_exact_content(tmp_path):
    store = _store(tmp_path)
    store.put(content_hash("hello world"), "hello world")

    assert store.get(content_hash("hello world")) == "hello world"


def test_has_reflects_presence(tmp_path):
    store = _store(tmp_path)
    assert store.has(content_hash("x")) is False

    store.put(content_hash("x"), "x")

    assert store.has(content_hash("x")) is True


def test_get_of_an_absent_hash_raises_not_found(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(BlobNotFoundError):
        store.get(content_hash("never stored"))


def test_put_is_idempotent(tmp_path):
    store = _store(tmp_path)
    hash_ = content_hash("same content")
    store.put(hash_, "same content")
    store.put(hash_, "same content")  # second put of identical content -- silent no-op

    assert store.get(hash_) == "same content"


def test_put_of_an_existing_hash_never_overwrites_the_stored_file(tmp_path):
    """A second put() under the SAME hash is a true no-op -- it does not
    even re-write the file -- verified by checking the file's content is
    untouched even if a caller (incorrectly) tries to put different
    bytes under an already-used hash (a caller bug this store cannot
    detect, since it trusts its own name-your-own-key contract; see the
    module's own docstring)."""
    store = _store(tmp_path)
    hash_ = content_hash("original")
    store.put(hash_, "original")
    store.put(hash_, "different bytes, same (wrong) key")

    assert store.get(hash_) == "original"


def test_corruption_is_detected_on_read(tmp_path):
    store = _store(tmp_path)
    hash_ = content_hash("A")
    store.put(hash_, "A")

    # Simulate on-disk tampering: rewrite the stored blob without
    # changing its filename/hash. Content-addressing makes this
    # impossible via this store's own API -- only direct disk
    # manipulation can do it.
    blob_path = store.root / f"{hash_}.blob"
    blob_path.write_text("TAMPERED")

    with pytest.raises(BlobCorruptionError):
        store.get(hash_)


def test_atomic_write_leaves_no_stray_tmp_file(tmp_path):
    store = _store(tmp_path)
    store.put(content_hash("y"), "y")

    assert list(store.root.glob("*.tmp")) == []
    assert list(store.root.glob("*.blob")) == [store.root / f"{content_hash('y')}.blob"]


def test_persists_across_a_fresh_store_instance_at_the_same_path(tmp_path):
    root = tmp_path / "blobs"
    BlobStore(root).put(content_hash("z"), "z")

    fresh_store = BlobStore(root)
    assert fresh_store.get(content_hash("z")) == "z"
