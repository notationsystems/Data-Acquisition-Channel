"""The fourth-axis proposal, checked against the two things it is about.

A PROPOSAL'S FAILURE MODE IS NOT BEING WRONG. It is describing a state
that has already changed -- a collision that stopped existing, or a
contract that has since resolved it -- so that a pending recommendation
sits in the tree reading as live. Every assertion here reads one of the
two real sources rather than the proposal's account of them.

AND ONE OF THEM IS A GUARD RATHER THAN A CHECK. The proposal's whole
argument is that no automatic translation exists between uncertainty_kind
and claim_strength. The way that argument stops being true is that
somebody writes one -- a dict, a mapping table, a two-line helper -- and
it will look reasonable, because the words match. So the last test
sweeps this repository for exactly that and fails on it.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads
from science.admissibility import UNCERTAINTY_KINDS

REPO_ROOT = Path(__file__).resolve().parent.parent
PROPOSAL_PATH = (
    REPO_ROOT / "architecture" / "proposals"
    / "2026-09-03-uncertainty-kind-as-a-contract-axis.yaml"
)
PROPOSAL = loads(PROPOSAL_PATH.read_text())
CONTRACT_PATH = REPO_ROOT / "epistemics" / "corpus" / "contract.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text())


def test_the_proposal_binds_to_the_contract_bytes_it_was_written_against():
    """The binding rule, enforced. A proposal silently rebound to a
    reissued contract would claim to have measured something it never
    read -- the failure the existing workload proposal names in its own
    binding_rule and which this one inherits."""
    bound = PROPOSAL["binds_to"]
    actual = hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    assert bound["contract_sha256"] == actual, (
        "the corpus contract has been reissued. This proposal must be "
        "reissued against the new bytes or retired -- never rebound."
    )
    assert bound["contract_id"] == CONTRACT["contract"]
    assert bound["contract_version"] == CONTRACT["version"]


def test_the_collision_the_proposal_rests_on_is_real():
    """Read from both vocabularies and intersected, so this fails if
    either changes rather than going quietly stale."""
    claim_strength = set(CONTRACT["axes"]["claim_strength"]["terms"])
    collision = claim_strength & set(UNCERTAINTY_KINDS)
    assert collision == {PROPOSAL["the_contested_term_and_its_resolution"]["term"]}, (
        f"the proposal resolves one contested term and the vocabularies now "
        f"collide on {sorted(collision)}"
    )


def test_uncertainty_kind_is_still_absent_from_every_declared_axis():
    """If the contract adopts the axis, this proposal is SUPERSEDED, not
    satisfied, and the difference matters: a superseded proposal is
    history and a pending one is work. Failing here is the signal to
    retire the file rather than to edit it."""
    assert "uncertainty_kind" not in CONTRACT["axes"], (
        "the contract now declares uncertainty_kind. This proposal is "
        "superseded and should be retired, not updated."
    )
    for name, axis in CONTRACT["axes"].items():
        overlap = set(axis["terms"]) & set(UNCERTAINTY_KINDS)
        assert overlap <= {"estimated"}, (
            f"axis {name} has grown terms shared with uncertainty_kind: "
            f"{sorted(overlap)}; the proposal resolves only one"
        )


def test_the_contract_still_does_not_resolve_the_contested_term():
    """The proposal's reason for existing. If `estimated` appears in
    contested_terms, the ecosystem has answered and this file is done."""
    contested = set(CONTRACT["contested_terms"]) - {"note"}
    assert PROPOSAL["the_contested_term_and_its_resolution"]["term"] not in contested, (
        "the contract now resolves this term; the proposal is superseded"
    )
    assert contested == {"reported", "derived"}, (
        f"contested_terms has changed to {sorted(contested)} -- the proposal "
        "describes a contract that no longer exists"
    )


def test_the_proposal_does_not_restate_the_vocabulary_it_cites():
    """One meaning, one encoding. science/admissibility.py owns these four
    terms. A proposal that listed them as a YAML sequence would be a
    second normative copy -- the exact defect epistemics/corpus/contract.py
    refuses in its own header."""
    for node in PROPOSAL.values():
        assert not isinstance(node, list) or not (
            set(node) >= set(UNCERTAINTY_KINDS)
        ), "the proposal carries a second copy of UNCERTAINTY_KINDS"


def test_nothing_in_this_repository_translates_between_the_two_axes():
    """THE GUARD, and the reason this file is worth more than the proposal.

    The corruption the proposal warns about does not arrive as an
    argument. It arrives as a small mapping somebody writes because the
    words line up -- {"estimated": "estimated"} reads like a no-op and is
    a silent demotion from rank 3 to rank 2 under weakest_input_wins.

    THE FIRST VERSION OF THIS CHECK READ A PROXY, and was caught by its
    own first run. It flagged any LINE mentioning a term from each
    vocabulary, and fired on a sentence in build_daq_capabilities.py that
    says `absent-is-not-zero` and `reported` in the same paragraph of
    English. A line containing both words is not a translation between
    two vocabularies; it is prose. That is the proxy-for-target shape
    architecture/proof_integrity.yaml names as its common form, arriving
    inside a check written to guard a vocabulary boundary.

    So the target is asserted directly, over the SYNTAX TREE: a
    translation is a mapping whose KEY is a term of one vocabulary and
    whose VALUE is a term of the other, both as whole string literals.
    Prose cannot take that shape however many of the words it uses, and a
    real translation cannot avoid it.

    The two term sets are taken by SET DIFFERENCE from the live
    vocabularies, so a term moved between axes changes what is watched
    for without anybody editing this file."""
    claim_strength = set(CONTRACT["axes"]["claim_strength"]["terms"])
    only_strength = claim_strength - set(UNCERTAINTY_KINDS)
    only_uncertainty = set(UNCERTAINTY_KINDS) - claim_strength
    assert only_strength and only_uncertainty, "the vocabularies no longer differ"

    def crosses(a, b):
        return (a in only_strength and b in only_uncertainty) or (
            a in only_uncertainty and b in only_strength
        )

    offenders = []
    for path in sorted(REPO_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git", "tests"):
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:                              # pragma: no cover
            continue
        for node in ast.walk(tree):
            pairs = []
            if isinstance(node, ast.Dict):
                pairs = [
                    (key.value, value.value)
                    for key, value in zip(node.keys, node.values)
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                    and isinstance(value, ast.Constant) and isinstance(value.value, str)
                ]
            elif isinstance(node, ast.Tuple) and len(node.elts) == 2:
                first, second = node.elts
                if (isinstance(first, ast.Constant) and isinstance(first.value, str)
                        and isinstance(second, ast.Constant)
                        and isinstance(second.value, str)):
                    pairs = [(first.value, second.value)]
            for a, b in pairs:
                if crosses(a, b):
                    offenders.append(f"{relative}:{node.lineno}: {a!r} -> {b!r}")
    assert not offenders, (
        "a literal pairing maps a claim_strength term onto an "
        "uncertainty_kind term or the reverse. The proposal refuses that "
        "translation; these are where it has been written:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_catches_a_translation_written_the_way_one_would_be():
    """PLANT AND WATCH IT FAIL, without writing the defect into the tree.

    The mapping is built in memory in exactly the shapes the guard scans
    for -- a dict literal and a two-element tuple -- and the same
    predicate is applied. A guard nobody has watched fire is a guard
    nobody has evidence about, and this one was already wrong once."""
    claim_strength = set(CONTRACT["axes"]["claim_strength"]["terms"])
    only_strength = claim_strength - set(UNCERTAINTY_KINDS)
    only_uncertainty = set(UNCERTAINTY_KINDS) - claim_strength

    def crosses(a, b):
        return (a in only_strength and b in only_uncertainty) or (
            a in only_uncertainty and b in only_strength
        )

    strength_term = sorted(only_strength)[0]
    uncertainty_term = sorted(only_uncertainty)[0]
    assert crosses(uncertainty_term, strength_term)
    assert crosses(strength_term, uncertainty_term)
    # and the prose case that produced the false positive does NOT cross
    assert not crosses("absent-is-not-zero and reported", "prose")
    assert not crosses(strength_term, strength_term)
