"""Real scout.interface.Extractor implementation for
daf.adapters.noaa_water_level -- structural parsing of one real NOAA
CO-OPS windowed water-level response only. Deliberately produces zero
entities/relations and no oceanographic ontology: this extractor proves
a real, revisable, per-window (not per-reading) external artifact can
become the existing SCOUT extraction contract.

Format (confirmed against a real fetched window -- see the adapter's
own docstring): a JSON object with `metadata` (station id/name/lat/lon)
and `data` (a list of readings, each `{t, v, s, f, q}` -- time, value,
sigma, flags, quality). `q` is `"p"` (preliminary) or `"v"` (verified) --
this extractor counts both, never discards one in favor of the other,
since a window legitimately mixes them during NOAA's rolling QC process.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from evidence.types import Record
from scout.interface import ExtractionCandidate


class NoaaWaterLevelExtractionError(ValueError):
    """Raised when a Record's raw_content is not a parseable NOAA
    windowed water-level response -- invalid JSON, or missing the
    top-level `metadata`/`data` keys, or a reading missing `t`/`v`/`q`."""


@dataclass(frozen=True)
class NoaaWaterLevelExtractor:
    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        try:
            payload = json.loads(record.raw_content)
        except json.JSONDecodeError as exc:
            raise NoaaWaterLevelExtractionError(f"record {record.id!r} is not valid JSON") from exc

        if not isinstance(payload, dict) or "metadata" not in payload or "data" not in payload:
            raise NoaaWaterLevelExtractionError(
                f"record {record.id!r} is missing the required 'metadata'/'data' top-level keys"
            )

        metadata = payload["metadata"]
        readings: List[Dict[str, Any]] = []
        quality_counts: Dict[str, int] = {}
        for row in payload["data"]:
            try:
                time_str, value, quality = row["t"], row["v"], row["q"]
            except (KeyError, TypeError) as exc:
                raise NoaaWaterLevelExtractionError(
                    f"record {record.id!r} has a reading missing t/v/q: {row!r}"
                ) from exc
            readings.append(
                {"time": time_str, "value": value, "sigma": row.get("s"), "flags": row.get("f"), "quality": quality}
            )
            quality_counts[quality] = quality_counts.get(quality, 0) + 1

        content = {
            "station_id": metadata.get("id"),
            "station_name": metadata.get("name"),
            "reading_count": len(readings),
            "quality_counts": quality_counts,
            "readings": readings,
        }

        return (
            ExtractionCandidate(
                content=content,
                entities=(),
                relations=(),
                extraction_method="json:noaa_water_level_v1",
                confidence=1.0,
            ),
        )
