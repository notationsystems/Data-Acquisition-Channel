"""`intent_for(requirement)` / `intents_for(gap)` -- the one translation
that did not already exist.

WHAT THE AUDIT FOUND ALREADY PRESENT. The step this phase's brief calls
`gap_to_requirement(gap) -> EvidenceRequirement` is ALREADY a field:
`InformationGap.requirements` carries the vendored
`materials.specification.EvidenceRequirement`s verbatim, put there by
`diagnose_information_gap`. Adding a function whose whole body is
`return gap.requirements` would be the thin descriptive wrapper this
project has repeatedly declined, and the vendored
`materials/trajectory.py` declined for the same reason. So it is not
added; `gap.requirements` IS that mapping, and `intents_for` below
consumes it directly.

WHAT WAS ACTUALLY MISSING. `EvidenceRequirement` is a `materials` type,
and `daf` is AST-verified never to import `materials`. So a scientific
requirement could not be READ by an acquiring layer at all -- not because
the semantics were wrong, but because no object existed that both sides
were allowed to name. `boundary.acquisition_intent.AcquisitionIntent` is
that object; this module performs the translation into it.

WHY THE TRANSLATION LIVES HERE AND NOT IN `boundary/`. Deciding which
parts of a requirement constitute the evidence WANTED -- and which parts
are decision thresholds, pool state, or explanations that must NOT cross
the boundary -- is a scientific judgement. `boundary/` stays a neutral
data definition that imports no `materials`; if it performed this
translation it would have to import `materials`, and `daf` could then no
longer read it. The direction is deliberate:

    science  --imports-->  boundary  <--imports--  daf / operator
    science  --imports-->  materials
    daf      --NEVER-->    materials

No layer imports the layer that would create a cycle, and `science` never
imports `daf` in either direction.

BOUNDARY: pure, deterministic, immutable output. No `EvidencePool`
access, no `daf` import, no network, no scheduling, no execution, no
adapter selection, no side effect of any kind. Nothing here mutates the
`InformationGap` or `EvidenceRequirement` passed in.
"""

from __future__ import annotations

from typing import Dict, Tuple

from boundary.acquisition_intent import AcquisitionIntent, make_acquisition_intent
from materials.specification import EvidenceRequirement

from science.information_gap import InformationGap


def intent_for(requirement: EvidenceRequirement) -> AcquisitionIntent:
    """One `EvidenceRequirement` -> one `AcquisitionIntent`.

    Deterministic and pure. Reads exactly four things off the
    requirement -- the subject referent, the property, the role, and the
    criterion's own context -- and deliberately drops the criterion's
    operator/target, the gap category, and every pool-derived field. See
    `boundary.acquisition_intent`'s module docstring for why each is
    excluded rather than merely omitted."""
    return make_acquisition_intent(
        subject_natural_key=requirement.formulation.natural_key,
        subject_kind=requirement.formulation.kind,
        property=requirement.property,
        role=requirement.role,
        target_context=requirement.criterion_context,
    )


def intents_for(gap: InformationGap) -> Tuple[AcquisitionIntent, ...]:
    """Every distinct intent the gap's requirements express, in canonical
    `AcquisitionIntent.id` order.

    Deduplicated by intent id, not by requirement: two requirements that
    want the same class of evidence are ONE thing to acquire, and
    reporting it twice would invite an acquirer to fetch it twice. The
    ordering is content-derived, so it does not depend on the order
    `materials` happened to produce the requirements in."""
    by_id: Dict[str, AcquisitionIntent] = {}
    for requirement in gap.requirements:
        intent = intent_for(requirement)
        by_id.setdefault(intent.id, intent)
    return tuple(intent for _, intent in sorted(by_id.items()))
