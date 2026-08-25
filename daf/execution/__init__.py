"""`execution_recorded` -- how an artifact entered the scientific substrate.

    source
      |
      v  acquisition operation          operation_id  (plan + source + parameters)
      v  execution identity minted      execution_id  (operation + runtime + start)
      v  artifact acquired              artifact_id / version_id  (unchanged)
      v  result normalized              AcquisitionResult          (unchanged)
      v  execution record retained      ExecutionRecord            (this package)
      v  evidence admission             class_assigned_at_ingest   (unchanged)

WHAT THIS PACKAGE IS NOT. It is not evidence, not scientific state, and
not a second provenance architecture. An `ExecutionRecord` describes the
OPERATION; `artifact_id` describes the acquired CONTENT; `Observation.id`
describes the admitted FACT. `tests/test_execution_record.py` asserts
those stay separate, that an execution record never reaches the
`EvidencePool`, and that recording one leaves the pool's own fingerprint
untouched.

OWNERSHIP (Phase 26 §5, Case B). The repository already had a
content-addressed identity substrate (`evidence.identity.content_hash`)
and two provenance shapes -- `core.canonical.version.ProvenanceInfo` and
`morpho.provenance.ProvenanceRecord` -- but neither records an execution
EVENT, both describe other subsystems, and both live in the vendored
submodule this project never modifies. So the identity substrate is
reused rather than re-invented, the field vocabulary deliberately reuses
their shared terms (`source`, `transaction_id`, `timestamp`) instead of
coining synonyms, and the record itself is DAF-owned because DAF is the
acquisition boundary.

That last part is an INTEGRATION DEPENDENCY, stated rather than assumed:
this contract is canonical for DAF acquisition only. A broader unified
substrate that later grows its own execution-record contract should
absorb this one, not sit beside it.
"""

from __future__ import annotations
