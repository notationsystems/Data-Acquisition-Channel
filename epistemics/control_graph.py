"""The substrate control loop, as transitions rather than layer boxes.

    acquisition -> evidence -> observation -> trust -> canonical_state
         ^                                                   |
         |                                                   v
    derived_state <- validation <- retrieval_execution -------+

The correction this module encodes: the substrate's entry is
ACQUISITION, not evidence. A linear stack that starts at evidence has no
way to say where evidence came from, and therefore no way to forbid an
interpretation from becoming its own evidence. A loop does, because the
prohibition is a property of an EDGE -- `derived_state -> evidence` must
not exist -- and edges are only expressible once the graph closes.

The return edge is mandatory and exclusive. Mandatory: derived state must
be able to provoke new acquisition, or the loop is a stack with extra
steps. Exclusive: it must be the ONLY way out of derived state, or the
prohibition is decoration.

WHAT THIS MODULE IS AND IS NOT. It is the graph, its invariants, and the
check that the committed `architecture/control_graph.yaml` states the
same graph. It is NOT a runtime dispatcher: nothing routes through it,
and adding routing would make it a fifth place where the pipeline is
described. The edges are enforced where they actually live -- by the AST
tests named in each transition's `enforced_by`, which prove that no
module outside the acquisition path calls a pool mutator at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Tuple

from epistemics._yaml import loads

ACQUISITION = "acquisition"
EVIDENCE = "evidence"
OBSERVATION = "observation"
TRUST = "trust"
CANONICAL_STATE = "canonical_state"
RETRIEVAL_EXECUTION = "retrieval_execution"
VALIDATION = "validation"
DERIVED_STATE = "derived_state"

STAGES: Tuple[str, ...] = (
    ACQUISITION,
    EVIDENCE,
    OBSERVATION,
    TRUST,
    CANONICAL_STATE,
    RETRIEVAL_EXECUTION,
    VALIDATION,
    DERIVED_STATE,
)

ARCHITECTURE_DIR = Path(__file__).resolve().parent.parent / "architecture"
CONTROL_GRAPH_YAML = ARCHITECTURE_DIR / "control_graph.yaml"


class ControlGraphViolation(ValueError):
    """The graph does not close, or an edge exists that must not."""


@dataclass(frozen=True)
class Transition:
    source: str
    target: str
    via: str
    enforced_by: str
    mandatory: bool = False
    exclusive: bool = False


@dataclass(frozen=True)
class ForbiddenTransition:
    source: str
    target: str
    reason: str
    enforced_by: str


def load_control_graph(path: Path = CONTROL_GRAPH_YAML) -> Tuple[
    Tuple[Transition, ...], Tuple[ForbiddenTransition, ...]
]:
    """Reads the committed canonical graph. The YAML is the source of
    truth; this module is the code that checks it."""
    document = loads(path.read_text())
    transitions = tuple(
        Transition(
            source=t["from"],
            target=t["to"],
            via=t["via"],
            enforced_by=t["enforced_by"],
            mandatory=bool(t.get("mandatory", False)),
            exclusive=bool(t.get("exclusive", False)),
        )
        for t in document["transitions"]
    )
    forbidden = tuple(
        ForbiddenTransition(
            source=f["from"], target=f["to"], reason=f["reason"], enforced_by=f["enforced_by"]
        )
        for f in document["forbidden_transitions"]
    )
    return transitions, forbidden


def out_edges(transitions: Tuple[Transition, ...]) -> Mapping[str, Tuple[str, ...]]:
    edges: Dict[str, Tuple[str, ...]] = {stage: () for stage in STAGES}
    for t in transitions:
        edges[t.source] = edges[t.source] + (t.target,)
    return edges


def validate_control_graph(
    transitions: Tuple[Transition, ...], forbidden: Tuple[ForbiddenTransition, ...]
) -> None:
    """Raises `ControlGraphViolation` on the first failure. Checks, in
    order: every stage is known; the graph is a single cycle covering
    every stage exactly once; acquisition is the only producer of
    evidence; derived state's only exit is the return edge; and no
    forbidden edge is also declared as a transition."""
    known = set(STAGES)
    for t in transitions:
        if t.source not in known or t.target not in known:
            raise ControlGraphViolation(f"unknown stage in transition {t.source} -> {t.target}")

    edges = out_edges(transitions)
    for stage, targets in edges.items():
        if len(targets) != 1:
            raise ControlGraphViolation(
                f"{stage} has {len(targets)} outgoing transitions; the loop requires exactly one"
            )

    # A single cycle covering every stage: walk from acquisition and
    # require exactly len(STAGES) steps to return.
    seen = [ACQUISITION]
    cursor = edges[ACQUISITION][0]
    while cursor != ACQUISITION:
        if cursor in seen:
            raise ControlGraphViolation(f"sub-cycle re-entering {cursor} without closing the loop")
        seen.append(cursor)
        cursor = edges[cursor][0]
    if len(seen) != len(STAGES):
        missing = sorted(set(STAGES) - set(seen))
        raise ControlGraphViolation(f"the loop does not reach every stage; missing {missing}")

    producers = tuple(t.source for t in transitions if t.target == EVIDENCE)
    if producers != (ACQUISITION,):
        raise ControlGraphViolation(
            f"evidence must be produced by acquisition alone; found producers {list(producers)}"
        )

    return_edge = tuple(t for t in transitions if t.source == DERIVED_STATE)
    if len(return_edge) != 1 or return_edge[0].target != ACQUISITION:
        raise ControlGraphViolation("derived_state must have exactly one exit, to acquisition")
    if not (return_edge[0].mandatory and return_edge[0].exclusive):
        raise ControlGraphViolation("the return edge must be declared mandatory and exclusive")

    declared = {(t.source, t.target) for t in transitions}
    for f in forbidden:
        if (f.source, f.target) in declared:
            raise ControlGraphViolation(
                f"{f.source} -> {f.target} is declared both as a transition and as forbidden"
            )
