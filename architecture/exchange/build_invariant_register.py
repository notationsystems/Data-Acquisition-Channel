#!/usr/bin/env python3
"""The three-party invariant register, derived.

WHAT A REGISTER IS FOR. `bent: []`, `core_invariants_modified: 0` and
every `extends: core@1.0.0` are claims made RELATIVE TO A CORE. Thirty-two
artifacts in this repository make one. Until the register exists, nothing
answers the prior question: WHOSE invariants, held WHERE, and checkable by
WHOM.

THE THREE PARTIES DO NOT HOLD THE SAME KIND OF SOURCE, and that asymmetry
is the register's first finding rather than an inconvenience to normalize
away:

    DAQ  architecture/invariants.yaml      id + rule + STATUS per entry.
                                           Machine readable. Owned here.
    SCL  native/include/scl/operation.hpp  a numbered contract in a header,
                                           checked by a suite that
                                           enumerates the registry from the
                                           BINARY. No status vocabulary.
                                           Exchanged as
                                           scl_contract_clauses.yaml.
    STE  nowhere in the tree               referenced by NUMBER in the
                                           vendored docs, defined in a
                                           brief this repository does not
                                           hold.

THE CORE PARTY IS THE ONE EVERY `bent: zero` IS ABOUT, and it is the one
with no enumeration. Measured, the vendored docs do not even agree with
themselves on the cardinality: ARCHITECTURE_SPEC.md says "Invariants I1-I8
(see brief)", and PHASE_13 says "all 10 invariants re-verified in Phase
12". Eight or ten, listed neither place.

WHAT THAT DOES AND DOES NOT DO TO `bent: zero`. It does not falsify it. It
relocates its evidence. "Zero core invariants were modified" cannot be
checked against a set nobody enumerates -- but it is ENTAILED by something
stronger that can be checked: the core's bytes are unmodified at the
participating referent. Zero files changed entails zero invariants
changed, whatever they are and however many. The register records the
claim as SUPPORTED BY A DIFFERENT ROUTE THAN ITS WORDING IMPLIES, and
names the route.

JOINED ON THE PARTICIPATING REFERENT. core.yaml declares
submodule_commit PARTICIPATING and version ANNOTATING. This register joins
on the commit and carries the label. Before that declaration existed the
join would have been on a string upstream controls.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from canonical_yaml import canonical_bytes  # noqa: E402

sys.path.insert(0, str(REPO))
from epistemics._yaml import loads  # noqa: E402

CORE = loads((REPO / "architecture" / "core.yaml").read_text())
PROBE = loads((REPO / "architecture" / "_probes" / "generality.yaml").read_text())
INVARIANTS = loads((REPO / "architecture" / "invariants.yaml").read_text())
VENDOR = REPO / CORE["submodule_path"]


# ------------------------------------------------------------ the parties


def gitlink_commit():
    """The commit this repository's tree actually points at."""
    out = subprocess.run(
        ["git", "ls-tree", "HEAD", CORE["submodule_path"]],
        cwd=str(REPO), capture_output=True, text=True,
    )
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return out.stdout.split()[2]


def core_tree_is_unmodified():
    """Whether the vendored tree matches the commit it is pinned to.

    `git submodule status` prefixes a MODIFIED submodule with '+' and an
    out-of-sync one with '-'. A bare hash means the checkout is exactly
    the pinned commit -- which is the observable that carries `bent: zero`.
    """
    out = subprocess.run(
        ["git", "submodule", "status", CORE["submodule_path"]],
        cwd=str(REPO), capture_output=True, text=True,
    )
    if out.returncode != 0 or not out.stdout:
        return None
    return not out.stdout[0] in "+-U"


def ste_invariant_references():
    """Every place the vendored core refers to its own invariants.

    Derived by reading the docs, because there is nothing structured to
    read. What comes back is the evidence for the register's central
    finding, so it is collected rather than asserted."""
    numbered, cardinalities, files = set(), {}, []
    for path in sorted(VENDOR.rglob("*.md")):
        relative = path.relative_to(VENDOR)
        if relative.parts and relative.parts[0] in ("node_modules", ".git"):
            continue
        text = path.read_text(errors="replace")
        if "nvariant" not in text:
            continue
        files.append(str(relative))
        for match in re.finditer(r"\bI(\d{1,2})\b(?:[–—-]I?(\d{1,2}))?", text):
            low = int(match.group(1))
            high = int(match.group(2)) if match.group(2) else low
            if 1 <= low <= high <= 20:
                numbered.update(range(low, high + 1))
        for match in re.finditer(r"\b(\d{1,2})\s+invariants\b", text):
            cardinalities.setdefault(int(match.group(1)), []).append(str(relative))
    return {
        "documents_mentioning_invariants": files,
        "numbers_referenced": sorted(numbered),
        # String keys: the canonical serializer refuses integer keys, and it is
        # right to -- `8:` and `"8":` are the implicit-typing ambiguity the
        # whole exchange format exists to refuse. Caught by the emitter on the
        # first run of this generator.
        "cardinalities_asserted": {
            f"{n}_invariants": sorted(set(w)) for n, w in sorted(cardinalities.items())
        },
        "structured_source_files": sorted(
            str(p.relative_to(VENDOR)) for p in VENDOR.rglob("*.yaml")
        ),
    }



def ste_exchange_register():
    """STE's own EXCHANGE register, if the pinned tree holds one.

    THE INTEROP SURFACE IS THE EXCHANGE DIRECTORY, and that is the whole
    reason this reads there rather than at STE's hand-authored
    architecture files. Measured when the pin moved: of STE's four
    architecture documents, this reader can read exactly one -- the
    exchange register, which the SHARED CANONICAL EMITTER produces. The
    other three use folded block scalars and plain multi-line scalars
    that `epistemics/_yaml.py` does not implement, so a citation pointing
    at them would be a citation nobody here could follow.

    That is not a defect to patch under time pressure. Teaching this
    reader enough YAML to read another repository's hand-authored prose
    was attempted and abandoned: two constructs in, it read two of four
    files correctly and two incorrectly, with nothing to say which --
    partial correctness with silent disagreement, which is the failure
    mode this pair's whole canonicalization effort exists to prevent.
    Recorded in architecture/proof_integrity.yaml instead.

    The exchange surface was built to be byte-agreed between parties.
    Hand-authored internal architecture never was, and citing it would
    quietly widen the contract to documents nobody agreed to keep
    readable."""
    path = HERE.parent.parent / "vendor/scout-retrieval-agent/architecture/exchange/invariant_register.yaml"
    if not path.exists():
        return None
    document = loads(path.read_text())
    rows = document.get("invariants") or []
    return {
        "path": "vendor/scout-retrieval-agent/architecture/exchange/invariant_register.yaml",
        "invariant_count": document.get("invariant_count"),
        "bound_parties": document.get("bound_parties"),
        "rows_present": len(rows),
        "readable_by_this_repositorys_reader": True,
        "why_this_path_and_not_the_architecture_files": (
            "the exchange directory is the interop surface and its artifacts are emitted by the "
            "shared canonical emitter, which both readers agree on. Of STE's four architecture "
            "documents this reader reads exactly one, and it is this one."
        ),
    }


STE = ste_invariant_references()
STE_EXCHANGE = ste_exchange_register()
GITLINK = gitlink_commit()
UNMODIFIED = core_tree_is_unmodified()

DAQ_INVARIANTS = {e["id"]: e for e in INVARIANTS["invariants"]}
STATUS_HISTOGRAM = {}
for entry in DAQ_INVARIANTS.values():
    STATUS_HISTOGRAM[entry["status"]] = STATUS_HISTOGRAM.get(entry["status"], 0) + 1

CLAUSES_PATH = HERE / "scl_contract_clauses.yaml"
SCL = loads(CLAUSES_PATH.read_text()) if CLAUSES_PATH.exists() else None


# ------------------------------------------------------- the extends join


def artifacts_declaring_extends():
    """Every YAML document here whose top-level `extends` names a core.

    PARSED, never grepped. The count recorded in core.yaml was 26 and the
    parsed count is 32: a text search for `extends: core@1.0.0` cannot see
    `"extends": "core@1.0.0"`, which is what the shared canonical emitter
    writes, because it always-quotes. Six artifacts were invisible to the
    count precisely BECAUSE they are the canonically-emitted ones."""
    agreeing, disagreeing = [], []
    for path in sorted(REPO.rglob("*.yaml")):
        relative = path.relative_to(REPO)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        if path == HERE / "invariant_register.yaml":
            # The census does not count itself. Not an ad-hoc exclusion: a
            # census whose value includes its own row reports a number that
            # depends on whether it has been run before rather than on the
            # world, and it would not be a fixed point of its own generator.
            continue
        try:
            document = loads(path.read_text())
        except Exception:
            continue
        if not isinstance(document, dict) or "extends" not in document:
            continue
        (agreeing if document["extends"] == f"core@{CORE['version']}"
         else disagreeing).append(str(relative))
    return agreeing, disagreeing


AGREEING, DISAGREEING = artifacts_declaring_extends()


def bent_zero_claims():
    """Every `Bent: zero` this repository holds, with its document.

    Derived by scanning, so a claim written tomorrow and not accounted for
    here moves this artifact's digest and fails its test."""
    found = []
    for path in sorted((REPO / "docs").rglob("*.md")):
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if re.search(r"\*\*Bent: zero\.?\*\*|(?<![\w])Bent: zero(?![\w])", line):
                found.append({
                    "document": str(path.relative_to(REPO)),
                    "line": number,
                    "text": line.strip()[:180],
                })
    return found


BENT_ZERO = bent_zero_claims()

DOCUMENT = {
    "extends": f"core@{CORE['version']}",
    "artifact": "invariant_register",
    "owner": "daf",
    "purpose": (
        "which party owns which invariants, held where, checkable by whom. Derived, never listed: "
        "every count and every id in this file is read from a source at generation time."
    ),
    "joined_on": {
        "referent": CORE["core_referent"]["participating"],
        "value": CORE["submodule_commit"],
        "gitlink_at_generation": GITLINK,
        "annotating_label_carried": f"core@{CORE['version']}",
        "why_not_the_label": (
            "the version is ANNOTATING -- upstream controls it and it can move without the vendored "
            "code changing. This register would otherwise join three parties on a string one of "
            "them can rewrite. See architecture/core.yaml core_referent."
        ),
    },
    "parties": {
        "daf": {
            "role": "acquisition layer; holds the vendored core",
            "invariant_source": "architecture/invariants.yaml",
            "source_kind": "machine_readable_id_rule_status",
            "invariant_count": len(DAQ_INVARIANTS),
            "status_histogram": STATUS_HISTOGRAM,
            "reachable_from_this_register": True,
        },
        "scl": {
            "role": "compute layer",
            "invariant_source": (SCL["source_of_truth"]["clauses"] if SCL else None),
            "source_kind": "numbered_contract_in_a_header_checked_against_the_binary",
            "invariant_count": (SCL["clause_count"] if SCL else None),
            "status_histogram": None,
            "why_no_status_histogram": (
                "SCL's clauses carry no status vocabulary. A clause has a dedicated test and a "
                "mutation shown to break it, or it does not. Mapping that onto this repository's "
                "status words would make the register join on a term meaning two things."
            ),
            "exchanged_as": "architecture/exchange/scl_contract_clauses.yaml",
            "reachable_from_this_register": SCL is not None,
        },
        "ste": {
            "role": "the core; deterministic-state-architecture, vendored and unmodifiable",
            "invariant_source": (STE_EXCHANGE or {}).get("path"),
            "source_kind": (
                "declared_in_the_counterpartys_exchange_register"
                if STE_EXCHANGE
                else "referenced_by_number_defined_in_a_brief_this_tree_does_not_hold"
            ),
            "invariant_count": (STE_EXCHANGE or {}).get("invariant_count"),
            "status_histogram": None,
            "reachable_from_this_register": bool(STE_EXCHANGE),
            "evidence": STE,
            "exchange_register": STE_EXCHANGE,
            "what_changed_when_the_pin_moved": (
                "at the previous pin this party had no enumeration reachable from here and this "
                "entry recorded that as a measured absence. The pin moved and the enumeration "
                "arrived. The absence was never a claim about what STE's invariants ARE -- only "
                "about what this tree held -- which is why the entry changes without anything "
                "recorded here turning out to have been wrong."
            ) if STE_EXCHANGE else None,
        },
    },
    "the_core_partys_invariants_are_not_enumerated_anywhere_here": {
        "finding": (
            "the party every `bent: zero` is a claim about is the one party with no enumeration. Its "
            "own documents disagree on the cardinality."
        ),
        "cardinalities_found": STE["cardinalities_asserted"],
        "numbers_referenced": STE["numbers_referenced"],
        "the_brief_is_not_in_the_tree": (
            "ARCHITECTURE_SPEC.md says 'Invariants I1-I8 (see brief)'. There is no brief in the "
            "vendored tree, and no YAML of any kind in it."
        ),
    },
    "what_bent_zero_actually_rests_on": {
        "the_claim_as_worded": "zero core invariants required modification",
        "why_it_cannot_be_checked_as_worded": (
            "an unenumerated set has no members to check. A claim quantified over it is not false; "
            "it is unfalsifiable in the form it is written."
        ),
        "the_stronger_observable_that_entails_it": (
            "the core's bytes are unmodified at the participating referent. Zero files changed "
            "entails zero invariants changed, whatever they are and however many -- so the claim is "
            "SUPPORTED, by a different route than its wording implies."
        ),
        "measured_at_generation": {
            "recorded_submodule_commit": CORE["submodule_commit"],
            "gitlink": GITLINK,
            "working_tree_matches_the_pin": UNMODIFIED,
            "modifiable": CORE["modifiable"],
        },
        "checked_as_worded_for_the_first_time": {
            "when": "the pin moved to 5e146d5 and the core party declared its set",
            "the_declared_set": (
                "five canonical-state invariants stated as rules, eleven rows in the "
                "counterparty's exchange register, none contested"
            ),
            "the_result": (
                "SILENCE, NOT CLEANLINESS. Every declared invariant names a subject under core.*, "
                "and no authored package here imports core.* at all. By this repository's own rule "
                "-- admission_reachability.yaml's zero_rate_when_unreachable -- a zero over a "
                "subject nothing reaches is not a measurement."
            ),
            "why_it_is_still_a_real_improvement": (
                "the claim moved from UNFALSIFIABLE to FALSIFIABLE. Before, the set had no members, "
                "so nothing could make it fail. Now it has members and one becomes reachable the "
                "moment any authored module imports its subject. It can fail; today it does not."
            ),
            "what_the_check_found_that_was_not_enforced": (
                "unreachability was only PARTLY checked. epistemics/ had a leaf-layer test "
                "forbidding core, three adapter files had their own, and daf/, science/, bridge/, "
                "boundary/ and assertion/ had none -- so the zero was structural for some packages "
                "and incidental for the rest, with nothing saying which. Coverage specified by "
                "enumeration, inside the check the claim now depends on. Closed as a property over "
                "every authored package, derived rather than listed, and detector-proved."
            ),
            "enforcement": "tests/test_bent_zero_is_checkable.py",
        },
        "what_would_break_the_entailment": (
            "this said a submodule bump, and BOTH HALVES of that turned out differently. The pin "
            "moved 68 commits and the bytes are STILL unmodified -- core/ is byte-identical across "
            "the whole range -- so the entailment did not lapse. And the set is no longer "
            "unenumerated: the core party declared it. What actually breaks the entailment is a "
            "bump that CHANGES core/; what breaks the as-worded check is an authored module "
            "importing core.*. Both are measured now rather than predicted."
        ),
        "what_is_NOT_claimed": (
            "that STE's invariants hold. Nothing here inspects them, because nothing here can. The "
            "claim is that this pair did not modify them."
        ),
    },
    "which_property_set_bent_zero_quantifies_over": {
        "the_question": (
            "`bent: zero` is a claim about a SET of properties, and the generality probe's set has "
            "changed size once. A claim written against the old set and read against the new one is "
            "two different claims wearing the same words."
        ),
        "resolved": True,
        "the_canonical_set_is_the_union_of_both_axes": {
            "observation_properties": list(PROBE["observation_properties"]),
            "computation_properties": list(PROBE["computation_properties"]),
            "total": len(PROBE["observation_properties"]) + len(PROBE["computation_properties"]),
        },
        "the_divergence_measured_in_git": (
            "ca3d0aa recorded the probe at 52 lines with FOUR observation properties and no "
            "computation axis at all; c80a2f0 recorded it at 73 lines, adding recursive_computation "
            "as a COMPUTATION property and an outcome.failed list to go with it. Every `bent: zero` "
            "written before c80a2f0 quantifies over four properties; every one after quantifies "
            "over five. Verified against git in tests/test_invariant_register.py rather than "
            "asserted here."
        ),
        "why_the_axes_are_separate_and_not_merged": (
            "appending recursive_computation to the observation list would have been a category "
            "error -- it is not a property any source's OBSERVATIONS can have. The probe recorded "
            "that reasoning at the time and it is why the set grew a second axis instead of a fifth "
            "member."
        ),
        "what_prevents_it_recurring": (
            "tests/test_generality_probe_gate.py asserts a PARTITION: every property either axis "
            "declares appears in exactly one outcome list, and every outcome-list member is a "
            "declared property. A property added to either axis without a result and a placement "
            "now fails, so the set cannot grow silently underneath a `bent: zero` again."
        ),
    },
    "bent_zero_claims_held_here": {
        "what_they_are": (
            "every `Bent: zero` written in this repository's phase reports is a claim that no CORE "
            "invariant changed -- a claim about STE, the party with no enumeration."
        ),
        "occurrences": BENT_ZERO,
        "count": len(BENT_ZERO),
        "the_property_set_split": (
            "ten of them were written when the generality probe declared FOUR properties; one was "
            "written after it declared five. Same words, two assertions. Which set each quantified "
            "over is verified against git in tests/test_invariant_register.py, not asserted here."
        ),
        "does_the_fifth_property_change_any_of_the_ten": (
            "NO, and this is measured rather than assumed. recursive_computation's verdict was FAIL "
            "and its subject was generation_depth_bounded -- an invariant of THIS repository, not "
            "of the core. The probe recorded core_invariants_modified: 0 for it at the time and "
            "still does: the invariant was declared and never implemented, which is a truthfulness "
            "repair and then an implementation, never a core modification. So the ten verdicts "
            "stand as verdicts."
        ),
        "what_was_wrong_was_not_the_verdicts": (
            "it was that nothing recorded WHICH SET each claim quantified over. A verdict that "
            "happens to survive a change in what it quantifies over is not a verdict that accounted "
            "for the change. All eleven rest on the same byte-identity entailment named above, "
            "which is what actually carries them."
        ),
        "what_stops_it_recurring": (
            "this block is derived by scanning the documents, so a `Bent: zero` written tomorrow "
            "and not accounted for here moves the register's digest and fails its test until "
            "someone re-derives -- which is the point at which they have to say what set they mean."
        ),
    },
    "ste_invariants_reconstruction": {
        "artifact": "architecture/exchange/ste_invariants.yaml",
        "status": "RECONSTRUCTION_NOT_DECLARATION",
        "why_it_is_not_a_declaration": (
            "STE has not declared its invariant set and cannot be made to from here. A set written "
            "about a party by another party is not that party's set."
        ),
        "what_it_measured": (
            "six of the numbers cited in the range are cited INDIVIDUALLY somewhere and can be "
            "reconstructed to varying strength; two appear only inside the range `I1-I8` and cannot "
            "be recovered at all; and the two implied by the competing count of ten are referenced "
            "in no document in the tree."
        ),
        "why_it_cannot_be_written_into_the_core": (
            "modifiable: false, and `bent: zero` is entailed by the core's bytes being unmodified "
            "at the pin. Writing a declaration into the vendored tree would move the pin and "
            "destroy the entailment carrying the claim. It has to come from upstream -- and when it "
            "does, the pin bump re-opens `bent: zero` against a set that is enumerable for the "
            "first time."
        ),
    },
    "extends_join": {
        "artifacts_declaring_the_core": len(AGREEING),
        "artifacts_declaring_a_different_core": DISAGREEING,
        "counted_by": "parsing every YAML document, never by text search",
        "why_that_matters_here": (
            "core.yaml recorded 26. Parsed, it is 32. A search for `extends: core@1.0.0` cannot see "
            "`\"extends\": \"core@1.0.0\"`, which is exactly what the shared canonical emitter "
            "writes -- so the artifacts invisible to the count were the canonically-emitted ones, "
            "the most carefully produced files in the pair."
        ),
    },
    "what_this_register_does_not_do": (
        "it does not reconcile statuses across parties, because there is nothing to reconcile: SCL "
        "has no status vocabulary and STE has no enumeration. The only cross-party status claims "
        "that exist are DAQ invariants cited in SCL-authored artifacts, and those are already "
        "checked by tests/test_cross_repository_claims.py over every document this repository "
        "holds. Adding a second mechanism here would be the parallel architecture this pair has "
        "refused everywhere else."
    ),
}


def _refuse_if_the_pin_and_the_tree_disagree() -> None:
    """A generator that READS the vendored tree may not run while that
    tree and the index disagree about which commit it is.

    WHY, measured rather than anticipated. This generator's output is a
    function of the vendored tree. Running it with the submodule checked
    out at one commit while the index pins another produces an artifact
    derived from a tree state the pin does not name -- self-consistent,
    correctly hashed, and wrong. That state occurred: a suite run against
    an unpinned checkout rewrote both sidecars in this directory, and the
    fixed-point test restored only the artifact, leaving the digests
    bound to bytes no committed pin identifies.

    The general shape is that a VERIFICATION WITH A WRITE SIDE EFFECT
    cannot witness the thing it verifies, because running it changes the
    subject. See architecture/proof_integrity.yaml. This guard closes the
    half that matters here: the generator refuses rather than producing
    an artifact whose provenance nobody can state.

    It fails CLOSED and it fails LOUD, because the alternative -- reading
    the pinned commit's bytes out of git rather than the worktree -- would
    let the generator succeed while silently disagreeing with the tree a
    reader is looking at.
    """
    import subprocess

    repo_root = HERE.parent.parent
    status = subprocess.run(
        ["git", "submodule", "status", "vendor/scout-retrieval-agent"],
        cwd=str(repo_root), capture_output=True, text=True, timeout=60,
    )
    if status.returncode != 0 or not status.stdout:
        return  # no git here; nothing to disagree with
    marker = status.stdout[0]
    if marker in "+-U":
        raise SystemExit(
            f"REFUSING to generate: the vendored tree and the index disagree "
            f"({status.stdout.strip()!r}).\n"
            "This generator reads that tree, so running now would produce an artifact derived "
            "from a commit the pin does not name -- correctly hashed and wrong.\n"
            "Check the submodule out at the pinned commit, or bump the pin deliberately, then "
            "re-run."
        )

if __name__ == "__main__":
    _refuse_if_the_pin_and_the_tree_disagree()
    payload = canonical_bytes(DOCUMENT)
    (HERE / "invariant_register.yaml").write_bytes(payload)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    (HERE / "invariant_register.sha256").write_text(digest + "\n")
    print("wrote invariant_register.yaml")
    print(f"  daf {len(DAQ_INVARIANTS)} invariants | "
          f"scl {SCL['clause_count'] if SCL else '-'} clauses | ste none enumerated")
    print(f"  extends join: {len(AGREEING)} agreeing, {len(DISAGREEING)} disagreeing")
    print(f"  core unmodified at {GITLINK}: {UNMODIFIED}")
    print(" ", digest)
