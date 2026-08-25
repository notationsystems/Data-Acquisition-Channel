"""Real scout.interface.Extractor implementation for
daf.adapters.edgar_daily_index -- structural parsing of the real EDGAR
daily-index text format only. Deliberately produces zero entities/
relations and no per-form-type classification ontology: this extractor
proves a real external document can become the existing SCOUT
extraction contract, not a SEC filing taxonomy.

Format (confirmed against real fetched files for 2026-07-01 and
2026-07-15 -- see the adapter's own docstring): a fixed header block,
then a line of 20+ dashes marking the start of data, then fixed-width
rows of five fields: Company Name, Form Type, CIK, Date Filed
(YYYYMMDD), File Name.

Rows are parsed with a right-anchored regex, not a naive split on runs
of 2+ whitespace: the LAST four fields (Form Type, CIK, Date Filed,
File Name) are each guaranteed single whitespace-delimited tokens, but
Company Name is free text that occasionally itself contains a run of
2+ spaces (confirmed live, e.g. an individual filer name such as
"PRICHEP PATRICIA  B" -- two spaces before a middle initial). A
2+-whitespace split misparses that row as six fields instead of five.
Anchoring from the right and taking everything remaining on the left
as the company name handles this correctly regardless of internal
whitespace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from evidence.types import Record
from scout.interface import ExtractionCandidate

_SEPARATOR_LINE_RE = re.compile(r"^-{10,}$")
_DATA_ROW_RE = re.compile(r"^(?P<company_name>.*\S)\s+(?P<form_type>\S+)\s+(?P<cik>\d+)\s+(?P<date_filed>\d{8})\s+(?P<file_name>\S+)\s*$")


class EdgarDailyIndexExtractionError(ValueError):
    """Raised when a Record's raw_content is not a parseable EDGAR daily
    index file -- missing the header separator, or a data row that does
    not split into exactly the five expected fields."""


@dataclass(frozen=True)
class EdgarDailyIndexExtractor:
    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        lines = record.raw_content.splitlines()

        separator_index = next(
            (i for i, line in enumerate(lines) if _SEPARATOR_LINE_RE.match(line.strip())), None
        )
        if separator_index is None:
            raise EdgarDailyIndexExtractionError(
                f"record {record.id!r} has no EDGAR daily-index header separator line"
            )

        filings: List[Dict[str, Any]] = []
        form_type_counts: Dict[str, int] = {}
        for line in lines[separator_index + 1 :]:
            if not line.strip():
                continue
            match = _DATA_ROW_RE.match(line.strip())
            if match is None:
                raise EdgarDailyIndexExtractionError(
                    f"record {record.id!r} has an EDGAR daily-index row that does not match the expected format: {line!r}"
                )
            company_name = match.group("company_name")
            form_type = match.group("form_type")
            cik = match.group("cik")
            date_filed = match.group("date_filed")
            file_name = match.group("file_name")
            filings.append(
                {
                    "company_name": company_name,
                    "form_type": form_type,
                    "cik": cik,
                    "date_filed": date_filed,
                    "file_name": file_name,
                }
            )
            form_type_counts[form_type] = form_type_counts.get(form_type, 0) + 1

        content = {
            "date_filed": filings[0]["date_filed"] if filings else None,
            "filing_count": len(filings),
            "form_type_counts": form_type_counts,
            "filings": filings,
        }

        return (
            ExtractionCandidate(
                content=content,
                entities=(),
                relations=(),
                extraction_method="text:edgar_daily_index_v1",
                confidence=1.0,
            ),
        )
