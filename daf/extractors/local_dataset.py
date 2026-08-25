"""Real scout.interface.Extractor implementation for
daf.adapters.local_dataset -- purely structural JSON parsing, no model,
no invented entities/relations.

Deliberately produces zero entities/relations: not every source needs to
populate the trust graph. `evidence.types.Observation.content` is
complete on its own as an open, extraction-defined mapping -- inventing
a generic "dataset_record" entity/relation here would be exactly the
scientific-ontology invention this DAF layer must avoid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Tuple

from evidence.types import Record
from scout.interface import ExtractionCandidate


class LocalDatasetExtractionError(ValueError):
    """Raised when a Record's raw_content is not the JSON object this
    extractor expects."""


@dataclass(frozen=True)
class LocalDatasetExtractor:
    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        try:
            content = json.loads(record.raw_content)
        except json.JSONDecodeError as exc:
            raise LocalDatasetExtractionError(f"record {record.id!r} is not valid JSON") from exc
        if not isinstance(content, dict):
            raise LocalDatasetExtractionError(f"record {record.id!r} is not a JSON object")

        return (
            ExtractionCandidate(
                content=content,
                entities=(),
                relations=(),
                extraction_method="json:local_dataset_v1",
                confidence=1.0,
            ),
        )
