"""`resolve_sources(intent, capabilities, sources, vocabulary) ->
CandidateSource[]` -- which registered sources could *potentially*
satisfy a scientific requirement.

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

NORMALIZATION (Phase 23). `vocabulary` canonicalizes both the intent's
terms and the source's declared terms before comparison, so a source
that calls a concept `ultimate_tensile_strength` can answer a
requirement phrased as `UTS` -- but only where someone explicitly
declared that equivalence. It defaults to `EMPTY_VOCABULARY`, which maps
nothing, so omitting it reproduces exact-string matching precisely. The
source's own wording is preserved on every `TermMatch`, never
overwritten.

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
from bridge.vocabulary import (
    CONTEXT_KEY,
    EMPTY_VOCABULARY,
    PROPERTY,
    ROLE,
    SUBJECT_KIND,
    Vocabulary,
)
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
class TermMatch:
    """Why one dimension matched, in all three vocabularies at once
    (Phase 23 sec.5/sec.10):

        requested   what the intent asked for, verbatim
        canonical   what an explicit vocabulary mapping turned it into
                    (equal to `requested` when nothing declares it)
        declared    what the SOURCE called it, verbatim -- never
                    overwritten, so "what did the source call this?" and
                    "what concept did the catalog map it to?" remain
                    separately answerable

    `via_alias` records whether an explicit mapping was actually used on
    either side, so a match by declared alias is distinguishable from a
    match that needed no vocabulary at all."""

    dimension: str
    requested: str
    canonical: str
    declared: str
    via_alias: bool


@dataclass(frozen=True)
class CandidateSource:
    """One source that could potentially satisfy the intent, with the
    reasons it matched. No score: see the module docstring.

    `matched_*` carry the CANONICAL terms; `term_matches` carries the
    full per-dimension explanation including the source's own wording.
    The flat fields are surfaced alongside the embedded object for the
    same ergonomic-access reason every `materials/` layer already does."""

    source_id: str
    intent_id: str
    matched_property: str
    matched_subject_kind: str
    matched_role: str
    matched_context_keys: Tuple[str, ...]
    term_matches: Tuple[TermMatch, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "matched_context_keys", tuple(self.matched_context_keys))
        object.__setattr__(self, "term_matches", tuple(self.term_matches))


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


def _match_term(vocabulary, dimension, requested, declared_terms):
    """One dimension's comparison, performed on CANONICAL forms.

    Both sides are canonicalized independently, so a match can arise from
    an alias on the requirement side, on the source side, or on neither.
    The declared term reported back is the SOURCE's own wording -- the
    one whose canonical form matched -- never the canonical form itself."""
    canonical_request = vocabulary.canonical_for(dimension, requested)
    for declared in declared_terms:
        if vocabulary.canonical_for(dimension, declared) == canonical_request:
            return TermMatch(
                dimension=dimension, requested=requested, canonical=canonical_request,
                declared=declared,
                via_alias=(
                    vocabulary.declares(dimension, requested)
                    or vocabulary.declares(dimension, declared)
                ),
            )
    return None


def _evaluate(
    intent: AcquisitionIntent,
    capability: SourceCapability,
    source: Optional[SourceDefinition],
    vocabulary: Vocabulary,
) -> Tuple[Optional[CandidateSource], Optional[CapabilityMismatch]]:
    reasons = []
    missing_context: Tuple[str, ...] = ()
    term_matches = []

    if source is None:
        reasons.append(NOT_REGISTERED)
    elif not source.enabled:
        reasons.append(DISABLED)

    for dimension, requested, declared_terms, failure in (
        (PROPERTY, intent.property, capability.properties, PROPERTY_NOT_DECLARED),
        (SUBJECT_KIND, intent.subject_kind, capability.subject_kinds, SUBJECT_KIND_NOT_DECLARED),
        (ROLE, intent.role, capability.roles, ROLE_NOT_DECLARED),
    ):
        match = _match_term(vocabulary, dimension, requested, declared_terms)
        if match is None:
            reasons.append(failure)
        else:
            term_matches.append(match)

    undeclared = []
    for context_key in sorted(intent.target_context):
        match = _match_term(vocabulary, CONTEXT_KEY, context_key, capability.context_keys)
        if match is None:
            undeclared.append(context_key)
        else:
            term_matches.append(match)
    if undeclared:
        reasons.append(CONTEXT_KEYS_NOT_DECLARED)
        missing_context = tuple(undeclared)

    if reasons:
        return None, CapabilityMismatch(
            source_id=capability.source_id, intent_id=intent.id,
            reasons=tuple(sorted(reasons)), missing_context_keys=missing_context,
        )

    by_dimension = {match.dimension: match for match in term_matches}
    return (
        CandidateSource(
            source_id=capability.source_id,
            intent_id=intent.id,
            matched_property=by_dimension[PROPERTY].canonical,
            matched_subject_kind=by_dimension[SUBJECT_KIND].canonical,
            matched_role=by_dimension[ROLE].canonical,
            matched_context_keys=tuple(
                match.canonical for match in term_matches if match.dimension == CONTEXT_KEY
            ),
            term_matches=tuple(term_matches),
        ),
        None,
    )


def resolve_sources(
    intent: AcquisitionIntent,
    capabilities: Iterable[SourceCapability],
    sources: SourceRegistry,
    vocabulary: Vocabulary = EMPTY_VOCABULARY,
) -> SourceResolution:
    """Deterministic, side-effect-free, read-only. Performs no network
    access, touches no `EvidencePool`, calls no adapter, executes no
    plan, and mutates neither the intent nor the registry.

    A source is a candidate only if it is registered, enabled, and
    positively declares the intent's property, subject kind, role, and
    EVERY key of its conditioning context. A source with no
    `SourceCapability` entry is not considered at all -- silence is not a
    declaration.

    `vocabulary` (Phase 23) canonicalizes both the intent's terms and the
    source's declared terms BEFORE comparison. It defaults to
    `EMPTY_VOCABULARY`, which canonicalizes nothing -- so without one this
    function behaves exactly as it did before that layer existed, and no
    existing match changes.

    Candidates and mismatches are both returned, each in `source_id`
    order, so that "nothing matched" can be explained."""
    candidates = []
    mismatches = []
    for capability in sorted(capabilities, key=lambda c: c.source_id):
        candidate, mismatch = _evaluate(
            intent, capability, _lookup(sources, capability.source_id), vocabulary
        )
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
