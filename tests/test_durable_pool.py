"""Tests for daf.storage.durable_pool.DurablePool -- the acquire -> persist
-> restart -> retrieve invariant, plus proof that run_scout cannot tell a
DurablePool from a plain EvidencePool (the SCOUT regression requirement)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from evidence.pool import EvidencePool
from scout.pipeline import run_scout

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.extractors.arxiv import ArxivExtractor
from daf.storage.durable_pool import DurablePool, load_pool
from daf.storage.filesystem_store import FilesystemEvidenceStore

FIXTURES = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).parent.parent


def _fixture_adapter(fixture_name: str) -> ArxivSourceAdapter:
    def _fetch(url: str) -> bytes:
        return (FIXTURES / fixture_name).read_bytes()

    return ArxivSourceAdapter(arxiv_ids=("9999.00001",), retrieved_at="2026-08-24T00:00:00Z", fetch_bytes=_fetch)


def test_durable_pool_is_indistinguishable_from_evidencepool_to_run_scout(tmp_path):
    """SCOUT regression: identical findings/failures/ids/fingerprint
    whether run_scout is given a plain EvidencePool or a DurablePool."""
    plain_pool = EvidencePool()
    durable_pool = DurablePool(FilesystemEvidenceStore(tmp_path / "store"))

    findings_plain, failures_plain = run_scout(
        _fixture_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), plain_pool
    )
    findings_durable, failures_durable = run_scout(
        _fixture_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), durable_pool
    )

    assert failures_plain == failures_durable == ()
    assert findings_plain[0].observation.id == findings_durable[0].observation.id
    assert findings_plain[0].document.id == findings_durable[0].document.id
    assert plain_pool.fingerprint() == durable_pool.fingerprint()


def test_acquire_persist_restart_retrieve_identical_identity(tmp_path):
    store_path = tmp_path / "store"

    # ACQUIRE + PERSIST ("process A")
    store_a = FilesystemEvidenceStore(store_path)
    pool_a = DurablePool(store_a)
    findings, failures = run_scout(_fixture_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool_a)
    assert failures == ()

    original_document = findings[0].document
    original_observation = findings[0].observation
    original_fingerprint = pool_a.fingerprint()
    original_raw_content = original_document.raw_content

    del pool_a, store_a, findings, failures  # nothing below may reference process A's objects

    # RETRIEVE ("process B" -- brand new objects, same on-disk path only)
    store_b = FilesystemEvidenceStore(store_path)
    pool_b = DurablePool.restore(store_b)

    assert pool_b.fingerprint() == original_fingerprint

    restored_document = pool_b.get_document(original_document.id)
    assert restored_document.id == original_document.id  # identical version identity
    assert restored_document.raw_content == original_raw_content  # exact raw bytes
    assert restored_document.retrieval_method == original_document.retrieval_method  # acquisition metadata
    assert restored_document.retrieved_at == original_document.retrieved_at

    restored_observation = pool_b.get_observation(original_observation.id)
    assert dict(restored_observation.content) == dict(original_observation.content)
    assert restored_observation.confidence == original_observation.confidence


def test_version_distinguishability_survives_restart(tmp_path):
    store_path = tmp_path / "store"
    store_a = FilesystemEvidenceStore(store_path)
    pool_a = DurablePool(store_a)
    run_scout(_fixture_adapter("arxiv_single_entry_v1.xml"), ArxivExtractor(), pool_a)
    run_scout(_fixture_adapter("arxiv_single_entry_v1_revised.xml"), ArxivExtractor(), pool_a)
    del pool_a, store_a

    store_b = FilesystemEvidenceStore(store_path)
    pool_b = load_pool(store_b)
    assert len(pool_b.all_observations()) == 2  # both versions survived restart, distinguishable


def test_restart_across_two_real_separate_os_processes(tmp_path):
    """The strongest possible restart proof: two genuinely separate
    Python processes, sharing nothing but the filesystem path -- no
    module state, no object references, nothing in common but disk."""
    store_dir = tmp_path / "cli_store"

    acquire = subprocess.run(
        [sys.executable, "-m", "daf.storage.demo", "acquire", str(store_dir), "1706.03762"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    if acquire.returncode != 0:
        pytest.skip(f"live acquisition unavailable in this environment: {acquire.stderr}")

    retrieve = subprocess.run(
        [sys.executable, "-m", "daf.storage.demo", "retrieve", str(store_dir)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    assert retrieve.returncode == 0, retrieve.stderr

    def _value(output: str, key: str) -> str:
        for line in output.splitlines():
            if key in line:
                return line.split("=", 1)[1].strip()
        raise AssertionError(f"{key!r} not found in output:\n{output}")

    for key in ("version_id", "artifact_id", "content_hash", "raw_bytes_len", "pool.fingerprint()"):
        acquired_value = _value(acquire.stdout, key)
        retrieved_value = _value(retrieve.stdout, key)
        assert acquired_value == retrieved_value, f"{key} differed across restart"


# -- Phase K: lazy restore -- proving the algorithmic path actually changed --


def _populate(store_path: Path, count: int) -> None:
    """A small, deterministic synthetic corpus -- `count` distinct
    arXiv-shaped acquisitions, each a genuinely different Document (a
    unique arxiv_id baked into fixture text), persisted through the
    exact same DurablePool/FilesystemEvidenceStore path any real
    adapter uses."""
    from evidence.types import make_document, make_record, make_source

    store = FilesystemEvidenceStore(store_path)
    pool = DurablePool(store)
    source = make_source(kind="paper", name="synthetic corpus")
    pool.put_source(source)
    for i in range(count):
        document = make_document(
            source_id=source.id, raw_content=f"synthetic content #{i}", retrieval_method="m",
            retrieved_at=f"2026-01-{(i % 28) + 1:02d}T00:00:00Z",
        )
        record = make_record(document_id=document.id, locator=f"locator-{i}", raw_content=document.raw_content)
        pool.put_document(document)
        pool.put_record(record)


def test_restart_does_not_hydrate_until_a_full_corpus_method_is_called(tmp_path, monkeypatch):
    """The actual Phase J complaint, demonstrated directly: restoring a
    pool over a non-trivial corpus and doing ordinary duplicate-
    detection-shaped work (has_document/get_document for specific ids)
    must never touch the store's full-scan methods at all -- proven by
    making those methods raise if called, not by timing anything."""
    store_path = tmp_path / "store"
    _populate(store_path, count=50)

    store = FilesystemEvidenceStore(store_path)
    known_document = store.all_documents()[0]  # established via a real call, before patching

    def _forbidden(*args, **kwargs):
        raise AssertionError("a full-scan method was called -- restore()/has_/get_ must stay lazy")

    monkeypatch.setattr(store, "all_documents", _forbidden)
    monkeypatch.setattr(store, "all_records", _forbidden)
    monkeypatch.setattr(store, "all_sources", _forbidden)
    monkeypatch.setattr(store, "all_observations", _forbidden)

    pool = DurablePool.restore(store)  # must not scan anything itself
    assert pool.has_document(known_document.id) is True  # single-id lookup -- must not scan
    assert pool.has_document("no-such-id") is False  # a genuine miss -- also must not scan
    document = pool.get_document(known_document.id)  # single-id load -- must not scan
    assert document.raw_content == known_document.raw_content
    assert pool._hydrated is False  # still true after all of the above


def test_all_observations_still_triggers_full_hydration_when_actually_needed(tmp_path):
    """The other half of the same claim: `all_*`/`fingerprint_history`/
    `__len__` still give the FULL, CORRECT answer -- laziness changed
    WHEN the cost is paid, never WHETHER the answer is correct."""
    store_path = tmp_path / "store"
    _populate(store_path, count=12)

    pool = DurablePool.restore(FilesystemEvidenceStore(store_path))
    assert pool._hydrated is False

    assert len(pool.all_observations()) == 0  # no Observations in this synthetic corpus, but the CALL must succeed
    assert pool._hydrated is True
    assert len(pool) == 12 + 12 + 1  # documents + records + the one shared source


def test_fingerprint_is_equivalent_whether_or_not_the_pool_has_hydrated(tmp_path):
    """Phase J section 8's explicit requirement: fingerprint() computed
    via the lazy/indexed path must be byte-for-byte identical to the
    value the original, fully-hydrated computation would produce."""
    store_path = tmp_path / "store"
    _populate(store_path, count=25)

    lazy_pool = DurablePool.restore(FilesystemEvidenceStore(store_path))
    lazy_fingerprint = lazy_pool.fingerprint()
    assert lazy_pool._hydrated is False  # computed WITHOUT hydrating

    hydrated_pool = DurablePool.restore(FilesystemEvidenceStore(store_path))
    hydrated_pool.force_full_hydration()
    hydrated_fingerprint = hydrated_pool.fingerprint()
    assert hydrated_pool._hydrated is True

    assert lazy_fingerprint == hydrated_fingerprint


def test_fingerprint_reflects_partial_in_process_hydration_correctly(tmp_path):
    """A pool that has lazily loaded SOME objects (via get_document) but
    not others must still fingerprint identically to a pool that loaded
    none of them lazily -- the in-memory/index union in the fingerprint()
    override must not double-count or miss anything."""
    store_path = tmp_path / "store"
    _populate(store_path, count=10)

    store = FilesystemEvidenceStore(store_path)
    some_document_id = store.all_documents()[3].id

    partially_loaded_pool = DurablePool.restore(FilesystemEvidenceStore(store_path))
    partially_loaded_pool.get_document(some_document_id)  # touch exactly one document
    assert partially_loaded_pool._hydrated is False

    never_touched_pool = DurablePool.restore(FilesystemEvidenceStore(store_path))

    assert partially_loaded_pool.fingerprint() == never_touched_pool.fingerprint()


def test_index_rebuild_after_deletion_recovers_the_same_logical_state(tmp_path):
    """Phase J's own stated invariant: filesystem = authority, SQLite =
    derived. Deleting index.sqlite and reopening the store must
    transparently rebuild it, with list_versions/fingerprint answering
    exactly as before the deletion."""
    from daf.storage.artifact_store import ArtifactStore

    store_path = tmp_path / "store"
    _populate(store_path, count=8)

    store = FilesystemEvidenceStore(store_path)
    artifact_store = ArtifactStore(store)
    document = store.all_documents()[0]
    locator = artifact_store._locator_for(document)
    artifact_id = artifact_store.artifact_id(document.source_id, locator)
    versions_before = artifact_store.list_versions(artifact_id)
    fingerprint_before = DurablePool.restore(store).fingerprint()

    (store_path / "index.sqlite").unlink()

    reopened_store = FilesystemEvidenceStore(store_path)  # __init__ detects the stale/missing index and rebuilds
    reopened_artifact_store = ArtifactStore(reopened_store)
    assert reopened_artifact_store.list_versions(artifact_id) == versions_before
    assert DurablePool.restore(reopened_store).fingerprint() == fingerprint_before
