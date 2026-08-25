"""Per-measurement, graph-declaring extractor for NOAA CO-OPS water
level -- the first DAF extractor to carry a REAL external scientific
measurement all the way to `materials.analysis`.

RELATIONSHIP TO THE EXISTING NOAA EXTRACTOR. `daf.extractors.noaa_water_level`
already parses this exact response, but produces ONE Observation per
WINDOW whose content holds a `readings` list. Phase M measured the
consequence: `materials.model_state.update`/`materials.analysis` read a
scalar `content["value"]`, and a window-shaped observation has none, so
that extractor's output stops at the evidence boundary. Both extractors
are correct for different questions and both are kept: the window one
answers "what did this acquisition window contain", this one answers
"what individual measurements were made". Neither is a replacement for
the other, and this module does not modify it.

FIELD CLASSIFICATION (Phase 17 sec.3), decided by reading a real
response rather than the API docs alone. A real reading is
`{"t": "2024-01-15 00:00", "v": "0.136", "s": "0.006",
  "f": "0,0,0,0", "q": "v"}`:

  SCIENTIFIC CONTENT
    v  -> `value`, parsed to float. NOAA returns numeric strings;
          `materials.analysis._as_float` ASSERTS a numeric type rather
          than coercing, so parsing here is required, and it is faithful
          parsing of a numeric literal, not interpretation.
    s  -> `sigma`, the standard deviation of the 1-second samples behind
          the reading. Genuinely scientific, kept.

  SCIENTIFIC CONTEXT (conditioning variables -- what would have to match
  for two readings to be measurements OF THE SAME THING)
    t         -> `measurement_time`. See the note below; this is the
                 single most consequential classification in the module.
    datum     -> `datum`. A water level is meaningless without one; MLLW
                 and STND readings are not comparable quantities.
    units     -> `unit`. Supplied as the request's own parameter.
    station   -> `station_id`, so readings from different stations are
                 never silently pooled.

  SOURCE IDENTITY / GRAPH STRUCTURE (never content)
    metadata.id/name/lat/lon -> the station referent.

  ACQUISITION METADATA (never content)
    f (QC flag vector), the request URL, the window bounds, `product`,
    `application`, `time_zone`, `format`.

  REVISION METADATA (never content)
    q -> "p" (preliminary) or "v" (verified). Deliberately EXCLUDED from
         content, and that exclusion is load-bearing: NOAA revises
         preliminary readings into verified ones for the SAME timestamp.
         Were `q` part of content it would become part of the comparison
         context, and a preliminary reading and its own later verified
         correction would land in DIFFERENT comparison groups -- so the
         architecture could never see that they disagree. Excluding it
         means they share a context and a genuine conflict is reported,
         which is the scientifically correct outcome. The flag is not
         lost: it remains in the durably stored raw artifact.

WHY `measurement_time` IS CONTENT, THOUGH IT MAKES EVERY READING
INCOMPARABLE. Phase 16 removed the acquisition locator `id` from content
because a field unique to each record makes every observation its own
single-member comparison group, so nothing is ever comparable. `t` is
also unique per reading and has exactly that mechanical effect -- but the
opposite classification is correct here, and the difference is the whole
point of the Phase 16 invariant. `id` was an ACQUISITION identifier: two
records with different ids could still be measurements of the same
quantity, so letting it split the context was a defect. `t` is a
SCIENTIFIC conditioning variable: a water level at 00:00 and one at 00:06
are measurements of genuinely DIFFERENT quantities, and reporting them as
disagreeing measurements of one quantity would be a misrepresentation of
the physics. The resulting `INCOMPARABLE` status is therefore the correct
answer, not a defect -- a tide gauge series is not a set of repeated
measurements. See docs/PHASE_17_LIVE_SCIENTIFIC_OBSERVATION.md for the
full argument and for what this implies about the analysis layer's
applicability to time series.

GRAPH DECLARATION (sec.5), deliberately minimal. Two entities the source
itself establishes -- the station (`metadata.id`, explicitly identified
in every response) and the vertical datum every value in the response is
referenced to -- joined by one relation, `referenced_to`. Because each
relation carries its own `observation_id`, that relation asserts exactly
"this water-level observation, taken at this station, is referenced to
this datum", which is precisely what the CO-OPS API establishes and
nothing more. Richer structures were considered and rejected as
fabrication: no sensor entity (the response never identifies a sensor),
no location entity (lat/lon describe the station, and inventing a
`located_at` place referent would assert a spatial ontology the source
does not supply), and no relation between successive readings (the source
asserts no such link). One relation per reading is also the minimum for
reachability -- `retrieval.engine` reaches observations only through
relationships, so an entity-only declaration would leave the evidence
admitted but invisible to analysis.

PHASE 32 -- `uncertainty`/`uncertainty_kind`, ADDITIVE, SIGMA-CONDITIONAL.
Added only for a reading that actually carries `s`, exactly mirroring
the existing `if sigma is not None` guard -- a reading NOAA does not
report `s` for gets neither key, and remains genuinely
`MISSING_UNCERTAINTY_KIND`, never defaulted.

SOURCE SEMANTICS, established by real reconnaissance (this module's own
Phase 17 investigation), not inferred from the field name `sigma`: CO-OPS
6-minute water-level products are computed by averaging the underlying
1-second (or comparable high-frequency) samples collected within that
interval, and `s` is the standard deviation of exactly those samples --
a dispersion statistic about the samples the reported value was computed
from, directly reported by the source alongside that value. This is
`uncertainty_kind = "stated"`: the source itself supplies the number, so
it is neither DAF's estimate, a propagated combination of other
uncertainties, nor an explicit declaration of no error (`"absent"` would
assert the opposite of what `s` says). `uncertainty` is `sigma` itself,
unmodified -- same value, same unit as `value` (a standard deviation of a
quantity is expressed in that quantity's own unit; this is a property of
what a standard deviation IS, not a claim invented for this module).

WHAT THIS DOES NOT RESOLVE. `method` is untouched and still absent: CO-OPS
does not report, per reading, which sensor or algorithm produced a value
-- inventing "tide gauge" would be exactly the fabrication Phase 29
already rejected for this same extractor. `conditions` is untouched for
the same reason Phase 29 left it untouched: reshaping `datum`/`station_id`/
`measurement_time` into a nested `conditions` mapping is a materially
different, larger content-shape decision than adding two new keys, and
this phase's scope is uncertainty alone -- solving it must not be allowed
to silently solve, or appear to solve, either of the other two.

IDENTITY AND COMPARABILITY, MEASURED, NOT ASSUMED. Adding `uncertainty`/
`uncertainty_kind` changes `Observation.content`, and therefore
`Observation.id`, for every reading that carries `s` -- disclosed, not
concealed (see docs/PHASE_32_NOAA_UNCERTAINTY_PROVENANCE.md). Unlike
Phase 29's decision not to touch this same extractor, this addition does
NOT touch `datum`/`station_id`/`measurement_time` -- the keys Phase 17's
own INCOMPARABLE finding rests on -- and cannot change that finding:
`materials.analysis._comparison_context` already treated the (per-reading
varying) `sigma` key as part of every reading's comparison context before
this phase, via `measurement_time` alone every reading was already its
own singleton group, and adding two more keys to an already-maximally-
fragmented context changes nothing about whether any two readings compare
-- verified against the real test suite, not merely reasoned about.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from evidence.types import Record
from scout.interface import ExtractedEntity, ExtractedRelation, ExtractionCandidate

PROPERTY = "water_level"
STATION_KIND = "monitoring_station"
DATUM_KIND = "vertical_datum"
REFERENCED_TO = "referenced_to"

# NOAA's `units` request parameter -> the symbol the returned values carry.
# The response body does NOT echo the unit, so it can only come from what
# was requested; the binding therefore parameterises adapter and extractor
# together so the two can never disagree.
UNIT_SYMBOLS = {"metric": "m", "english": "ft"}

# `sigma` is a standard deviation the source states directly -- not DAF's
# estimate, not a propagated combination, and not a declaration of no
# error. See the module docstring's "PHASE 32" section for why this is
# the one uncertainty_kind that is true here, and no other.
SIGMA_UNCERTAINTY_KIND = "stated"


class NoaaMeasurementExtractionError(ValueError):
    """Raised when a Record's raw_content is not a parseable NOAA CO-OPS
    water-level response, or a reading is missing `t`/`v`, or a value is
    not a parseable number."""


def _float(value: Any, field: str, record_id: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise NoaaMeasurementExtractionError(
            f"record {record_id!r} has a non-numeric {field!r}: {value!r}"
        ) from exc


def _optional_float(value: Any, field: str, record_id: str) -> Optional[float]:
    if value is None or value == "":
        return None
    return _float(value, field, record_id)


@dataclass(frozen=True)
class NoaaWaterLevelMeasurementExtractor:
    """`datum`/`units` are the request parameters the paired adapter
    actually sent -- not defaults invented here. See the module docstring
    for why the response cannot supply them."""

    datum: str
    units: str

    def _unit_symbol(self) -> str:
        try:
            return UNIT_SYMBOLS[self.units]
        except KeyError:
            raise NoaaMeasurementExtractionError(
                f"unknown NOAA units {self.units!r}; expected one of {sorted(UNIT_SYMBOLS)}"
            ) from None

    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        try:
            payload = json.loads(record.raw_content)
        except json.JSONDecodeError as exc:
            raise NoaaMeasurementExtractionError(f"record {record.id!r} is not valid JSON") from exc
        if not isinstance(payload, dict) or "metadata" not in payload or "data" not in payload:
            raise NoaaMeasurementExtractionError(
                f"record {record.id!r} is missing the required 'metadata'/'data' top-level keys"
            )

        metadata: Mapping[str, Any] = payload["metadata"]
        station_id = metadata.get("id")
        if not isinstance(station_id, str) or not station_id:
            raise NoaaMeasurementExtractionError(
                f"record {record.id!r} has no usable station id in metadata: {metadata!r}"
            )

        unit_symbol = self._unit_symbol()
        entities = (
            ExtractedEntity(label=station_id, kind=STATION_KIND),
            ExtractedEntity(label=self.datum, kind=DATUM_KIND),
        )
        relations = (
            ExtractedRelation(from_label=station_id, to_label=self.datum, type=REFERENCED_TO),
        )

        candidates: List[ExtractionCandidate] = []
        for row in payload["data"]:
            if not isinstance(row, dict) or "t" not in row or "v" not in row:
                raise NoaaMeasurementExtractionError(
                    f"record {record.id!r} has a reading missing 't'/'v': {row!r}"
                )
            content: Dict[str, Any] = {
                "property": PROPERTY,
                "value": _float(row["v"], "v", record.id),
                "unit": unit_symbol,
                "datum": self.datum,
                "station_id": station_id,
                "measurement_time": row["t"],
            }
            sigma = _optional_float(row.get("s"), "s", record.id)
            if sigma is not None:
                content["sigma"] = sigma
                # Same value, same unit as `value` -- a standard
                # deviation is expressed in the quantity's own unit.
                # Never added when the source omits `s`: that reading
                # stays genuinely MISSING_UNCERTAINTY_KIND.
                content["uncertainty"] = sigma
                content["uncertainty_kind"] = SIGMA_UNCERTAINTY_KIND

            candidates.append(
                ExtractionCandidate(
                    content=content, entities=entities, relations=relations,
                    extraction_method="json:noaa_water_level_measurement_v1", confidence=1.0,
                )
            )
        return tuple(candidates)
