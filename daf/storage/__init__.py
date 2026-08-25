"""DAF durable acquisition plane (Phase B).

This package persists the acquisition/evidence objects already defined by
the vendored State-Space repository's `evidence.types` -- `Source`,
`Document`, `Record`, `Observation`, `Referent`, `ClaimedRelationship`,
`DerivedValue`, `DerivedGrounding` -- across process restarts. It:

- introduces NO new evidence type, NO new identity scheme, and NO new
  admission path (`evidence.admission` and `scout.pipeline.run_scout`
  are unmodified and untouched by anything here);
- introduces NO execution/operation identity, execution record, or
  authenticity claim (that is explicitly out of scope for this phase --
  see `docs/DAF_DURABLE_STORAGE.md`);
- reuses `evidence.identity.content_hash` for every identity computation
  it performs -- it never mints an id independently.

Module map:

- `serialization`: to_dict/from_dict for each evidence.types object,
  round-tripping through the SAME `make_*` factory used at acquisition
  time so a persisted object's identity is re-verified, never trusted,
  on every read.
- `filesystem_store`: `FilesystemEvidenceStore` -- the actual durable
  substrate, one content-addressed JSON file per object per evidence
  category, atomic writes, conflict/corruption detection.
- `artifact_store`: `ArtifactStore` -- a `Document`-centric convenience
  facade answering "artifact identity vs. version identity vs. content
  identity" explicitly (see its own docstring for the identified gap
  this fills, and why it is a derived, non-authoritative index rather
  than a new evidence type).
- `durable_pool`: `DurablePool`, an `EvidencePool` *subclass* that adds
  a persistence side-effect to the 8 `put_*` methods only -- every read
  method, and every method's existing behavior, is inherited unchanged.
"""

from __future__ import annotations
