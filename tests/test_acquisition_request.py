"""Tests for daf.orchestration.request.AcquisitionRequest."""

from __future__ import annotations

import types

from daf.orchestration.request import AcquisitionRequest


def test_parameters_are_immutable():
    request = AcquisitionRequest(
        source_id="arxiv-papers", parameters={"arxiv_ids": ["1706.03762"]}, requested_at="2026-08-24T00:00:00Z"
    )
    assert isinstance(request.parameters, types.MappingProxyType)
    assert request.parameters["arxiv_ids"] == ["1706.03762"]


def test_request_only_describes_which_source_to_acquire():
    """No scientific-conclusion vocabulary (property/formulation/criterion/
    ModelState) belongs on this type -- only what a source needs to be
    acquired."""
    assert set(AcquisitionRequest.__dataclass_fields__) == {"source_id", "parameters", "requested_at"}
