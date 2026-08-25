"""Real scout.interface.Extractor implementation for
daf.adapters.usgs_earthquakes -- structural parsing of one real USGS
earthquake event-detail GeoJSON Feature only. Deliberately produces zero
entities/relations and no seismological ontology: this extractor proves
a real, mutable external record can become the existing SCOUT extraction
contract, not an earthquake-science taxonomy.

Format (confirmed against real fetched event-detail documents -- see the
adapter's own docstring): a single JSON object with top-level `id`,
`properties` (a flat dict including `mag`, `place`, `time`, `updated`,
`status`, `magType`), and `geometry.coordinates` (`[longitude, latitude,
depth_km]`). Unlike EDGAR's fixed-width text, this is already
structured JSON -- extraction here is projection, not parsing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Tuple

from evidence.types import Record
from scout.interface import ExtractionCandidate


class UsgsEarthquakeExtractionError(ValueError):
    """Raised when a Record's raw_content is not a parseable USGS
    event-detail GeoJSON Feature -- invalid JSON, or missing any of
    `id`/`properties.mag`/`properties.time`/`properties.updated`/
    `geometry.coordinates`."""


@dataclass(frozen=True)
class UsgsEarthquakeExtractor:
    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        try:
            feature = json.loads(record.raw_content)
        except json.JSONDecodeError as exc:
            raise UsgsEarthquakeExtractionError(f"record {record.id!r} is not valid JSON") from exc

        try:
            event_id = feature["id"]
            properties = feature["properties"]
            magnitude = properties["mag"]
            origin_time = properties["time"]
            updated = properties["updated"]
            coordinates = feature["geometry"]["coordinates"]
            longitude, latitude, depth_km = coordinates[0], coordinates[1], coordinates[2]
        except (KeyError, TypeError, IndexError) as exc:
            raise UsgsEarthquakeExtractionError(
                f"record {record.id!r} is missing a required USGS event-detail field: {exc}"
            ) from exc

        content = {
            "event_id": event_id,
            "magnitude": magnitude,
            "magnitude_type": properties.get("magType"),
            "place": properties.get("place"),
            "origin_time": origin_time,
            "updated": updated,
            "status": properties.get("status"),
            "longitude": longitude,
            "latitude": latitude,
            "depth_km": depth_km,
        }

        return (
            ExtractionCandidate(
                content=content,
                entities=(),
                relations=(),
                extraction_method="json:usgs_earthquake_v1",
                confidence=1.0,
            ),
        )
