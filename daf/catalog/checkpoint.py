"""AcquisitionCheckpoint: DAF-owned acquisition PROGRESS, never
scientific state.

    "the acquisition apparatus successfully progressed to this source
     position for this plan"

is a categorically different claim from "the scientific system has
learned everything before this point." A checkpoint says nothing about
evidence, ModelState, or any downstream system -- it exists purely so
`daf.scheduling` does not re-acquire an entire incremental source's
history on every run.

`position` is deliberately OPAQUE (`Optional[str]`) rather than a typed
universal Cursor: the two existing snapshot adapters
(`daf.adapters.arxiv`, `daf.adapters.local_dataset`) have no cursor
concept at all, and even between two genuinely incremental sources,
"position" could mean a sequence number, an ISO timestamp, or an opaque
pagination token. Only the adapter binding that produced a given
position (see `daf.orchestration.adapter_registry.AdapterBinding.advance_position`)
ever interprets it; this module never parses or compares position
values -- it only stores and returns them.

`updated_at` doubles as "when this plan last SUCCEEDED" for BOTH
incremental cursor tracking and snapshot due-scheduling
(`daf.scheduling.due`) -- a snapshot-mode plan's checkpoint always has
`position=None` but still advances `updated_at` on every successful run,
which is exactly the information a scheduler needs to know when a
snapshot plan is next due.

Persistence follows the same "operator/apparatus-owned, last-write-wins"
model as `daf.catalog.source_catalog`/`plan_catalog` -- a checkpoint is
legitimately overwritten (advanced) in place, unlike the content-addressed
evidence store from Phase B.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from daf.storage.serialization import strict_json_loads


@dataclass(frozen=True)
class AcquisitionCheckpoint:
    plan_id: str
    source_id: str
    position: Optional[str]  # opaque, adapter-defined; None = no cursor progress (or snapshot mode)
    updated_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock


def _checkpoint_to_dict(checkpoint: AcquisitionCheckpoint) -> Dict[str, Any]:
    return {
        "plan_id": checkpoint.plan_id,
        "source_id": checkpoint.source_id,
        "position": checkpoint.position,
        "updated_at": checkpoint.updated_at,
    }


def _checkpoint_from_dict(payload: Dict[str, Any]) -> AcquisitionCheckpoint:
    return AcquisitionCheckpoint(
        plan_id=payload["plan_id"],
        source_id=payload["source_id"],
        position=payload.get("position"),
        updated_at=payload["updated_at"],
    )


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, plan_id: str) -> Optional[AcquisitionCheckpoint]:
        path = self.root / f"{plan_id}.json"
        if not path.exists():
            return None
        return _checkpoint_from_dict(strict_json_loads(path.read_text()))

    def advance(self, checkpoint: AcquisitionCheckpoint) -> None:
        path = self.root / f"{checkpoint.plan_id}.json"
        tmp_path = self.root / f"{checkpoint.plan_id}.json.tmp"
        tmp_path.write_text(json.dumps(_checkpoint_to_dict(checkpoint), sort_keys=True, indent=2, allow_nan=False))
        tmp_path.replace(path)  # atomic on POSIX
