"""Applies `science.admissibility` to REAL acquired evidence.

    ClassifiedPool (real acquisition)
        |
        v  every Observation whose content declares a "property"
    PropertyCandidate
        |
        v  science.admissibility.no_context_free_property  (UNCHANGED)
        |
    admissible ---------------------------+--- inadmissible
        |                                 |
        v                                 v
   (already in the pool;              QuarantineRecord
    nothing further to do)            stage="canonical_assertion"
                                       (daf.execution.quarantine, UNCHANGED)

WHY "PROPERTY CANDIDATE" IS A FILTER, NEVER A TRANSFORMATION. A
candidate is exactly an admitted `Observation` whose `content` mapping
already contains a `property` key -- checked by KEY PRESENCE only, never
by inspecting or reshaping the value. Nothing here adds a `method` or
`conditions` key that the extractor did not put there, and nothing
renames an existing key to satisfy the gate. An extractor whose content
lacks the keys `no_context_free_property` requires is measured as
inadmissible, honestly, not repaired.

WHY A SEPARATE QUARANTINE STORE. `daf.execution.recorded.execute_plan_recorded`
already writes to `<root>/quarantine/` for `ScoutAdmissionFailure`s, and
`daf.execution.metrics.rejection_metrics` cross-checks that store's count
against `ExecutionRecord.admission_failure_count` -- a field fixed at
acquisition time and never covering canonical-assertion refusals (an
inadmissible property observation is NOT a `ScoutAdmissionFailure`; the
Observation genuinely entered the pool). Writing "canonical_assertion"
stage records into the SAME store would make that count mismatch and
raise `QuarantineAccountingError` on every Phase 27/28 metrics call for
this execution, which is exactly the coupling this phase must not
introduce.

`QuarantineStore` itself is UNCHANGED and UNCONSULTED for its internal
layout: it always creates `<given-root>/quarantine/`. This module simply
never gives it the acquisition run's own root -- it gives it
`<root>/canonical_assertion/`, so the resulting directory is
`<root>/canonical_assertion/quarantine/`, sibling to but never colliding
with `<root>/quarantine/`. Phase 27/28's metrics are computed exactly as
before, over the untouched original store, because nothing here ever
opens it.

`stage="canonical_assertion"` is a string value, not a new type or a new
admission stage in `architecture/admission_reachability.yaml`'s sense --
that file is scoped to the vendored pipeline's own six stages and is
drift-guarded against `scout/pipeline.py`'s real code; this phase adds
nothing to it and nothing here is checked against that guard.

BOUNDARY: this module writes NOTHING into `EvidencePool`. It calls no
`put_*`, no `admit_*`. An inadmissible Observation remains exactly what
it was -- an admitted, retrievable piece of evidence -- for canonical
assertion boundary. That distinction (`refusal != evidence`,
`admissible-for-training != canonical-assertion` are separate
questions) is Phase 25's `class_admissibility`, unmodified and untouched
by anything here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple

# precede every `evidence`/`scout`/`materials` import in this module.
from evidence.pool import EvidencePool

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate; must
from daf.execution.quarantine import QuarantineError, make_quarantine_record
from daf.execution.store import QuarantineStore
from science.admissibility import Admissibility, no_context_free_property

CANONICAL_ASSERTION_STAGE = "canonical_assertion"
CANONICAL_ASSERTION_QUARANTINE_DIRNAME = "canonical_assertion_quarantine"


@dataclass(frozen=True)
class PropertyCandidate:
    """One admitted Observation whose content declares a `property`.
    Carries the execution it was acquired under for linkage, never for
    identity -- `observation_id` is the only thing this object names as
    "which evidence"."""

    observation_id: str
    execution_id: str
    content: Mapping[str, object]


@dataclass(frozen=True)
class PropertyVerdict:
    candidate: PropertyCandidate
    admissibility: Admissibility
    quarantine_record_id: Optional[str]

    @property
    def admissible(self) -> bool:
        return self.admissibility.admissible


@dataclass(frozen=True)
class PropertyAdmissibilityReport:
    """A derived view, exactly the discipline `daf/execution/metrics.py`
    already establishes: no `id`, never persisted, recomputable from the
    pool and the quarantine store it was built from."""

    execution_id: str
    candidates_examined: int
    accepted: int
    refused: int
    verdicts: Tuple[PropertyVerdict, ...]
    by_code: Mapping[str, int]

    @property
    def rejection_rate(self) -> Optional[float]:
        return self.refused / self.candidates_examined if self.candidates_examined else None


def property_candidates(pool: EvidencePool, execution_id: str) -> Tuple[PropertyCandidate, ...]:
    """Every admitted Observation carrying a `property` key -- a filter
    on key PRESENCE, never on the value. Ordered by observation id so a
    report never depends on pool iteration order."""
    return tuple(
        PropertyCandidate(observation_id=o.id, execution_id=execution_id, content=o.content)
        for o in sorted(pool.all_observations(), key=lambda o: o.id)
        if "property" in o.content
    )


def canonical_assertion_quarantine_store(root: str | Path) -> QuarantineStore:
    """The second, independent quarantine directory this module writes
    to -- never the acquisition run's own `<root>/quarantine/`.
    `QuarantineStore` is unmodified; it is simply never given the
    acquisition run's own root."""
    return QuarantineStore(Path(root) / CANONICAL_ASSERTION_QUARANTINE_DIRNAME)


def assess_property_candidate(candidate: PropertyCandidate) -> Admissibility:
    """The gate, called exactly as `science/admissibility.py` defines
    it -- no reshaping of `candidate.content` before the call."""
    return no_context_free_property(candidate.content)


def assess_pool(
    pool: EvidencePool, execution_id: str, quarantine: QuarantineStore
) -> PropertyAdmissibilityReport:
    """Runs every property candidate in `pool` through the unmodified
    gate, retains each refusal in `quarantine`, and returns the report.
    Never mutates `pool`; never mutates an `ExecutionRecord`."""
    candidates = property_candidates(pool, execution_id)
    verdicts = []
    by_code: dict = {}

    for candidate in candidates:
        admissibility = assess_property_candidate(candidate)
        quarantine_record_id = None
        if not admissibility.admissible:
            record = make_quarantine_record(
                execution_id=execution_id,
                stage=CANONICAL_ASSERTION_STAGE,
                errors=tuple(
                    QuarantineError(
                        object_type="Observation",
                        code=reason,
                        message=(
                            f"Observation {candidate.observation_id!r} content is inadmissible "
                            f"for canonical assertion: {reason}"
                        ),
                    )
                    for reason in admissibility.reasons
                ),
            )
            quarantine.put(record)
            quarantine_record_id = record.id
            for reason in admissibility.reasons:
                by_code[reason] = by_code.get(reason, 0) + 1
        verdicts.append(
            PropertyVerdict(
                candidate=candidate, admissibility=admissibility, quarantine_record_id=quarantine_record_id
            )
        )

    refused = sum(1 for v in verdicts if not v.admissible)
    return PropertyAdmissibilityReport(
        execution_id=execution_id,
        candidates_examined=len(candidates),
        accepted=len(candidates) - refused,
        refused=refused,
        verdicts=tuple(verdicts),
        by_code=dict(sorted(by_code.items())),
    )
