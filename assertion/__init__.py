"""The canonical-assertion admissibility boundary -- the one place
acquired evidence and scientific admissibility judgment meet.

    daf/       acquires evidence            never imports science
    science/   judges admissibility         never imports daf
        \\           /
         assertion/       imports BOTH -- the only package that may

WHY A NEW PACKAGE, RATHER THAN PUTTING THIS IN `daf` OR `science`.
`science/admissibility.py`'s own docstring already names the gap this
package closes: "these are ADMISSIBILITY validators the scientific layer
applies to already-admitted evidence, not an ingest gate... inadmissible
evidence still exists in the pool; it is refused for canonical
assertion." Nothing before this phase ever DID that application. It
could not live in `daf` (`daf` never imports `science` -- AST-verified
since Phase C) or in `science` (`science` never imports `daf`, so it has
no way to reach a pool). Exactly the same reasoning that added
`epistemics/` beneath both layers in Phase 25 applies here, above both:
a new package is added rather than an existing verified boundary being
widened to accommodate a capability neither side is allowed to have.

WHAT THIS PACKAGE IS NOT. It is not a second evidence system, not a
second metrics system, and not a second Quarantine. It calls the
existing `science.admissibility` functions UNCHANGED, retains refusals
through the existing `daf.execution.quarantine.QuarantineRecord`/
`QuarantineStore` types UNCHANGED, and produces a metrics VIEW (no new
identity, never persisted) in the same derived-view style
`daf/execution/metrics.py` already established. See
`architecture/property_admissibility.yaml` for what is and is not wired.

Nothing outside this package and its own tests may import it: `daf`,
`science`, `boundary`, `bridge`, and `epistemics` must never import
`assertion`, or the one-directional composition this package exists to
provide would become a cycle.
"""

from __future__ import annotations
