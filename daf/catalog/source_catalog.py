"""SourceCatalog: a persistent daf.orchestration.source_registry.SourceRegistry.

Unlike evidence.types objects, a SourceDefinition is operator-declared
acquisition configuration, not content-addressed evidence -- it is
legitimately mutable (an operator may update a source's configuration or
flip enabled/disabled), so persistence here is a plain "last write wins"
JSON file per `source_id`, deliberately NOT a content-addressed store
like Phase B's `FilesystemEvidenceStore`. This is a different persistence
model for a different kind of object: declarative acquisition capability,
never scientific evidence.

Mirrors `daf.storage.durable_pool.DurablePool`'s relationship to
`EvidencePool`: a subclass that adds a persistence side-effect to
`register()` only, inheriting `get`/`all_sources` unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from daf.orchestration.source_registry import SourceDefinition, SourceRegistry


def _source_to_dict(source: SourceDefinition) -> Dict[str, Any]:
    return {
        "source_id": source.source_id,
        "name": source.name,
        "domain": source.domain,
        "adapter_id": source.adapter_id,
        "configuration": dict(source.configuration),
        "capabilities": list(source.capabilities),
        "required_parameters": list(source.required_parameters),
        "enabled": source.enabled,
    }


def _source_from_dict(payload: Dict[str, Any]) -> SourceDefinition:
    return SourceDefinition(
        source_id=payload["source_id"],
        name=payload["name"],
        domain=payload["domain"],
        adapter_id=payload["adapter_id"],
        configuration=payload.get("configuration", {}),
        capabilities=tuple(payload.get("capabilities", ())),
        required_parameters=tuple(payload.get("required_parameters", ())),
        enabled=payload.get("enabled", True),
    )


class SourceCatalog(SourceRegistry):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.root.glob("*.json")):
            SourceRegistry.register(self, _source_from_dict(json.loads(path.read_text())))

    def register(self, definition: SourceDefinition) -> None:
        path = self.root / f"{definition.source_id}.json"
        tmp_path = self.root / f"{definition.source_id}.json.tmp"
        tmp_path.write_text(json.dumps(_source_to_dict(definition), sort_keys=True, indent=2, allow_nan=False))
        tmp_path.replace(path)  # atomic on POSIX
        SourceRegistry.register(self, definition)
