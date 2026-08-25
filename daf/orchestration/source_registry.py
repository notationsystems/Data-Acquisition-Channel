"""SourceDefinition / SourceRegistry.

A SourceDefinition answers exactly one question: "how can the DAF
acquire from this source?" It never answers "what does this source mean
scientifically" -- no property/formulation/criterion/unit vocabulary
belongs here, only acquisition mechanics (which adapter, what
configuration it needs). `domain` is a free-form, human-readable label
(e.g. "scientific-literature", "public-dataset") that the orchestration
layer never branches on -- see
tests/test_acquisition_orchestrator.py::test_orchestrator_never_imports_domain_specific_adapter_modules
for the structural proof.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Dict, Mapping, Tuple


class SourceNotFoundError(KeyError):
    """Raised when no SourceDefinition is registered under a given id."""


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    name: str
    domain: str
    adapter_id: str
    configuration: Mapping[str, Any] = field(default_factory=dict)
    capabilities: Tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "configuration", MappingProxyType(dict(self.configuration)))
        object.__setattr__(self, "capabilities", tuple(self.capabilities))


class SourceRegistry:
    def __init__(self) -> None:
        self._sources: Dict[str, SourceDefinition] = {}

    def register(self, definition: SourceDefinition) -> None:
        self._sources[definition.source_id] = definition

    def get(self, source_id: str) -> SourceDefinition:
        try:
            return self._sources[source_id]
        except KeyError:
            raise SourceNotFoundError(f"no source registered under id {source_id!r}") from None

    def all_sources(self) -> Tuple[SourceDefinition, ...]:
        return tuple(self._sources[key] for key in sorted(self._sources))
