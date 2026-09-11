"""A guard that can be UNWIRED with the suite still green.

THE CLASS. A validator is written, and a test is written for it, and the
test calls the validator DIRECTLY. The call site inside the function the
validator protects is then untested: delete that one line and every test
still passes. The guard still exists, is still correct, and no longer
runs.

It is the vacuous-evidence class one level up. The usual form is a check
that could not have detected the falsity of its claim. This one is a check
that is not reached at all -- and the test suite reports the guard as
covered, because the guard IS covered. What is uncovered is its wiring.

HOW IT WAS FOUND. Not here. Retrofitting a disposition-band guard into a
separate BIM project, six planted defects were detected and a seventh was
not: removing the `_validate_disposition_band(...)` call from the function
it protects left the suite green, because every test called the validator
by name. The fix was a test through the public entry point. This tool is
that fix generalised -- the hand method was to plant one defect and look,
so the tool plants every one of them and looks.

THE METHOD. A guard is a function that returns no value and can raise: it
exists to refuse. Its call site is a bare expression statement, so the
line can be deleted without any other change. For each such site the line
is commented out, the tests are run, and the site is restored. A site
whose removal nothing notices is reported.

TARGETED FIRST, THEN FULL. Running the whole suite for every site costs
minutes each. A targeted selection -- the test modules that name the
guard's own module -- is tried first, and only a site that SURVIVES the
targeted pass is re-run against the full suite before being reported. So
a survivor is always confirmed against everything, and a detection is
never claimed on a partial run.

WHAT IT DOES NOT ESTABLISH. That a detected site is WELL tested; only
that removing it is noticed. And it cannot see a guard whose call site is
not a bare statement -- an inline `if not valid(x): raise` is a different
shape and is invisible here. Both are limits of the method, recorded
rather than left for a reader to discover.

Run:  PYTHONPATH=vendor/scout-retrieval-agent python3 tools/wiring_probe.py
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
from typing import Iterator, List, NamedTuple, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

PRODUCT_PACKAGES = ("daf", "science", "boundary", "bridge", "epistemics", "session",
                    "commerce", "tools", "assertion", "instrument")


class Site(NamedTuple):
    path: pathlib.Path
    line: int
    guard: str

    def label(self) -> str:
        return f"{self.path.relative_to(REPO_ROOT)}:{self.line} {self.guard}()"


def _guard_names() -> dict:
    """Functions that exist to refuse: they raise, and return no value."""
    guards: dict = {}
    for package in PRODUCT_PACKAGES:
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                raises = any(isinstance(n, ast.Raise) for n in ast.walk(node))
                returns_value = any(
                    isinstance(n, ast.Return) and n.value is not None
                    for n in ast.walk(node)
                )
                if raises and not returns_value:
                    guards.setdefault(node.name, []).append(path)
    return guards


def _entry_point_lines(tree: ast.AST) -> set:
    """Lines inside `if __name__ == "__main__":`.

    A module entry point matches the guard shape -- it raises and returns
    nothing -- and is not a guard. Excluded STRUCTURALLY, by the block it
    sits in, rather than by naming `_main` in a list: an exclusion list is
    how this kind of sweep goes quiet.
    """
    lines = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name) and test.left.id == "__name__"):
            for inner in ast.walk(node):
                if hasattr(inner, "lineno"):
                    lines.add(inner.lineno)
    return lines


def sites() -> List[Site]:
    guards = _guard_names()
    found: List[Site] = []
    for package in PRODUCT_PACKAGES:
        for path in sorted((REPO_ROOT / package).rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            tree = ast.parse(path.read_text())
            skip = _entry_point_lines(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Expr) or node.lineno in skip:
                    continue
                call = node.value
                if not isinstance(call, ast.Call):
                    continue
                if isinstance(call.func, ast.Name):
                    name = call.func.id
                elif isinstance(call.func, ast.Attribute):
                    name = call.func.attr
                else:
                    continue
                if name in guards:
                    found.append(Site(path, node.lineno, name))
    return found


def _targeted(site: Site) -> List[str]:
    """Test modules that name the guard's module or the guard itself.

    A heuristic, and recorded as one. It only ever SHORTENS the work: a
    site that survives it is re-run against the whole suite.
    """
    stem = site.path.stem
    chosen = []
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        text = path.read_text()
        if stem in text or site.guard in text:
            chosen.append(str(path.relative_to(REPO_ROOT)))
    return chosen


def _run(selection: List[str]) -> bool:
    """True when the tests PASS, which for a planted defect means the
    removal went unnoticed."""
    for cache in REPO_ROOT.rglob("__pycache__"):
        if "vendor" not in str(cache):
            subprocess.run(["rm", "-rf", str(cache)], check=False)
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
         *(selection or ["tests"])],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**__import__("os").environ,
             "PYTHONPATH": str(REPO_ROOT / "vendor" / "scout-retrieval-agent")},
    )
    return completed.returncode == 0


def _without(site: Site) -> str:
    lines = site.path.read_text().splitlines(keepends=True)
    original = lines[site.line - 1]
    indent = len(original) - len(original.lstrip())
    lines[site.line - 1] = " " * indent + "pass  # wiring_probe: removed\n"
    return "".join(lines)


def probe() -> Tuple[List[Site], List[Site]]:
    detected: List[Site] = []
    survived: List[Site] = []
    for site in sites():
        original = site.path.read_text()
        try:
            site.path.write_text(_without(site))
            targeted = _targeted(site)
            if not _run(targeted):
                detected.append(site)
                print(f"  detected  {site.label()}   ({len(targeted)} targeted modules)")
                continue
            # Survived the targeted pass -- confirm against everything before
            # reporting it, so no survivor is claimed on a partial run.
            if _run([]):
                survived.append(site)
                print(f"  SURVIVED  {site.label()}   (full suite green without it)")
            else:
                detected.append(site)
                print(f"  detected  {site.label()}   (full suite only)")
        finally:
            site.path.write_text(original)
    return detected, survived


def main() -> int:
    found = sites()
    print(f"{len(found)} guard call sites derived from the tree\n")
    detected, survived = probe()
    print(f"\n{len(detected)} detected, {len(survived)} SURVIVED")
    for site in survived:
        print(f"  UNWIRABLE: {site.label()}")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
