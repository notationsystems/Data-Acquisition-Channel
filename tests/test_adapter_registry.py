"""Tests for daf.orchestration.adapter_registry."""

from __future__ import annotations

import pytest

from daf.orchestration.adapter_registry import AdapterBinding, AdapterNotFoundError, AdapterRegistry


def test_register_and_get():
    registry = AdapterRegistry()
    binding = AdapterBinding(
        adapter_id="dummy", build_adapter=lambda source, request: object(), build_extractor=lambda: object()
    )
    registry.register(binding)

    assert registry.get("dummy") is binding


def test_get_unknown_adapter_raises():
    registry = AdapterRegistry()
    with pytest.raises(AdapterNotFoundError):
        registry.get("does-not-exist")
