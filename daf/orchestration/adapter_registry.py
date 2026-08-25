"""AdapterBinding / AdapterRegistry.

Maps an `adapter_id` (as named by a SourceDefinition) to the two
factories the orchestrator needs: one producing a `SourceAdapter`
instance from the request, one producing a fresh `Extractor` instance.
Both factories return objects satisfying the EXISTING, unmodified
`scout.interface` Protocols -- this registry adds no new adapter
contract, it only names how to construct one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from scout.interface import Extractor, SourceAdapter

from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.source_registry import SourceDefinition

BuildAdapter = Callable[[SourceDefinition, AcquisitionRequest], SourceAdapter]
BuildExtractor = Callable[[], Extractor]


class AdapterNotFoundError(KeyError):
    """Raised when no AdapterBinding is registered under a given id."""


@dataclass(frozen=True)
class AdapterBinding:
    adapter_id: str
    build_adapter: BuildAdapter
    build_extractor: BuildExtractor


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
