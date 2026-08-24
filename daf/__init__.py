"""Data Acquisition Fabric (DAF).

This package is the acquisition/durability layer around the existing
State-Space repository's proven SCOUT evidence-admission contract
(`scout.interface.SourceAdapter` / `scout.interface.Extractor` ->
`scout.pipeline.run_scout` -> `evidence.admission` -> `evidence.pool`).

Importing this package makes the vendored State-Space repository
importable (`scout`, `evidence`, `retrieval`, ...); see `daf._vendor` for
why and its known limitation. The DAF never imports `materials`,
`experiment`, `workbench`, `core`, `morpho`, `backends`, or `runtime` --
see `docs/ARCHITECTURE_RECONNAISSANCE.md` section 15 (coupling
prohibitions) for why.
"""

from __future__ import annotations

from daf import _vendor  # noqa: F401  -- import side effect: vendored repo onto sys.path
