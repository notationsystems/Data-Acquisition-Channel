"""AdapterBinding / AdapterRegistry.

Maps an `adapter_id` (as named by a SourceDefinition) to the two
factories the orchestrator needs: one producing a `SourceAdapter`
instance from the request, one producing a fresh `Extractor` instance.
Both factories return objects satisfying the EXISTING, unmodified
`scout.interface` Protocols -- this registry adds no new adapter
contract, it only names how to construct one.

`advance_position` (Phase E, optional, default `None`) is how a binding
declares it supports incremental/checkpointed acquisition: given the
`AcquiredArtifact`s from one execution and the PREVIOUS checkpoint
position, it returns the new position -- purely by inspecting
`AcquiredArtifact.locator` (adapter-defined, e.g. a zero-padded sequence
number), never by reaching into evidence content. Left `None` for
snapshot-only adapters (`daf.adapters.arxiv`, `daf.adapters.local_dataset`)
-- `daf.catalog.plan.validate_plan` rejects a plan that requests
`mode="incremental"` against a binding with no `advance_position`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from scout.interface import Extractor, SourceAdapter

from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.result import AcquiredArtifact
from daf.orchestration.source_registry import SourceDefinition

BuildAdapter = Callable[[SourceDefinition, AcquisitionRequest], SourceAdapter]
BuildExtractor = Callable[[], Extractor]
AdvancePosition = Callable[[Tuple[AcquiredArtifact, ...], Optional[str]], Optional[str]]


class AdapterNotFoundError(KeyError):
    """Raised when no AdapterBinding is registered under a given id."""


@dataclass(frozen=True)
class AdapterBinding:
    adapter_id: str
    build_adapter: BuildAdapter
    build_extractor: BuildExtractor
    advance_position: Optional[AdvancePosition] = None


class AdapterRegistry:
    def __init__(self) -> None:
        self._bindings: Dict[str, AdapterBinding] = {}

    def register(self, binding: AdapterBinding) -> None:
        self._bindings[binding.adapter_id] = binding

    def get(self, adapter_id: str) -> AdapterBinding:
        try:
            return self._bindings[adapter_id]
        except KeyError:
            raise AdapterNotFoundError(f"no adapter registered under id {adapter_id!r}") from None
