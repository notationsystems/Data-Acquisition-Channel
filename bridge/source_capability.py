"""`resolve_sources(intent, capabilities, sources) -> CandidateSource[]`
-- which registered sources could *potentially* satisfy a scientific
requirement.

WHAT THE AUDIT FOUND, before any of this was written:

  * `SourceDefinition.capabilities` ALREADY EXISTS and already means
    something else: it is an ACQUISITION-MODE vocabulary
    (`"incremental"`, `"snapshot"`, `"read"`), and
    `daf/catalog/plan.py:116` reads it to decide whether incremental mode
    is supported. Overloading it with scientific meaning would silently
    change plan validation.
  * `SourceDefinition.configuration` is a free-form mapping that is
    persisted and round-tripped but **never read by any logic**. Hiding
    capability declarations in it would make them untyped, unvalidated,
    and indistinguishable from adapter configuration.
  * No field anywhere records which scientific subjects, properties or
    conditioning contexts a source can supply. Phase 21's finding stands.

WHY THIS LIVES OUTSIDE `SourceDefinition`. Capability metadata is
descriptive catalog state, not part of a source's identity, so it does
not have to be a field on the source at all -- and keeping it separate
buys three things: `daf/` is not modified (no adapter, no catalog, no
serialization change, so existing acquisition behaviour is provably
untouched); a source with no declaration simply has no entry, which is
the correct "unknown" default; and the declaration can name the neutral
scientific vocabulary without `daf` having to import `boundary`, which
would break the dependency direction Phase 21 asserted.

WHY MATCHING IS AGAINST `AcquisitionIntent`, NOT `EvidenceRequirement`.
An `EvidenceRequirement` is a `materials` type. A matcher taking one
would have to import `materials`, and would then be unable to read
`SourceDefinition` -- the same dependency trap Phase 20 and 21 already
navigated. `AcquisitionIntent` is the neutral statement of what evidence
is wanted and already carries exactly the discriminating fields
(`property`, `subject_kind`, `role`, `target_context`), so
`science.acquisition_seam.intent_for` remains the one translation and
this module needs no scientific import at all.

WHAT A MATCH CLAIMS, AND WHAT IT DOES NOT. `resolve_sources` answers
"could this source potentially supply this class of evidence?" It does
NOT answer "will this source produce the requested evidence", and it does
NOT answer "can this context be expressed in this source's request
parameters" -- that second question is `operationalize_intent`'s, and it
is a different question: capability declares the SCIENTIFIC context keys
a source can condition on (`temperature`), while operationalization maps
them onto ACQUISITION parameters (`begin_date`, `station`, `path`).
Keeping them apart is the whole reason a source can be a candidate and
still fail to operationalize.

UNKNOWN IS NOT COMPATIBLE. A source with no `SourceCapability`, or one
declaring nothing, matches nothing. That is the deliberate default: a
source must EARN eligibility by declaring, never inherit it by silence.

NO RANKING. `CandidateSource` carries the reasons a source matched and
no score. Ordering candidates by presumed usefulness would be expected
information gain by another name, which remains `NOT_DETERMINABLE`.
Results are returned in `source_id` order so the output is deterministic
without implying preference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Tuple

from boundary.acquisition_intent import AcquisitionIntent
from daf.orchestration.source_registry import SourceDefinition, SourceNotFoundError, SourceRegistry

# Reasons a source did not match. Reported rather than silently dropped,
# so a caller can tell "no source can do this" from "no source declared".
NOT_REGISTERED = "NOT_REGISTERED"
DISABLED = "DISABLED"
PROPERTY_NOT_DECLARED = "PROPERTY_NOT_DECLARED"
SUBJECT_KIND_NOT_DECLARED = "SUBJECT_KIND_NOT_DECLARED"
ROLE_NOT_DECLARED = "ROLE_NOT_DECLARED"
CONTEXT_KEYS_NOT_DECLARED = "CONTEXT_KEYS_NOT_DECLARED"


@dataclass(frozen=True)
class SourceCapability:
    """What a source declares it can scientifically supply.

    Four dimensions, each included because it was measured to
    discriminate between real sources and real intents:

      properties     `tensile_strength` vs `water_level` -- the coarsest
                     and most obviously necessary filter.
      subject_kinds  `formulation` vs `monitoring_station` vs
                     `earthquake_event`. A source may report a property
                     about one kind of subject and not another.
      roles          OBSERVED vs PREDICTED. Phase 20 produces BOTH kinds
                     of intent for a single criterion, so without this a
                     measurement dataset would be offered as a candidate
                     for a request for a prediction.
      context_keys   the SCIENTIFIC conditioning variables the source can
                     supply evidence under (`temperature`), never its
                     acquisition parameters.

    Every tuple is a positive declaration. An empty tuple means "declares
    none", never "accepts anything"."""

    source_id: str
    properties: Tuple[str, ...] = ()
    subject_kinds: Tuple[str, ...] = ()
    roles: Tuple[str, ...] = ()
    context_keys: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("properties", "subject_kinds", "roles", "context_keys"):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))


@dataclass(frozen=True)
class CandidateSource:
    """One source that could potentially satisfy the intent, with the
    reasons it matched. No score: see the module docstring."""

    source_id: str
    intent_id: str
    matched_property: str
    matched_subject_kind: str
    matched_role: str
    matched_context_keys: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "matched_context_keys", tuple(self.matched_context_keys))


@dataclass(frozen=True)
class CapabilityMismatch:
    """Why a declared source was not a candidate. Returned alongside the
    candidates so "nothing matched" is explainable rather than silent."""

    source_id: str
    intent_id: str
    reasons: Tuple[str, ...]
    missing_context_keys: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "missing_context_keys", tuple(self.missing_context_keys))


@dataclass(frozen=True)
class SourceResolution:
    """One `resolve_sources` call's complete, ordered result."""

    intent_id: str
    candidates: Tuple[CandidateSource, ...]
    mismatches: Tuple[CapabilityMismatch, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "mismatches", tuple(self.mismatches))


def _lookup(sources: SourceRegistry, source_id: str) -> Optional[SourceDefinition]:
    try:
        return sources.get(source_id)
    except SourceNotFoundError:
        return None


def _evaluate(
    intent: AcquisitionIntent, capability: SourceCapability, source: Optional[SourceDefinition]
) -> Tuple[Optional[CandidateSource], Optional[CapabilityMismatch]]:
    reasons = []
    missing_context: Tuple[str, ...] = ()

    if source is None:
        reasons.append(NOT_REGISTERED)
    elif not source.enabled:
        reasons.append(DISABLED)

    if intent.property not in capability.properties:
        reasons.append(PROPERTY_NOT_DECLARED)
    if intent.subject_kind not in capability.subject_kinds:
        reasons.append(SUBJECT_KIND_NOT_DECLARED)
    if intent.role not in capability.roles:
        reasons.append(ROLE_NOT_DECLARED)

    undeclared = tuple(sorted(set(intent.target_context) - set(capability.context_keys)))
    if undeclared:
        reasons.append(CONTEXT_KEYS_NOT_DECLARED)
        missing_context = undeclared

    if reasons:
        return None, CapabilityMismatch(
            source_id=capability.source_id, intent_id=intent.id,
            reasons=tuple(sorted(reasons)), missing_context_keys=missing_context,
        )

    return (
        CandidateSource(
            source_id=capability.source_id,
            intent_id=intent.id,
            matched_property=intent.property,
            matched_subject_kind=intent.subject_kind,
            matched_role=intent.role,
            matched_context_keys=tuple(sorted(intent.target_context)),
        ),
        None,
    )


def resolve_sources(
    intent: AcquisitionIntent,
    capabilities: Iterable[SourceCapability],
    sources: SourceRegistry,
) -> SourceResolution:
    """Deterministic, side-effect-free, read-only. Performs no network
    access, touches no `EvidencePool`, calls no adapter, executes no
    plan, and mutates neither the intent nor the registry.

    A source is a candidate only if it is registered, enabled, and
    positively declares the intent's property, subject kind, role, and
    EVERY key of its conditioning context. A source with no
    `SourceCapability` entry is not considered at all -- silence is not a
    declaration.

    Candidates and mismatches are both returned, each in `source_id`
    order, so that "nothing matched" can be explained."""
    candidates = []
    mismatches = []
    for capability in sorted(capabilities, key=lambda c: c.source_id):
        candidate, mismatch = _evaluate(intent, capability, _lookup(sources, capability.source_id))
        if candidate is not None:
            candidates.append(candidate)
        if mismatch is not None:
            mismatches.append(mismatch)

    return SourceResolution(
        intent_id=intent.id, candidates=tuple(candidates), mismatches=tuple(mismatches)
    )


def capability_index(capabilities: Iterable[SourceCapability]) -> Mapping[str, SourceCapability]:
    """Convenience for callers holding a collection: `source_id` ->
    capability. Later declarations for one source id replace earlier
    ones, which is ordinary mutable-catalog behaviour -- this module adds
    no revision or versioning mechanism, because nothing in the existing
    catalog semantics requires one."""
    return {capability.source_id: capability for capability in capabilities}
