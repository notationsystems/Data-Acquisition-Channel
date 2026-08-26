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
from daf.storage.serialization import NonJsonConstantError, strict_json_loads

_SEQUENCE_WIDTH = 12  # generous zero-padding -- string and numeric ordering
                       # agree for any realistic sequence range at this width


class IncrementalDatasetFetchError(RuntimeError):
    """Raised when the dataset file is missing, not valid JSON, not a
    JSON array, or contains a record with no integer "sequence" field."""


def locator_for(sequence: int) -> str:
    """The CHECKPOINT POSITION format -- a bare, zero-padded sequence
    number, carrying no dataset identity. This is what
    `incremental_dataset_binding`'s `advance_position` returns and what
    comes back as `request.parameters["since"]`.

    Phase S: deliberately NOT the document locator any more. Through
    Phase F this one function served as both, which conflated "where
    should acquisition resume" with "which external object is this" --
    the two questions Phase R established must stay separate. See
    `document_locator_for`."""
    return str(sequence).zfill(_SEQUENCE_WIDTH)


def document_locator_for(path: Path, sequence: int) -> str:
    """The LOGICAL ARTIFACT locator -- `"{path}#{padded sequence}"`.

    Phase S fixed a reproduced collision: `artifact_id` is
    `H({source_id, locator})`, and a bare sequence number made record 7
    of one dataset file indistinguishable from record 7 of a completely
    different one acquired under the same registered source. Their
    contents differ, so the second acquisition read as a REVISION of the
    first rather than as a different object.

    `path` is the request parameter that determines the payload, so it
    belongs in the artifact's name -- exactly the rule
    `daf.adapters.local_dataset` (`"{path}#{id}"`) already followed, and
    exactly the dimension `daf.adapters.noaa_water_level` was missing.
    The sequence stays LAST so `sequence_of` can recover the cursor from
    either shape."""
    return f"{path}#{locator_for(sequence)}"


def sequence_of(value: str) -> int:
    """Recovers the numeric sequence from EITHER a checkpoint position
    (`"000000000007"`) or a document locator
    (`"/data/stream.json#000000000007"`) -- used by
    daf.orchestration.bindings.incremental_dataset_binding's
    advance_position, which sees both. Reading the last `#`-separated
    component mirrors NOAA's `window_end_of` (`rsplit(":", 1)[-1]`):
    a cursor may be embedded in a locator, but it is always recoverable
    without knowing what precedes it. Adapter-specific by design:
    nothing outside this module and its binding needs to know a locator
    encodes a sequence number at all."""
    return int(value.rsplit("#", 1)[-1])


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
            records = strict_json_loads(raw_text)
        except json.JSONDecodeError as exc:
            raise IncrementalDatasetFetchError(f"{self.path} is not valid JSON") from exc
        except NonJsonConstantError as exc:
            # A bare NaN/Infinity. Refused HERE rather than at the
            # json.dumps below, for two measured reasons: the dumps
            # ValueError escapes this adapter's own error type and does
            # not name the file, and a record filtered out before it
            # reaches dumps never triggers it at all.
            raise IncrementalDatasetFetchError(f"{self.path} is not valid JSON: {exc}") from exc
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
                    content=json.dumps(record, sort_keys=True, allow_nan=False),
                    locator=document_locator_for(self.path, sequence),
                    retrieval_method="file:incremental_json_v1",
                    retrieved_at=self.retrieved_at,
                )
            )
        documents.sort(key=lambda d: d.locator)  # deterministic order, ascending sequence
        return tuple(documents)
