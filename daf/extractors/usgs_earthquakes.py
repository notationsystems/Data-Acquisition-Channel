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

PHASE 31 -- PROPERTY/METHOD/UNIT KEYS, ADDITIVE. `property`, `value`,
`unit` and `method` are new content keys, added alongside every existing
one (`magnitude`, `magnitude_type`, ... are all still here, unchanged).
This is an identity-changing addition -- `Observation.content` differs,
so `Observation.id` differs from every prior phase's USGS acquisition --
disclosed rather than hidden (docs/PHASE_31_USGS_METHOD_PROVENANCE_AND_QUANTITY_SEMANTICS.md
§Identity). It is safe to make here because nothing in this repository
persists evidence between runs (`architecture/invariants.yaml` migration:
0 committed records) and because a USGS Observation has always emitted
`entities=(), relations=()`, so it has never been reachable through
`retrieval.engine`/`materials.analysis` -- no existing comparison-context
behavior (Phase 17's NOAA incomparability argument) exists for this
source to disturb.

`property`/`method` are chosen by real reconnaissance, not assumption
(`architecture/method_provenance_reachability.yaml`), which Phase 30
already answered for `magnitude_type` alone:

  property = "earthquake_magnitude" -- descriptive, not an invented
             ontology term; matches the naming style of every other
             DAF property ("water_level", "tensile_strength").
  value    = the SAME number as `magnitude` (never a second fact --
             both keys are set from the one Python variable below).
  unit     = "dimensionless", the true physical fact about a
             seismic-magnitude scale, which is logarithmic and carries no
             physical dimension by international convention (SI itself
             recognises "1" as a genuine unit for dimensionless
             quantities) -- not a placeholder invented to pass the gate.
  method   = verbatim `magnitude_type` (e.g. "mb"), because USGS's own
             data model already separates WHICH NUMBER (`mag`) from HOW
             IT WAS COMPUTED (`magType`) -- the same method/value split
             `science.admissibility.no_context_free_property` requires.
             `None` when the source itself supplies no magType, so an
             event genuinely missing one is refused (`MISSING_METHOD`),
             never defaulted.

WHAT IS DELIBERATELY NOT ADDED. No `conditions` key: the fields this
extractor can supply (`place`/`origin_time`/`depth_km`) identify WHICH
EVENT this is, not a measurement CONDITION a second measurement of the
same quantity could vary by, and `status` (automatic/reviewed) is
revision/QC metadata -- the exact category Phase 17 excluded from NOAA
content (`q`) for the same reason: a later, reviewed revision of the
same event must stay comparable to its own earlier automatic reading,
not be silently split into a different context. No `uncertainty_kind`
key either: no fixture or documented field in this repository's USGS
acquisition carries a magnitude error/confidence value. Both remain
genuinely `MISSING_*`, on their own evidence, not invented to close the
gap `magnitude_type` opened for `method`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Tuple

from evidence.types import Record
from scout.interface import ExtractionCandidate

PROPERTY = "earthquake_magnitude"
# A seismic magnitude scale is logarithmic and carries no physical
# dimension by international convention -- this is the true unit,
# not a placeholder. See the module docstring.
DIMENSIONLESS_UNIT = "dimensionless"


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

        magnitude_type = properties.get("magType")
        content = {
            "event_id": event_id,
            "magnitude": magnitude,
            "magnitude_type": magnitude_type,
            "place": properties.get("place"),
            "origin_time": origin_time,
            "updated": updated,
            "status": properties.get("status"),
            "longitude": longitude,
            "latitude": latitude,
            "depth_km": depth_km,
            # Phase 31: property-admissibility keys, additive -- see the
            # module docstring for why each value is what it is, and why
            # `conditions`/`uncertainty_kind` are deliberately absent.
            "property": PROPERTY,
            "value": magnitude,
            "unit": DIMENSIONLESS_UNIT,
            "method": magnitude_type,
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
