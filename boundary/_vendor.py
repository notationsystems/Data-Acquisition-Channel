"""Path bootstrap for the vendored State-Space repository.

A deliberate seven-line copy of the same bootstrap in `daf/_vendor.py`
and `science/_vendor.py`, for the same reason each of those has its own:
this package must not import either of them. `boundary` is the neutral
layer, and importing `daf` or `science` merely to put a directory on
`sys.path` would make that neutrality false.
"""

from __future__ import annotations

import sys
from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parent.parent / "vendor" / "scout-retrieval-agent"


def ensure_on_path() -> None:
    """Idempotent: safe to call from every entry point."""
    vendor_str = str(VENDOR_ROOT)
    if VENDOR_ROOT.is_dir() and vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)


ensure_on_path()
