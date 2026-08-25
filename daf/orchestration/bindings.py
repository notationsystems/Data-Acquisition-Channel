"""Concrete AdapterBinding factories for the two Phase C sources.

This is deliberately the ONE module in `daf.orchestration` allowed to
import `daf.adapters.*`/`daf.extractors.*` -- `daf.orchestration.orchestrator`
itself never does (see its own docstring and the AST-level proof in
tests/test_acquisition_orchestrator.py). Adding a third source means
adding one function here, never touching the orchestrator.
"""

from __future__ import annotations

from pathlib import Path

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.adapters.local_dataset import LocalDatasetSourceAdapter
from daf.extractors.arxiv import ArxivExtractor
from daf.extractors.local_dataset import LocalDatasetExtractor
from daf.orchestration.adapter_registry import AdapterBinding
from daf.orchestration.request import AcquisitionRequest
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
