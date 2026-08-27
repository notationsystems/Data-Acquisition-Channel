"""Real scout.interface.Extractor for one GPC run -- the first DAF
extractor that emits content shaped to reach the SCIENTIFIC gates rather
than only the structural ones.

WHAT MAKES THIS DIFFERENT FROM THE PASS-THROUGH EXTRACTORS.
`local_dataset` and `graph_dataset` are generic transports: they carry
whatever a record declares, uninterpreted, and that genericity is right
for sources that declare no measurement structure. A GPC report does
declare one. So this extractor is TYPED where those are generic -- it
requires a property, a unit, a method, non-empty conditions and an
uncertainty posture, and refuses a run that is missing any of them --
and it invents none of them. Every field it emits is a field the report
itself declared.

IT SATISFIES TWO GATES THAT WERE NEVER POINTED AT THE SAME CONTENT.
Measured during this build, not assumed:

  * `science.table.observation_is_table_alignable` requires `sample_id`
    and `variable`.
  * `science.admissibility.no_context_free_property` requires `property`
    and `method`.

Neither gate mentions the other's column key. The content in
`architecture/polymer_acquisition_readiness.yaml`'s own tests passes the
first and is REFUSED by the second with
`('MISSING_METHOD', 'MISSING_PROPERTY')`. Both gates are correct on their
own terms and nothing owns the relation between them, so this extractor
emits `variable` and `property` carrying the identical string, and
`method` beside them. That is duplication in content and it is recorded
as such rather than resolved here: reconciling two gates in the science
layer is not an acquisition extractor's decision to make. See the report
for this phase.

A DERIVED COLUMN IS REFUSED, NOT DROPPED. Real GPC reports carry
dispersity, which is Mw/Mn -- computed, not measured.
`architecture/evidence_class.yaml` maps `computed` onto
`evidence.types.DerivedValue`, and there is no path from `Extractor` to
DerivedValue: `extract` returns ExtractionCandidates, which
`run_scout` admits as Observations, which are the `measured` class. So
the only thing this extractor could do with a derived column is emit it
wearing the measured class, which would be false. Dropping it silently
would be the other failure -- the report would say something the pool
does not. It is refused, naming the key, so a caller who wants dispersity
knows it needs a computed path this repository has not built.

RUN IDENTITY IS ABSENT FROM CONTENT BY CONSTRUCTION, not by filtering
here: `daf.adapters.gpc_report` never puts it in the payload. This
extractor asserts that rather than trusting it -- a locator leaking into
content is the one acquisition failure the readiness record says cannot
be repaired afterwards, and it is silent in every layer that does not
look for it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

from evidence.types import Record
from scout.interface import ExtractedEntity, ExtractionCandidate

from daf.adapters.gpc_report import DATA_PROVENANCE_KINDS
from daf.extractors._passthrough import tighten_passthrough_content

EXTRACTION_METHOD = "gpc_report_v1"

# Names under which a GPC report reports Mw/Mn. Refused rather than
# emitted: it is computed evidence and this interface only makes
# measured evidence. Matched on the declared variable name, which is the
# only thing the report tells us about it.
DERIVED_VARIABLES = ("dispersity", "polydispersity_index", "pdi", "mw_over_mn", "molar_mass_dispersity")

# Keys an acquisition layer must never let into content -- they are
# locators, and a locator in content makes every run its own comparison
# group. Asserted here even though the adapter already excludes them,
# because the failure they cause is silent and unrepairable.
_LOCATOR_KEYS = ("run_id", "report_id", "id")


class GpcReportExtractionError(ValueError):
    """A GPC run declares something this extractor cannot carry
    honestly. Raised at extraction -- loud and early -- rather than
    admitted and left to mislead a consumer later."""


def _require_str(payload: Mapping[str, Any], key: str, record_id: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GpcReportExtractionError(
            f"record {record_id!r} has a missing or non-string {key!r}: {value!r}"
        )
    return value


def _measurement_content(
    measurement: Mapping[str, Any], payload: Mapping[str, Any], record_id: str
) -> Dict[str, Any]:
    if not isinstance(measurement, dict):
        raise GpcReportExtractionError(f"record {record_id!r} has a non-object measurement: {measurement!r}")

    variable = _require_str(measurement, "variable", record_id)
    if variable in DERIVED_VARIABLES:
        raise GpcReportExtractionError(
            f"record {record_id!r} declares {variable!r}, which is computed from other reported "
            "quantities rather than measured. This interface produces evidence.types.Observation, "
            "which architecture/evidence_class.yaml classes as `measured`; emitting a computed "
            "quantity through it would assign it the wrong class. It is refused rather than "
            "dropped so the omission is visible to the caller."
        )

    value = measurement.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GpcReportExtractionError(
            f"record {record_id!r} reports a non-numeric value for {variable!r}: {value!r}. "
            "If the intent is a missing measurement, state it with science/table.py's "
            "value_absence reasons rather than as a value."
        )

    uncertainty = measurement.get("uncertainty")
    if uncertainty is not None and (isinstance(uncertainty, bool) or not isinstance(uncertainty, (int, float))):
        raise GpcReportExtractionError(
            f"record {record_id!r} reports a non-numeric uncertainty for {variable!r}: {uncertainty!r}"
        )
    # PRESENCE is an acquisition concern; MEMBERSHIP is not. An earlier
    # draft of this module imported science.admissibility.UNCERTAINTY_KINDS
    # and checked the value against it, and the layer test caught it:
    # `daf` must not import `science`. The rule it was reaching for was
    # not missing, it was already owned -- quantity_is_typed returns
    # UNKNOWN_UNCERTAINTY_KIND for exactly this. So the vocabulary is
    # neither imported nor restated here (restating it would be a second
    # copy to drift), and the extractor asserts only what an acquisition
    # layer can know: that the report said something rather than nothing.
    kind = measurement.get("uncertainty_kind")
    if not isinstance(kind, str) or not kind:
        raise GpcReportExtractionError(
            f"record {record_id!r} declares no uncertainty posture for {variable!r}: {kind!r}. "
            "An explicit `absent` is declarable; silence is not. Whether the posture it names is a "
            "known one is science.admissibility's judgement, not this layer's."
        )

    content: Dict[str, Any] = {
        "sample_id": _require_str(payload, "sample_id", record_id),
        # Two column keys carrying one string. See this module's docstring:
        # `science.table` reads `variable`, `science.admissibility` reads
        # `property`, and nothing owns the relation between them.
        "variable": variable,
        "property": variable,
        "value": float(value),
        "unit": _require_str(measurement, "unit", record_id),
        "uncertainty": None if uncertainty is None else float(uncertainty),
        "uncertainty_kind": kind,
        "method": _require_str(payload, "method", record_id),
        "conditions": payload["conditions"],
        "data_provenance": payload["data_provenance"],
    }
    return tighten_passthrough_content(content, record_id)


@dataclass(frozen=True)
class GpcReportExtractor:
    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        try:
            payload = json.loads(record.raw_content)
        except json.JSONDecodeError as exc:
            raise GpcReportExtractionError(f"record {record.id!r} is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise GpcReportExtractionError(f"record {record.id!r} is not a JSON object")

        leaked = [key for key in _LOCATOR_KEYS if key in payload]
        if leaked:
            raise GpcReportExtractionError(
                f"record {record.id!r} carries acquisition locator(s) {leaked!r} in its payload. "
                "Left in content they make every run its own comparison group, so a replicate set "
                "reports TOO_FEW_RUNS_FOR_A_COVARIANCE and is indistinguishable from a pool holding "
                "one run. The run identity belongs on Record.locator."
            )

        provenance = payload.get("data_provenance")
        if provenance not in DATA_PROVENANCE_KINDS:
            raise GpcReportExtractionError(
                f"record {record.id!r} declares data_provenance {provenance!r}, which is not one of "
                f"{list(DATA_PROVENANCE_KINDS)}. Unlabelled figures are refused: fabricated and "
                "measured numbers must not be indistinguishable once they are in the pool."
            )

        conditions = payload.get("conditions")
        if not isinstance(conditions, Mapping) or not conditions:
            raise GpcReportExtractionError(
                f"record {record.id!r} declares no non-empty 'conditions'. An empty conditions "
                "mapping asserts the measurement was condition-independent, which a GPC run is not."
            )

        measurements = payload.get("measurements")
        if not isinstance(measurements, list) or not measurements:
            raise GpcReportExtractionError(
                f"record {record.id!r} must declare a non-empty 'measurements' list"
            )

        # The sample identity the report itself declares, transported as
        # a referent so acquired evidence is reachable from `materials`
        # at all -- the defect `graph_dataset` was built to fix. `kind`
        # is the report's own word; this module neither supplies nor
        # interprets it.
        entities = (
            ExtractedEntity(
                label=_require_str(payload, "sample_id", record.id),
                kind=_require_str(payload, "sample_kind", record.id),
            ),
        )

        candidates: List[ExtractionCandidate] = []
        for measurement in measurements:
            candidates.append(
                ExtractionCandidate(
                    content=_measurement_content(measurement, payload, record.id),
                    entities=entities,
                    relations=(),
                    extraction_method=EXTRACTION_METHOD,
                    confidence=1.0,
                )
            )
        return tuple(candidates)
