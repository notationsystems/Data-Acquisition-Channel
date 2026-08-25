"""Tests for daf.catalog.checkpoint.{AcquisitionCheckpoint, CheckpointStore}."""

from __future__ import annotations

from daf.catalog.checkpoint import AcquisitionCheckpoint, CheckpointStore


def test_unknown_plan_has_no_checkpoint(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoints")
    assert store.get("does-not-exist") is None


def test_advance_then_get_returns_the_checkpoint(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoints")
    checkpoint = AcquisitionCheckpoint(
        plan_id="p1", source_id="events", position="000000000002", updated_at="2026-08-24T00:00:00Z"
    )
    store.advance(checkpoint)
    assert store.get("p1") == checkpoint


def test_checkpoint_persists_and_reloads_across_a_fresh_store_instance(tmp_path):
    root = tmp_path / "checkpoints"
    checkpoint = AcquisitionCheckpoint(
        plan_id="p1", source_id="events", position="000000000002", updated_at="2026-08-24T00:00:00Z"
    )
    CheckpointStore(root).advance(checkpoint)

    reloaded = CheckpointStore(root)
    assert reloaded.get("p1") == checkpoint


def test_advancing_overwrites_the_previous_checkpoint(tmp_path):
    store = CheckpointStore(tmp_path / "checkpoints")
    store.advance(AcquisitionCheckpoint(plan_id="p1", source_id="events", position="1", updated_at="2026-08-24T00:00:00Z"))
    store.advance(AcquisitionCheckpoint(plan_id="p1", source_id="events", position="2", updated_at="2026-08-25T00:00:00Z"))

    checkpoint = store.get("p1")
    assert checkpoint.position == "2"
    assert checkpoint.updated_at == "2026-08-25T00:00:00Z"


def test_snapshot_style_checkpoint_can_have_no_position():
    checkpoint = AcquisitionCheckpoint(plan_id="p1", source_id="s", position=None, updated_at="2026-08-24T00:00:00Z")
    assert checkpoint.position is None
