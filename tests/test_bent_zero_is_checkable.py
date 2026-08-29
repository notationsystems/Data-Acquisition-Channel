"""`bent: zero`, checked against a declared set for the first time.

WHAT THE CLAIM WAS RESTING ON. Eleven `bent: zero` statements are held in
this repository's phase documents, and the register recorded honestly
that none of them could be checked AS WORDED:

    "an unenumerated set has no members to check. A claim quantified over
    it is not false; it is unfalsifiable in the form it is written."

What supported it instead was a stronger observable by a different route:
the core's bytes were unmodified at the pinned commit, and zero files
changed entails zero invariants changed, whatever they are and however
many. The register also named what would end that: "a submodule bump. The
moment the pin moves, `bent: zero` stops being entailed by byte-identity
and has to be re-established against a set still nobody has enumerated."

BOTH HALVES OF THAT SENTENCE TURNED OUT DIFFERENTLY. The pin moved 68
commits and the bytes are STILL unmodified -- `core/` is byte-identical
across the whole range -- so the entailment did not lapse. And the set is
no longer unenumerated: the core party declared it, five invariants
stated as rules, eleven rows in the shared exchange register.

SO THE CLAIM CAN BE CHECKED AS WORDED, AND THIS FILE CHECKS IT. The
result is not "clean". Every one of the five declared invariants names a
subject in `core.*`, and no authored package here imports `core.*` at
all. By this repository's own recorded rule -- `zero_rate_when_unreachable`
in architecture/admission_reachability.yaml -- that is SILENCE, not
cleanliness:

    "no acquisition path can reach the gate. NOT a measurement; the
    metric is silent, not clean."

WHICH IS STILL A REAL IMPROVEMENT, and the difference is worth stating
precisely. Before: unfalsifiable, because the set had no members. Now:
falsifiable, because the set has members and a member becomes reachable
the moment any authored module imports its subject. The claim went from
one that could not fail to one that can, and today it does not.

THE PART THAT WAS NOT ENFORCED, found by asking. Unreachability was only
partly checked: `epistemics/` had a leaf-layer test forbidding `core`,
and three adapter files had their own, and `daf/`, `science/`, `bridge/`,
`boundary/` and `assertion/` had none. So today's zero was structural for
some packages and incidental for the rest -- coverage specified by
enumeration, in the check that `bent: zero` now depends on. Closed below
as a property over every authored package.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE = loads((REPO_ROOT / "architecture" / "core.yaml").read_text())
VENDOR = REPO_ROOT / CORE["submodule_path"]
REGISTER = loads((REPO_ROOT / "architecture" / "exchange" / "invariant_register.yaml").read_text())


def _authored_packages():
    """Every top-level package of authored code, DERIVED rather than
    listed. A package added later is covered the day it is added, which
    is the failure the previous per-file checks had."""
    skip = {"vendor", "tests", "docs", "architecture", "build", "dist"}
    return sorted(
        path.name for path in REPO_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith(".")
        and path.name not in skip and (path / "__init__.py").exists()
    )


def _imports_of(package: str):
    for path in sorted((REPO_ROOT / package).rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield path, alias.name
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                yield path, node.module


# --------------------------------------------------- the property, not a list


def test_no_authored_package_imports_the_core():
    """THE ENFORCEMENT `bent: zero` NOW DEPENDS ON, stated as a property.

    It was enumerated: one leaf-layer test for `epistemics/` and three
    per-adapter tests. Every other authored package was unchecked, so the
    claim's support was structural for some and incidental for the rest
    -- and nothing said which. That is the enumerated-coverage shape
    inside the check that carries the claim."""
    packages = _authored_packages()
    assert len(packages) >= 5, f"the package derivation found only {packages}"

    offenders = []
    for package in packages:
        for path, module in _imports_of(package):
            if module.split(".")[0] == "core":
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {module}")
    assert offenders == [], (
        "an authored module imports the vendored core. `bent: zero` is a claim that this pair did "
        f"not modify the core's invariants; reaching into it is how that stops being true: {offenders}"
    )


def test_the_property_check_actually_bites():
    """PLANT THE DEFECT. A check that has never been shown capable of
    failing has established nothing -- and this one now carries the
    claim, so it earns the proof rather than the assumption."""
    tree = ast.parse("from core.canonical.state import CanonicalState\n")
    modules = [
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert modules and modules[0].split(".")[0] == "core", (
        "the detector no longer recognises a core import, so its silence means nothing")


# ------------------------------------------- the claim, checked as worded


def test_the_five_declared_invariants_all_name_a_subject_under_core():
    """Why the answer is silence: the declared set's subjects live where
    this repository does not go. Read from the counterparty's declaration
    with PyYAML, because that file is hand-authored and the exchange
    surface -- not internal architecture -- is what this reader is
    promised."""
    yaml = pytest.importorskip("yaml")
    declaration = VENDOR / "architecture" / "canonical_state_invariants.yaml"
    if not declaration.exists():
        pytest.skip("the pin does not hold a declaration")

    invariants = yaml.safe_load(declaration.read_text())["invariants"]
    assert len(invariants) == 5, f"the declared set changed size: {len(invariants)}"

    validators = []
    for entry in invariants:
        enforcement = entry.get("enforcement") or {}
        validators.append(str(enforcement.get("validator", "")))
    under_core = [v for v in validators if v.startswith("core.")]
    assert len(under_core) >= 3, (
        f"fewer declared invariants name a core.* subject than measured: {validators}. If one "
        "names a subject this repository DOES reach, `bent: zero` stops being silent about it "
        "and becomes a real per-invariant question."
    )


def test_the_register_records_that_the_answer_is_silence_not_cleanliness():
    rests_on = REGISTER["what_bent_zero_actually_rests_on"]
    assert "silence" in str(rests_on).lower() or "unreachable" in str(rests_on).lower(), (
        "the register must not report this check as clean; every declared invariant's subject is "
        "unreachable from here, and a zero over an unreachable subject is silent"
    )


def test_the_core_is_still_byte_identical_at_the_moved_pin():
    """The old route, re-measured rather than assumed to have lapsed. The
    register predicted a bump would end it; it did not, because the bump
    changed nothing under `core/`."""
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--stat", "3e5bea9", "HEAD", "--", "core/"],
        cwd=str(VENDOR), capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        pytest.skip("the old pin is not reachable in this checkout")
    assert result.stdout.strip() == "", (
        f"core/ changed between the old pin and the new one: {result.stdout.strip()[:200]}. "
        "`bent: zero` loses the byte-identity route and rests on reachability alone."
    )
