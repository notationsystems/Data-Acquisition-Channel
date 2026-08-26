"""Durable, append-only stores for execution and quarantine records.

Deliberately their OWN directories (`<root>/executions/`,
`<root>/quarantine/`) rather than categories on
`FilesystemEvidenceStore`. Two reasons, both load-bearing:

  * an execution record is not an `evidence.types` object, and putting it
    in the evidence store is one refactor away from it being treated as
    one;
  * `EvidencePool.fingerprint()` is computed over the evidence store's
    categories, and a pool's fingerprint must not change because an
    operation was recorded. `tests/test_execution_record.py` measures
    that it does not.

Filename is the record's own content-addressed id, and reads go through
`*_from_dict`, so on-disk alteration is refused on load rather than
trusted -- the same discipline `daf/storage/serialization.py` and
`daf/storage/class_store.py` already apply.

There is no delete method here, for the same reason there is none on
`FilesystemEvidenceStore`: retraction semantics remain unresolved
(`architecture/invariants.yaml`, `retraction`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

from daf.execution.quarantine import (
    QuarantineRecord,
    quarantine_record_from_dict,
    quarantine_record_to_dict,
)
from daf.execution.record import (
    ExecutionRecord,
    execution_record_from_dict,
    execution_record_to_dict,
)


class ExecutionRecordStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / "executions"
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, record: ExecutionRecord) -> None:
        path = self.root / f"{record.id}.json"
        path.write_text(json.dumps(execution_record_to_dict(record), sort_keys=True, indent=2, allow_nan=False))

    def get(self, execution_id: str) -> ExecutionRecord:
        path = self.root / f"{execution_id}.json"
        return execution_record_from_dict(json.loads(path.read_text()))

    def has(self, execution_id: str) -> bool:
        return (self.root / f"{execution_id}.json").exists()

    def all_records(self) -> Tuple[ExecutionRecord, ...]:
        records = []
        for path in sorted(self.root.glob("*.json")):
            record = execution_record_from_dict(json.loads(path.read_text()))
            if path.stem != record.id:
                raise ValueError(f"execution stored as {path.stem!r} identifies as {record.id!r}")
            records.append(record)
        return tuple(records)

    def for_operation(self, operation_id: str) -> Tuple[ExecutionRecord, ...]:
        """Every run of one operation, ordered by `started_at` then id so
        the order never depends on filesystem iteration."""
        return tuple(
            sorted(
                (r for r in self.all_records() if r.operation_id == operation_id),
                key=lambda r: (r.started_at, r.id),
            )
        )

    def latest_for_operation(self, operation_id: str) -> Optional[ExecutionRecord]:
        """The lineage parent for the next run of this operation."""
        runs = self.for_operation(operation_id)
        return runs[-1] if runs else None


class QuarantineStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root) / "quarantine"
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, record: QuarantineRecord) -> None:
        path = self.root / f"{record.id}.json"
        path.write_text(json.dumps(quarantine_record_to_dict(record), sort_keys=True, indent=2, allow_nan=False))

    def all_records(self) -> Tuple[QuarantineRecord, ...]:
        records = []
        for path in sorted(self.root.glob("*.json")):
            record = quarantine_record_from_dict(json.loads(path.read_text()))
            if path.stem != record.id:
                raise ValueError(f"quarantine stored as {path.stem!r} identifies as {record.id!r}")
            records.append(record)
        return tuple(records)

    def for_execution(self, execution_id: str) -> Tuple[QuarantineRecord, ...]:
        return tuple(
            sorted(
                (r for r in self.all_records() if r.execution_id == execution_id),
                key=lambda r: r.id,
            )
        )
