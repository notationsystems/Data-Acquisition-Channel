"""AcquisitionOrchestrator: the smallest layer that executes an
AcquisitionRequest through the EXISTING, unmodified acquisition path.

    AcquisitionRequest
          |
          v
    AcquisitionOrchestrator  (selects adapter, invokes it, calls run_scout, persists, reports)
          |
          v
    SourceAdapter -> scout.pipeline.run_scout -> EvidencePool/DurablePool

This module deliberately imports NOTHING from `daf.adapters` or
`daf.extractors` -- it operates only through the callables an
AdapterBinding supplies (see daf.orchestration.bindings for where
concrete adapters are wired in). This is what "domain-independent
orchestration" means operationally: no `if source.domain == "..."`
branch could even compile here, because this module has no way to name
a domain-specific type in the first place. See
tests/test_acquisition_orchestrator.py for the AST-level proof.

It also never imports `evidence.admission` and never calls a pool
mutator (`put_*`) directly -- the ONLY write path is the unmodified
`scout.pipeline.run_scout` call below. This is the one-door invariant
carried forward from Phase A/B.

CALLER RESPONSIBILITY -- duplicate detection reflects `pool`'s IN-MEMORY
state, not the durable store's on-disk state: if `pool` is a freshly
constructed `DurablePool(store)` in a new process that already has prior
data on disk, `is_new` will be wrong (everything looks new) even though
the durable writes themselves stay correctly deduplicated. Any caller
that might be a fresh process against existing storage -- e.g.
`daf.catalog.cli` -- must construct the pool via `DurablePool.restore(store)`,
never the plain constructor, exactly as Phase B's own restart tests do.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from evidence.pool import EvidencePool
from evidence.types import make_document, make_source
from scout.interface import RawDocument
from scout.pipeline import run_scout

from daf.orchestration.adapter_registry import AdapterNotFoundError, AdapterRegistry
from daf.orchestration.request import AcquisitionRequest
from daf.orchestration.result import AcquiredArtifact, AcquisitionOutcome, AcquisitionResult
from daf.orchestration.source_registry import SourceNotFoundError, SourceRegistry
from daf.storage.artifact_store import ArtifactStore
from daf.storage.serialization import ArtifactIdentityMismatch


@dataclass(frozen=True)
class _PrefetchedAdapter:
    """Structurally satisfies scout.interface.SourceAdapter by returning
    an already-fetched tuple. Used so the orchestrator can call
    `adapter.fetch()` itself (to classify a fetch-time failure as
    "source unavailable" / "adapter failure" before SCOUT ever runs)
    without fetching twice."""

    documents: Tuple[RawDocument, ...]

    def fetch(self) -> Tuple[RawDocument, ...]:
        return self.documents


def _expected_document_id(raw_doc: RawDocument) -> str:
    """Recomputes the Document id a RawDocument WOULD get, using the
    exact same evidence.types factories run_scout itself calls -- purely
    a read-side identity check, never a new identity scheme, and never a
    write. Lets the orchestrator know whether an artifact already existed
    BEFORE calling run_scout (see `is_new` on AcquiredArtifact)."""
    source = make_source(kind=raw_doc.source_kind, name=raw_doc.source_name)
    document = make_document(
        source_id=source.id,
        raw_content=raw_doc.content,
        retrieval_method=raw_doc.retrieval_method,
        retrieved_at=raw_doc.retrieved_at,
    )
    return document.id


class AcquisitionOrchestrator:
    def __init__(self, sources: SourceRegistry, adapters: AdapterRegistry, pool: EvidencePool) -> None:
        self._sources = sources
        self._adapters = adapters
        self._pool = pool

    def run(self, request: AcquisitionRequest) -> AcquisitionResult:
        try:
            source = self._sources.get(request.source_id)
        except SourceNotFoundError as exc:
            return AcquisitionResult(
                source_id=request.source_id, outcome=AcquisitionOutcome.SOURCE_UNAVAILABLE, error=str(exc)
            )

        if not source.enabled:
            return AcquisitionResult(
                source_id=request.source_id,
                outcome=AcquisitionOutcome.SOURCE_UNAVAILABLE,
                error=f"source {source.source_id!r} is disabled",
            )

        try:
            binding = self._adapters.get(source.adapter_id)
        except AdapterNotFoundError as exc:
            return AcquisitionResult(
                source_id=request.source_id, outcome=AcquisitionOutcome.ADAPTER_FAILURE, error=str(exc)
            )

        try:
            adapter = binding.build_adapter(source, request)
            raw_documents = adapter.fetch()
        except (OSError, ConnectionError, TimeoutError) as exc:
            return AcquisitionResult(
                source_id=request.source_id, outcome=AcquisitionOutcome.SOURCE_UNAVAILABLE, error=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 -- classified deliberately broad: any other adapter-side failure
            return AcquisitionResult(
                source_id=request.source_id, outcome=AcquisitionOutcome.ADAPTER_FAILURE, error=str(exc)
            )

        pre_existing_ids = {
            expected_id
            for raw_doc in raw_documents
            if self._pool.has_document(expected_id := _expected_document_id(raw_doc))
        }

        try:
            extractor = binding.build_extractor()
            findings, admission_failures = run_scout(
                _PrefetchedAdapter(raw_documents), extractor, self._pool
            )
        except (ArtifactIdentityMismatch, OSError) as exc:
            return AcquisitionResult(
                source_id=request.source_id, outcome=AcquisitionOutcome.PERSISTENCE_FAILURE, error=str(exc)
            )
        except Exception as exc:  # noqa: BLE001 -- classified deliberately broad: any other extractor-side failure
            return AcquisitionResult(
                source_id=request.source_id, outcome=AcquisitionOutcome.EXTRACTION_FAILURE, error=str(exc)
            )

        artifacts = tuple(
            AcquiredArtifact(
                artifact_id=ArtifactStore.artifact_id(finding.document.source_id, finding.record.locator),
                version_id=finding.document.id,
                is_new=finding.document.id not in pre_existing_ids,
                locator=finding.record.locator,
            )
            for finding in findings
        )
        outcome = (
            AcquisitionOutcome.DUPLICATE
            if artifacts and not any(a.is_new for a in artifacts)
            else AcquisitionOutcome.ACQUIRED
        )
        return AcquisitionResult(
            source_id=request.source_id,
            outcome=outcome,
            artifacts=artifacts,
            admission_failures=admission_failures,
        )
