"""AcquisitionRequest -- describes WHAT SOURCE should be acquired, never
what scientific conclusion should result from it.

`parameters` is an open, adapter-defined mapping -- mirroring
`evidence.types.Observation.content`'s own "open, extraction-defined
mapping, no forced schema" discipline. The orchestrator never inspects
its keys; only the `build_adapter` callable bound to the request's
`source_id` (via the AdapterRegistry) does.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class AcquisitionRequest:
    source_id: str
    parameters: Mapping[str, Any]
    requested_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
