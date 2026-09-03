"""`" ".join(a_mapping)` joins the KEYS.

THE DEFECT. A record in this repository is a mapping whose keys are
descriptive sentences-as-identifiers. So `assert "x" in " ".join(record)`
searches the KEY NAMES, and a key called `what_is_not_claimed` satisfies
an assertion meant to check that something is not claimed. The assertion
passes without any value being read.

It has been caught by hand eight times in this programme and never by a
check. This is the check. It asserts the PROPERTY -- no join over a name
used as a mapping in the same function -- rather than enumerating the
sites, which is the repair rule architecture/proof_integrity.yaml adopts
for the whole coverage-by-enumeration class.

WHY THE PROPERTY IS THIS ONE AND NOT A BROADER ONE. `.join(<bare name>)`
occurs 62 times in this tree and almost all are lists: `lines`, `parts`,
`conflicts`. A guard on bare names would raise 62 alarms to catch two
defects and would be turned off within a day. Measured before choosing:
the narrower property -- the joined name is ALSO subscripted by a string
literal, or has .items()/.values()/.keys() called on it, in the same
function -- found exactly two sites and no false positives.

WHAT IT CANNOT CATCH, stated because an unstated limit is how the first
form of the corpus guard got written. A mapping joined in one function
and only ever subscripted in another is invisible here, as is one reached
through an attribute rather than a name. The check is a lower bound on
the defect and not a proof of its absence.
"""

from __future__ import annotations

import ast
import pathlib
from typing import List, Set, Tuple

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _names_used_as_a_mapping(function: ast.AST) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(function):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)):
            names.add(node.value.id)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("items", "values", "keys")
                and isinstance(node.func.value, ast.Name)):
            names.add(node.func.value.id)
    return names


def _joins_over_a_mapping(source: str, path: str) -> List[Tuple[str, int, str]]:
    """Every `<sep>.join(name)` where `name` is used as a mapping nearby."""
    found: List[Tuple[str, int, str]] = []
    tree = ast.parse(source)
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        mapping_names = _names_used_as_a_mapping(function)
        for node in ast.walk(function):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "join" and len(node.args) == 1
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in mapping_names):
                found.append((path, node.lineno, node.args[0].id))
    return found


def _tracked_python():
    for path in sorted(REPO_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        yield relative, path


def test_no_module_joins_a_name_it_uses_as_a_mapping():
    offenders: List[Tuple[str, int, str]] = []
    for relative, path in _tracked_python():
        try:
            source = path.read_text()
        except OSError:
            continue
        try:
            offenders.extend(_joins_over_a_mapping(source, str(relative)))
        except SyntaxError:
            continue
    assert offenders == [], (
        f"joining a mapping yields its KEYS: {offenders}. If the intent is the values, "
        "say .values(); if it is the keys, say .keys(). A bare join over a record is an "
        "assertion that a KEY NAME contains a substring, which passes without reading "
        "anything the record says."
    )


def test_the_check_fires_on_the_construction_it_names():
    """DETECTOR PROOF, in-process rather than by editing the tree.

    Both halves matter: the mapping form must be caught and the list form
    must NOT be, because a guard that flagged every join would have been
    turned off before it caught anything.
    """
    defective = (
        "def f(record):\n"
        "    assert 'x' in ' '.join(record)\n"
        "    return record['key']\n"
    )
    assert _joins_over_a_mapping(defective, "planted.py") == [("planted.py", 2, "record")]

    innocent = (
        "def f(rows):\n"
        "    lines = [str(r) for r in rows]\n"
        "    return '\\n'.join(lines)\n"
    )
    assert _joins_over_a_mapping(innocent, "innocent.py") == []

    explicit = (
        "def f(record):\n"
        "    assert 'x' in ' '.join(record.values())\n"
        "    return record['key']\n"
    )
    assert _joins_over_a_mapping(explicit, "explicit.py") == [], (
        "saying .values() is the repair; flagging it would leave no way to comply"
    )


def test_the_broader_property_was_measured_and_rejected_rather_than_assumed():
    """The docstring claims 62 bare-name joins exist and that a guard on
    them would be unusable. Measured here, so the reason the narrow
    property was chosen is evidence rather than an assertion."""
    bare = 0
    for _relative, path in _tracked_python():
        try:
            tree = ast.parse(path.read_text())
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "join" and len(node.args) == 1
                    and isinstance(node.args[0], ast.Name)):
                bare += 1
    assert bare > 40, (
        f"only {bare} bare-name joins remain; the argument for the narrow property "
        "rested on there being many, and it needs re-making"
    )
