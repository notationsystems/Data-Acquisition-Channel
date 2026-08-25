"""The epistemic boundary layer -- the bottom layer of this repository.

    epistemics/  what class of thing a record is, and which transitions
                 may produce one. Imports ONLY `evidence.identity` from
                 the vendored substrate, plus the standard library.
                 NEVER imports daf, science, boundary, bridge, materials.
        ^   ^
        |   |
     daf/   science/, boundary/, bridge/

WHY A NEW LAYER RATHER THAN A NEW MODULE IN AN EXISTING ONE. The
evidence class is assigned by acquisition (`daf`) and consumed by the
scientific admissibility check (`science`). The existing, AST-asserted
directions are `daf -> evidence` only and `science -> materials,
boundary` only; there is no existing package both may import. Putting
the class in `daf` would make `science` import `daf`; putting it in
`boundary` would make `daf` import `boundary`. Either would change a
verified boundary to avoid adding a layer. `epistemics` is added
BENEATH both instead, so every existing direction is preserved
unchanged and the new one only ever points downward.

`architecture/` holds the canonical YAML this package reads. The YAML is
the source of truth for architectural state; this package is the code
that enforces it; `docs/generated/` is a projection of the YAML and is
authoritative for nothing.
"""

from __future__ import annotations

from epistemics import _vendor as _vendor  # sys.path bootstrap; imports no sibling layer
