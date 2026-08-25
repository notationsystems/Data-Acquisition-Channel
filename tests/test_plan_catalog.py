"""Tests for daf.catalog.plan_catalog.PlanCatalog."""

from __future__ import annotations

import pytest

from daf.catalog.plan import AcquisitionPlan
from daf.catalog.plan_catalog import PlanCatalog, PlanNotFoundError


def test_register_and_get(tmp_path):
    catalog = PlanCatalog(tmp_path / "plans")
    plan = AcquisitionPlan(plan_id="p1", source_id="arxiv-papers", parameters={"arxiv_ids": ["1"]})
    catalog.register(plan)

    assert catalog.get("p1") == plan


def test_get_unknown_plan_raises(tmp_path):
    catalog = PlanCatalog(tmp_path / "plans")
    with pytest.raises(PlanNotFoundError):
        catalog.get("does-not-exist")


def test_plan_persists_and_reloads_across_a_fresh_catalog_instance(tmp_path):
    root = tmp_path / "plans"
    plan = AcquisitionPlan(
        plan_id="widget-daily",
        source_id="widget-prices",
        parameters={"path": "/data/widgets.json"},
        schedule="daily",
    )
    PlanCatalog(root).register(plan)

    reloaded = PlanCatalog(root)
    assert reloaded.get("widget-daily") == plan


def test_all_plans_is_deterministically_ordered(tmp_path):
    catalog = PlanCatalog(tmp_path / "plans")
    catalog.register(AcquisitionPlan(plan_id="b", source_id="s", parameters={}))
    catalog.register(AcquisitionPlan(plan_id="a", source_id="s", parameters={}))

    assert [p.plan_id for p in catalog.all_plans()] == ["a", "b"]
