"""The SCOUT live-ingestion vertical slice, wired end to end.

    real arXiv API
          |
          v
    ArxivSourceAdapter.fetch()          (daf.adapters.arxiv)
          |
          v
    RawDocument                          (scout.interface, unmodified)
          |
          v
    ArxivExtractor.extract()             (daf.extractors.arxiv)
          |
          v
    ExtractionCandidate                  (scout.interface, unmodified)
          |
          v
    scout.pipeline.run_scout             (unmodified -- the ONE admission door)
          |
          v
    evidence.admission gate              (unmodified)
          |
          v
    Source / Document / Record / Observation / Referent / ClaimedRelationship
    (evidence.types, unmodified) inside an evidence.pool.EvidencePool

This module adds no new evidence types, no new identity scheme, and no
new admission path -- it only supplies real inputs (`ArxivSourceAdapter`,
`ArxivExtractor`) to the existing, unmodified `run_scout` pipeline. It
never imports `materials`, `experiment`, `workbench`, `core`, `morpho`,
`backends`, or `runtime` -- see docs/ARCHITECTURE_RECONNAISSANCE.md
section 15.
"""

from __future__ import annotations

from typing import Optional, Tuple

import daf  # noqa: F401  -- ensures the vendored repo is on sys.path
from evidence.pool import EvidencePool
from scout.pipeline import ScoutAdmissionFailure, ScoutFinding, run_scout

from daf.adapters.arxiv import ArxivSourceAdapter
from daf.extractors.arxiv import ArxivExtractor


def acquire_arxiv_papers(
    arxiv_ids: Tuple[str, ...],
    retrieved_at: str,
    pool: Optional[EvidencePool] = None,
) -> Tuple[EvidencePool, Tuple[ScoutFinding, ...], Tuple[ScoutAdmissionFailure, ...]]:
    """Run the full vertical slice for one or more arXiv ids, admitting
    the result into `pool` (a fresh `EvidencePool` if none is given, so
    repeated calls against the SAME pool demonstrate the append-only,
    deduplicating behavior evidence.pool already guarantees)."""
    pool = pool if pool is not None else EvidencePool()
    adapter = ArxivSourceAdapter(arxiv_ids=arxiv_ids, retrieved_at=retrieved_at)
    extractor = ArxivExtractor()
    findings, failures = run_scout(adapter, extractor, pool)
    return pool, findings, failures


def _main() -> None:  # pragma: no cover -- manual/CLI demonstration only
    import sys

    arxiv_ids = tuple(sys.argv[1:]) or ("1706.03762",)
    retrieved_at = "2026-08-24T00:00:00Z"
    pool, findings, failures = acquire_arxiv_papers(arxiv_ids, retrieved_at)

    print(f"Acquired {len(findings)} finding(s), {len(failures)} admission failure(s).")
    for finding in findings:
        print(f"  Observation {finding.observation.id}: {dict(finding.observation.content)}")
        for referent in finding.referents:
            print(f"    Referent {referent.id}: {referent.kind}:{referent.natural_key}")
    for failure in failures:
        print(f"  FAILED at stage {failure.stage!r}: {failure.errors}")


if __name__ == "__main__":  # pragma: no cover
    _main()
