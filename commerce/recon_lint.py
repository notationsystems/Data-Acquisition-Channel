"""Defect class 8 — THE CONSTRAINT THAT WAS MEASURED AND NOT CARRIED.

A constraint is correctly measured, correctly reported, and then not
carried into the design BY THE SAME AGENT THAT MEASURED IT.

THE INSTANCE THAT NAMED IT. A recon probe fetched Quebec's terms of use,
quoted the prohibition on `reproduire, telecharger, stocker` verbatim in
its own `terms` field, and then recommended a daily snapshot-and-diff
store in its `design_consequence` -- in the same report, a few hundred
words apart.

WHY IT IS NOT ANY OF THE SEVEN. Nothing was silently filtered: the
constraint is in the output. The check was not narrower than its claim: it
measured exactly what it said. The example was not vacuous, the
attribution was correct, the context was not severed -- it was on the same
page -- and nothing came back empty. Every existing class describes a
fault in the MEASUREMENT. This one is a fault in the SEAM between a
correct measurement and the design that follows it.

WHY IT RECURS IN MULTI-AGENT WORK SPECIFICALLY. A single agent producing
a finding and a design in one pass has nothing between them: no reviewer,
no interval, and no forcing function that re-reads the constraint section
before writing the recommendation. The measurement is in the context
window and is simply not consulted again. Splitting finding from design
across agents is one fix; this linter is the cheaper one.

WHAT THE DETECTOR ASSERTS, and what it cannot. It reads a record's own
declared `constraints_measured` block and scans every other text field for
the acts that block forbids. It CANNOT tell whether a proposal is
genuinely constrained -- `do not build a local mirror` and `build a local
mirror` both contain "mirror". So it flags CANDIDATES for a reader, and
excludes text that is itself a prohibition. A detector that decided would
be committing the class one level up: acting confidently on a rule it
measured loosely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

#: Language that marks a sentence as FORBIDDING rather than proposing. A
#: hit inside such a sentence is the record obeying the constraint, not
#: breaching it.
_PROHIBITIVE = re.compile(
    r"\b(do not|don't|must not|may not|never|prohibit\w*|forbid\w*|refus\w*|"
    r"without prior authoris|not permitted|is a decision for a person|hold until)\b",
    re.IGNORECASE)

#: Language that marks a sentence as PROPOSING an act.
_PROPOSING = re.compile(
    r"\b(recommend\w*|should|build|construct|create|maintain|store|cache|mirror|"
    r"snapshot|ingest|persist|schedul\w*|nightly|daily)\b",
    re.IGNORECASE)

CONSTRAINT_MEASURED_AND_NOT_CARRIED = "CONSTRAINT_MEASURED_AND_NOT_CARRIED"


@dataclass(frozen=True)
class Constraint:
    """A constraint the record says it measured, and what it forbids."""

    name: str
    quoted: str
    forbids: Tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    """A place the record may propose what it measured as forbidden."""

    constraint: str
    forbidden_term: str
    path: str
    sentence: str


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _walk(node: Any, path: str = "") -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if isinstance(node, str):
        out.append((path, node))
    elif isinstance(node, Mapping):
        for key, value in node.items():
            out.extend(_walk(value, f"{path}/{key}"))
    elif isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
        for index, value in enumerate(node):
            out.extend(_walk(value, f"{path}[{index}]"))
    return out


def constraints_of(record: Mapping[str, Any]) -> Tuple[Constraint, ...]:
    """Read the record's own declared constraints.

    A record with no `constraints_measured` block declares none, which is
    a legitimate state and NOT the same as one that declares an empty
    block. The census below distinguishes them.
    """
    declared = record.get("constraints_measured")
    if not isinstance(declared, Mapping):
        return ()
    out: List[Constraint] = []
    for name, body in declared.items():
        if not isinstance(body, Mapping):
            continue
        forbids = body.get("forbids") or []
        if isinstance(forbids, str):
            forbids = [forbids]
        out.append(Constraint(name=str(name), quoted=str(body.get("quoted", "")),
                              forbids=tuple(str(f) for f in forbids)))
    return tuple(out)


def unheeded(record: Mapping[str, Any]) -> Tuple[Candidate, ...]:
    """Find text in the record proposing an act its own constraints forbid.

    Sentences that are themselves prohibitions are excluded -- a record
    saying `do not build a mirror` contains the word `mirror` and is the
    record working correctly.
    """
    constraints = constraints_of(record)
    if not constraints:
        return ()
    skip = {"constraints_measured"}
    found: List[Candidate] = []
    for path, text in _walk({k: v for k, v in record.items() if k not in skip}):
        for sentence in _sentences(text):
            if _PROHIBITIVE.search(sentence):
                continue
            if not _PROPOSING.search(sentence):
                continue
            for constraint in constraints:
                for term in constraint.forbids:
                    if re.search(rf"\b{re.escape(term)}\w*", sentence, re.IGNORECASE):
                        found.append(Candidate(constraint.name, term, path, sentence.strip()))
    return tuple(found)


@dataclass(frozen=True)
class LintReport:
    record: str
    constraints: int
    candidates: Tuple[Candidate, ...]
    empty_because: str


def lint(name: str, record: Mapping[str, Any]) -> LintReport:
    """Class 7 applied to this linter's own output.

    A clean report is a claim. Three different nothings produce it and the
    reader must be told which: the record declared no constraints, it
    declared some and none was breached, or it declared an EMPTY block --
    which looks clean and has checked nothing.
    """
    constraints = constraints_of(record)
    candidates = unheeded(record)
    if not constraints:
        if isinstance(record.get("constraints_measured"), Mapping):
            because = ("NO_CONSTRAINTS_PARSED: a constraints_measured block is present and "
                       "yielded none. An empty block reads as a clean record and has checked "
                       "nothing.")
        else:
            because = ("NO_CONSTRAINTS_DECLARED: this record declares no measured constraint, so "
                       "the linter had nothing to check. That is not a finding that the recon "
                       "met no constraints -- an unprobed terms page declares none either.")
    elif not candidates:
        because = (f"NO_CANDIDATES: {len(constraints)} declared constraint(s) checked against "
                   "every other text field and no proposing sentence names a forbidden act.")
    else:
        because = f"{len(candidates)} candidate(s) for {CONSTRAINT_MEASURED_AND_NOT_CARRIED}."
    return LintReport(name, len(constraints), candidates, because)


def render(report: LintReport) -> str:
    lines = [f"RECON LINT {report.record} — {report.constraints} constraint(s), "
             f"{len(report.candidates)} candidate(s)"]
    lines.append(f"  {report.empty_because}")
    for candidate in report.candidates:
        lines.append(f"  ! {candidate.constraint} forbids {candidate.forbidden_term!r}, and "
                     f"{candidate.path} proposes:")
        lines.append(f"      {candidate.sentence[:200]}")
    return "\n".join(lines)
