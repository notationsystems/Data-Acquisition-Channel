"""`AcquisitionIntent` -- the smallest statement of WHAT CLASS OF EVIDENCE
is wanted, expressed without naming how to get it.

WHY THIS OBJECT EXISTS, from the two ends it joins:

    materials.specification.EvidenceRequirement   (semantic)
        formulation, property, criterion, criterion_context, role,
        category, existing_evidence_ids, provenance_observation_id_sets,
        available_contexts, matching_contexts, description

    daf.catalog.plan.AcquisitionPlan               (operational)
        plan_id, source_id, parameters, schedule, mode, interval_seconds

Nothing stood between them. The first is a materials type that `daf` is
AST-verified never to import; the second names a `source_id` and adapter
`parameters`, which is a decision already made. An `AcquisitionIntent` is
what a scientific layer can say and an acquiring layer can read without
either importing the other.

FIELD DERIVATION -- every field is here because an acquirer cannot choose
a mechanism without it, and nothing is here for descriptive completeness:

  subject_natural_key / subject_kind
      WHICH referent the evidence must concern. Taken from
      `EvidenceRequirement.formulation` (a `Referent`), reduced to its
      natural key and kind so this object carries no evidence type.
  property
      WHAT quantity. Verbatim from the requirement.
  role
      OBSERVED or PREDICTED. This genuinely changes which mechanism can
      satisfy the intent -- a measurement source cannot supply a
      prediction -- so it is not cosmetic.
  target_context
      UNDER WHAT CONDITIONS, from `EvidenceRequirement.criterion_context`
      (e.g. `{"temperature": 25, "temperature_unit": "C"}`). Two intents
      differing only in context are different intents, because evidence
      gathered under one condition does not answer the other.

DELIBERATELY ABSENT, each for a stated reason:

  the criterion's operator/target (">= 80")
      That is the DECISION THRESHOLD, not the evidence wanted. A source
      does not filter measurements by whether they pass; the threshold is
      applied afterwards, by `materials.decision`. Carrying it here would
      push a scientific decision into the acquisition boundary.
  gap category (MEASUREMENT_CONFLICT, MISSING_EVIDENCE, ...)
      It explains WHY the gap exists, not what to acquire. An acquirer
      does the same thing either way: obtain evidence of this property,
      about this subject, under this context.
  existing_evidence_ids / provenance_observation_id_sets
      Pool state. Leaking it here would make the boundary depend on which
      evidence store the requirement was computed against.
  source_id, adapter_id, url, plan_id, parameters, schedule
      Acquisition decisions. An intent that named them would not be an
      intent.

IDENTITY is `evidence.identity.content_hash` over exactly the fields
above -- the same content-addressed discipline every other identity in
this repository uses, reused rather than re-derived. Two requirements
that want the same class of evidence therefore produce the SAME intent
id, which is what makes "different mechanisms may satisfy one intent"
checkable.

BOUNDARY: imports only `evidence.identity`, which `daf` and `materials`
both already depend on. No `materials`, no `daf`, no `science` import
anywhere in this package; no I/O, no network, no execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from evidence.identity import content_hash

OBSERVED = "OBSERVED"
PREDICTED = "PREDICTED"


@dataclass(frozen=True)
class AcquisitionIntent:
    """Immutable. `target_context` is wrapped read-only on construction,
    the same protection every `Mapping` field in this codebase already
    gets."""

    id: str
    subject_natural_key: str
    subject_kind: str
    property: str
    role: str
    target_context: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_context", MappingProxyType(dict(self.target_context)))


def make_acquisition_intent(
    *,
    subject_natural_key: str,
    subject_kind: str,
    property: str,
    role: str,
    target_context: Mapping[str, object],
) -> AcquisitionIntent:
    """The only supported way to construct an `AcquisitionIntent` --
    keyword-only, so a caller cannot silently transpose two same-typed
    string fields. Deterministic: identical arguments always produce an
    identical `id`, independent of mapping insertion order."""
    intent_id = content_hash(
        {
            "subject_natural_key": subject_natural_key,
            "subject_kind": subject_kind,
            "property": property,
            "role": role,
            "target_context": dict(sorted(target_context.items())),
        }
    )
    return AcquisitionIntent(
        id=intent_id,
        subject_natural_key=subject_natural_key,
        subject_kind=subject_kind,
        property=property,
        role=role,
        target_context=target_context,
    )
