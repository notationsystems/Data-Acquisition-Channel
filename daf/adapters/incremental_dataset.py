"""A deterministic, LOCAL adapter demonstrating genuine incremental/cursor
acquisition semantics.

Built because neither existing adapter has any cursor concept:
`daf.adapters.arxiv` fetches an explicit identifier list (snapshot-by-id),
and `daf.adapters.local_dataset` reads an entire file every time
(whole-file snapshot). Inventing incremental behavior against a real
external API was explicitly out of scope for this phase; this is a
plain local file, clearly labeled as such.

Reads a local JSON array of records, each carrying an explicit integer
`"sequence"` field (monotonically increasing, caller-authored -- this
adapter never assigns sequence numbers itself, the same "acquisition
never assigns identity" discipline every other adapter in this codebase
follows). `fetch()` returns only records whose sequence is strictly
greater than `since_sequence` (`None` = from the beginning).

Each record's `locator` IS its own sequence number, zero-padded for
stable string ordering -- this is what lets
`daf.orchestration.bindings.incremental_dataset_binding`'s
`advance_position` compute "the highest sequence acquired this run"
generically from `AcquiredArtifact.locator`, without parsing evidence
content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from scout.interface import RawDocument

_SEQUENCE_WIDTH = 12  # generous zero-padding -- string and numeric ordering
                       # agree for any realistic sequence range at this width


class IncrementalDatasetFetchError(RuntimeError):
    """Raised when the dataset file is missing, not valid JSON, not a
    JSON array, or contains a record with no integer "sequence" field."""


def locator_for(sequence: int) -> str:
    return str(sequence).zfill(_SEQUENCE_WIDTH)


def sequence_of(locator: str) -> int:
    """Inverse of `locator_for` -- used by
    daf.orchestration.bindings.incremental_dataset_binding's
    advance_position to recover the numeric sequence from an
    AcquiredArtifact.locator. Adapter-specific by design: nothing outside
    this module and its binding needs to know a locator encodes a
    sequence number at all."""
    return int(locator)


@dataclass(frozen=True)
class IncrementalDatasetSourceAdapter:
    path: Path
    source_name: str
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock
    since_sequence: Optional[int] = None  # None = from the beginning

    def fetch(self) -> Tuple[RawDocument, ...]:
        try:
            raw_text = self.path.read_text()
        except OSError as exc:
            raise IncrementalDatasetFetchError(f"could not read dataset file {self.path}: {exc}") from exc

        try:
            records = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise IncrementalDatasetFetchError(f"{self.path} is not valid JSON") from exc
        if not isinstance(records, list):
            raise IncrementalDatasetFetchError(f"{self.path} must contain a JSON array of records")

        documents = []
        for record in records:
            sequence = record.get("sequence") if isinstance(record, dict) else None
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                raise IncrementalDatasetFetchError(
                    f"record in {self.path} has no integer 'sequence' field: {record!r}"
                )
            if self.since_sequence is not None and sequence <= self.since_sequence:
                continue
            documents.append(
                RawDocument(
                    source_name=self.source_name,
                    source_kind="incremental-dataset",
                    content=json.dumps(record, sort_keys=True),
                    locator=locator_for(sequence),
                    retrieval_method="file:incremental_json_v1",
                    retrieved_at=self.retrieved_at,
                )
            )
        documents.sort(key=lambda d: d.locator)  # deterministic order, ascending sequence
        return tuple(documents)
