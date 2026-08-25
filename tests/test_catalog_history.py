"""Tests for daf.catalog.history -- derived-only, no new persistent record."""

from __future__ import annotations

from pathlib import Path

from daf.adapters.local_dataset import LocalDatasetSourceAdapter
from daf.catalog.history import has_ever_been_acquired, known_versions
from daf.extractors.local_dataset import LocalDatasetExtractor
from daf.storage.artifact_store import ArtifactStore
from daf.storage.durable_pool import DurablePool
from daf.storage.filesystem_store import FilesystemEvidenceStore
from scout.pipeline import run_scout

FIXTURES = Path(__file__).parent / "fixtures"


def test_has_never_been_acquired_for_an_unknown_artifact(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "store")
    artifact_id = ArtifactStore.artifact_id("some-source-id", "some-locator")
    assert not has_ever_been_acquired(store, artifact_id)
    assert known_versions(store, artifact_id) == ()


def test_known_versions_reflects_durable_storage_after_acquisition(tmp_path):
    store = FilesystemEvidenceStore(tmp_path / "store")
    pool = DurablePool(store)
    adapter = LocalDatasetSourceAdapter(
        path=FIXTURES / "local_dataset_sample.json", source_name="widget-dataset", retrieved_at="2026-08-24T00:00:00Z"
    )
    findings, failures = run_scout(adapter, LocalDatasetExtractor(), pool)
    assert failures == ()

    finding = findings[0]
    artifact_id = ArtifactStore.artifact_id(finding.document.source_id, finding.record.locator)

    assert has_ever_been_acquired(store, artifact_id)
    assert known_versions(store, artifact_id) == (finding.document.id,)
