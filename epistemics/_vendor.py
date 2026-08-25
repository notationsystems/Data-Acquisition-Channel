"""Path bootstrap for the vendored State-Space repository.

A self-contained copy of the same seven lines `science/_vendor.py` and
`boundary/_vendor.py` already carry, for the same reason they carry them:
`epistemics` must not depend on `daf` in any direction. `daf` imports
`epistemics`, so importing `daf._vendor` here purely for `sys.path`
would close a cycle and falsify the layering assertion in
`tests/test_epistemic_boundary.py`.
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
