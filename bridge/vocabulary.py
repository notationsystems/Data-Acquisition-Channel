"""Explicit, declared alias -> canonical normalization. Not an ontology.

WHAT THE AUDIT FOUND. There is no vocabulary, alias, synonym, canonical
or normalization primitive anywhere in this repository -- not in `daf/`,
`science/`, `boundary/`, `bridge/`, and not in the vendored State-Space
system. What exists instead are repeated refusals to invent one:
`materials/program.py:68` records that `Referent.kind` "has no controlled
vocabulary anywhere", and every DAF extractor docstring declines to
assert a domain ontology. So there was nothing to reuse.

MEASURED LEXICAL DIVERGENCE -- and the honest result. Across every real
source in the repository:

    graph_dataset      property: record-declared (tensile_strength in the
                                 fixtures)
                       subjects: formulation, process
    noaa_water_level_measurements
                       property: water_level
                       subjects: monitoring_station, vertical_datum
                       context:  datum, unit
    arxiv              no property; subjects paper, author
    usgs/edgar/local/incremental
                       no property, no declared subjects

**No two labels in this repository denote the same scientific concept
today.** The two property-emitting sources mean genuinely different
things. Any `UTS -> tensile_strength` mapping used in the tests is
therefore a DELIBERATE PROOF FIXTURE demonstrating the mechanism, not a
production ontology and not a claim about materials science. The
mechanism is still justified: Phase 22 matches by exact string equality
and named this as its own frontier, and independently authored catalogs
will diverge the moment there is more than one author.

WHAT THIS IS NOT (Phase 23 sec.18). No semantic inference, no
hierarchical reasoning, no synonym discovery, no ontology alignment, no
embeddings, no fuzzy matching, no LLM interpretation. Every equivalence
is a line someone wrote down.

IDENTITY WHEN UNMAPPED. `canonical_for` returns the term unchanged when
no mapping declares it. That is what keeps Phase 22's behaviour exactly
intact -- two unmapped terms are compared literally, so `strength` still
does not match `tensile_strength`, and adding this layer changes no
existing match. Unknown stays unknown; silence never broadens a
requirement.

NO CHAINS, BY VALIDATION RATHER THAN BY RESOLUTION. A term that is both
an alias and a canonical target would make the canonical form depend on
where you entered the chain (`UTS -> X` and `X -> tensile_strength` give
`UTS` two different answers). Resolving chains transitively would be
inference; instead `make_vocabulary` REJECTS them. Normalization is
always exactly one hop.

DIRECTION IS ONE-WAY (sec.9). `alias -> canonical` never implies
`canonical -> alias`. Nothing here may be used to generate an acquisition
parameter named `UTS` because a requirement said `tensile_strength`.
Request-parameter translation is `bridge.intent_execution`'s concern and
uses a separate, explicitly caller-supplied mapping.

DIMENSIONS STAY SEPARATE (sec.7). A mapping belongs to exactly one of
`property`, `subject_kind`, `role`, `context_key`. A property alias can
never satisfy a subject-kind comparison, so no cross-dimensional
equivalence can be expressed at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Optional, Tuple

# How a declared pair of terms relates. Phase 24 added this because real
# external evidence forced it: Wikidata lists `elastic modulus` as an
# alias of `Young's modulus` (Q2091584) AND as its own separate concept
# (Q192005). In materials science the second is right -- "elastic
# modulus" is the general family (Young's, shear, bulk), so treating it
# as an equivalence would silently broaden a requirement for Young's
# modulus into any elastic modulus at all.
#
# EXACT_EQUIVALENT mappings canonicalize. RELATED mappings do NOT, and
# never participate in matching -- they are recorded so that a rejected
# equivalence stays visible and inspectable, rather than being deleted
# and re-proposed later by someone reading the same alias list.
EXACT_EQUIVALENT = "EXACT_EQUIVALENT"
RELATED = "RELATED_BUT_NOT_EQUIVALENT"
RELATIONSHIPS = (EXACT_EQUIVALENT, RELATED)

PROPERTY = "property"
SUBJECT_KIND = "subject_kind"
ROLE = "role"
CONTEXT_KEY = "context_key"
DIMENSIONS = (PROPERTY, SUBJECT_KIND, ROLE, CONTEXT_KEY)


class AmbiguousVocabulary(ValueError):
    """Raised when a vocabulary cannot be canonicalized deterministically.

    Reported rather than resolved: picking one interpretation of an
    ambiguous declaration would make the result depend on declaration
    order, which sec.12 forbids."""


@dataclass(frozen=True)
class VocabularyMapping:
    """One declared relationship, in one dimension, in one direction.

    `relationship` defaults to `EXACT_EQUIVALENT`, so every Phase 23
    declaration keeps its meaning unchanged. `evidence` is a free-text
    citation (e.g. `"wikidata:Q76005"`) recording WHERE the relationship
    was established; it is never interpreted, only carried, so a reader
    can re-check the claim rather than trust it."""

    dimension: str
    alias: str
    canonical: str
    relationship: str = EXACT_EQUIVALENT
    evidence: Optional[str] = None

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ValueError(f"dimension must be one of {DIMENSIONS}, got {self.dimension!r}")
        if self.relationship not in RELATIONSHIPS:
            raise ValueError(f"relationship must be one of {RELATIONSHIPS}, got {self.relationship!r}")
        if not self.alias or not self.canonical:
            raise ValueError("alias and canonical must both be non-empty")


@dataclass(frozen=True)
class Vocabulary:
    """A validated set of mappings. Construct with `make_vocabulary`,
    which is the only place ambiguity is checked."""

    mappings: Tuple[VocabularyMapping, ...]
    _by_dimension: Mapping[str, Mapping[str, str]]
    _related: Mapping[str, Mapping[str, Tuple[str, ...]]] = field(default_factory=dict)

    def canonical_for(self, dimension: str, term: str) -> str:
        """The canonical form of `term`, or `term` itself when nothing
        declares it. Exactly one hop -- chains are rejected at
        construction, never followed here."""
        if dimension not in DIMENSIONS:
            raise ValueError(f"dimension must be one of {DIMENSIONS}, got {dimension!r}")
        return self._by_dimension.get(dimension, {}).get(term, term)

    def declares(self, dimension: str, term: str) -> bool:
        """Whether `term` is an alias this vocabulary explicitly maps to
        a canonical form -- distinct from `canonical_for` returning it
        unchanged, and false for a term that is only RELATED."""
        return term in self._by_dimension.get(dimension, {})

    def related_terms(self, dimension: str, term: str) -> Tuple[str, ...]:
        """Terms explicitly declared RELATED_BUT_NOT_EQUIVALENT to
        `term`, in sorted order.

        Purely inspectable: nothing in matching consults this. Acting on
        it would be exactly the silent broadening the relationship exists
        to prevent -- `elastic modulus` is recorded as related to
        `youngs_modulus` precisely so that it never matches it."""
        if dimension not in DIMENSIONS:
            raise ValueError(f"dimension must be one of {DIMENSIONS}, got {dimension!r}")
        return self._related.get(dimension, {}).get(term, ())


def make_vocabulary(mappings: Iterable[VocabularyMapping]) -> Vocabulary:
    """The only supported constructor. Deterministic and
    order-independent: the same set of mappings in any order produces an
    equal `Vocabulary`, and the same conflicts are reported either way.

    Raises `AmbiguousVocabulary` when one alias maps to two different
    canonical terms in the same dimension, or when a term is both an
    alias and a canonical target in the same dimension (a chain).

    Only `EXACT_EQUIVALENT` mappings canonicalize or participate in those
    checks. A `RELATED` declaration is stored for inspection and is never
    a conflict, because it asserts the opposite of an equivalence."""
    ordered = tuple(
        sorted(mappings, key=lambda m: (m.dimension, m.alias, m.canonical, m.relationship))
    )

    related: Dict[str, Dict[str, set]] = {}
    targets: Dict[str, Dict[str, set]] = {}
    for mapping in ordered:
        if mapping.relationship == RELATED:
            related.setdefault(mapping.dimension, {}).setdefault(mapping.alias, set()).add(mapping.canonical)
            related.setdefault(mapping.dimension, {}).setdefault(mapping.canonical, set()).add(mapping.alias)
            continue
        targets.setdefault(mapping.dimension, {}).setdefault(mapping.alias, set()).add(mapping.canonical)

    conflicts = [
        f"{dimension}:{alias} -> {sorted(canonicals)}"
        for dimension, aliases in sorted(targets.items())
        for alias, canonicals in sorted(aliases.items())
        if len(canonicals) > 1
    ]
    if conflicts:
        raise AmbiguousVocabulary(
            "one alias maps to more than one canonical term: " + "; ".join(conflicts)
        )

    by_dimension: Dict[str, Dict[str, str]] = {
        dimension: {alias: next(iter(canonicals)) for alias, canonicals in aliases.items()}
        for dimension, aliases in targets.items()
    }

    chains = [
        f"{dimension}:{term}"
        for dimension, table in sorted(by_dimension.items())
        for term in sorted(set(table) & set(table.values()))
    ]
    if chains:
        raise AmbiguousVocabulary(
            "a term is both an alias and a canonical target, so its canonical form would "
            "depend on where the chain is entered: " + "; ".join(chains)
        )

    return Vocabulary(
        mappings=ordered,
        _by_dimension={dimension: dict(table) for dimension, table in by_dimension.items()},
        _related={
            dimension: {term: tuple(sorted(others)) for term, others in sorted(table.items())}
            for dimension, table in sorted(related.items())
        },
    )


EMPTY_VOCABULARY = make_vocabulary(())
"""The default. Canonicalizes nothing, so resolution behaves exactly as
it did before this layer existed."""
