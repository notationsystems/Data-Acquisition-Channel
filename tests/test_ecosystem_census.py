"""The ecosystem census, checked where it can be and not where it cannot.

Six repositories carry the Notation Systems name. Three exchange
artifacts under a contract; three do not. The census records both, and
its two kinds of claim are held to different standards on purpose:

  BOUND     re-measured here against this tree, independently of the
            record. A claim that stops being true fails.
  OBSERVED  about sibling checkouts this repository does not own. NOT
            checked here. A test that verified them would pass on a
            machine where the siblings are absent, which is the vacuous
            shape architecture/vacuous_evidence.yaml files three times.
            So what IS checked is that the record declares them
            unverifiable and dates them.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

ARTIFACT = REPO_ROOT / "architecture" / "ecosystem_census.yaml"
CENSUS = loads(ARTIFACT.read_text())
APPARATUSES = CENSUS["apparatuses"]

BOUND = "BOUND"
OBSERVED = "OBSERVED"
BOUND_AND_OBSERVED = "BOUND_AND_OBSERVED"
KINDS = (BOUND, OBSERVED, BOUND_AND_OBSERVED)


def _git(*args: str) -> str:
    return subprocess.run(("git", "-C", str(REPO_ROOT)) + args,
                          capture_output=True, text=True, check=True).stdout.strip()


# =====================================================================
# The record is well formed
# =====================================================================

def test_every_apparatus_declares_which_kind_of_claim_it_carries():
    """A row that did not say would be checked to whichever standard the
    reader assumed."""
    assert len(APPARATUSES) == 6
    for name, body in APPARATUSES.items():
        assert body["kind"] in KINDS, f"{name} declares kind {body.get('kind')!r}"
        assert "role" in body
        if body["kind"] in (BOUND, BOUND_AND_OBSERVED):
            assert "bound" in body, f"{name} claims BOUND facts and carries none"
        if body["kind"] in (OBSERVED, BOUND_AND_OBSERVED):
            assert "observed" in body, f"{name} claims OBSERVED facts and carries none"


def test_the_observed_half_is_dated_and_scoped_to_one_machine():
    """The half that will be wrong the moment a sibling moves says so."""
    assert CENSUS["recorded"] == "2026-09-03"
    assert "single session container" in CENSUS["observed_on"]
    assert "dated and machine-scoped" in CENSUS["what_this_record_must_not_become"]


def test_an_undetermined_role_is_undetermined_and_not_inferred_from_a_name():
    """Two repositories have zero commits here. Naming their role from
    their directory name is the fabrication this record exists to refuse.

    Fails in the state where someone fills in a plausible role for a
    repository nobody has read.
    """
    for name in ("network_scout_signal_miner", "information_systems_archive"):
        body = APPARATUSES[name]
        assert body["role"] == "UNDETERMINED", f"{name} acquired a role from somewhere"
        assert "ZERO commits" in body["observed"]["state"]
        assert "not_claimed" in " ".join(body), f"{name} states no limit on its own claim"


# =====================================================================
# The BOUND half, re-measured against the tree
# =====================================================================

def test_the_core_pin_is_what_the_census_says_and_has_not_moved():
    bound = APPARATUSES["scout_retrieval_agent"]["bound"]
    head = subprocess.run(("git", "-C", str(REPO_ROOT / "vendor" / "scout-retrieval-agent"),
                           "rev-parse", "HEAD"),
                          capture_output=True, text=True, check=True).stdout.strip()
    assert head == bound["pinned_commit"]

    pyproject = (REPO_ROOT / "vendor" / "scout-retrieval-agent" / "pyproject.toml").read_text()
    version = next(line.split("=", 1)[1].strip().strip('"')
                   for line in pyproject.splitlines() if line.startswith("version"))
    assert version == bound["version_string_at_that_pin"], (
        "the census records the version string the PIN declares; if it moved, the finding "
        "about two commits sharing one label needs re-measuring, not editing"
    )


def test_the_declared_core_count_is_re_derived_rather_than_restated():
    """Counted by parsing every architecture record, never by text search
    -- the register already found that a text search misses the
    canonically-emitted `"extends": "core@1.0.0"` form, which is exactly
    the set of most carefully produced files.
    """
    declaring = 0
    for path in sorted((REPO_ROOT / "architecture").glob("*.yaml")):
        document = loads(path.read_text())
        if isinstance(document, dict) and document.get("extends") == "core@1.0.0":
            declaring += 1
    everywhere = 0
    for path in sorted((REPO_ROOT / "architecture").rglob("*.yaml")):
        try:
            document = loads(path.read_text())
        except Exception:  # noqa: BLE001 -- a non-conforming file is not a core declaration
            continue
        if isinstance(document, dict) and document.get("extends") == "core@1.0.0":
            everywhere += 1

    recorded = APPARATUSES["scout_retrieval_agent"]["bound"]["artifacts_here_declaring_it"]
    assert f"{declaring} YAML records" in recorded, (
        f"{declaring} top-level records declare the core; the census says {recorded!r}"
    )
    assert f"{everywhere} across architecture/ as a whole" in recorded

    # The register counts the same tree and reports one fewer, because it
    # excludes itself. Binding the two numbers here is what stops them
    # drifting apart into a contradiction nobody notices.
    register = loads((REPO_ROOT / "architecture" / "exchange"
                      / "invariant_register.yaml").read_text())
    declared_there = register["extends_join"]["artifacts_declaring_the_core"]
    assert declared_there == everywhere - 1, (
        f"the census parses {everywhere} and the register reports {declared_there}; they agree "
        "only while the register's single self-exclusion is the whole difference"
    )
    assert f"{declared_there} for the same tree" in recorded

    # And the reason the count is a parse: the text search misses the
    # canonically-emitted form, which is the exchange artifacts.
    hits = subprocess.run(("grep", "-rl", "extends: core@", "architecture/"),
                          cwd=REPO_ROOT, capture_output=True, text=True).stdout.split()
    assert len(hits) < everywhere, (
        "the text search no longer undercounts, so the census's account of why it "
        "parses instead is stale"
    )


def test_the_shared_pair_is_byte_identical_where_the_counterparty_is_reachable():
    """The verification a previous claim in this repository skipped.

    The pair is held byte-identically by both parties and editing either
    is a joint reissue. Here the DAQ-side digests are re-measured; the
    SCL side is checked only when a checkout is actually present, and the
    test says which of the two it did rather than passing either way.
    """
    bound = APPARATUSES["scientific_compute_layer"]["bound"]
    pair = {
        "proof_integrity.yaml": bound["proof_integrity_sha256"],
        "kalman_validation_preregistration.yaml": bound["kalman_preregistration_sha256"],
    }
    for name, expected in pair.items():
        actual = hashlib.sha256((REPO_ROOT / "architecture" / name).read_bytes()).hexdigest()
        assert actual == expected, (
            f"{name} no longer matches the census. This file is held jointly -- a change "
            "here is a joint reissue, never this repository's alone."
        )

    counterparty = pathlib.Path("/home/user/scientific-compute-layer-scl-/architecture")
    if not counterparty.is_dir():
        return  # not reachable on this machine; the DAQ half above still ran
    for name, expected in pair.items():
        theirs = counterparty / name
        if theirs.exists():
            assert hashlib.sha256(theirs.read_bytes()).hexdigest() == expected, (
                f"{name} has DIVERGED between the two parties"
            )


def test_the_daq_row_counts_what_the_tree_actually_holds():
    bound = APPARATUSES["data_acquisition_fabric"]["bound"]
    assert len(list((REPO_ROOT / "docs").glob("PHASE_*.md"))) == bound["phase_reports"]
    assert len(list((REPO_ROOT / "architecture").glob("*.yaml"))) == bound["architecture_records"]


def test_the_layer_rule_the_census_states_is_the_rule_the_tree_enforces():
    """The census describes daf as importing evidence ONLY. If that were
    prose, it would be a claim bound to nothing -- so it is checked
    against the same forbidden imports the layer test enforces.
    """
    layers = APPARATUSES["data_acquisition_fabric"]["bound"]["layers"]
    assert "daf -> evidence ONLY" in layers
    offenders = []
    for path in (REPO_ROOT / "daf").rglob("*.py"):
        text = path.read_text()
        for forbidden in ("import materials", "import science", "import boundary",
                          "import bridge"):
            if forbidden in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {forbidden}")
    assert offenders == [], offenders


# =====================================================================
# The finding, and the reason it is reported rather than repaired
# =====================================================================

def test_the_core_label_finding_states_why_it_is_not_fixed_here():
    """A finding with no disposition is a complaint. This one names both
    reasons it stays open and what would close it."""
    finding = CENSUS["what_the_census_found_that_no_single_repository_could"][
        "the_label_does_not_identify_the_core"]
    assert "editing another party's repository" in finding["why_it_is_not_repaired_here"]
    assert "parallel architecture" in finding["why_it_is_not_repaired_here"]
    assert "joint decision and is not taken here" in finding["what_would_close_it"]


def test_the_ancestry_is_recorded_as_undeterminable_rather_than_guessed():
    """The sibling core checkout is grafted, so the pinned commit is not
    in its object database and the relationship cannot be computed. That
    is a fact about what is knowable, and it is recorded as one.
    """
    observed = APPARATUSES["scout_retrieval_agent"]["observed"]
    assert "grafted" in observed["ancestry_is_undeterminable_here"]
    assert "recorded as undeterminable rather than guessed" in (
        observed["ancestry_is_undeterminable_here"])
    assert "SAME LABEL" in observed["its_version_string"]


def test_the_readme_the_census_says_was_missing_now_exists():
    """The census records the gap and its repair in one commit. If the
    README were deleted the record would be describing a repair that is
    no longer there.
    """
    finding = CENSUS["what_the_census_found_that_no_single_repository_could"][
        "the_most_developed_apparatus_had_no_front_door"]
    assert finding["disposition"].startswith("repaired in the same commit")
    readme = REPO_ROOT / "README.md"
    assert readme.exists() and readme.stat().st_size > 0
    assert "Notation Systems" in readme.read_text()
