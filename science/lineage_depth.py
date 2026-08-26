"""Evidence-lineage depth: bounded, recorded, and guarded against chaining.

WHAT THIS CLOSES. `generation_depth_bounded` -- "derivation from
derivation is bounded and the depth is recorded" -- which was measured to
be implemented in NEITHER clause: nothing was bounded and no depth was
recorded. Its status has been `represented_unenforced` since the
correction that found the earlier evidence line proved acyclicity rather
than boundedness.

THE SEMANTIC DOMAIN IS QUOTED, NOT PARAPHRASED, from the invariant:

    "depth is EVIDENCE LINEAGE depth, never computation iteration count.
    A recursive estimator running N iterations over one measurement
    stream is one lineage step, not N. A recursive computation must carry
    stream_identity, window_or_horizon and initialization_provenance
    (measured | computed(prior_id)); where initialization derives from a
    computed prior, lineage depth inherits from that prior."

`stream_identity` is a list here and keeps its recorded name despite
reading singular: the field name comes from the domain as recorded rather
than being tidied, because the record is what the compute layer reads.

THE COMPOSITION GUARD IS THE PART THAT MATTERS. The domain's last clause
covers initialization only, and initialization alone does not close
chaining. A filter initialized from a fresh measured state but CONSUMING
ANOTHER FILTER'S OUTPUT is one lineage step beyond that filter and would
report depth 0 under an initialization-only rule. So depth is the maximum
over BOTH kinds of source -- the initialization prior and every input
stream -- and a computed stream contributes exactly as an initialization
prior does:

    depth = max( init_contribution, max over streams of stream_contribution )

    init_contribution    = 0                     if measured
                         = depth(prior_id) + 1   if computed(prior_id)
    stream_contribution  = 0                     if measured
                         = depth(producer_id)+ 1 if computed(producer_id)

Depth 0 therefore means what it says: initialization measured AND every
input stream measured. Nothing else reaches 0.

WHY A BOUND AT ALL, and why this one is a POLICY rather than a
derivation. Each lineage step moves a result further from measurement and
there is no path back -- a re-derivation cannot recover what an earlier
step discarded. A bound says how many composed computations may stand
between a canonical assertion and the measurement under it. The specific
number is a declared choice and is recorded as one; what the invariant
requires is that a bound EXIST, be enforced, and be recorded per record.

BOUNDARY: pure. This module resolves no ids itself. Depth of a prior is
supplied by a caller-provided lookup, so the rule is testable without a
pool and `science/` keeps its no-`daf` boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Sequence, Tuple

from science.admissibility import Admissibility

#: The declared bound. A POLICY, recorded rather than derived: what the
#: invariant requires is that a bound exist and be enforced, not that this
#: number be provable. Three composed computations may stand between a
#: canonical assertion and its measurement; the fourth must re-ground.
MAX_LINEAGE_DEPTH = 3

MEASURED = "measured"
COMPUTED = "computed"
PROVENANCE_KINDS = (MEASURED, COMPUTED)

#: The four fields a recursive computation declares. Three are named by
#: the semantic domain; `lineage_depth` is the "and the depth is recorded"
#: half of the rule, which nothing carried before.
STREAM_IDENTITY = "stream_identity"
WINDOW_OR_HORIZON = "window_or_horizon"
INITIALIZATION_PROVENANCE = "initialization_provenance"
LINEAGE_DEPTH = "lineage_depth"
RECURSIVE_FIELDS = (STREAM_IDENTITY, WINDOW_OR_HORIZON, INITIALIZATION_PROVENANCE, LINEAGE_DEPTH)

PARTIALLY_DECLARED_RECURSION = "PARTIALLY_DECLARED_RECURSION"
UNTYPED_STREAM_IDENTITY = "UNTYPED_STREAM_IDENTITY"
EMPTY_STREAM_IDENTITY = "EMPTY_STREAM_IDENTITY"
UNTYPED_WINDOW_OR_HORIZON = "UNTYPED_WINDOW_OR_HORIZON"
UNKNOWN_PROVENANCE_KIND = "UNKNOWN_PROVENANCE_KIND"
COMPUTED_PROVENANCE_NAMES_NO_PRIOR = "COMPUTED_PROVENANCE_NAMES_NO_PRIOR"
MEASURED_PROVENANCE_NAMES_A_PRIOR = "MEASURED_PROVENANCE_NAMES_A_PRIOR"
DECLARED_DEPTH_DISAGREES_WITH_LINEAGE = "DECLARED_DEPTH_DISAGREES_WITH_LINEAGE"
LINEAGE_DEPTH_EXCEEDS_BOUND = "LINEAGE_DEPTH_EXCEEDS_BOUND"
UNRESOLVABLE_PRIOR = "UNRESOLVABLE_PRIOR"

#: Resolves a prior record's id to its recorded lineage depth. Raises
#: KeyError for an id it does not know, which this module turns into a
#: refusal rather than letting it escape.
DepthLookup = Callable[[str], int]


@dataclass(frozen=True)
class DepthAccount:
    """Why a record has the depth it has, not merely what the depth is.

    Kept because the failure this bounds is silent: a trajectory drifting
    far from measured input looks exactly like one that has not. A number
    alone cannot be argued with; a number with its contributions can."""

    depth: int
    from_initialization: int
    from_streams: Tuple[Tuple[str, int], ...]

    @property
    def inherited_from_a_stream(self) -> bool:
        """True when a STREAM, not the initialization, set the depth --
        the composition case an initialization-only rule misses."""
        return bool(self.from_streams) and max(
            level for _, level in self.from_streams) > self.from_initialization


def declares_recursion(content: Mapping[str, object]) -> bool:
    """Whether this record claims to be a recursive computation at all.

    Any one of the four fields is a claim. That is deliberate: a record
    declaring some of them and not the rest is refused rather than
    treated as non-recursive, because a partial declaration is how a
    recursive result would otherwise slip through as an ordinary one."""
    return any(field in content for field in RECURSIVE_FIELDS)


def _provenance_reasons(node: object, reasons: List[str]) -> None:
    if not isinstance(node, Mapping):
        reasons.append(UNKNOWN_PROVENANCE_KIND)
        return
    kind = node.get("kind")
    if kind not in PROVENANCE_KINDS:
        reasons.append(UNKNOWN_PROVENANCE_KIND)
        return
    prior = node.get("prior_id")
    if kind == COMPUTED and not (isinstance(prior, str) and prior.strip()):
        reasons.append(COMPUTED_PROVENANCE_NAMES_NO_PRIOR)
    if kind == MEASURED and prior is not None:
        # A measured provenance naming a prior is not a harmless extra
        # field. It is two incompatible claims about where the record
        # came from, and picking either would invent an answer.
        reasons.append(MEASURED_PROVENANCE_NAMES_A_PRIOR)


def _contribution(node: Mapping[str, Any], depth_of: DepthLookup) -> int:
    if node.get("kind") == MEASURED:
        return 0
    return depth_of(str(node["prior_id"])) + 1


def lineage_depth(content: Mapping[str, object], depth_of: DepthLookup) -> DepthAccount:
    """The depth this record's lineage actually has.

    Raises KeyError from `depth_of` for an unresolvable prior; callers
    that want a verdict rather than an exception use
    `recursive_computation_is_depth_bounded`."""
    initialization = content[INITIALIZATION_PROVENANCE]
    assert isinstance(initialization, Mapping)
    from_initialization = _contribution(initialization, depth_of)

    from_streams: List[Tuple[str, int]] = []
    streams = content[STREAM_IDENTITY]
    assert isinstance(streams, Sequence)
    for stream in streams:
        assert isinstance(stream, Mapping)
        stream_id = str(stream.get("stream_id"))
        from_streams.append((stream_id, _contribution(stream, depth_of)))

    depth = max([from_initialization] + [level for _, level in from_streams])
    return DepthAccount(
        depth=depth,
        from_initialization=from_initialization,
        from_streams=tuple(from_streams),
    )


def _structural_reasons(content: Mapping[str, object]) -> List[str]:
    reasons: List[str] = []

    missing = [field for field in RECURSIVE_FIELDS if field not in content]
    if missing:
        reasons.append(PARTIALLY_DECLARED_RECURSION)
        return reasons

    streams = content[STREAM_IDENTITY]
    if not isinstance(streams, (list, tuple)):
        reasons.append(UNTYPED_STREAM_IDENTITY)
    elif not streams:
        # A recursive computation consuming no stream consumes no
        # measurement, which is not a measurement-derived result at all.
        reasons.append(EMPTY_STREAM_IDENTITY)
    else:
        for stream in streams:
            if not isinstance(stream, Mapping):
                reasons.append(UNTYPED_STREAM_IDENTITY)
                continue
            stream_id = stream.get("stream_id")
            if not isinstance(stream_id, str) or not stream_id.strip():
                reasons.append(UNTYPED_STREAM_IDENTITY)
            _provenance_reasons(stream, reasons)

    window = content[WINDOW_OR_HORIZON]
    if window is None or (isinstance(window, str) and not window.strip()):
        # Stated rather than inferred: a filter's horizon is a modelling
        # choice, and an absent one is not "unbounded", it is unstated.
        reasons.append(UNTYPED_WINDOW_OR_HORIZON)

    _provenance_reasons(content[INITIALIZATION_PROVENANCE], reasons)

    declared = content[LINEAGE_DEPTH]
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
        reasons.append(DECLARED_DEPTH_DISAGREES_WITH_LINEAGE)

    return list(dict.fromkeys(reasons))


def recursive_computation_is_depth_bounded(
    content: Mapping[str, object], depth_of: DepthLookup
) -> Admissibility:
    """Whether a recursive computation records a depth that matches its
    lineage and stays within the declared bound.

    A record declaring no recursion at all passes untouched -- this gate
    answers a question about recursive computations and does not restate
    any other gate's question."""
    if not declares_recursion(content):
        return Admissibility(admissible=True, reasons=())

    reasons = _structural_reasons(content)
    if reasons:
        return Admissibility(admissible=False, reasons=tuple(reasons))

    try:
        account = lineage_depth(content, depth_of)
    except KeyError:
        return Admissibility(admissible=False, reasons=(UNRESOLVABLE_PRIOR,))

    if account.depth != content[LINEAGE_DEPTH]:
        reasons.append(DECLARED_DEPTH_DISAGREES_WITH_LINEAGE)
    if account.depth > MAX_LINEAGE_DEPTH:
        reasons.append(LINEAGE_DEPTH_EXCEEDS_BOUND)

    return Admissibility(admissible=not reasons, reasons=tuple(reasons))
