"""Real `scout.interface.Extractor` implementation for arXiv Atom entries.

Purely structural XML parsing -- no model is involved anywhere in this
module, so `extraction_method` never starts with `"model:"` and
`scout.pipeline.run_scout`'s mandatory-model-confidence rule
(docs/PHASE_14_DATA_POOL_ARCHITECTURE.md section K) does not apply here.
`confidence` is fixed at `1.0` for the same reason
`scout.extraction.DeterministicExtractor` fixes it at `1.0`: this is a
verbatim, deterministic transcription of structured source fields, not a
probabilistic guess.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional, Tuple

from evidence.types import Record
from scout.interface import ExtractedEntity, ExtractedRelation, ExtractionCandidate

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"
_A = f"{{{_ATOM_NS}}}"
_X = f"{{{_ARXIV_NS}}}"

# The raw <entry> fragment stored in evidence.types.Record.raw_content carries
# no namespace declarations of its own -- those live on the parent <feed>
# element in the original arXiv response, which was never stored (only the
# per-paper entry was, per daf.adapters.arxiv's raw-content-fidelity choice).
# Inject the declarations here, for parsing only -- this never touches or
# rewrites the stored raw content.
_NS_DECLARATIONS = f' xmlns="{_ATOM_NS}" xmlns:arxiv="{_ARXIV_NS}"'


class ArxivExtractionError(ValueError):
    """Raised when a Record's raw_content is not a parseable arXiv entry."""


def _parseable(entry_xml: str) -> str:
    if not entry_xml.startswith("<entry>"):
        raise ArxivExtractionError(f"expected an arXiv <entry> fragment, got: {entry_xml[:120]!r}")
    return entry_xml.replace("<entry>", f"<entry{_NS_DECLARATIONS}>", 1)


def _text(element: ET.Element, path: str) -> str:
    return " ".join((element.findtext(path) or "").split())


@dataclass(frozen=True)
class ArxivExtractor:
    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]:
        try:
            root = ET.fromstring(_parseable(record.raw_content))
        except ET.ParseError as exc:
            raise ArxivExtractionError(f"malformed arXiv entry XML in record {record.id!r}") from exc

        arxiv_id = _text(root, f"{_A}id")
        if not arxiv_id:
            raise ArxivExtractionError(f"arXiv entry in record {record.id!r} has no <id>")

        title = _text(root, f"{_A}title")
        summary = _text(root, f"{_A}summary")
        published = _text(root, f"{_A}published")
        updated = _text(root, f"{_A}updated")

        primary_category_el = root.find(f"{_X}primary_category")
        primary_category: Optional[str] = (
            primary_category_el.get("term") if primary_category_el is not None else None
        )

        authors = tuple(
            name
            for author_el in root.findall(f"{_A}author")
            if (name := _text(author_el, f"{_A}name"))
        )

        content = {
            "arxiv_id": arxiv_id,
            "title": title,
            "summary": summary,
            "published": published,
            "updated": updated,
            "primary_category": primary_category,
        }

        entities = (ExtractedEntity(label=arxiv_id, kind="paper"),) + tuple(
            ExtractedEntity(label=author, kind="author") for author in authors
        )
        relations = tuple(
            ExtractedRelation(from_label=arxiv_id, to_label=author, type="authored_by")
            for author in authors
        )

        return (
            ExtractionCandidate(
                content=content,
                entities=entities,
                relations=relations,
                extraction_method="xml:arxiv_atom_v1",
                confidence=1.0,
            ),
        )
