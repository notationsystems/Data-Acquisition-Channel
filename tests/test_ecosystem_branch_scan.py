"""The branch scan, and the fifth-axis proposal it produced.

WHAT CAN AND CANNOT BE CHECKED HERE. The scan's subject is other
repositories' branches. Nothing in this tree can re-run that measurement
offline, and pretending otherwise would be the vacuous shape this
repository has filed repeatedly. So the split is the same one the
ecosystem register uses: claims about THIS tree are derived and asserted;
claims about other trees are a dated reading that must name what it read
and be internally consistent with everything else recorded here.

THE ONE THING THAT IS FULLY CHECKABLE, and it is the one that matters:
the collision. Two of the three contested terms are terms of THIS
repository's own vocabularies -- the contract it carries and the
uncertainty kinds it enforces -- so whether the collision still exists is
a fact about files in this tree, and it is asserted by intersection
rather than restated.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads
from science.admissibility import UNCERTAINTY_KINDS

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = REPO_ROOT / "architecture"
SCAN = loads((ARCHITECTURE / "ecosystem_branch_scan.yaml").read_text())
PROPOSAL_PATH = (
    ARCHITECTURE / "proposals" / "2026-09-03-attestation-class-as-a-contract-axis.yaml"
)
PROPOSAL = loads(PROPOSAL_PATH.read_text())
CONTRACT_PATH = REPO_ROOT / "epistemics" / "corpus" / "contract.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text())

#: The six terms observed in the other repository, in weakest-first order.
#: Recorded here because the enforcement needs them and the scan names
#: them; this is a READING of another party's vocabulary, and the proposal
#: says so.
OBSERVED_ATTESTATION_CLASS = (
    "absent", "self_reported", "computed", "our_observation",
    "insurer_confirmed", "regulator_reported",
)


def test_the_proposal_binds_to_the_contract_bytes_it_was_written_against():
    bound = PROPOSAL["binds_to"]
    actual = hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()
    assert bound["contract_sha256"] == actual, (
        "the corpus contract has been reissued; this proposal must be "
        "reissued against the new bytes or retired, never rebound"
    )
    assert bound["contract_version"] == CONTRACT["version"]


def test_every_contested_term_still_collides():
    """THE CHECK THAT MATTERS, and it is fully local. Two of the three
    terms live in this repository's own vocabularies, so the collision is
    asserted by intersecting them rather than by trusting the reading."""
    contested = PROPOSAL["the_three_contested_terms"]
    assert set(contested) == {"self_reported", "computed", "absent"}

    interest = set(CONTRACT["axes"]["interest"]["terms"])
    production = set(CONTRACT["axes"]["production_class"]["terms"])
    observed = set(OBSERVED_ATTESTATION_CLASS)

    assert "self_reported" in interest & observed, (
        "self_reported no longer appears on both the interest axis and the "
        "observed vocabulary; the proposal describes a collision that has gone"
    )
    assert "computed" in production & observed
    assert "absent" in set(UNCERTAINTY_KINDS) & observed


def test_the_production_class_axis_is_still_unordered():
    """The `computed` argument rests entirely on this. If production_class
    ever became ordered, the collision would change shape -- two ordered
    axes sharing a term, which is the self_reported case -- and the
    proposal's reasoning for that term would need rewriting rather than
    keeping."""
    axis = CONTRACT["axes"]["production_class"]
    assert axis["ordered"] is False
    assert "ranks these" in axis["ordering_note"]
    reason = PROPOSAL["the_three_contested_terms"]["computed"]["refusal_reason"]
    assert "unordered on one axis and ranked on the other" in reason


def test_the_scale_length_argument_is_true_of_the_actual_scales():
    """self_reported is the dangerous collision BECAUSE the scales differ
    in length -- equal ranks are not equal distances from the top. That is
    an arithmetic claim and it is checked, not asserted."""
    interest_terms = CONTRACT["axes"]["interest"]["terms"]
    assert len(interest_terms) == 4, f"the interest axis now has {len(interest_terms)}"
    assert len(OBSERVED_ATTESTATION_CLASS) == 6
    reason = PROPOSAL["the_three_contested_terms"]["self_reported"]["refusal_reason"]
    assert "Four positions against six" in reason


def test_no_translation_between_the_axes_exists_in_this_repository():
    """The guard. The proposal refuses all three translations, and the way
    that stops being true is that somebody writes a mapping because the
    words line up. Over the syntax tree, for the same reason the
    uncertainty-kind guard reads it: a term in prose is not a term in
    code."""
    import ast

    only_attestation = set(OBSERVED_ATTESTATION_CLASS) - set(UNCERTAINTY_KINDS)
    contract_terms = set()
    for axis in CONTRACT["axes"].values():
        contract_terms.update(axis["terms"])
    only_contract = contract_terms - set(OBSERVED_ATTESTATION_CLASS)
    assert only_attestation and only_contract

    offenders = []
    for path in sorted(REPO_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git", "tests"):
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:                                  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(value, ast.Constant)):
                    continue
                pair = {key.value, value.value}
                if pair & only_attestation and pair & only_contract:
                    offenders.append(f"{relative}:{node.lineno}: {key.value!r} -> {value.value!r}")
    assert not offenders, (
        "a literal pairing maps an attestation term onto a contract-axis "
        "term:\n  " + "\n  ".join(offenders)
    )


def test_the_scan_records_agreement_as_well_as_collision():
    """A scan that reported only problems would be a scan nobody trusts.
    The first measured result was that the contract HOLDS on every branch
    read, and the record has to carry it."""
    holds = SCAN["the_contract_holds_on_every_payload_terminal_branch"]
    assert "BYTE-IDENTICAL" in holds["measured"]
    assert re.search(r"\b[0-9a-f]{12}\b", holds["measured"]), (
        "the agreement is claimed without the digest that establishes it"
    )
    assert CONTRACT["implementations"]["payload-terminal"]["declares"] in holds["what_was_checked"]


def test_the_sp1_near_miss_is_recorded_as_a_near_miss():
    """A manifest saying 6.0.1 beside a key saying 6.5.0 reads as a
    contradiction and is not one -- a caret range admits it and the
    lockfile pins it. That was nearly filed as a defect, and the record
    must say so: the reason it is not a finding is that the lockfile was
    read, and a record that showed only the conclusion would teach the
    wrong lesson."""
    codex = SCAN["two_sp1_implementations_that_cannot_verify_each_other"]["codex_side"]
    coherent = codex["and_it_is_internally_coherent"]
    assert "near-miss" in coherent
    assert "LOCKFILE" in coherent and "caret" in coherent
    assert "participating referent" in coherent


def test_the_scan_says_whose_problem_the_divergence_is():
    """Two SP1 pipelines a minor version apart. The one that works is the
    other party's; the one pinned to a fork that does not resolve is
    this pair's dependency. A scan that left that unattributed would read
    as a complaint."""
    divergence = SCAN["two_sp1_implementations_that_cannot_verify_each_other"]
    assert divergence["whose_problem_it_is"].startswith("not Codex's")
    assert "6.4.0" in divergence["core_side"]["and_the_fork_is_a_different_version"]
    register = loads((ARCHITECTURE / "ecosystem_register.yaml").read_text())
    assert "SP1-zero-knowledge-virtual-machine" in str(register["members"]), (
        "the scan cites a fork the ecosystem register does not account for"
    )


def test_the_data_platform_record_no_longer_says_sp1_has_one_implementation():
    """The scan changes a claim this pair published hours earlier:
    architecture/data_platform_position.yaml recorded SP1 as adopted in
    the vendored core and nowhere else. There are two, and the working one
    is elsewhere. A record that stayed as it was would be the stale
    cross-repository claim this pair already checks for."""
    platform = loads((ARCHITECTURE / "data_platform_position.yaml").read_text())
    sp1 = platform["technologies"]["sp1"]
    assert "ecosystem_branch_scan" in str(sp1), (
        "the platform record's SP1 entry does not cite the scan that "
        "corrected it"
    )
