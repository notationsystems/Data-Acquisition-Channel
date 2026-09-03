"""Per-invariant rejection rate per ingest run, and the unclassified backlog.

The last unimplemented clause of the rejection policy
(`architecture/invariants.yaml`, `rejection_policy.rejection_rate_per_invariant`):
Phase 26 made refusals durable and linked them to the execution that
caused them, but nothing counted them.

DERIVED VIEWS, NOT RECORDS. Nothing here has an id, nothing is persisted,
and nothing is evidence -- the same discipline `evidence/trust_graph.py`
and `evidence/provenance.py` already establish for computed views over a
pool. Every function is pure over records that already exist, so a report
is recomputed rather than stored, and cannot drift from what it describes.
No new identity is introduced.

WHAT THE MEASUREMENT FOUND, and why the counts are split in two. A run of
four dataset records through the real pipeline produced 3 accepted, 1
refused at `extraction`, and 1 refused at `relationship`. The naive rate
-- refusals over refusals-plus-accepted, 2/5 = 0.40 -- is WRONG, because
those two refusals are not the same kind of event:

    extraction    the observation candidate never entered the pool
    relationship  the observation DID enter; one of its edges did not

Three observations were admitted, not two. So refusals divide into:

    TERMINAL   document, record, extraction, observation
               the candidate did not enter. accepted + terminal = attempts,
               which is what a rate may be taken over.
    PARTIAL    referent, relationship
               the observation entered anyway. Counted and reported, never
               folded into the rate, because doing so would claim a
               rejection that did not happen.

Measured: accepted 3 + terminal 1 = 4 = the records offered. The partial
refusal is reported beside that, not inside it.

RATES ARE `None` WHEN THERE IS NOTHING TO DIVIDE BY. A run that attempted
nothing has no rejection rate; it does not have a rejection rate of 0.0.
Same discipline as `output_fingerprint` on a failed execution
(`daf/execution/record.py`) -- absence is explicit, never a convenient
zero.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from daf.execution.record import ExecutionRecord
from daf.execution.store import ExecutionRecordStore, QuarantineStore
from daf.storage.filesystem_store import FilesystemEvidenceStore
from epistemics.evidence_class import ClassRegister

# The candidate did not enter the pool. `run_scout` `continue`s past it.
TERMINAL_STAGES: Tuple[str, ...] = ("document", "extraction", "observation", "record")
# The observation entered; part of what it claimed did not.
PARTIAL_STAGES: Tuple[str, ...] = ("referent", "relationship")
STAGES: Tuple[str, ...] = tuple(sorted(TERMINAL_STAGES + PARTIAL_STAGES))


class QuarantineAccountingError(ValueError):
    """The retained refusals do not add up to what the execution record
    says was refused -- quarantine records are missing, or belong to an
    execution that did not record them."""


@dataclass(frozen=True)
class RejectionCount:
    """One (stage, code) pair and how often it fired in a run.

    `rate` is over the run's ATTEMPTS and is `None` for a partial stage:
    a refused relationship is not a refused admission, so dividing it by
    admissions would produce a number with no meaning."""

    stage: str
    code: str
    count: int
    rate: Optional[float]


@dataclass(frozen=True)
class IngestRunRejectionMetrics:
    execution_id: str
    operation_id: str
    status: str
    outcome: str
    accepted: int
    terminal_refusals: int
    partial_refusals: int
    attempts: int
    rejection_rate: Optional[float]
    by_code: Tuple[RejectionCount, ...]
    by_stage: Mapping[str, int]


@dataclass(frozen=True)
class CategoryBacklog:
    category: str
    total: int
    classified: int
    unclassified: int


@dataclass(frozen=True)
class UnclassifiedBacklog:
    """§22's "unclassified count is a reported metric", reported.

    Counted from the durable store rather than from an in-memory pool, so
    it survives a restart and so a corpus persisted before
    `class_assigned_at_ingest` existed is counted as what it is: wholly
    unclassified."""

    categories: Tuple[CategoryBacklog, ...]
    total: int
    classified: int
    unclassified: int
    unclassified_fraction: Optional[float]


@dataclass(frozen=True)
class IngestReport:
    """Rejection metrics for one or more runs, beside the standing
    backlog. Deliberately one object: a rejection rate read without the
    backlog invites treating refusals as the only way evidence fails to
    become assertable, when an admitted-but-unclassified record is the
    other way."""

    runs: Tuple[IngestRunRejectionMetrics, ...]
    backlog: UnclassifiedBacklog


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return numerator / denominator if denominator else None


def rejection_metrics(
    execution: ExecutionRecord, quarantine: QuarantineStore
) -> IngestRunRejectionMetrics:
    """Per-invariant rejection counts and rates for one ingest run.

    Computed entirely from records already on disk -- the execution and
    its quarantine entries -- so it is recomputable after a restart and
    never needs the run to be repeated."""
    refusals = quarantine.for_execution(execution.id)
    if len(refusals) != execution.admission_failure_count:
        raise QuarantineAccountingError(
            f"execution {execution.id!r} recorded {execution.admission_failure_count} refused "
            f"admissions but {len(refusals)} quarantine records reference it"
        )

    for refusal in refusals:
        if refusal.stage not in STAGES:
            raise QuarantineAccountingError(
                f"quarantine record {refusal.id!r} names stage {refusal.stage!r}, "
                f"which is not one of {list(STAGES)}"
            )

    terminal = tuple(r for r in refusals if r.stage in TERMINAL_STAGES)
    partial = tuple(r for r in refusals if r.stage in PARTIAL_STAGES)

    accepted = len(execution.artifact_ids)
    attempts = accepted + len(terminal)

    pairs: Counter = Counter()
    for refusal in refusals:
        for error in refusal.errors:
            pairs[(refusal.stage, error.code)] += 1

    by_code = tuple(
        RejectionCount(
            stage=stage,
            code=code,
            count=count,
            rate=_rate(count, attempts) if stage in TERMINAL_STAGES else None,
        )
        for (stage, code), count in sorted(pairs.items())
    )
    by_stage: Dict[str, int] = {}
    for refusal in refusals:
        by_stage[refusal.stage] = by_stage.get(refusal.stage, 0) + 1

    return IngestRunRejectionMetrics(
        execution_id=execution.id,
        operation_id=execution.operation_id,
        status=execution.status,
        outcome=execution.outcome,
        accepted=accepted,
        terminal_refusals=len(terminal),
        partial_refusals=len(partial),
        attempts=attempts,
        rejection_rate=_rate(len(terminal), attempts),
        by_code=by_code,
        by_stage=dict(sorted(by_stage.items())),
    )


def unclassified_backlog(
    # Concrete: reads `store.categories`, a filesystem-store attribute.
    store: FilesystemEvidenceStore, register: ClassRegister
) -> UnclassifiedBacklog:
    """How much of the durable corpus carries no evidence class.

    `Referent` is counted like everything else even though
    `ClassifiedPool` deliberately never classifies one (an identity
    anchor asserts nothing, so it has no class to be measured). That is
    honest rather than flattering: the backlog says what is unclassified,
    and a Referent genuinely is."""
    categories = []
    for category in store.categories():
        ids = store.all_ids_by_filename(category)
        unclassified = register.unclassified(ids)
        categories.append(
            CategoryBacklog(
                category=category,
                total=len(ids),
                classified=len(ids) - len(unclassified),
                unclassified=len(unclassified),
            )
        )

    total = sum(c.total for c in categories)
    unclassified_total = sum(c.unclassified for c in categories)
    return UnclassifiedBacklog(
        categories=tuple(categories),
        total=total,
        classified=total - unclassified_total,
        unclassified=unclassified_total,
        unclassified_fraction=_rate(unclassified_total, total),
    )


def ingest_report(
    executions: ExecutionRecordStore,
    quarantine: QuarantineStore,
    store: FilesystemEvidenceStore,
    register: ClassRegister,
    *,
    operation_id: Optional[str] = None,
) -> IngestReport:
    """Every recorded run, or every run of one operation, beside the
    standing backlog. Runs are ordered by `started_at` then id, the same
    ordering `ExecutionRecordStore.for_operation` uses, so a report never
    depends on filesystem iteration order."""
    records = (
        executions.for_operation(operation_id)
        if operation_id is not None
        else tuple(sorted(executions.all_records(), key=lambda r: (r.started_at, r.id)))
    )
    return IngestReport(
        runs=tuple(rejection_metrics(record, quarantine) for record in records),
        backlog=unclassified_backlog(store, register),
    )
