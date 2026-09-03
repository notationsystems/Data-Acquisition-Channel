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
sys.path.insert(0, str(REPO_ROOT / "tests"))
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
    # Bound to the record's own declared count, not to a literal here:
    # a literal went stale the first time a seventh apparatus arrived.
    assert len(APPARATUSES) == CENSUS["counts"]["apparatuses"]
    assert CENSUS["counts"]["apparatuses"] != CENSUS["counts"]["repositories_carrying_the_name"]
    assert "no repository of its own" in CENSUS["counts"]["why_they_differ"], (
        "the counts differ and the record must say why, or the difference reads as an error"
    )
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
        # `" ".join(body)` joins the KEYS, so this passed by matching a
        # key NAME and never read a value. Caught by
        # tests/test_mapping_join_defect.py, which is the class guard for
        # a construction this programme had caught eight times by hand.
        limits = [str(value) for key, value in body.items() if "not_claimed" in key]
        assert limits, f"{name} states no limit on its own claim"
        for limit in limits:
            assert len(limit) > 40, f"{name}'s limit is a label rather than a statement"
            assert "empty" in limit.lower(), (
                f"{name} is recorded with zero commits present, and the limit must be about "
                "not concluding emptiness from that -- an empty local clone is evidence "
                "about this machine and nothing else"
            )


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
    # THE SAME SCOPE THE REGISTER SCANS, not a convenient subset. An
    # earlier version of this counted only architecture/ and compared the
    # result to a register that walks the whole repository: the relation
    # held by luck, and one core-declaring YAML under commerce/ would
    # have broken it while looking like a real disagreement.
    register_path = REPO_ROOT / "architecture" / "exchange" / "invariant_register.yaml"
    everywhere = 0
    for path in sorted(REPO_ROOT.rglob("*.yaml")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        if path == register_path:
            continue                       # the register excludes itself; so does this
        try:
            document = loads(path.read_text())
        except Exception:  # noqa: BLE001 -- a non-conforming file is not a core declaration
            continue
        if isinstance(document, dict) and document.get("extends") == "core@1.0.0":
            everywhere += 1

    assert declaring > 0 and everywhere >= declaring

    recorded = APPARATUSES["scout_retrieval_agent"]["bound"]["artifacts_here_declaring_it"]
    assert "NOT RECORDED AS A NUMBER" in recorded, (
        "a tally is back in the census; it will be stale on the next commit that adds a record, "
        "which is what happened three times before the row was changed to carry relations"
    )

    # RELATION ONE: the register reports exactly one fewer than a parse of
    # the same tree, because it excludes itself.
    register = loads((REPO_ROOT / "architecture" / "exchange"
                      / "invariant_register.yaml").read_text())
    declared_there = register["extends_join"]["artifacts_declaring_the_core"]
    assert declared_there == everywhere, (
        f"a parse over the register's own scope finds {everywhere} and the register reports "
        f"{declared_there}. Both exclude the register itself, so the two are the same count and "
        "a difference means the register is stale -- re-derive it rather than editing either."
    )
    assert "THE SAME COUNT" in recorded

    # RELATION TWO: a text search undercounts, which is why the count is
    # a parse. Both halves measured, neither restated.
    hits = subprocess.run(("grep", "-rl", "--include=*.yaml", "extends: core@", "."),
                          cwd=REPO_ROOT, capture_output=True, text=True).stdout.split()
    hits = [h for h in hits if not h.startswith("./vendor/")]
    assert len(hits) < everywhere, (
        "the text search no longer undercounts, so the census's account of why it parses is stale"
    )
    assert "never by text search" in recorded

    # And the reason the count is a parse: the text search misses the
    # canonically-emitted form, which is the exchange artifacts.
    hits = subprocess.run(("grep", "-rl", "--include=*.yaml", "extends: core@", "."),
                          cwd=REPO_ROOT, capture_output=True, text=True).stdout.split()
    hits = [h for h in hits if not h.startswith("./vendor/")]
    assert len(hits) < everywhere, (
        "the text search no longer undercounts, so the census's account of why it "
        "parses instead is stale"
    )


def test_the_daq_side_of_the_pair_matches_what_the_census_recorded():
    """This side, re-measured. The PAIR verdict is not taken here.

    An earlier version of this test compared against a sibling directory
    and reported a divergence that did not exist. The counterparty is a
    remote; tests/test_pair_at_remote.py asks it.
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

    # THE COUNTERPARTY IS A REMOTE, NOT A DIRECTORY. This block used to
    # compare against /home/user/scientific-compute-layer-scl-, and on
    # 2026-09-03 that reported a DIVERGENCE for a pair that was
    # byte-identical at both parties' heads: the sibling checkout was four
    # commits behind its own remote. A local directory is versioned with
    # nothing, so the verdict was about a checkout and read as a verdict
    # about the pair. tests/test_pair_at_remote.py now owns the real
    # comparison; what is left here is this side, which is what a census
    # of THIS repository can honestly bind.
    from _pair import local_sibling_is_current
    current, reason = local_sibling_is_current()
    if current is False:
        # Named rather than passed over: the machine holds a stale mirror,
        # and any byte comparison against it would be a verdict about that.
        assert "vs remote" in reason


def test_the_daq_row_records_no_tally_and_the_tallies_are_measured_here():
    """The counts are real and they move on every commit, so the record
    declines to restate them and this measures them instead.

    Fails in the state where a tally comes back into the record -- which
    is the state that produced three stale rows in one session.
    """
    bound = APPARATUSES["data_acquisition_fabric"]["bound"]
    for volatile in ("phase_reports", "architecture_records", "tests_collected"):
        assert volatile not in bound, (
            f"{volatile} is back in the census as a number; it is stale on the next commit"
        )
    assert "a tally is a statement about a moment" in bound["counts_are_not_recorded_here"]

    # Measured, so the claim that they are real is not itself a prose claim.
    assert len(list((REPO_ROOT / "docs").glob("PHASE_*.md"))) > 25
    assert len(list((REPO_ROOT / "architecture").glob("*.yaml"))) > 50


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


def test_the_ancestry_row_separates_what_was_measured_from_what_is_unknowable():
    """CORRECTED. This test previously asserted that the row said
    `undeterminable` and gave `grafted` as the reason -- which pinned a
    claim that was, in part, an artefact of its instrument.

    The sibling trees are PARTIAL CLONES. A presence query there is not a
    read: on a miss git fetches from the promisor and answers yes, and an
    abbreviated sha misses locally and never reaches that path. So `the
    pinned commit is not in its object database` was never true; it was
    what a short sha looks like. Measured with the guard on, every commit
    is present, and one relation the row called undeterminable --
    d43a569 to dfbdce1 -- is determinable and holds.

    What survives is a real limit for a DIFFERENT reason: the clone is
    grafted, and merge-base cannot see past a graft. So the row must now
    carry three separable things, and this test asserts all three are
    there rather than that a conclusion is stated."""
    observed = APPARATUSES["scout_retrieval_agent"]["observed"]
    corrected = observed["ancestry_is_PARTLY_determinable_and_the_stated_reason_was_wrong"]
    assert "artefact of the instrument" in corrected
    assert "partialclonefilter" in corrected.lower() or "PARTIAL CLONE" in corrected
    determined = observed["what_is_determinable_measured_with_the_guard_on"]
    assert "ANCESTOR" in determined.upper()
    remaining = observed["what_remains_undeterminable_and_for_the_RIGHT_reason"]
    assert "graft" in remaining.lower()
    assert "not because objects are missing" in remaining.lower()
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
