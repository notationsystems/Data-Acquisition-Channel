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
from typing import Any, Dict, List, Mapping, Tuple

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


@dataclass(frozen=True)
class GpcReportSourceAdapter:
    """One local GPC report file -> one RawDocument per run in it."""

    path: Path
    source_name: str
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock

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
            payload["acquisition_declared"] = ""
            payload.update({k: v for k, v in run.items() if k != "run_id"})
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
