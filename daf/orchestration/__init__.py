"""DAF acquisition orchestration (Phase C).

Sits strictly ABOVE the existing, unmodified acquisition contract proven
in Phase A/B:

    SourceRegistry -> AcquisitionRequest -> AcquisitionOrchestrator
        -> SourceAdapter -> scout.pipeline.run_scout -> DurablePool
        -> ArtifactStore

The orchestrator selects a registered adapter/extractor pair and invokes
the existing SCOUT admission path -- it never admits evidence itself,
never constructs a domain-specific state (ModelState/CanonicalState),
and never branches on domain/source type. Domain-specific behavior lives
exclusively in `daf.adapters.*`/`daf.extractors.*`, wired in via
`daf.orchestration.bindings` -- the one module allowed to import them.
"""

from __future__ import annotations
