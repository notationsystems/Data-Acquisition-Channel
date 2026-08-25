"""DAF scheduling (Phase E) -- checkpoint-aware, deterministic plan
execution, and a `run_due_plans` interface. NOT a daemon: nothing here
reads the wall clock, sleeps, or loops. A caller (a cron entry, an
operator, a future real scheduler) invokes `run_due_plans` periodically
and supplies `now` explicitly.

    AcquisitionPlan (+ its AcquisitionCheckpoint)
          |
          v  daf.scheduling.runner.execute_plan
    AcquisitionRequest -> AcquisitionOrchestrator -> SCOUT -> DurablePool -> ArtifactStore
                                                                    [all unmodified]
          |
          v  only on ACQUIRED/DUPLICATE
    AcquisitionCheckpoint advances

Nothing in this package admits evidence, mutates EvidencePool, or
bypasses the existing AcquisitionOrchestrator.
"""

from __future__ import annotations
