"""The single, shared definition of `artifact_id` -- extracted here
(Phase K) so `daf.storage.artifact_store.ArtifactStore` and
`daf.storage.metadata_index.MetadataIndex` compute it identically
without one importing the other. Not a new identity scheme: this is
exactly the formula `ArtifactStore.artifact_id` has used since Phase C
(`content_hash({"source_id": ..., "locator": ...})`), only relocated so
it has one home instead of being duplicated.
"""

from __future__ import annotations

from evidence.identity import content_hash


def compute_artifact_id(source_id: str, locator: str) -> str:
    return content_hash({"source_id": source_id, "locator": locator})
