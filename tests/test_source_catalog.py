"""Tests for daf.catalog.source_catalog.SourceCatalog."""

from __future__ import annotations

from daf.catalog.source_catalog import SourceCatalog
from daf.orchestration.source_registry import SourceDefinition


def test_empty_catalog_has_no_sources(tmp_path):
    catalog = SourceCatalog(tmp_path / "sources")
    assert catalog.all_sources() == ()


def test_register_and_get(tmp_path):
    catalog = SourceCatalog(tmp_path / "sources")
    definition = SourceDefinition(
        source_id="arxiv-papers",
        name="arXiv",
        domain="scientific-literature",
        adapter_id="arxiv",
        required_parameters=("arxiv_ids",),
    )
    catalog.register(definition)

    assert catalog.get("arxiv-papers") == definition


def test_source_persists_and_reloads_across_a_fresh_catalog_instance(tmp_path):
    root = tmp_path / "sources"
    definition = SourceDefinition(
        source_id="widget-prices",
        name="widget-dataset",
        domain="public-dataset",
        adapter_id="local-dataset",
        configuration={"path": "/data/widgets.json"},
        capabilities=("snapshot",),
        required_parameters=("path",),
    )
    SourceCatalog(root).register(definition)

    # A brand new SourceCatalog instance pointed at the same path -- no
    # in-memory state shared with the one that registered it.
    reloaded = SourceCatalog(root)
    assert reloaded.get("widget-prices") == definition
    assert reloaded.get("widget-prices").required_parameters == ("path",)
    assert reloaded.get("widget-prices").capabilities == ("snapshot",)


def test_re_registering_a_source_updates_it_last_write_wins(tmp_path):
    root = tmp_path / "sources"
    catalog = SourceCatalog(root)
    catalog.register(
        SourceDefinition(source_id="s", name="S", domain="d", adapter_id="a", enabled=True)
    )
    catalog.register(
        SourceDefinition(source_id="s", name="S", domain="d", adapter_id="a", enabled=False)
    )

    assert catalog.get("s").enabled is False
    assert SourceCatalog(root).get("s").enabled is False  # persisted, not just in-memory
