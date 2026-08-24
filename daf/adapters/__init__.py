"""DAF SourceAdapter implementations.

Each module here implements `scout.interface.SourceAdapter` (unmodified,
from the vendored State-Space repository) against one real external
source. Per docs/ARCHITECTURE_RECONNAISSANCE.md section 15, an adapter is
responsible only for acquisition (source access, retrieval, retrieval
metadata, raw content) -- never for identity assignment, canonical-truth
decisions, ModelState construction, or predictive-variable selection.
"""

from __future__ import annotations
