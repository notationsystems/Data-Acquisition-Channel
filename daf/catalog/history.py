"""Derived acquisition history -- thin, read-only helpers over Phase B's
ArtifactStore. No new persistent record is introduced: "what versions
exist for this artifact" is answered entirely from durable artifact
storage already written by the orchestrator, per this phase's explicit
preference for deriving over duplicating history into a second store.

SCOPE NOTE: this only answers "what versions exist for a KNOWN
artifact_id" -- it deliberately does not attempt "has this catalog
source EVER produced anything," which would require guessing the
evidence-layer `Source` identity (kind/name) an adapter happens to use
internally. That mapping is not uniform across the existing adapters:
`daf.adapters.local_dataset` derives it from the SourceDefinition's own
`name`, while `daf.adapters.arxiv` hardcodes its own `source_name`/
`source_kind` regardless of catalog configuration. Inferring it
generically here would require the catalog/planning layer to reach into
adapter internals -- exactly what `daf.orchestration.orchestrator` is
built to avoid. A caller that needs this already has `artifact_id` on
hand from a prior `AcquisitionResult.artifacts` entry.
"""

from __future__ import annotations

from typing import Tuple

from daf.storage.artifact_store import ArtifactStore
from daf.storage.filesystem_store import FilesystemEvidenceStore


def known_versions(store: FilesystemEvidenceStore, artifact_id: str) -> Tuple[str, ...]:
    """All version_ids known for `artifact_id`, chronological -- a thin
    pass-through to ArtifactStore.list_versions, exposed at the catalog
    layer so callers don't need to reach into daf.storage directly."""
    return ArtifactStore(store).list_versions(artifact_id)


def has_ever_been_acquired(store: FilesystemEvidenceStore, artifact_id: str) -> bool:
    return len(known_versions(store, artifact_id)) > 0
