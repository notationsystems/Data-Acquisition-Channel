"""Path bootstrap for the vendored State-Space repository.

Deliberately a self-contained copy of `daf/_vendor.py`'s few lines
rather than an import of it. `science` must not depend on `daf` in any
direction -- that independence is the point of this package existing
separately, and `tests/test_state_gap_frontier.py` enforces it at the
AST level. Importing `daf._vendor` purely for `sys.path` would make that
assertion false for a reason that has nothing to do with acquisition,
and the honest fix is these seven lines, not a weakened assertion.
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
