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
    # The Record.raw_content this artifact was acquired from (Phase H).
    # Exists for the case Phase E's `locator`-only design did not anticipate:
    # a source whose stable identity (locator) and incremental cursor value
    # are two DIFFERENT things -- e.g. an event id (identity, never changes)
    # versus a last-revised timestamp buried in that event's own content
    # (the actual checkpoint cursor, which only content, not locator,
    # carries). An AdapterBinding whose `advance_position` cannot compute
    # the next position from `locator` alone may parse this field itself;
    # the orchestrator and checkpoint machinery still never interpret it.
    raw_content: str


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
