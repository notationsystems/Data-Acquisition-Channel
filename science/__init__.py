"""The scientific-state composition layer.

Sits ABOVE the vendored State-Space system (`materials`, `evidence`) and
BESIDE `daf`, never inside either:

    daf/        acquisition            -- never imports `materials`
                                          (AST-verified since Phase C)
    vendor/     evidence + science     -- vendored, never modified
                                          (see daf/_vendor.py)
    science/    composition over the   -- imports `materials`/`evidence`,
                vendored scientific       NEVER imports `daf`
                layer

This package exists because Phase T needed a representation that is
model-domain specific and independent of DAF, and neither existing home
could hold it: the vendored submodule is modified by nobody ("without
copying or modifying a single line"), and `daf/` is acquisition-only.
"""

from __future__ import annotations

from science import _vendor as _vendor  # sys.path bootstrap; never imports daf
