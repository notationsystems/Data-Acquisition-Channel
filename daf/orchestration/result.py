"""AcquisitionResult -- the outcome of one orchestrated acquisition run.

This is an ORCHESTRATION result: it says whether the orchestrator
successfully drove one request through the existing acquisition path,
and gives back references to whatever Phase B artifact/version
identities resulted. It is explicitly NOT scientific evidence, NOT
provenance, and NOT an execution ledger -- it carries no operation id,
no execution record, and is never persisted anywhere by this module
(callers may log it if they wish, but nothing here requires that).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from scout.pipeline import ScoutAdmissionFailure


class AcquisitionOutcome(str, Enum):
    ACQUIRED = "acquired"
    DUPLICATE = "duplicate"
    SOURCE_UNAVAILABLE = "source_unavailable"
    ADAPTER_FAILURE = "adapter_failure"
    EXTRACTION_FAILURE = "extraction_failure"
    PERSISTENCE_FAILURE = "persistence_failure"


@dataclass(frozen=True)
class AcquiredArtifact:
    artifact_id: str
    version_id: str
    is_new: bool  # False if this exact version already existed before this run
    # The Record.locator this artifact was acquired under -- adapter-defined
    # (Phase E). Exists so an incremental-capable AdapterBinding can compute
    # its own next checkpoint position (e.g. the max sequence number encoded
    # in locators) without the orchestrator or checkpoint machinery needing
    # to understand what a locator means for any given source.
    locator: str


@dataclass(frozen=True)
class AcquisitionResult:
    source_id: str
    outcome: AcquisitionOutcome
    artifacts: Tuple[AcquiredArtifact, ...] = ()
    admission_failures: Tuple[ScoutAdmissionFailure, ...] = ()
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.outcome in (AcquisitionOutcome.ACQUIRED, AcquisitionOutcome.DUPLICATE)
