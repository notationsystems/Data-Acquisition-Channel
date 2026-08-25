"""Tests for daf.orchestration.source_registry."""

from __future__ import annotations

import pytest

from daf.orchestration.source_registry import SourceDefinition, SourceNotFoundError, SourceRegistry


def test_register_and_get():
    registry = SourceRegistry()
    definition = SourceDefinition(
        source_id="arxiv-papers", name="arXiv", domain="scientific-literature", adapter_id="arxiv"
    )
    registry.register(definition)

    assert registry.get("arxiv-papers") == definition


def test_get_unknown_source_raises():
    registry = SourceRegistry()
    with pytest.raises(SourceNotFoundError):
        registry.get("does-not-exist")


def test_all_sources_is_deterministically_ordered():
    registry = SourceRegistry()
    registry.register(SourceDefinition(source_id="b", name="B", domain="x", adapter_id="a"))
    registry.register(SourceDefinition(source_id="a", name="A", domain="x", adapter_id="a"))

    assert [s.source_id for s in registry.all_sources()] == ["a", "b"]


def test_configuration_and_capabilities_are_immutable():
    definition = SourceDefinition(
        source_id="s", name="S", domain="d", adapter_id="a", configuration={"k": "v"}, capabilities=["read"]
    )
    import types

    assert isinstance(definition.configuration, types.MappingProxyType)
    assert definition.capabilities == ("read",)


def test_enabled_defaults_true_and_can_be_disabled():
    enabled = SourceDefinition(source_id="s1", name="S1", domain="d", adapter_id="a")
    disabled = SourceDefinition(source_id="s2", name="S2", domain="d", adapter_id="a", enabled=False)

    assert enabled.enabled is True
    assert disabled.enabled is False
