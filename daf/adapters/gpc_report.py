"""Real scout.interface.SourceAdapter for a gel-permeation-chromatography
report: one RawDocument PER RUN, never per report.

WHY THE GRANULARITY IS HERE AND NOT IN THE EXTRACTOR.
`architecture/polymer_acquisition_readiness.yaml` names one irreversible
precondition -- "the extractor emits one Record per RUN and keeps the run
identifier out of content" -- and MEASURING the composition shows the
first half of that sentence cannot be discharged by an extractor at all.
`scout.pipeline.run_scout` builds exactly one Record per RawDocument
(`make_record(document_id=document.id, locator=raw_doc.locator,
raw_content=raw_doc.content)`), and `Extractor.extract` RECEIVES that one
Record; every candidate it returns names it. So an extractor handed one
Record per REPORT has no way to emit five Records, and every observation
it produces names the same run. `science.replicate_pairing` then reads
five values against one run and refuses with CONFLICTING_VALUE_FOR_A_RUN.

The obligation is real and its owner is the adapter. Written where a
future adapter author will be standing, because getting it wrong is the
one failure the readiness record says cannot be repaired after the data
exists.

RUN IDENTITY LIVES ON THE LOCATOR, NEVER IN CONTENT. The second half of
the precondition. `graph_dataset` already found this by measurement for
its own `id` field: an acquisition locator left in content flows into
`materials.analysis._comparison_context`, which treats every non-value
content key as part of the comparison context, so every run becomes its
own single-member group and nothing is ever comparable. Here the same
leak also takes `EVERY_RUN_DIFFERS_IN` out of `replicate_pairing`. So
`run_id` is stripped from the emitted payload and appears only in
`locator`, which is exactly where an acquisition identity belongs -- and
which is also what keeps two runs reporting the SAME number two distinct
Records rather than one (`make_document` hashes only source/content/
method, so identical runs collapse to one Document; `make_record` hashes
the locator too, so they stay two Records).

DATA PROVENANCE IS REQUIRED, NOT DEFAULTED. Every payload must declare
`data_provenance` from a closed vocabulary, and it is carried into
content. The fixtures in this repository are FABRICATED -- there is no
GPC instrument, no polymer and no acquisition anywhere in reach of it --
and this repository's own repeated finding is that a measured fact
recorded only in prose is bound to nothing. A label carried in content is
content-addressed with the numbers it labels, so fabricated figures
cannot enter the evidence pool wearing the same shape as measured ones.
Nothing is defaulted: a report that declares no provenance is refused
rather than assumed to be an instrument's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from scout.interface import RawDocument

from daf.storage.serialization import NonJsonConstantError, strict_json_loads

# Factored into daf.adapters._provenance when a second GPC source needed
# it: one adapter importing another is a coupling nothing reports, while
# two adapters that drift is a state a check can see. Re-exported here so
# existing callers and tests keep working.
from daf.adapters._provenance import (DATA_PROVENANCE_KINDS,  # noqa: F401
                                      FABRICATED_FIXTURE, INSTRUMENT_MEASUREMENT)

# Report-level keys copied onto every run's payload. `report_id` is
# deliberately NOT among them: like `run_id` it is an acquisition
# locator, and it is carried on `locator` instead.
_REPORT_KEYS = ("data_provenance", "sample_id", "sample_kind", "method", "conditions")


class GpcReportFetchError(RuntimeError):
    """The report file is missing, is not the JSON object this adapter
    expects, or declares runs it cannot identify."""


def _require(report: Mapping[str, Any], key: str, path: Path) -> Any:
    value = report.get(key)
    if value is None or value == "" or value == {}:
        raise GpcReportFetchError(
            f"{path} declares no non-empty {key!r}. Nothing is defaulted here: a GPC report "
            f"missing {key!r} is a report this adapter cannot describe honestly."
        )
    return value


#: The four fields a GPC report is required to supply and that a real one
#: does not carry as fields. Measured on ANCHOR 1 (EPA ChemView, TSCA
#: P-22-0051): removing any one of them from a faithful transcription is
#: refused individually, so the report cannot be acquired at all without
#: writing fields into it that it does not contain.
CALLER_DECLARABLE = ("data_provenance", "sample_id", "sample_kind", "method")

#: The extractor's word for a measured quantity, held here as a LITERAL
#: rather than imported. An adapter importing an extractor is a coupling
#: nothing reports -- the same argument that put DATA_PROVENANCE_KINDS in
#: daf.adapters._provenance -- and it would be a circular import besides.
#: tests/test_gpc_acquisition.py asserts the two copies agree, so a drift
#: is a failure rather than a silent divergence.
MEASURED_KIND = "measured"


@dataclass(frozen=True)
class GpcReportSourceAdapter:
    """One local GPC report file -> one RawDocument per run in it.

    THE FOUR DECLARABLE FIELDS ARE HERE BECAUSE A REAL REPORT FORCED
    THEM. This adapter was written first and required
    `data_provenance`, `sample_id`, `sample_kind` and `method` IN THE
    DOCUMENT. `daf/adapters/gpc_summary_export.py`, written second, takes
    them as caller declarations -- and the second one was right: no
    chromatography report states whether its own output is fabricated,
    or what kind of entity a sample is. The contract grew and never
    propagated back, which was invisible until a faithfully transcribed
    real report could not be acquired by any route that did not
    fabricate.

    DECLARING IS NOT DEFAULTING AND IT IS NOT OVERRIDING. A field the
    document states is taken from the document; a field it omits may be
    declared here; a field neither supplies is REFUSED. A field supplied
    by both is refused as a conflict rather than silently resolved --
    the acquirer must not overwrite what the document says, and if they
    disagree that is a fact somebody needs to see.

    `conditions` is deliberately NOT declarable. A caller supplying the
    measurement's own context would be inventing method provenance,
    which is the fabrication the whole path exists to refuse.
    """

    path: Path
    source_name: str
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock
    data_provenance: Optional[str] = None
    sample_id: Optional[str] = None
    sample_kind: Optional[str] = None
    method: Optional[str] = None
    #: OPT-IN, and off by default. When set, measurements the DOCUMENT
    #: declares with a kind other than `measured` are declined visibly
    #: and named in `not_acquired_because_not_measured`, the way
    #: gpc_summary_export.py declines a column its caller declares
    #: derived. Off, they are passed through and the extractor refuses
    #: the whole record -- which is the correct default, because an
    #: acquirer who has not thought about it should lose the record
    #: rather than silently drop part of it.
    decline_non_measured: bool = False

    def _declared(self) -> Tuple[str, ...]:
        return tuple(name for name in CALLER_DECLARABLE if getattr(self, name))

    def _resolve(self, report: Dict[str, Any]) -> Tuple[str, ...]:
        """Fill declarable fields the document omits, refuse a conflict,
        and return exactly which came from the acquirer."""
        declared: List[str] = []
        for name in CALLER_DECLARABLE:
            supplied = getattr(self, name)
            stated = report.get(name)
            has_stated = stated is not None and stated != "" and stated != {}
            if supplied and has_stated:
                raise GpcReportFetchError(
                    f"{self.path} states {name!r} and the acquirer also declares it. Refused "
                    "rather than resolved: the acquirer must not overwrite the document, and a "
                    "disagreement between them is a fact a consumer needs rather than one this "
                    "layer settles."
                )
            if supplied and not has_stated:
                report[name] = supplied
                declared.append(name)
        return tuple(declared)

    def fetch(self) -> Tuple[RawDocument, ...]:
        try:
            raw_text = self.path.read_text()
        except OSError as exc:
            raise GpcReportFetchError(f"could not read GPC report {self.path}: {exc}") from exc

        try:
            report = strict_json_loads(raw_text)
        except json.JSONDecodeError as exc:
            raise GpcReportFetchError(f"{self.path} is not valid JSON") from exc
        except NonJsonConstantError as exc:
            raise GpcReportFetchError(f"{self.path} is not valid JSON: {exc}") from exc
        if not isinstance(report, dict):
            raise GpcReportFetchError(f"{self.path} must contain a JSON object")

        declared = self._resolve(report)

        provenance = _require(report, "data_provenance", self.path)
        if provenance not in DATA_PROVENANCE_KINDS:
            raise GpcReportFetchError(
                f"{self.path} declares data_provenance {provenance!r}, which is not one of "
                f"{list(DATA_PROVENANCE_KINDS)}. It is refused rather than assumed: fabricated "
                "figures and instrument figures must not be indistinguishable in the pool."
            )
        for key in ("sample_id", "sample_kind", "method", "conditions"):
            _require(report, key, self.path)
        if not isinstance(report["conditions"], dict):
            raise GpcReportFetchError(f"{self.path} declares a non-object 'conditions'")

        report_id = _require(report, "report_id", self.path)
        runs = report.get("runs")
        if not isinstance(runs, list) or not runs:
            raise GpcReportFetchError(f"{self.path} must declare a non-empty 'runs' list")

        documents: List[RawDocument] = []
        seen: set = set()
        for run in runs:
            if not isinstance(run, dict) or not run.get("run_id"):
                raise GpcReportFetchError(f"{self.path} has a run with no 'run_id': {run!r}")
            run_id = run["run_id"]
            if run_id in seen:
                # Two runs sharing an id would share a locator, hence a
                # Record, hence an Observation -- silently merging two
                # measurements into one and understating the spread.
                raise GpcReportFetchError(
                    f"{self.path} declares run_id {run_id!r} twice; run identity must be unique "
                    "within a report or two runs collapse into one observation"
                )
            seen.add(run_id)

            payload: Dict[str, Any] = {key: report[key] for key in _REPORT_KEYS}
            # EMITTED EMPTY, NOT OMITTED. This source states every required
            # field in the document, so the acquirer declares none -- and
            # saying that explicitly is not the same as saying nothing.
            # Measured in WO-4: with the key absent, a source that stated
            # everything is indistinguishable from an adapter that forgot to
            # report what it declared, which is absence-as-signal and the
            # shape this pair files as a vacuous pass.
            payload["acquisition_declared"] = ",".join(declared)
            body = {k: v for k, v in run.items() if k != "run_id"}
            declined: Tuple[str, ...] = ()
            if self.decline_non_measured and isinstance(body.get("measurements"), list):
                kept, names = [], []
                for measurement in body["measurements"]:
                    if isinstance(measurement, dict) and measurement.get("kind") not in (
                            None, MEASURED_KIND):
                        names.append(str(measurement.get("variable")))
                    else:
                        kept.append(measurement)
                if not kept:
                    raise GpcReportFetchError(
                        f"{self.path} run {run_id!r} declares every measurement non-measured "
                        f"({sorted(names)!r}). Refused rather than acquired empty."
                    )
                body["measurements"] = kept
                declined = tuple(sorted(names))
            payload["not_acquired_because_not_measured"] = ",".join(declined)
            payload.update(body)
            documents.append(
                RawDocument(
                    source_name=self.source_name,
                    source_kind="instrument_report",
                    content=json.dumps(payload, sort_keys=True, allow_nan=False),
                    locator=f"{self.path}#{report_id}/{run_id}",
                    retrieval_method="file:gpc_report_v1",
                    retrieved_at=self.retrieved_at,
                )
            )
        return tuple(documents)
