"""Real scout.interface.SourceAdapter implementation over a local, static
JSON file -- deliberately a different acquisition pattern from
daf.adapters.arxiv (filesystem read of an already-downloaded resource,
vs. a live HTTP query API), to prove the Phase C orchestration layer is
genuinely adapter-agnostic rather than accidentally arXiv-shaped.

Represents the "static document / structured downloadable resource"
pattern: a file already present on disk, containing a JSON array of flat
records. No scientific ontology is assumed about record shape -- only
that each record is a JSON object with a stable "id" field, used as the
acquisition locator (the same role RawDocument.locator plays for arXiv's
entry URLs).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from scout.interface import RawDocument
from daf.storage.serialization import NonJsonConstantError, strict_json_loads


class LocalDatasetFetchError(RuntimeError):
    """Raised when the dataset file is missing, not valid JSON, not a
    JSON array, or contains a record with no "id" field."""


@dataclass(frozen=True)
class LocalDatasetSourceAdapter:
    path: Path
    source_name: str
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock

    def fetch(self) -> Tuple[RawDocument, ...]:
        try:
            raw_text = self.path.read_text()
        except OSError as exc:
            raise LocalDatasetFetchError(f"could not read dataset file {self.path}: {exc}") from exc

        try:
            records = strict_json_loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LocalDatasetFetchError(f"{self.path} is not valid JSON") from exc
        except NonJsonConstantError as exc:
            # A bare NaN/Infinity. Refused HERE rather than at the
            # json.dumps below, for two measured reasons: the dumps
            # ValueError escapes this adapter's own error type and does
            # not name the file, and a record filtered out before it
            # reaches dumps never triggers it at all.
            raise LocalDatasetFetchError(f"{self.path} is not valid JSON: {exc}") from exc
        if not isinstance(records, list):
            raise LocalDatasetFetchError(f"{self.path} must contain a JSON array of records")

        documents = []
        for record in records:
            if not isinstance(record, dict) or "id" not in record:
                raise LocalDatasetFetchError(f"record in {self.path} has no 'id' field: {record!r}")
            documents.append(
                RawDocument(
                    source_name=self.source_name,
                    source_kind="dataset",
                    content=json.dumps(record, sort_keys=True, allow_nan=False),
                    locator=f"{self.path}#{record['id']}",
                    retrieval_method="file:local_json_v1",
                    retrieved_at=self.retrieved_at,
                )
            )
        return tuple(documents)
