"""Real scout.interface.Extractor for datasets whose records DECLARE
their own trust-graph structure -- the first DAF extractor to populate
`ExtractionCandidate.entities`/`.relations` rather than leaving both
empty.

WHY THIS EXISTS (Phase P's identified frontier). Every other DAF
extractor (`local_dataset`, `noaa_water_level`, `usgs_earthquakes`,
`edgar_daily_index`, `arxiv`) deliberately emits `entities=()`,
`relations=()`. That is correct for those sources -- none of them
declares what its records are ABOUT in any structural way, and inventing
entities for them would be exactly the scientific-ontology invention the
DAF layer must avoid. But it has a consequence that went unnoticed until
it was measured: evidence acquired through DAF lands in the pool with no
referents and no relationships, so
`materials.analysis`/`materials.iteration` cannot reach it at all --
`reevaluate_program` raises `KeyError: no Referent with natural_key ...`.
Every scientific analysis in this repository's phases M/N/O therefore ran
on hand-built fixture evidence, never on anything DAF actually acquired.

`scout.pipeline.run_scout` has always supported the missing half: it
already turns each `ExtractedEntity` into an admitted `Referent`
(`natural_key=entity.label`, `kind=entity.kind`) and each
`ExtractedRelation` into an admitted `ClaimedRelationship`, resolving
endpoints by label. No DAF extractor had ever used it. This module is
that use -- no new admission path, no new evidence type, no change to
SCOUT.

STRUCTURAL TRANSPORT, NOT DOMAIN LOGIC. This extractor knows nothing
about materials, formulations, processes, properties, or measurements,
and deliberately does not require any of them. It transports a subgraph
the SOURCE RECORD ITSELF declares:

    {
      "id": "ts-001",
      "property": "tensile_strength",     <-- content, passed through verbatim
      "value": 78,                        <-- content, passed through verbatim
      "unit": "MPa",                      <-- content, passed through verbatim
      "entities":  [{"label": "formulation-f1",   "kind": "formulation"},
                    {"label": "process-std-190c", "kind": "process"}],
      "relations": [{"from": "formulation-f1", "to": "process-std-190c",
                     "type": "tested_during"}]
    }

`entities`/`relations` are consumed as structure; EVERY other key is
passed through into `Observation.content` unmodified, exactly as
`LocalDatasetExtractor` already does. The labels, kinds and relation
types are the source's own vocabulary -- this module neither supplies,
validates, defaults, nor interprets them. Whether a record is
scientifically USABLE (carries a numeric `value`, names a property a
criterion cares about) is not this extractor's judgment to make: that
determination already belongs to `materials.analysis`, which reads
`content` and decides for itself. Requiring a `property`/`value` pair
here would be precisely the domain assumption this layer must not
encode, so it is not required.

FAILS LOUDLY, NEVER SILENTLY. A record that declares no `entities` key,
declares one malformed, or names a relation endpoint that is not among
its own declared labels, raises `GraphDatasetExtractionError`. The
endpoint check duplicates one `run_scout` also performs, deliberately:
catching it here names the offending record and locator, where a caller
can act on it, rather than surfacing as a pipeline admission failure
several stages later.

PASS-THROUGH IS VERBATIM BUT NOT UNCONDITIONAL. Every non-structural key
is still carried uninterpreted, but two shapes are no longer carried
silently: a non-finite number (a sentinel absence, which `json.loads`
accepts as bare `NaN`/`Infinity`) is refused, and a dict-valued entry is
frozen into the hashable representation Phase 34 imposed at the read
boundary. The second closes the write-side asymmetry Phase 35 measured
and deliberately left open -- a `conditions` mapping declared here used
to raise `TypeError: unhashable type: 'dict'` in `materials.analysis`
in-process, repaired only by a restart. See `daf.extractors._passthrough`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

from daf.extractors._passthrough import tighten_passthrough_content
from evidence.types import Record
from scout.interface import ExtractedEntity, ExtractedRelation, ExtractionCandidate

# Consumed as structure, never passed through into Observation.content.
#
# `id` is in this list for a reason found by MEASURING the composition, not
# by reading the code. It is the paired adapter's REQUIRED acquisition
# locator (`LocalDatasetSourceAdapter` builds `locator=f"{path}#{record['id']}"`
# from it), so it is present on every record and unique to every record.
# Left in `content`, it flows into `materials.analysis._comparison_context`
# -- which by deliberate Phase 53 design treats EVERY non-value content key
# as part of an observation's comparison context -- and the consequence is
# that no two acquired measurements are ever comparable to each other: each
# lands in its own single-member ComparisonGroup and the property's status
# comes back INCOMPARABLE, forever, no matter how much evidence is acquired.
#
# That is an acquisition concern silently corrupting scientific semantics,
# and the fix belongs here rather than in `materials`: SCOUT is right not to
# guess which content keys are incidental, and DAF is the layer that knows
# `id` is its own locator. Nothing is lost by dropping it -- the acquisition
# identity is fully preserved on `Record.locator`, which is exactly where an
# acquisition identity belongs.
STRUCTURAL_KEYS = ("entities", "relations", "id")


class GraphDatasetExtractionError(ValueError):
    """Raised when a Record's raw_content is not a JSON object declaring
    a well-formed `entities` list (and, if present, a `relations` list
    whose endpoints are all among the declared entity labels)."""


def _require_str(value: Any, field: str, record_id: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphDatasetExtractionError(
            f"record {record_id!r} has a non-string or empty {field!r}: {value!r}"
        )
    return value


def _parse_entities(payload: Mapping[str, Any], record_id: str) -> Tuple[ExtractedEntity, ...]:
    raw = payload.get("entities")
    if not isinstance(raw, list) or not raw:
        raise GraphDatasetExtractionError(
            f"record {record_id!r} must declare a non-empty 'entities' list; got {raw!r}"
        )
    entities: List[ExtractedEntity] = []
    for item in raw:
        if not isinstance(item, dict):
            raise GraphDatasetExtractionError(f"record {record_id!r} has a non-object entity: {item!r}")
        entities.append(
            ExtractedEntity(
                label=_require_str(item.get("label"), "entity label", record_id),
                kind=_require_str(item.get("kind"), "entity kind", record_id),
            )
        )
    return tuple(entities)


def _parse_relations(
    payload: Mapping[str, Any], entities: Tuple[ExtractedEntity, ...], record_id: str
) -> Tuple[ExtractedRelation, ...]:
    raw = payload.get("relations", [])
    if not isinstance(raw, list):
        raise GraphDatasetExtractionError(f"record {record_id!r} has a non-list 'relations': {raw!r}")

    declared = {entity.label for entity in entities}
    relations: List[ExtractedRelation] = []
    for item in raw:
        if not isinstance(item, dict):
            raise GraphDatasetExtractionError(f"record {record_id!r} has a non-object relation: {item!r}")
        from_label = _require_str(item.get("from"), "relation 'from'", record_id)
        to_label = _require_str(item.get("to"), "relation 'to'", record_id)
        for endpoint in (from_label, to_label):
            if endpoint not in declared:
                raise GraphDatasetExtractionError(
                    f"record {record_id!r} declares a relation endpoint {endpoint!r} that is not among "
                    f"its own declared entity labels {sorted(declared)!r}"
                )
        relations.append(
            ExtractedRelation(
                from_label=from_label, to_label=to_label,
                type=_require_str(item.get("type"), "relation 'type'", record_id),
            )
        )
    return tuple(relations)


@dataclass(frozen=True)
class GraphDatasetExtractor:
    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        try:
            payload = json.loads(record.raw_content)
        except json.JSONDecodeError as exc:
            raise GraphDatasetExtractionError(f"record {record.id!r} is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise GraphDatasetExtractionError(f"record {record.id!r} is not a JSON object")

        entities = _parse_entities(payload, record.id)
        relations = _parse_relations(payload, entities, record.id)

        # Everything that is not declared graph structure is observation
        # content, passed through verbatim and uninterpreted.
        content: Dict[str, Any] = tighten_passthrough_content(
            {k: v for k, v in payload.items() if k not in STRUCTURAL_KEYS}, record.id
        )

        return (
            ExtractionCandidate(
                content=content,
                entities=entities,
                relations=relations,
                extraction_method="json:graph_dataset_v1",
                confidence=1.0,
            ),
        )
