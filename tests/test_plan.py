"""Tests for daf.catalog.plan.{AcquisitionPlan, validate_plan}."""

from __future__ import annotations

from daf.catalog.plan import AcquisitionPlan, validate_plan
from daf.orchestration.adapter_registry import AdapterBinding, AdapterRegistry
from daf.orchestration.source_registry import SourceDefinition, SourceRegistry


def _registries():
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    sources.register(
        SourceDefinition(
            source_id="arxiv-papers",
            name="arXiv",
            domain="scientific-literature",
            adapter_id="arxiv",
            required_parameters=("arxiv_ids",),
        )
    )
    adapters.register(
        AdapterBinding(adapter_id="arxiv", build_adapter=lambda s, r: object(), build_extractor=lambda: object())
    )
    return sources, adapters


def test_to_request_converts_plan_fields_verbatim():
    plan = AcquisitionPlan(plan_id="p1", source_id="arxiv-papers", parameters={"arxiv_ids": ["1706.03762"]})
    request = plan.to_request(requested_at="2026-08-24T00:00:00Z")

    assert request.source_id == "arxiv-papers"
    assert request.parameters["arxiv_ids"] == ["1706.03762"]
    assert request.requested_at == "2026-08-24T00:00:00Z"


def test_to_request_is_deterministic():
    plan = AcquisitionPlan(plan_id="p1", source_id="arxiv-papers", parameters={"arxiv_ids": ["1706.03762"]})
    assert plan.to_request("2026-08-24T00:00:00Z") == plan.to_request("2026-08-24T00:00:00Z")


def test_valid_plan_has_no_issues():
    sources, adapters = _registries()
    plan = AcquisitionPlan(plan_id="p1", source_id="arxiv-papers", parameters={"arxiv_ids": ["1706.03762"]})
    assert validate_plan(plan, sources, adapters) == ()


def test_unknown_source_is_rejected():
    sources, adapters = _registries()
    plan = AcquisitionPlan(plan_id="p1", source_id="does-not-exist", parameters={})
    issues = validate_plan(plan, sources, adapters)
    assert len(issues) == 1
    assert issues[0].code == "UNKNOWN_SOURCE"


def test_disabled_source_is_rejected():
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    sources.register(
        SourceDefinition(source_id="s", name="S", domain="d", adapter_id="a", enabled=False)
    )
    adapters.register(AdapterBinding(adapter_id="a", build_adapter=lambda s, r: object(), build_extractor=lambda: object()))
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={})

    codes = {issue.code for issue in validate_plan(plan, sources, adapters)}
    assert "SOURCE_DISABLED" in codes


def test_unknown_adapter_is_rejected():
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    sources.register(SourceDefinition(source_id="s", name="S", domain="d", adapter_id="missing-adapter"))
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={})

    codes = {issue.code for issue in validate_plan(plan, sources, adapters)}
    assert "UNKNOWN_ADAPTER" in codes


def test_disabled_plan_is_rejected():
    sources, adapters = _registries()
    plan = AcquisitionPlan(
        plan_id="p1", source_id="arxiv-papers", parameters={"arxiv_ids": ["1706.03762"]}, enabled=False
    )
    codes = {issue.code for issue in validate_plan(plan, sources, adapters)}
    assert "PLAN_DISABLED" in codes


def test_missing_required_parameters_are_rejected():
    sources, adapters = _registries()
    plan = AcquisitionPlan(plan_id="p1", source_id="arxiv-papers", parameters={})  # missing "arxiv_ids"
    codes = {issue.code for issue in validate_plan(plan, sources, adapters)}
    assert "MISSING_PARAMETERS" in codes


def test_multiple_issues_can_be_reported_together():
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    sources.register(
        SourceDefinition(
            source_id="s", name="S", domain="d", adapter_id="a", enabled=False, required_parameters=("x",)
        )
    )
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={}, enabled=False)

    codes = {issue.code for issue in validate_plan(plan, sources, adapters)}
    assert codes == {"SOURCE_DISABLED", "UNKNOWN_ADAPTER", "PLAN_DISABLED", "MISSING_PARAMETERS"}


def test_plan_defaults_are_backward_compatible_with_phase_d():
    """A plan constructed exactly the way Phase D constructed them (no
    mode/interval_seconds) must behave identically: mode="snapshot",
    interval_seconds=None, and no new validation issue is raised."""
    sources, adapters = _registries()
    plan = AcquisitionPlan(plan_id="p1", source_id="arxiv-papers", parameters={"arxiv_ids": ["1706.03762"]})

    assert plan.mode == "snapshot"
    assert plan.interval_seconds is None
    assert validate_plan(plan, sources, adapters) == ()


def test_invalid_mode_is_rejected():
    sources, adapters = _registries()
    plan = AcquisitionPlan(
        plan_id="p1", source_id="arxiv-papers", parameters={"arxiv_ids": ["1"]}, mode="continuous"
    )
    codes = {issue.code for issue in validate_plan(plan, sources, adapters)}
    assert "INVALID_MODE" in codes


def test_incremental_mode_is_rejected_when_source_lacks_the_capability():
    sources, adapters = _registries()  # arxiv-papers has no "incremental" capability
    plan = AcquisitionPlan(
        plan_id="p1", source_id="arxiv-papers", parameters={"arxiv_ids": ["1"]}, mode="incremental"
    )
    codes = {issue.code for issue in validate_plan(plan, sources, adapters)}
    assert "INCREMENTAL_NOT_SUPPORTED" in codes


def test_incremental_mode_is_rejected_when_binding_has_no_advance_position():
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    sources.register(
        SourceDefinition(source_id="s", name="S", domain="d", adapter_id="a", capabilities=("incremental",))
    )
    adapters.register(
        AdapterBinding(adapter_id="a", build_adapter=lambda s, r: object(), build_extractor=lambda: object())
    )
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={}, mode="incremental")

    codes = {issue.code for issue in validate_plan(plan, sources, adapters)}
    assert "INCREMENTAL_NOT_SUPPORTED" in codes


def test_incremental_mode_is_accepted_when_source_and_binding_both_support_it():
    sources = SourceRegistry()
    adapters = AdapterRegistry()
    sources.register(
        SourceDefinition(source_id="s", name="S", domain="d", adapter_id="a", capabilities=("incremental",))
    )
    adapters.register(
        AdapterBinding(
            adapter_id="a",
            build_adapter=lambda s, r: object(),
            build_extractor=lambda: object(),
            advance_position=lambda artifacts, previous: previous,
        )
    )
    plan = AcquisitionPlan(plan_id="p1", source_id="s", parameters={}, mode="incremental")

    assert validate_plan(plan, sources, adapters) == ()
