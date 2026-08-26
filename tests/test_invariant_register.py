"""The three-party invariant register, checked against the three parties.

WHAT THIS FILE IS FOR. The register answers a prior question that 33
artifacts in this repository assume an answer to: `bent: []`,
`core_invariants_modified: 0` and every `extends: core@1.0.0` are claims
made relative to a core, and until the register existed nothing said
whose invariants, held where, checkable by whom.

The register is DERIVED, so the checks here are of two kinds only:

  1. it is a fixed point of its generator -- regenerate and compare, the
     same discipline every other artifact in exchange/ is held to. This is
     what makes the numbers in it evidence rather than assertions.
  2. the load-bearing findings are still true of the tree, re-measured
     here independently of the generator, so a generator that quietly
     stopped looking does not take the finding with it.

WHAT IS DELIBERATELY NOT HERE. No status reconciliation across parties.
SCL has no status vocabulary and STE has no enumeration, so there is
nothing to reconcile; the cross-party status claims that DO exist are DAQ
invariants cited in SCL-authored artifacts, and
tests/test_cross_repository_claims.py already sweeps every document this
repository holds for those. A second mechanism here would be the parallel
architecture this pair has refused everywhere else.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess

import pytest

import daf  # noqa: F401
from epistemics._yaml import loads

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCHANGE = REPO_ROOT / "architecture" / "exchange"
REGISTER_PATH = EXCHANGE / "invariant_register.yaml"

REGISTER = loads(REGISTER_PATH.read_text())
CORE = loads((REPO_ROOT / "architecture" / "core.yaml").read_text())
INVARIANTS = loads((REPO_ROOT / "architecture" / "invariants.yaml").read_text())


# ------------------------------------------------------- 1. derived, not written


def test_the_register_is_a_fixed_point_of_its_generator():
    """Every number in the register is read from a source at generation
    time. If the file and the generator disagree, the file is a claim."""
    before = REGISTER_PATH.read_bytes()
    result = subprocess.run(
        ["python3", str(EXCHANGE / "build_invariant_register.py")],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
    )
    after = REGISTER_PATH.read_bytes()
    if after != before:
        REGISTER_PATH.write_bytes(before)
    assert result.returncode == 0, result.stderr
    assert after == before, (
        "the committed register differs from regeneration -- run "
        "`python3 architecture/exchange/build_invariant_register.py` and commit the result"
    )


def test_the_recorded_digest_matches_the_bytes():
    recorded = (EXCHANGE / "invariant_register.sha256").read_text().strip()
    assert recorded == "sha256:" + hashlib.sha256(REGISTER_PATH.read_bytes()).hexdigest()


def test_the_census_does_not_count_itself():
    """A census whose value includes its own row reports a number that
    depends on whether it has been run before rather than on the world."""
    source = (EXCHANGE / "build_invariant_register.py").read_text()
    assert 'path == HERE / "invariant_register.yaml"' in source, (
        "the extends census must skip the register, or the artifact is not a fixed point of its "
        "own generator"
    )


# --------------------------------------------- 2. the findings, re-measured here


def test_it_joins_on_the_participating_referent_not_the_label():
    join = REGISTER["joined_on"]
    assert join["referent"] == CORE["core_referent"]["participating"]
    assert join["referent"] != CORE["core_referent"]["annotating"]
    assert join["value"] == CORE["submodule_commit"]
    assert join["gitlink_at_generation"].startswith(CORE["submodule_commit"]), (
        "the register was generated against a different core than core.yaml records"
    )


def test_the_core_party_enumerates_no_invariants_anywhere_in_the_tree():
    """The register's central finding, re-measured rather than read back.

    If the vendored core ever grows a structured invariant source, this
    fails and the register must be re-derived -- which is the correct
    outcome, because the whole shape of `bent: zero` changes that day."""
    vendor = REPO_ROOT / CORE["submodule_path"]
    structured = [
        p for p in vendor.rglob("*.yaml")
        if ".git" not in p.parts and "node_modules" not in p.parts
    ]
    assert structured == [], (
        f"the core now holds structured documents: {[str(p) for p in structured]}. Re-derive the "
        "register; `bent: zero` may now be checkable as worded."
    )
    assert REGISTER["parties"]["ste"]["invariant_source"] is None
    assert REGISTER["parties"]["ste"]["reachable_from_this_register"] is False


def test_the_cores_own_documents_disagree_on_how_many_invariants_it_has():
    """Not a nitpick: it is why `bent: zero` cannot be checked as worded.

    Two independent numbers in the core's own docs, neither enumerated. If
    they ever agree AND a list appears, the finding is closed and this
    test should be the thing that says so."""
    cardinalities = REGISTER["the_core_partys_invariants_are_not_enumerated_anywhere_here"][
        "cardinalities_found"]
    numbers = REGISTER["the_core_partys_invariants_are_not_enumerated_anywhere_here"][
        "numbers_referenced"]
    assert numbers, "the register found no invariant references at all in the core"
    assert len(cardinalities) >= 1
    highest_referenced = max(numbers)
    asserted = sorted(int(key.split("_")[0]) for key in cardinalities)
    assert highest_referenced not in asserted or len(asserted) > 1, (
        "the referenced range and the asserted cardinality now agree; if an enumeration also "
        "exists, the register's central finding is closed and must be re-derived"
    )


def test_bent_zero_is_recorded_as_supported_by_byte_identity_not_by_enumeration():
    rests = REGISTER["what_bent_zero_actually_rests_on"]
    assert rests["measured_at_generation"]["working_tree_matches_the_pin"] is True
    assert rests["measured_at_generation"]["gitlink"].startswith(CORE["submodule_commit"])
    assert "unfalsifiable in the form it is written" in rests["why_it_cannot_be_checked_as_worded"]
    assert "what_is_NOT_claimed" in rests, (
        "the register must say that it does not claim STE's invariants HOLD -- only that this pair "
        "did not modify them"
    )


def test_the_core_is_still_unmodified_measured_here():
    """The observable the entailment rests on, checked independently of
    the generator that recorded it."""
    out = subprocess.run(
        ["git", "submodule", "status", CORE["submodule_path"]],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0 or not out.stdout:
        pytest.skip("submodule status unavailable in this checkout")
    assert out.stdout[0] not in "+-U", (
        f"the vendored core is modified or out of sync: {out.stdout.strip()!r}. `bent: zero` is no "
        "longer entailed by byte-identity and has to be re-established."
    )


def test_the_extends_census_is_parsed_and_matches_a_parse_done_here():
    """Recorded as 26 in prose, parsed as 33. The gap is the point: a text
    search for `extends: core@1.0.0` cannot see `"extends": "core@1.0.0"`,
    which is what the shared canonical emitter writes."""
    counted = 0
    for path in sorted(REPO_ROOT.rglob("*.yaml")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        if path == REGISTER_PATH:
            continue
        try:
            document = loads(path.read_text())
        except Exception:
            continue
        if isinstance(document, dict) and document.get("extends") == f"core@{CORE['version']}":
            counted += 1
    assert REGISTER["extends_join"]["artifacts_declaring_the_core"] == counted
    assert REGISTER["extends_join"]["artifacts_declaring_a_different_core"] == []

    grepped = len(re.findall(
        r"^extends: core@",
        "\n".join(
            p.read_text() for p in REPO_ROOT.rglob("*.yaml")
            if "vendor" not in p.parts and ".git" not in p.parts
        ),
        re.M,
    ))
    assert grepped < counted, (
        "a text search now finds as many as a parse does; the finding that the canonically-emitted "
        "artifacts were invisible to the count no longer holds and the note should be re-measured"
    )


def test_scls_half_is_reachable_and_carries_no_borrowed_status_vocabulary():
    scl = REGISTER["parties"]["scl"]
    assert scl["reachable_from_this_register"] is True, (
        "SCL's invariant source is not exchanged; a three-party register with one party "
        "unreachable is a two-party register with a footnote"
    )
    assert scl["status_histogram"] is None
    daq_vocabulary = {entry["status"] for entry in INVARIANTS["invariants"]}
    clauses = loads((EXCHANGE / "scl_contract_clauses.yaml").read_text())
    for name, clause in clauses["clauses"].items():
        assert clause["coverage"] not in daq_vocabulary, (
            f"{name} reports coverage {clause['coverage']!r}, which is one of this repository's "
            "invariant statuses -- the register would then join on a word meaning two things"
        )


def test_every_party_says_whether_it_is_reachable():
    """The property, not the list: a party added later must answer it too."""
    for name, party in REGISTER["parties"].items():
        assert "reachable_from_this_register" in party, f"{name} does not say"
        assert isinstance(party["reachable_from_this_register"], bool)
        assert "source_kind" in party, f"{name} does not say what kind of source it holds"


def test_the_property_set_divergence_is_verified_against_git_not_asserted():
    """The register says `bent: zero` meant four properties before c80a2f0
    and five after. That is a claim about history, so it is checked
    against history."""
    block = REGISTER["which_property_set_bent_zero_quantifies_over"]
    canonical = block["the_canonical_set_is_the_union_of_both_axes"]
    probe = loads((REPO_ROOT / "architecture" / "_probes" / "generality.yaml").read_text())
    assert canonical["observation_properties"] == list(probe["observation_properties"])
    assert canonical["computation_properties"] == list(probe["computation_properties"])
    assert canonical["total"] == len(probe["observation_properties"]) + len(
        probe["computation_properties"])

    counts = {}
    for revision in ("ca3d0aa", "c80a2f0"):
        shown = subprocess.run(
            ["git", "show", f"{revision}:architecture/_probes/generality.yaml"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
        )
        if shown.returncode != 0:
            pytest.skip(f"{revision} not reachable from this checkout")
        historical = loads(shown.stdout)
        counts[revision] = (
            len(historical.get("observation_properties") or [])
            + len(historical.get("computation_properties") or [])
        )
    assert counts["ca3d0aa"] == 4, counts
    assert counts["c80a2f0"] == 5, counts
    assert counts["c80a2f0"] != counts["ca3d0aa"], (
        "the register claims the property set changed size; git says it did not"
    )


def test_the_partition_that_prevents_the_set_growing_silently_still_exists():
    """The register cites test_generality_probe_gate.py as what keeps this
    from recurring. A citation of a check that has been deleted is worse
    than no citation."""
    gate = REPO_ROOT / "tests" / "test_generality_probe_gate.py"
    assert gate.exists(), "the register cites a partition check that no longer exists"
    source = gate.read_text()
    assert "test_every_declared_property_is_accounted_for_in_exactly_one_outcome_list" in source
    assert "test_every_declared_property_has_a_result" in source
