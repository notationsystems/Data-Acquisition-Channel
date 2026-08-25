"""The neutral acquisition boundary.

    science/     semantic:  what is unresolved, what evidence would bear
                 on it. Imports `materials`; NEVER imports `daf`.
                     |
                     v  translates a requirement into an intent
    boundary/    NEUTRAL:   what class of evidence is wanted.
                 Imports only `evidence` (the substrate `daf` and
                 `materials` ALREADY share). NEVER imports `materials`,
                 `daf`, or `science`.
                     |
                     v  an operator, scheduler, or DAF reads the intent
    daf/         operational: which source, which adapter, which
                 parameters. NEVER imports `materials`.

This package exists so that neither side has to name the other. A
scientific requirement can be expressed at the acquisition boundary
without `science` knowing that `daf` exists, and an acquirer can read it
without importing `materials` -- which `daf` is AST-verified never to do.

Deliberately NOT here: source ids, adapter ids, URLs, plan ids, query
parameters, schedules, credentials. Those are acquisition decisions, and
an `AcquisitionIntent` that carried them would have made the decision
already.
"""

from __future__ import annotations

from boundary import _vendor as _vendor  # sys.path bootstrap; imports no sibling layer
