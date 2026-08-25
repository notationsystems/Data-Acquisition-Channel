"""The execution bridge -- the application layer that may name both sides.

    science/     semantic     imports materials, boundary; NEVER daf
    boundary/    neutral      imports only `evidence`; names no domain layer
    bridge/      APPLICATION  imports boundary + daf; NEVER materials/science
    daf/         operational  imports evidence; NEVER materials

`bridge` is deliberately the ONE package allowed to see an
`AcquisitionIntent` and an `AcquisitionPlan` at the same time. That is
what an operationalization step is: a decision that belongs to neither
the scientific layer (which must not choose sources) nor the acquisition
layer (which must not read scientific requirements).

It does NOT import `materials` or `science`. It does not need to: an
`AcquisitionIntent` is already the neutral statement of what evidence is
wanted, so the bridge never touches a `ModelState`, an
`EvidenceRequirement`, or an `EvidencePool`.
"""

from __future__ import annotations
