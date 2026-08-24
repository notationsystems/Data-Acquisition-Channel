"""Path bootstrap for the vendored State-Space repository.

`vendor/scout-retrieval-agent` is a git submodule pinned to a specific
upstream commit of `notationsystems/scout-retrieval-agent` (see
`.gitmodules` and that directory's own git history) -- it is NOT a
pip-installable package: its `pyproject.toml` has no `[build-system]`
table and is scoped only to pytest configuration. Its own test suite
already relies on being run from its repo root with that root on
`sys.path`; this module does the same thing on the DAF's behalf so
`import scout`, `import evidence`, etc. resolve to the vendored code
without copying or modifying a single line of it.

KNOWN LIMITATION (see docs/SCOUT_VERTICAL_SLICE.md "Known limitations"):
the vendored repo's top-level package names (`evidence`, `scout`,
`retrieval`, `core`, `materials`, `morpho`, `backends`, `runtime`,
`workbench`, `experiment`, `adapters`, `tests`) are generic and could
collide with other dependencies in a larger environment. That is an
acceptable trade-off for a single vertical slice proving the acquisition
contract; a real DAF deployment should ask upstream for a
pip-installable, properly namespaced package instead of sys.path
injection of a submodule.
"""

from __future__ import annotations

import sys
from pathlib import Path

VENDOR_ROOT = Path(__file__).resolve().parent.parent / "vendor" / "scout-retrieval-agent"


def ensure_on_path() -> None:
    """Idempotent: safe to call from every DAF entry point and from
    conftest.py without risk of duplicate sys.path entries."""
    vendor_str = str(VENDOR_ROOT)
    if VENDOR_ROOT.is_dir() and vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)


ensure_on_path()
