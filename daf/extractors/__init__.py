"""DAF Extractor implementations.

Each module here implements `scout.interface.Extractor` (unmodified, from
the vendored State-Space repository), transforming one `evidence.types.Record`
into the existing `ExtractionCandidate` shape -- never a new,
DAF-specific normalized-record type.
"""

from __future__ import annotations
