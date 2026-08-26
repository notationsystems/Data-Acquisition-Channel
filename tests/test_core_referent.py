"""What `core@1.0.0` refers to, checked against the thing it refers to.

33 artifacts declare `extends: core@1.0.0`, the doctrine projection prints
it, and `bent: []` is a claim made RELATIVE to a core. Every one of those
joined on the VERSION -- the one field upstream controls and can move --
while `submodule_commit`, which cannot move without the vendored code
changing, was recorded and read by nothing.

THE FAILURE THIS EXISTS FOR IS NOT A VERSION BUMP. A bump is loud: the
substring check fails and someone looks. The silent case is a submodule
bumped to a commit whose pyproject still says 1.0.0, which is what patch
commits look like. Then the recorded commit is wrong, every check passes,
and all 33 `extends` still agree with each other about a core that moved.

Declared in architecture/core.yaml under `core_referent`: the commit is
PARTICIPATING, the version is ANNOTATING, and a join on an annotating
field is the defect (SCL_CONTRACT 6.1).
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

import daf  # noqa: F401
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = REPO_ROOT / "architecture"
CORE = loads((ARCHITECTURE / "core.yaml").read_text())
REFERENT = CORE["core_referent"]


def _gitlink_commit():
    """The commit this repository's tree actually points the submodule at.

    Read from the TREE rather than from the working directory, because a
    detached or locally-moved checkout is a different fact from what the
    repository records."""
    result = subprocess.run(
        ["git", "ls-tree", "HEAD", CORE["submodule_path"]],
        cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    fields = result.stdout.split()
    return fields[2] if len(fields) > 2 else None


def test_the_declaration_names_which_field_is_which():
    """The referent must be declared before it can be checked. A probe
    that infers which field is participating would be deciding the
    question it is meant to verify."""
    assert REFERENT["participating"] == "submodule_commit"
    assert REFERENT["annotating"] == "version"
    assert REFERENT["enforcement"] == "tests/test_core_referent.py"


def test_the_recorded_commit_is_the_one_the_repository_points_at():
    """THE CHECK THAT DID NOT EXIST. `submodule_commit` was recorded and
    verified by nothing, so a submodule bump left it silently stale."""
    actual = _gitlink_commit()
    if actual is None:
        pytest.skip("no gitlink for the submodule (not a submodule checkout)")
    recorded = CORE["submodule_commit"]
    assert actual.startswith(recorded), (
        f"core.yaml records submodule_commit {recorded!r} but the repository points at "
        f"{actual[:12]!r}. The core moved and the participating referent did not follow, "
        f"so every claim made relative to core@{CORE['version']} is about a different object.")


def test_the_version_label_is_parsed_from_the_project_table_not_matched_in_text():
    """The prior check was `f'version = \"{v}\"' in pyproject_text` -- a
    substring match over the whole file, which cannot distinguish the
    project version from a dependency pin, a tool table or a comment.
    Parsed instead, so the label is bound to the field that means it."""
    pyproject = REPO_ROOT / CORE["submodule_path"] / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("the vendored pyproject is not checked out")
    document = tomllib.loads(pyproject.read_text())
    declared = document.get("project", {}).get("version")
    assert declared is not None, "the vendored pyproject has no [project] version to bind to"
    assert declared == CORE["version"], (
        f"core.yaml labels the core {CORE['version']!r}; the vendored project declares "
        f"{declared!r}")
    assert document.get("project", {}).get("name") == CORE["name"]


def test_every_artifact_extends_the_declared_label():
    """Derived over every architecture artifact rather than a list, so an
    artifact added later cannot quietly extend a different core."""
    expected = f"core@{CORE['version']}"
    artifacts, disagreeing = 0, []
    for path in sorted(ARCHITECTURE.rglob("*.yaml")):
        try:
            document = loads(path.read_text())
        except Exception:
            continue
        if not isinstance(document, dict) or "extends" not in document:
            continue
        artifacts += 1
        if document["extends"] != expected:
            disagreeing.append((str(path.relative_to(REPO_ROOT)), document["extends"]))
    assert artifacts >= 20, f"only {artifacts} artifacts declare `extends`; the sweep has drifted"
    assert not disagreeing, (
        f"these extend a core other than {expected}: {disagreeing}")


def test_a_claim_relative_to_core_is_relative_to_the_participating_referent():
    """`bent: []` and `core_invariants_modified: 0` are assertions ABOUT
    the core. They are only meaningful at a stated referent, and the
    declaration has to say so -- otherwise a submodule bump silently
    re-points a claim nobody re-measured."""
    assert "participating referent" in REFERENT["what_a_claim_relative_to_core_means"].lower()
    probe = loads((ARCHITECTURE / "_probes" / "generality.yaml").read_text())
    outcome = probe["outcome"]
    assert "bent" in outcome and "core_invariants_modified" in outcome, (
        "the probe no longer carries the core-relative claims this rule governs")
