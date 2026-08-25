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
position, it returns the new position -- typically by inspecting
`AcquiredArtifact.locator` (adapter-defined, e.g. a zero-padded sequence
number or a date string that IS the cursor value). Left `None` for
snapshot-only adapters (`daf.adapters.arxiv`, `daf.adapters.local_dataset`)
-- `daf.catalog.plan.validate_plan` rejects a plan that requests
`mode="incremental"` against a binding with no `advance_position`.

SEC EDGAR's date-string locator happens to BE its own cursor value, and
so does `incremental_dataset`'s zero-padded sequence number -- but Phase H
found a real source (USGS's earthquake catalog) where identity and cursor
value genuinely diverge: a stable event id (locator, never changes across
revisions) versus a last-revised timestamp that only that event's own
content carries. For exactly that case, `advance_position` may instead
parse `AcquiredArtifact.raw_content` (Phase H) -- still never reaching
into `EvidencePool` or any admitted evidence type, just the same raw
bytes the adapter itself already produced.
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
    # WHICH CODE this binding runs, for execution records (Phase 26 §6).
    # Additive and defaulted, so every pre-existing construction site and
    # every externally-registered binding is unaffected -- an undeclared
    # version is recorded as `None`, never guessed at. `daf.orchestration.
    # bindings` derives real values from the adapter/extractor source
    # rather than hand-maintaining a version string that would drift.
    version: Optional[str] = None


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
