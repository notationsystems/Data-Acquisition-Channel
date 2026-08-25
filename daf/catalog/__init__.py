"""DAF acquisition catalog and planning (Phase D).

    SourceCatalog (persistent SourceRegistry)
          |
    AcquisitionPlan (declarative, persistable acquisition intent)
          |
          v  to_request(requested_at)
    AcquisitionRequest                       [unmodified, Phase C]
          |
          v
    AcquisitionOrchestrator                  [unmodified, Phase C]
          |
          v
    scout.pipeline.run_scout -> DurablePool -> ArtifactStore   [unmodified, Phase A/B]

Nothing in this package admits evidence, mutates EvidencePool, or
bypasses SCOUT -- every plan execution funnels through the existing,
unmodified AcquisitionOrchestrator. A SourceDefinition and an
AcquisitionPlan both answer only "what/how to acquire," never anything
about scientific meaning -- see daf.orchestration.source_registry's own
docstring for the discipline this package inherits.
"""

from __future__ import annotations
