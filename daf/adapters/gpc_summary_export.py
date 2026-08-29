"""Real scout.interface.SourceAdapter for a vendor SEC/GPC software
summary export -- the CSV-with-a-free-text-header shape chromatography
software actually writes.

THE POINT OF THIS ADAPTER IS NOT A SECOND SOURCE. It is a test of whether
the acquisition contract derived from the first GPC fixture is a contract
or a description of that fixture. One extractor against one fixture,
both written by the same author from the same reading, reproduces the
misreading and agrees with itself. Predictions were recorded in
architecture/gpc_second_source_preregistration.yaml BEFORE this file
existed.

WHAT DIFFERS STRUCTURALLY. Replicates are ROWS rather than documents;
several samples share one file; columns are ordered and named only by the
file's own header line; Mw and PDI are reported and Mn is NOT; there is
no uncertainty column at all; and the conditions are a free-text header
block rather than fields.

FOUR THINGS THIS SOURCE CANNOT STATE, AND THEY ARE THE FINDING.
`data_provenance`, `sample_kind`, `method` and `unit` are all required
downstream and none of them appears in a vendor export. No chromatography
software writes a field saying whether its own output is fabricated, or
what kind of entity a sample is, or -- in a summary table whose columns
are `Mw` and `PDI` -- what unit a molar mass is in.

They are therefore CALLER-DECLARED, and the content says so: every
observation carries `acquisition_declared` naming exactly which of its
fields came from the acquirer rather than from the document. That is the
difference between DECLARING and FABRICATING. Fabricating is writing
`g/mol` into content as though the file had said it. Declaring is the
acquirer stating what they know, marked so a consumer can tell the two
apart and discount accordingly. Nothing is defaulted: an adapter given
none of them refuses.

THE CONDITIONS ARE CARRIED VERBATIM AND NOT PARSED. The header says
`Temp: 35 C`. Turning that into {"column_temperature_c": 35.0} invents a
field name, a unit and a numeric type the source stated as none of those,
and it is the single most tempting move this source offers. The
pre-registration named it as the FAILURE condition rather than the fix:
if anything is found parsed out of that block, the prediction failed and
the contract did not. So the block is one condition, verbatim, under one
identifier key -- which fabricates nothing and costs comparability with
the first source, a cost recorded rather than repaired.

NO EXTRACTOR OF ITS OWN. This adapter normalizes into the payload shape
`daf.extractors.gpc_report.GpcReportExtractor` already reads, and that
extractor is reused UNCHANGED. Extraction is where the contract lives and
acquisition is where the source shape lives; if the second source had
needed its own extractor, the contract would have been the first
fixture's shape wearing a general name. Two adapters that drift is a
detectable state; one extractor with two modes is a silent one.
"""

from __future__ import annotations

import json
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from scout.interface import RawDocument

from daf.adapters._provenance import DATA_PROVENANCE_KINDS

#: Columns this adapter knows are not measured quantities. `Sample` and
#: `Inj` are identity; `Area` is an instrument response, not a property of
#: the material, and emitting it as one would be this layer inventing a
#: scientific claim.
_IDENTITY_COLUMNS = ("Sample", "Inj")
_NON_QUANTITY_COLUMNS = ("Area",)

#: The verbatim header block travels under one identifier key. Named for
#: what it IS -- text as the report stated it -- so nothing downstream
#: mistakes it for parsed conditions.
CONDITIONS_AS_REPORTED = "report_header_as_reported"


class GpcSummaryExportFetchError(RuntimeError):
    """The export is missing, malformed, or is missing something this
    adapter refuses to supply on its own."""


@dataclass(frozen=True)
class GpcSummaryExportSourceAdapter:
    """One vendor summary export -> one RawDocument per ROW.

    `data_provenance`, `sample_kind`, `method` and `unit_by_column` are
    caller-declared because the document cannot state them. Every one is
    required; none is defaulted.
    """

    path: Path
    source_name: str
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock
    data_provenance: str
    sample_kind: str
    method: str
    unit_by_column: Dict[str, str]
    #: measured | derived, per quantity column. The export states this
    #: nowhere -- `Mw` and `PDI` are both bare column names -- and DAQ
    #: cannot tell them apart from a header. Declared, refused if absent,
    #: and never assumed: assuming `measured` is precisely the error this
    #: source exposed in the extractor's name-based denylist.
    kind_by_column: Dict[str, str]
    #: quantity column -> the column carrying its status flag, when the
    #: export has one. A flag column is an ANNOTATION, not a quantity, and
    #: the file does not say which is which.
    flag_by_column: Dict[str, str] = dataclasses.field(default_factory=dict)
    #: the source's own flag vocabulary -> science/table.py's absence
    #: reasons. CALLER-DECLARED, and refused when a flag is unmapped.
    #:
    #: DAQ does not choose this mapping. `DETECTOR_SATURATED` means
    #: `above_range` in this vendor's vocabulary and might mean something
    #: else in another's; picking one here would be DAQ asserting a
    #: semantics the file did not state. An unmapped flag stops the
    #: acquisition rather than defaulting to `not_measured`, because
    #: defaulting would be inventing the reason -- and the absence
    #: vocabulary exists precisely so a reason is never guessed.
    absence_reason_by_flag: Dict[str, str] = dataclasses.field(default_factory=dict)
    #: flags that mean "this is a real measurement".
    measured_flags: Tuple[str, ...] = ("OK",)

    def _declared(self) -> Tuple[str, ...]:
        return ("data_provenance", "measurement_kind", "method", "sample_kind", "unit")

    def _check_declarations(self) -> None:
        if self.data_provenance not in DATA_PROVENANCE_KINDS:
            raise GpcSummaryExportFetchError(
                f"data_provenance {self.data_provenance!r} is not one of "
                f"{list(DATA_PROVENANCE_KINDS)}. A vendor export cannot state it, so the acquirer "
                "must -- and refusing is the alternative, not assuming."
            )
        for name, value in (("sample_kind", self.sample_kind), ("method", self.method)):
            if not isinstance(value, str) or not value:
                raise GpcSummaryExportFetchError(
                    f"{name} must be declared by the caller; this source does not state it"
                )
        if not self.kind_by_column:
            raise GpcSummaryExportFetchError(
                "kind_by_column must be declared: the export does not say which of its columns are "
                "measured and which are computed from the others, and reading that off a column "
                "name is what let a derived quantity into the pool as `measured`"
            )
        if not self.unit_by_column:
            raise GpcSummaryExportFetchError(
                "unit_by_column must be declared: the export's column headers are bare names "
                "(`Mw`), and reading a unit into one would be inventing what the file did not say"
            )

    def fetch(self) -> Tuple[RawDocument, ...]:
        self._check_declarations()
        try:
            lines = self.path.read_text().splitlines()
        except OSError as exc:
            raise GpcSummaryExportFetchError(f"could not read export {self.path}: {exc}") from exc

        header_block = [line.lstrip("#").strip() for line in lines if line.startswith("#")]
        body = [line for line in lines if line and not line.startswith("#")]
        if len(body) < 2:
            raise GpcSummaryExportFetchError(f"{self.path} has no header row and data rows")
        if not header_block:
            raise GpcSummaryExportFetchError(
                f"{self.path} states no conditions at all. An empty conditions mapping asserts the "
                "measurement was condition-independent, which a chromatographic run is not."
            )

        columns = [cell.strip() for cell in body[0].split(",")]
        flag_columns = set(self.flag_by_column.values())
        quantity_columns = [
            c for c in columns if c not in _IDENTITY_COLUMNS
            and c not in _NON_QUANTITY_COLUMNS and c not in flag_columns
        ]
        unknown_flag_columns = flag_columns - set(columns)
        if unknown_flag_columns:
            raise GpcSummaryExportFetchError(
                f"flag column(s) {sorted(unknown_flag_columns)!r} are not in the export"
            )
        if not quantity_columns:
            raise GpcSummaryExportFetchError(f"{self.path} declares no quantity columns")
        missing_units = [c for c in quantity_columns if c not in self.unit_by_column]
        if missing_units:
            raise GpcSummaryExportFetchError(
                f"no unit declared for column(s) {missing_units!r}. The file does not state them "
                "and this adapter will not choose one."
            )
        missing_kinds = [c for c in quantity_columns if c not in self.kind_by_column]
        if missing_kinds:
            raise GpcSummaryExportFetchError(
                f"no measured/derived kind declared for column(s) {missing_kinds!r}"
            )

        documents: List[RawDocument] = []
        seen: set = set()
        for index, line in enumerate(body[1:]):
            cells = [cell.strip() for cell in line.split(",")]
            if len(cells) != len(columns):
                raise GpcSummaryExportFetchError(
                    f"{self.path} row {index} has {len(cells)} cells against {len(columns)} columns"
                )
            row = dict(zip(columns, cells))
            sample_id = row.get("Sample")
            if not sample_id:
                raise GpcSummaryExportFetchError(f"{self.path} row {index} names no Sample")

            # THE RUN IDENTITY. `Inj` when the export carries it; the row's
            # POSITION when it does not. A positional locator is acquisition
            # identity and is exactly where an acquisition identity belongs;
            # it never enters content, where the table gate refuses
            # positional identity. This is the prediction the
            # pre-registration named as most likely to be wrong.
            run = row.get("Inj") or f"row-{index}"
            locator = f"{self.path}#{sample_id}/{run}"
            if locator in seen:
                raise GpcSummaryExportFetchError(
                    f"{self.path} yields locator {locator!r} twice; two runs sharing a locator "
                    "collapse into one observation and understate the spread"
                )
            seen.add(locator)

            # DERIVED COLUMNS ARE DECLINED HERE, VISIBLY, NOT DROPPED.
            #
            # Refusing the whole record would lose Mw along with PDI, and
            # this source has a perfectly good measured column. Routing a
            # derived quantity into an interface that only makes `measured`
            # evidence is what the extractor refuses; not routing it is an
            # acquisition decision, and the difference between that and
            # silently dropping it is that the omission is DECLARED in
            # content, where a consumer meets it.
            #
            # The extractor's refusal stays reachable from any source whose
            # payload declares a derived measurement -- the first GPC
            # source's derived-column fixture does exactly that.
            declined = tuple(sorted(c for c in quantity_columns
                                    if self.kind_by_column[c] != "measured"))

            measurements: List[Dict[str, Any]] = []
            for column in quantity_columns:
                if column in declined:
                    continue
                raw = row.get(column, "")
                flag = row.get(self.flag_by_column.get(column, ""), "")

                # ABSENCE IS CARRIED AS STRUCTURE WHEN THE SOURCE STATES A
                # REASON, and refused when it does not. A blank cell says
                # THAT a value is missing and never WHY; the flag says why,
                # in the vendor's vocabulary, and the caller maps that
                # vocabulary onto the absence reasons. Neither half is
                # invented here.
                if flag and flag not in self.measured_flags:
                    reason = self.absence_reason_by_flag.get(flag)
                    if reason is None:
                        raise GpcSummaryExportFetchError(
                            f"{self.path} row {index} flags {column!r} as {flag!r} and no absence "
                            "reason is declared for it. Refused rather than defaulted: a blank "
                            "cell says THAT a value is missing and never WHY, and guessing the "
                            "reason is the fabrication the absence vocabulary exists to prevent."
                        )
                    measurements.append({
                        "variable": column,
                        "value": None,
                        "value_absence": reason,
                        "unit": self.unit_by_column[column],
                        "uncertainty": None,
                        "uncertainty_kind": "absent",
                        "kind": self.kind_by_column[column],
                    })
                    continue

                if raw == "":
                    # Blank with no flag, or a flag meaning `measured`. The
                    # source says a value is missing and says nothing about
                    # why, so there is nothing honest to carry.
                    raise GpcSummaryExportFetchError(
                        f"{self.path} row {index} column {column!r} is blank with no absence "
                        f"reason (flag {flag!r}). An unexplained blank cannot be carried as "
                        "absence without inventing its reason, nor as a value."
                    )
                try:
                    value = float(raw)
                except ValueError as exc:
                    raise GpcSummaryExportFetchError(
                        f"{self.path} row {index} column {column!r} is not numeric: {raw!r}"
                    ) from exc
                measurements.append({
                    "variable": column,
                    "value": value,
                    "unit": self.unit_by_column[column],
                    # NO UNCERTAINTY EXISTS IN THIS SOURCE. Stated as the
                    # explicit vocabulary member rather than omitted, and
                    # never invented.
                    "uncertainty": None,
                    "uncertainty_kind": "absent",
                    "kind": self.kind_by_column[column],
                })
            if not measurements:
                raise GpcSummaryExportFetchError(
                    f"{self.path} row {index} reports no MEASURED quantity; every column it carries "
                    f"is declared derived ({declined!r}). Refused rather than acquired empty."
                )

            payload: Dict[str, Any] = {
                "data_provenance": self.data_provenance,
                "sample_id": sample_id,
                "sample_kind": self.sample_kind,
                "method": self.method,
                "acquisition_declared": ",".join(self._declared()),
                # Named so a consumer can tell an absent quantity from one
                # this layer chose not to carry, and why.
                "not_acquired_because_not_measured": ",".join(declined),
                "conditions": {CONDITIONS_AS_REPORTED: " | ".join(header_block)},
                "measurements": measurements,
            }
            documents.append(RawDocument(
                source_name=self.source_name,
                source_kind="instrument_report",
                content=json.dumps(payload, sort_keys=True, allow_nan=False),
                locator=locator,
                retrieval_method="file:gpc_summary_export_v1",
                retrieved_at=self.retrieved_at,
            ))
        return tuple(documents)
