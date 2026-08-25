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
