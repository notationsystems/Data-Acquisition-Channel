"""architecture/ecosystem_register.yaml, checked against the ecosystem.

WHY THIS FILE IS SHAPED THE WAY IT IS. The register's subject is mostly
NOT IN THIS REPOSITORY -- sibling checkouts on whatever machine happens to
be running, and remote refs on GitHub. A check whose subject can be absent
has exactly two honest dispositions and this file takes both: derive and
assert what is here, and for what is not, RE-RUN THE COMMAND when the
subject is reachable and SKIP WITH A STATED REASON when it is not. What it
must never do is pass silently over an absent subject, which is the
zero-over-an-unreachable-subject shape architecture/proof_integrity.yaml
has already filed twice.

THE GUARD THAT IS THE POINT OF THIS FILE. The register's first draft
reported that the three core commits shared no objects. They share one
history. The claim came from running `git cat-file -e <commit>` inside a
PARTIAL CLONE, where a presence query is not a read: on a local miss git
fetches the object from the promisor remote and answers yes. Re-running it
with full shas instead of abbreviated ones inverted every answer and left
two new promisor packs on disk, timestamped inside the same minute.

So every git invocation here goes through `_git`, which sets
GIT_NO_LAZY_FETCH=1. And that is not left as a convention: one test reads
THIS FILE'S OWN SOURCE and fails if any git call bypasses the helper,
because a guard that can be silently dropped by the next person editing
the file is not a guard. Asserting the property, not the enumeration, in
the file whose whole subject is a check that lied.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTER_PATH = REPO_ROOT / "architecture" / "ecosystem_register.yaml"
REGISTER = loads(REGISTER_PATH.read_text())

#: Where sibling checkouts live if they live anywhere: beside this one.
#: Derived from this file's location rather than configured, so the check
#: has no way to be pointed at a directory that happens to be tidy.
SIBLING_ROOT = REPO_ROOT.parent

#: Remote reads are real network. They run when the network answers and
#: skip with a reason when it does not -- never silently.
NETWORK_TIMEOUT_SECONDS = 60


def _git(*arguments, cwd=None, timeout=30):
    """Every git invocation in this file. Two properties, both required.

    GIT_NO_LAZY_FETCH=1 stops a query about an object from FETCHING that
    object. Without it, `is this commit present` is a write, and the
    answer it returns is the answer it created.

    GIT_TERMINAL_PROMPT=0 stops a credential prompt from hanging a suite
    on a machine where a remote needs auth. A hang is a worse failure
    than a refusal because it reports nothing at all.
    """
    environment = dict(os.environ)
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", *arguments],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )


def _checkout(path):
    """A sibling checkout, or None. `None` means the register's subject is
    not on this machine, and the caller must skip rather than pass."""
    candidate = SIBLING_ROOT / path
    if not (candidate / ".git").exists():
        return None
    return candidate


def _ls_remote(url):
    """The full ref set at a remote, or None if the network did not answer.

    Refs, deliberately, and not object reachability. GitHub serves a
    fork's whole network from one object store, so `does this remote have
    commit C` is true across every fork of anything and identifies
    nothing. Refs are what a repository IS at a name."""
    result = _git("ls-remote", url, timeout=NETWORK_TIMEOUT_SECONDS)
    if result.returncode != 0:
        return None
    refs = {}
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        sha, name = line.split("\t", 1)
        refs[name.strip()] = sha.strip()
    return refs or None


# --------------------------------------------------------------------
# the artifact is well formed, and says what it claims to be enforced by
# --------------------------------------------------------------------


def test_the_register_names_this_file_as_its_enforcement():
    assert REGISTER["enforcement"] == "tests/test_ecosystem_register.py"
    assert (REPO_ROOT / REGISTER["enforcement"]).exists()


def test_every_member_carries_a_declared_posture():
    """Derived from the classes the artifact declares, so a posture word
    invented in a later edit fails here rather than passing unnoticed."""
    declared = set(REGISTER["posture_classes"])
    assert declared, "no posture classes declared"
    for name, member in REGISTER["members"].items():
        assert member.get("posture") in declared, (
            f"{name} carries posture {member.get('posture')!r}, "
            f"which is not one of {sorted(declared)}"
        )


def test_no_posture_class_is_declared_and_unused():
    """The mirror of the check above, and the one that actually bites: a
    vocabulary entry nothing uses is either a member that was dropped
    without the class being retired, or a word written for its own sake.
    `declared_empty` was retired when it turned out to describe an empty
    CLONE, and this is what makes such a retirement visible."""
    used = {member["posture"] for member in REGISTER["members"].values()}
    unused = set(REGISTER["posture_classes"]) - used
    assert not unused, f"posture classes declared and never used: {sorted(unused)}"


def test_every_member_that_names_several_names_says_how_that_was_established():
    """Ref-set identity is the register's central structural claim -- six
    repositories under ten names. A member asserting an alias without
    saying what measured it would be the prose-bound claim this pair has
    already filed as defending nothing."""
    for name, member in REGISTER["members"].items():
        if "names_that_resolve_here" in member:
            assert len(member["names_that_resolve_here"]) > 1, (
                f"{name} lists names_that_resolve_here with one entry"
            )
            assert member.get("how_that_was_established"), (
                f"{name} claims an alias with no statement of what measured it"
            )


# --------------------------------------------------------------------
# the guard, and the assertion that the guard is still in force
# --------------------------------------------------------------------

_GIT_CALL = re.compile(r"""(?<![\w.])subprocess\.\w+\(\s*\[?\s*["']git["']""")


def test_no_git_call_in_this_file_bypasses_the_no_lazy_fetch_helper():
    """PLANT-AND-WATCH-IT-FAIL, applied to the guard rather than to the
    behaviour. `_git` is the only place GIT_NO_LAZY_FETCH is set; a git
    call written directly with subprocess would silently restore the
    fetching behaviour that produced the false finding, and every test
    here would still pass -- more easily, in fact, since lazily fetched
    objects make presence claims come out true.

    So the property asserted is over this file's SOURCE: exactly one
    construction of a git command line exists, and it is inside `_git`."""
    source = Path(__file__).read_text()
    body = source.split("def _git(", 1)[1].split("\ndef ", 1)[0]
    assert 'environment["GIT_NO_LAZY_FETCH"] = "1"' in body, (
        "_git no longer sets GIT_NO_LAZY_FETCH -- the guard is gone"
    )
    outside = source.replace(body, "")
    offenders = _GIT_CALL.findall(outside)
    assert not offenders, (
        f"{len(offenders)} git invocation(s) outside _git bypass the "
        "no-lazy-fetch guard"
    )


def test_this_git_understands_the_no_lazy_fetch_guard():
    """The guard is an environment variable, and an environment variable a
    program does not read is not a guard -- it is a comment that looks
    like one. Git has honoured GIT_NO_LAZY_FETCH since 2.36; older git
    ignores it silently and every presence check here goes back to
    fetching its own evidence.

    Checked by VERSION rather than by behaviour, because the behavioural
    probe needs a partial clone with a known-absent object, which is
    exactly the state the probe would destroy by running."""
    result = _git("--version")
    assert result.returncode == 0, "git is not runnable"
    match = re.search(r"(\d+)\.(\d+)", result.stdout)
    assert match, f"unparseable git version: {result.stdout!r}"
    major, minor = int(match.group(1)), int(match.group(2))
    assert (major, minor) >= (2, 36), (
        f"git {major}.{minor} predates GIT_NO_LAZY_FETCH; every presence "
        "check in this file would fetch what it asks about"
    )


def test_a_presence_query_over_a_partial_clone_leaves_the_pack_count_alone():
    """The finding itself, replayed as a check where a partial clone is
    present. It measures the SIDE EFFECT rather than the answer: whether
    the object turns out to be there is not the point, and on this machine
    the plant has already been spent -- the objects were fetched by the
    query that produced the false finding.

    What must stay true regardless is that ASKING WROTE NOTHING. Pack
    count before, pack count after, and the answer discarded."""
    partial = None
    for candidate in sorted(SIBLING_ROOT.iterdir()):
        if not (candidate / ".git").exists():
            continue
        result = _git("config", "--get", "remote.origin.promisor", cwd=candidate)
        if result.returncode == 0 and result.stdout.strip() == "true":
            partial = candidate
            break
    if partial is None:
        pytest.skip(
            "no partial clone on this machine -- the side effect this check "
            "measures cannot occur, and is not being reported as absent"
        )
    packs = partial / ".git" / "objects" / "pack"
    before = sorted(p.name for p in packs.glob("*.pack"))
    # A syntactically valid sha that no repository holds. If the guard
    # fails, git attempts a promisor fetch for it; if the guard holds,
    # git answers locally and writes nothing either way.
    _git("cat-file", "-e", "0" * 39 + "1", cwd=partial, timeout=NETWORK_TIMEOUT_SECONDS)
    after = sorted(p.name for p in packs.glob("*.pack"))
    assert before == after, (
        f"a presence query added {set(after) - set(before)} to {partial.name}'s "
        "pack directory -- the check is writing the evidence it reads"
    )


# --------------------------------------------------------------------
# the local half: every checkout the register names, where it is present
# --------------------------------------------------------------------


def test_each_recorded_local_checkout_is_at_the_recorded_commit():
    """Abbreviated commits in the artifact are compared as PREFIXES of the
    full sha read from the checkout, which is the only direction that is
    sound: a full sha starting with the recorded prefix confirms it, and
    nothing shorter could."""
    checked = 0
    for name, member in REGISTER["members"].items():
        entries = member.get("local_checkouts_of_it_on_this_machine") or member.get(
            "local_checkouts"
        )
        if not entries:
            continue
        for entry in entries:
            path = _checkout(entry["path"])
            if path is None:
                continue
            if entry["at"] == "THIS_CHECKOUT":
                # A REGISTER CANNOT RECORD ITS OWN REPOSITORY'S POSITION.
                # Any commit written into this row names the state BEFORE
                # the commit that writes it, so it is stale the instant it
                # lands -- measured on the first suite run after this file
                # was committed, which is when this branch was added. What
                # IS checkable is that the row names THIS checkout, so a
                # rename or a move fails here rather than passing quietly.
                assert path.resolve() == REPO_ROOT.resolve(), (
                    f"{name}: {entry['path']} is marked THIS_CHECKOUT and "
                    f"resolves to {path}, not {REPO_ROOT}"
                )
                checked += 1
                continue
            result = _git("rev-parse", "HEAD", cwd=path)
            assert result.returncode == 0, f"{entry['path']} has no HEAD"
            head = result.stdout.strip()
            assert head.startswith(entry["at"]), (
                f"{name}: {entry['path']} records {entry['at']} and is at {head[:12]}"
            )
            checked += 1
    if checked == 0:
        pytest.skip(
            "none of the recorded sibling checkouts are present on this machine"
        )


def test_the_core_pin_recorded_here_is_the_gitlink_this_repository_points_at():
    """The one member claim that is fully local, and the one that carries
    the most: `bent: zero` is an assertion about the core AT THE
    PARTICIPATING REFERENT, and this register now records that referent
    too. Two files stating one fact is two encodings unless they are
    joined, so they are joined."""
    core = None
    for member in REGISTER["members"].values():
        if member["posture"] == "core":
            core = member
            break
    assert core is not None, "the register declares a `core` posture and no core member"
    result = _git("ls-files", "-s", "vendor/scout-retrieval-agent", cwd=REPO_ROOT)
    if result.returncode != 0 or not result.stdout.strip():
        pytest.skip("no gitlink for the vendored core in this checkout")
    gitlink = result.stdout.split()[1]
    assert gitlink.startswith(core["pinned_here_at"]), (
        f"the register records the core pinned at {core['pinned_here_at']} "
        f"and the gitlink is {gitlink[:12]}"
    )
    declared = loads((REPO_ROOT / "architecture" / "core.yaml").read_text())
    assert gitlink.startswith(declared["submodule_commit"]), (
        "core.yaml and the gitlink disagree, which test_core_referent.py "
        "also covers -- reported here because this register joins on it"
    )


# --------------------------------------------------------------------
# the remote half: refs, when the network answers
# --------------------------------------------------------------------


def _remote_urls_of(member):
    if "names_that_resolve_here" in member:
        return list(member["names_that_resolve_here"])
    return [member["remote"]] if "remote" in member else []


def test_names_recorded_as_one_repository_have_identical_ref_sets():
    """The register's central structural claim: ten names, six
    repositories. Identity is EQUALITY OF THE FULL REF SET -- not a
    shared commit, which every fork of anything satisfies."""
    aliased = {
        name: member
        for name, member in REGISTER["members"].items()
        if "names_that_resolve_here" in member
    }
    if not aliased:
        pytest.skip("the register records no aliased members")
    checked = 0
    for name, member in aliased.items():
        sets = {}
        for url in member["names_that_resolve_here"]:
            refs = _ls_remote(url)
            if refs is None:
                continue
            sets[url] = refs
        if len(sets) < 2:
            continue
        first_url, first_refs = next(iter(sets.items()))
        for url, refs in sets.items():
            assert refs == first_refs, (
                f"{name}: {url} and {first_url} are recorded as one repository "
                f"and their ref sets differ"
            )
        checked += 1
    if checked == 0:
        pytest.skip(
            "no aliased member had two names answer -- the network did not "
            "reach them, and no identity claim is being reported as verified"
        )


def test_each_recorded_remote_head_is_still_served_by_its_remote():
    """A recorded head is a reading with a timestamp on it, and this
    ecosystem's timestamps are in minutes: the first run of this file
    failed because two remotes had moved in the eleven minutes since the
    register was written, both by one commit from a concurrent session.

    So asserting the recorded value EQUALS the live one would make this
    check red on ordinary work, and a check that is red on ordinary work
    is a check nobody reads. What is asserted instead is the property that
    actually carries: THE RECORDED COMMIT IS STILL SERVED. A branch
    advancing past a reading is expected. A reading the remote can no
    longer produce is a rewrite, a force-push or a collection -- and it
    voids, silently, every claim made relative to that referent.

    Fetched into a throwaway repository with no remote of its own, so the
    query cannot be answered by anything this machine already holds. A
    check that could be satisfied from the local object store would be
    measuring this machine rather than the remote."""
    checked = 0
    missing = []
    for name, member in REGISTER["members"].items():
        recorded = member.get("remote_head_at_measurement")
        if not recorded:
            continue
        urls = _remote_urls_of(member)
        if not urls:
            continue
        with tempfile.TemporaryDirectory() as scratch:
            initialised = _git("init", "-q", scratch)
            if initialised.returncode != 0:
                pytest.skip("git init failed; cannot isolate the query from this machine")
            result = _git(
                "fetch", "-q", "--depth=1", urls[0], recorded,
                cwd=scratch, timeout=NETWORK_TIMEOUT_SECONDS * 4,
            )
        if "could not resolve host" in result.stderr.lower():
            continue
        if "unable to access" in result.stderr.lower():
            continue
        checked += 1
        if result.returncode != 0:
            missing.append(f"{name}: {urls[0]} no longer serves {recorded}")
    if checked == 0:
        pytest.skip(
            "no remote answered -- the recorded referents are unverified on "
            "this run and are not being reported as confirmed"
        )
    assert not missing, (
        "a recorded referent has been rewritten or collected away, and every "
        "claim relative to it is now about an object that cannot be "
        "produced:\n  " + "\n  ".join(missing)
    )


def test_the_forks_recorded_as_unmodified_still_point_at_one_branch():
    """`unmodified_at_head` was established by showing the fork's head is a
    commit the true upstream serves. That half needs upstream's URL, which
    the register deliberately does not record as a member. What IS
    checkable here without inventing a member is the premise the claim
    rests on: the fork has ONE ref, so `at head` and `everywhere` coincide.
    A second branch appearing is exactly the state that would make the
    recorded claim narrower than it reads."""
    checked = 0
    for name, member in REGISTER["members"].items():
        if not member.get("unmodified_at_head"):
            continue
        refs = _ls_remote(member["remote"])
        if refs is None:
            continue
        branches = [ref for ref in refs if ref.startswith("refs/heads/")]
        assert len(branches) == 1, (
            f"{name} is recorded unmodified_at_head, and that claim covers "
            f"the whole repository only while it has one branch -- it has "
            f"{len(branches)}: {sorted(branches)}"
        )
        checked += 1
    if checked == 0:
        pytest.skip("no fork remote answered on this run")


# --------------------------------------------------------------------
# two records of one subject, bound to each other
# --------------------------------------------------------------------


def test_every_ecosystem_record_names_every_other_one():
    """Two records of this ecosystem exist because two sessions wrote one
    each and the merge could not conflict on it -- filed in
    architecture/proof_integrity.yaml as
    a_clean_merge_is_not_evidence_that_two_changes_are_compatible.

    Keeping both is the decision. What must not recur is keeping both
    WITHOUT EITHER KNOWING, so the property asserted is mutual reference
    over the DERIVED set: every architecture artifact whose own declared
    name says it is about the ecosystem must name each of the others by
    path. A third one written by a third session fails here on the day it
    lands, rather than sitting green beside the other two."""
    architecture = REPO_ROOT / "architecture"
    records = {}
    for path in sorted(architecture.glob("*.yaml")):
        document = loads(path.read_text())
        if not isinstance(document, dict):
            continue
        declared = str(document.get("artifact") or document.get("subject") or "")
        if "ecosystem" in declared:
            records[f"architecture/{path.name}"] = path.read_text()
    assert len(records) >= 2, (
        f"expected the census and the register, found {sorted(records)}"
    )
    unbound = []
    for name, text in records.items():
        for other in records:
            if other != name and other not in text:
                unbound.append(f"{name} does not name {other}")
    assert not unbound, (
        "a record of this ecosystem does not know the others exist:\n  "
        + "\n  ".join(unbound)
    )


# --------------------------------------------------------------------
# the candidate names are SWEPT, not listed
# --------------------------------------------------------------------

#: `notationsystems/<name>`, wherever it appears -- a URL, a markdown link,
#: a Cargo path, a prose reference. The owner prefix is required so this
#: cannot match an arbitrary path segment.
_OWNED_REPOSITORY = re.compile(r"notationsystems/([A-Za-z0-9][A-Za-z0-9._-]*)")

#: File kinds a human writes. A repository name reaches this register by
#: someone mentioning it, so the sweep covers what people edit.
_AUTHORED_SUFFIXES = (".yaml", ".yml", ".py", ".md", ".json", ".toml")


def _named_repositories(inside_vendor: bool):
    """Every notationsystems repository this tree names.

    THE SCOPE SPLIT IS LOAD-BEARING. Names under vendor/ are the CORE'S
    references to its own build environment -- sibling paths in a Cargo
    manifest, not claims this repository makes about the ecosystem.
    Sweeping them together would attribute the core's expectations to
    this layer; sweeping only outside vendor/ would lose two real
    repositories. So both are swept and they are kept apart."""
    found = set()
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in _AUTHORED_SUFFIXES:
            continue
        relative = path.relative_to(REPO_ROOT)
        if not relative.parts:
            continue
        in_vendor = relative.parts[0] == "vendor"
        if relative.parts[0] == ".git" or in_vendor != inside_vendor:
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):           # pragma: no cover
            continue
        for match in _OWNED_REPOSITORY.finditer(text):
            found.add(match.group(1).removesuffix(".git"))
    return found


def _names_the_register_accounts_for():
    names = set()
    for member in REGISTER["members"].values():
        for url in _remote_urls_of(member):
            tail = url.rstrip("/").rsplit("/", 1)[-1]
            names.add(tail.removesuffix(".git"))
    return names


def test_every_repository_this_tree_names_is_accounted_for_in_the_register():
    """THE DEFECT THIS CLOSES, WHICH BIT THREE TIMES.

    The first two versions of the register derived their candidate names
    from the REMOTES OF CHECKOUTS ON THIS MACHINE. That source cannot
    contain a name nothing here points at, so it missed
    `data-acquisition-fabric` (found by the census), then
    `Payload-Terminal-V0` and `Scientific-Compute-Layer-SCL-` (named in
    epistemics/corpus/contract.json, a file this repository CARRIES).
    Six members became eleven when the names were swept instead.

    Matching is by NAME rather than by ref set, deliberately: this check
    must run with no network, because its whole job is to fail when
    somebody writes a repository name nobody has classified -- and that
    failure must not depend on whether GitHub is reachable.

    A name that resolves nowhere is still accounted for by being recorded
    with a posture. `unclassified` exists for exactly that, so there is
    never a reason to leave one out."""
    named = _named_repositories(inside_vendor=False)
    accounted = _names_the_register_accounts_for()
    # A name that is a strict prefix of an accounted one, with no
    # occurrence of its own, is a match artefact rather than a repository.
    unaccounted = sorted(
        name for name in named - accounted
        if not any(other.startswith(name) and other != name for other in accounted)
    )
    assert not unaccounted, (
        "this repository names notationsystems repositories the ecosystem "
        f"register does not account for: {unaccounted}\n"
        "Give each one a posture -- `unclassified` is a posture and means "
        "it resolves and nobody has read it."
    )


def test_the_vendored_core_names_repositories_this_register_records_separately():
    """The core's own references, swept apart from this repository's.

    They are not noise: two of them are real repositories the register now
    carries, marked `found_by` the vendored sweep. What must stay true is
    that the two scopes are DISTINGUISHED -- a name that reaches the
    register only through the core is a fact about the core's environment,
    and recording it as this layer's claim would be false."""
    from_core = _named_repositories(inside_vendor=True)
    if not from_core:
        pytest.skip("the vendored core is not checked out here")
    accounted = _names_the_register_accounts_for()
    assert from_core & accounted, (
        "the vendored core names repositories and the register accounts for "
        f"none of them: {sorted(from_core)}"
    )
    for name, member in REGISTER["members"].items():
        if "found_by" in member:
            assert "vendor" in member["found_by"] or "core" in member["found_by"], (
                f"{name} records a found_by that does not name the scope it came from"
            )
