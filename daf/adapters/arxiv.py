"""Real `scout.interface.SourceAdapter` implementation against the public
arXiv API (`https://export.arxiv.org/api/query`).

Why arXiv, for this one vertical slice (see docs/SCOUT_VERTICAL_SLICE.md
for the full rationale): public, no authentication, stable, structured
(Atom XML), no browser automation, and directly representative of the
"scientific literature" acquisition domain the existing `materials/`
State-Space model already consumes via its fixture data.

This module performs acquisition ONLY. It never assigns identity --
`RawDocument` is pre-identity by contract (`scout.interface.RawDocument`'s
own docstring); `evidence.types.make_document`/`make_record` compute the
actual content-addressed ids, downstream, inside `scout.pipeline.run_scout`,
exactly as for every other `SourceAdapter`. It never decides what is
canonical and never references `materials`/`ModelState` in any way.
"""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from typing import Callable, Tuple

from scout.interface import RawDocument

ARXIV_API_URL = "https://export.arxiv.org/api/query"

# arXiv's Atom response nests one <entry>...</entry> block per paper inside
# the <feed>. We deliberately extract each entry as a raw substring (not a
# reparsed/re-serialized XML tree) so RawDocument.content is byte-identical
# to what arXiv actually sent for that entry -- the durable "raw evidence"
# principle from docs/ARCHITECTURE_RECONNAISSANCE.md section 12 -- rather
# than a reconstruction whose serialization could vary between runs. This
# is safe for arXiv's own well-formed Atom output, where literal
# "<entry>"/"</entry>" text inside escaped content would appear as
# "&lt;entry&gt;", never as literal angle brackets.
_ENTRY_RE = re.compile(r"<entry>.*?</entry>", re.DOTALL)
_ID_RE = re.compile(r"<id>(.*?)</id>")

Fetcher = Callable[[str], bytes]


def _default_fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 -- fixed https host, not user input
        return response.read()


class ArxivFetchError(RuntimeError):
    """Raised when the arXiv response cannot be parsed into entries.
    Acquisition failures are never swallowed into an empty result --
    an empty `fetch()` result must mean "no matching papers", never
    "something went wrong and nobody noticed"."""


@dataclass(frozen=True)
class ArxivSourceAdapter:
    """Acquires one or more arXiv papers by id.

    `retrieved_at` is always caller-supplied ISO-8601 UTC -- never
    wall-clock -- matching every other `RawDocument.retrieved_at` in this
    codebase (e.g. `scout/fixtures.py::FIXED_RETRIEVED_AT`), so runs stay
    reproducible. `fetch_bytes` is injectable so tests can supply a fixed
    fixture response instead of hitting the network; it defaults to a
    real HTTPS GET against the public API.
    """

    arxiv_ids: Tuple[str, ...]
    retrieved_at: str
    fetch_bytes: Fetcher = _default_fetch

    def fetch(self) -> Tuple[RawDocument, ...]:
        if not self.arxiv_ids:
            return ()
        url = f"{ARXIV_API_URL}?id_list={','.join(self.arxiv_ids)}"
        raw_bytes = self.fetch_bytes(url)
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ArxivFetchError(f"arXiv response for {url!r} was not valid UTF-8") from exc

        entries = _ENTRY_RE.findall(raw_text)
        documents = []
        for entry_text in entries:
            id_match = _ID_RE.search(entry_text)
            if id_match is None:
                raise ArxivFetchError(
                    f"arXiv entry has no <id> -- cannot determine its locator: {entry_text[:200]!r}"
                )
            documents.append(
                RawDocument(
                    source_name="arXiv",
                    source_kind="paper",
                    content=entry_text,
                    locator=id_match.group(1).strip(),
                    retrieval_method="http:arxiv_api_v1",
                    retrieved_at=self.retrieved_at,
                )
            )
        return tuple(documents)
