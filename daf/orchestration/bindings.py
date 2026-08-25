"""Concrete AdapterBinding factories for the DAF's sources.

This is deliberately the ONE module in `daf.orchestration` allowed to
import `daf.adapters.*`/`daf.extractors.*` -- `daf.orchestration.orchestrator`
itself never does (see its own docstring and the AST-level proof in
tests/test_acquisition_orchestrator.py). Adding a new source means adding
one function here, never touching the orchestrator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.adapters.incremental_dataset import IncrementalDatasetSourceAdapter, locator_for, sequence_of
from daf.adapters.local_dataset import LocalDatasetSourceAdapter
from daf.extractors.arxiv import ArxivExtractor
from daf.extractors.local_dataset import LocalDatasetExtractor
from daf.orchestration.adapter_registry import AdapterBinding
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.result import AcquiredArtifact
from daf.orchestration.source_registry import SourceDefinition


def arxiv_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> ArxivSourceAdapter:
        arxiv_ids = tuple(request.parameters["arxiv_ids"])
        return ArxivSourceAdapter(arxiv_ids=arxiv_ids, retrieved_at=request.requested_at)

    return AdapterBinding(adapter_id="arxiv", build_adapter=build_adapter, build_extractor=ArxivExtractor)


def local_dataset_binding() -> AdapterBinding:
    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> LocalDatasetSourceAdapter:
        path = Path(str(request.parameters["path"]))
        return LocalDatasetSourceAdapter(
            path=path, source_name=source.name, retrieved_at=request.requested_at
        )

    return AdapterBinding(
        adapter_id="local-dataset", build_adapter=build_adapter, build_extractor=LocalDatasetExtractor
    )


def _advance_incremental_position(
    artifacts: Tuple[AcquiredArtifact, ...], previous_position: Optional[str]
) -> Optional[str]:
    if not artifacts:
        return previous_position  # nothing acquired this run -- position is unchanged, never regresses
    max_sequence = max(sequence_of(artifact.locator) for artifact in artifacts)
    if previous_position is not None:
        max_sequence = max(max_sequence, sequence_of(previous_position))
    return locator_for(max_sequence)


def incremental_dataset_binding() -> AdapterBinding:
    """Same underlying record shape/extractor as `local_dataset_binding`
    -- the only difference is genuine cursor support: `request.parameters["since"]`
    (a locator-shaped string, injected by `daf.scheduling.runner.execute_plan`
    from the plan's checkpoint) becomes `since_sequence`, and
    `advance_position` computes the next checkpoint position from what was
    actually acquired."""

    def build_adapter(source: SourceDefinition, request: AcquisitionRequest) -> IncrementalDatasetSourceAdapter:
        path = Path(str(request.parameters["path"]))
        since = request.parameters.get("since")
        since_sequence = sequence_of(str(since)) if since is not None else None
        return IncrementalDatasetSourceAdapter(
            path=path, source_name=source.name, retrieved_at=request.requested_at, since_sequence=since_sequence
        )

    return AdapterBinding(
        adapter_id="incremental-dataset",
        build_adapter=build_adapter,
        build_extractor=LocalDatasetExtractor,
        advance_position=_advance_incremental_position,
    )
