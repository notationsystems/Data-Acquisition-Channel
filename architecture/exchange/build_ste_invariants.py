#!/usr/bin/env python3
"""STE's invariant set, RECONSTRUCTED -- and the word matters.

WHAT THIS IS NOT. It is not STE's declaration of its own invariants. STE
has not made one, cannot be made to make one from here, and a set written
about a party by another party is not that party's set. This pair already
refused the equivalent move once, when a decision authored with write
access to one side and read-only to the other was demoted to a proposal
because holding both pens is not two parties agreeing.

WHY IT EXISTS ANYWAY. The register found that the party every `bent: zero`
is about is the one with no enumeration, and that its own documents
disagree on the cardinality. Reconstructing what the documents DO
constrain is the difference between "unenumerated" as a verdict and
"unenumerated" as a measurement: it says which invariants are recoverable,
which are not, and exactly how much of the claim rests on text nobody in
this pair holds.

WHY IT CANNOT BE WRITTEN INTO STE. `architecture/core.yaml` records
`modifiable: false` -- the vendored system is used without copying or
modifying a single line -- and `bent: zero` is currently entailed by the
core's bytes being unmodified at the pinned commit. Writing a declaration
INTO the vendored tree would move the pin and destroy the entailment that
carries the claim. The declaration has to come from upstream, and when it
does, the pin bump re-opens `bent: zero` against a set that is for the
first time enumerable -- which is the payoff, not the problem.

DERIVED: the reference index below is scanned out of STE's own documents
at the pinned commit. The reconstruction of what each number MEANS is
inference from those references and is labelled as inference, per item,
with what would refute it.
"""

from __future__ import annotations

import collections
import hashlib
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))

from canonical_yaml import canonical_bytes  # noqa: E402
from epistemics._yaml import loads  # noqa: E402

CORE = loads((REPO / "architecture" / "core.yaml").read_text())
VENDOR = REPO / CORE["submodule_path"]


def reference_index():
    """Every place STE's documents cite a numbered invariant.

    The index is the evidence. Nothing below is remembered: if a citation
    disappears upstream, this file stops claiming it."""
    index = collections.defaultdict(list)
    ranges = []
    for path in sorted(VENDOR.rglob("*.md")):
        relative = path.relative_to(VENDOR)
        if relative.parts and relative.parts[0] in (".git", "node_modules"):
            continue
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            # Ranges are collected FIRST and then MASKED OUT of the line, so a
            # bare `I1` inside `I1-I8` is not counted as an individual citation.
            # Measured before the mask existed: I1 appeared to have a citation
            # of its own, and its only appearance in the tree is inside that
            # range. An index that inflates the evidence for the invariant it
            # is least able to recover is worse than no index.
            masked = line
            for match in re.finditer(r"\bI(\d{1,2})\s*[–—-]\s*I?(\d{1,2})\b", line):
                low, high = int(match.group(1)), int(match.group(2))
                if 1 <= low < high <= 20:
                    ranges.append({
                        "document": str(relative), "line": number,
                        "range": f"I{low}-I{high}", "text": line.strip()[:200],
                        "covers": [f"I{n}" for n in range(low, high + 1)],
                    })
                    masked = masked.replace(match.group(0), " " * len(match.group(0)))
            for match in re.finditer(r"\bI(\d{1,2})\b", masked):
                value = int(match.group(1))
                if 1 <= value <= 20:
                    index[value].append({
                        "document": str(relative), "line": number,
                        "text": line.strip()[:200],
                    })
    return {f"I{k}": v for k, v in sorted(index.items())}, ranges


def cardinalities():
    found = collections.defaultdict(list)
    for path in sorted(VENDOR.rglob("*.md")):
        relative = path.relative_to(VENDOR)
        if relative.parts and relative.parts[0] in (".git", "node_modules"):
            continue
        text = path.read_text(errors="replace")
        for match in re.finditer(r"\b(\d{1,2})\s+invariants\b", text):
            found[int(match.group(1))].append(str(relative))
    return {f"{k}_invariants": sorted(set(v)) for k, v in sorted(found.items())}


INDEX, RANGES = reference_index()
CARDINALITIES = cardinalities()

#: What each number is CONSTRAINED to mean by the citations above. Every
#: entry names what would refute it, because an inference presented
#: without its defeater reads as a finding.
RECONSTRUCTION = {
    "I1": {
        "recoverable": False,
        "reconstruction": None,
        "why_not": (
            "cited only inside the range `I1-I8`, never individually. The sentence carrying that "
            "range constrains the RANGE as a whole -- arrows point strictly downward/rightward "
            "from canonical state, and the only path back is the feedback loop through "
            "schema/validation -- so I1 is somewhere in that idea and nothing narrows it further."
        ),
    },
    "I2": {
        "recoverable": False,
        "reconstruction": None,
        "why_not": "same as I1: cited only inside the range, never individually.",
    },
    "I3": {
        "recoverable": "partially",
        "reconstruction": (
            "validation is what produces canonical truth: a candidate delta becomes canonical state "
            "only by passing schema/validation, and representation metadata is never admitted into "
            "CanonicalState, Version or ProjectedState."
        ),
        "cited_with": ["I4", "I8"],
        "what_would_refute_it": (
            "a citation of I3 on a statement about something other than admission-through-validation."
        ),
    },
    "I4": {
        "recoverable": "partially",
        "reconstruction": (
            "relationships are EXPLICIT ONLY. `CanonicalState.edges` carries `EdgeRecord`s that were "
            "stated, never inferred; inference is marked downstream in Morpho as "
            "`is_canonical`/`inference_status` rather than folded back into canonical state."
        ),
        "cited_with": ["I3"],
        "what_would_refute_it": "a citation of I4 on a non-edge, non-relationship statement.",
    },
    "I5": {
        "recoverable": True,
        "reconstruction": (
            "IDENTITY IS THE FIELD NAME, NEVER THE VALUE. `Field.id == field_name` and equals its "
            "own dict key; `Entity.id` is unchanged by value changes; every downstream identity "
            "(geometry_id, visual_id, node_id, cell_id) is a function of that same string. In v1 "
            "the id does not change."
        ),
        "citations": 6,
        "what_would_refute_it": (
            "nothing in the index: this is the one number cited enough times, in enough distinct "
            "statements, to be pinned rather than inferred."
        ),
    },
    "I6": {
        "recoverable": True,
        "reconstruction": (
            "determinism of projection, RELATIVE TO THE COMPILER: the same canonical version plus "
            "the same compiler_version yields the same projection. compiler_version is always "
            "present, and the spec says so explicitly -- 'this is what makes I6 checkable'."
        ),
        "cited_with": ["I7"],
        "what_would_refute_it": "a citation of I6 on a statement not about reproducible projection.",
    },
    "I7": {
        "recoverable": "partially",
        "reconstruction": (
            "byte-identity of the projection, the stronger form beside I6: same version in, "
            "byte-identical ProjectedState out, always. Cited only jointly with I6, so which half "
            "of that sentence is I6 and which is I7 is inference."
        ),
        "cited_with": ["I6"],
        "what_would_refute_it": (
            "any individual citation of I7. There is none, which is why the split between I6 and I7 "
            "is the weakest reconstruction here that is offered at all."
        ),
    },
    "I8": {
        "recoverable": "partially",
        "reconstruction": (
            "representation stays in the renderer. THREE.* objects live in the renderer runtime "
            "only, and backend/layout configuration is not part of CanonicalState at all."
        ),
        "cited_with": ["I3"],
        "what_would_refute_it": "a citation of I8 on a statement about canonical state itself.",
    },
}

REFERENCED = sorted(int(k[1:]) for k in INDEX)
COVERED_BY_A_RANGE = sorted({int(n[1:]) for r in RANGES for n in r["covers"]})
ONLY_INSIDE_A_RANGE = [n for n in COVERED_BY_A_RANGE if n not in REFERENCED]
RECONSTRUCTED = sorted(int(k[1:]) for k in RECONSTRUCTION)
ASSERTED_MAX = max((int(k.split("_")[0]) for k in CARDINALITIES), default=0)
UNACCOUNTED = [n for n in range(1, ASSERTED_MAX + 1) if n not in REFERENCED]

DOCUMENT = {
    "extends": f"core@{CORE['version']}",
    "artifact": "ste_invariants",
    "owner": "ste",
    "authored_by": "daf",
    "status": "RECONSTRUCTION_NOT_DECLARATION",
    "what_status_means": (
        "STE has not declared its invariant set. This is what its own documents CONSTRAIN, "
        "reconstructed by another party, and it must never be cited as STE's own statement. A set "
        "written about a party by another party is not that party's set -- the same reason a "
        "decision authored with both pens was demoted to a proposal in this pair's own history."
    ),
    "measured_at": {
        "submodule_commit": CORE["submodule_commit"],
        "referent_kind": CORE["core_referent"]["participating"],
        "modifiable": CORE["modifiable"],
    },
    "why_it_cannot_be_written_into_ste": (
        "core.yaml records modifiable: false, and `bent: zero` is currently entailed by the core's "
        "bytes being unmodified at the pinned commit. A declaration written INTO the vendored tree "
        "would move the pin and destroy the entailment that carries the claim. It has to come from "
        "upstream."
    ),
    "the_cardinality_conflict": {
        "asserted_in_documents": CARDINALITIES,
        "ranges_cited": RANGES,
        "numbers_cited_individually": REFERENCED,
        "numbers_covered_only_by_a_range": ONLY_INSIDE_A_RANGE,
        "referenced_nowhere_at_all": [
            n for n in range(1, ASSERTED_MAX + 1)
            if n not in REFERENCED and n not in COVERED_BY_A_RANGE
        ],
        "what_it_means": (
            "the spec cites the range I1-I8; a later phase document says all 10 invariants were "
            "re-verified. The numbers in the gap are cited nowhere at all, so the larger count is "
            "not merely unenumerated -- it names invariants no document in the tree ever mentions "
            "again."
        ),
    },
    "reconstruction": RECONSTRUCTION,
    "recoverability": {
        "fully": sorted(k for k, v in RECONSTRUCTION.items() if v["recoverable"] is True),
        "partially": sorted(k for k, v in RECONSTRUCTION.items() if v["recoverable"] == "partially"),
        "not_at_all": sorted(k for k, v in RECONSTRUCTION.items() if v["recoverable"] is False),
        "the_honest_summary": (
            "two of eight are pinned by their citations, four are inferred from joint citations and "
            "say what would refute them, and two cannot be recovered at all -- they are cited only "
            "inside a range. Nothing above is offered as STE's meaning; it is offered as the most "
            "the documents constrain."
        ),
    },
    "reference_index": INDEX,
    "the_request_to_ste": {
        "one": "declare the invariant set in a file the repository holds, ids and rules, one entry each.",
        "two": (
            "resolve the cardinality: eight or ten. If ten, the two beyond the cited range have "
            "never appeared in any document here."
        ),
        "three": (
            "re-run the generality probe against the FIVE-property canonical set -- four observation "
            "properties plus recursive_computation -- because every `bent: zero` recorded in this "
            "pair before c80a2f0 quantified over four."
        ),
        "there_is_no_counterparty_response_and_this_file_does_not_pretend_one": (
            "scl_requirements.yaml has daq_requirement_response.yaml beside it because there was a "
            "party to answer. There is none here. This request stands unanswered and is recorded as "
            "unanswered rather than as an agreement."
        ),
    },
}

if __name__ == "__main__":
    payload = canonical_bytes(DOCUMENT)
    (HERE / "ste_invariants.yaml").write_bytes(payload)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    (HERE / "ste_invariants.sha256").write_text(digest + "\n")
    print("wrote ste_invariants.yaml")
    print("  referenced:", REFERENCED, "| cardinalities:", list(CARDINALITIES))
    print("  only inside a range:", ONLY_INSIDE_A_RANGE)
    print("  referenced nowhere at all:", [
        n for n in range(1, ASSERTED_MAX + 1)
        if n not in REFERENCED and n not in COVERED_BY_A_RANGE])
    print(" ", digest)
