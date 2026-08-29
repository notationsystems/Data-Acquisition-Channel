"""The four chemistry rules a build brief filed to DAQ are STE's, exist,
and are enforced -- and nothing reaches them.

EVERY CLAIM IN THE ARTIFACT IS RE-MEASURED HERE AGAINST THE VENDORED TREE
rather than restated from it. A record that says `assert_identity_policy
is in structures/substance.py` is prose bound to nothing the moment that
file moves; these tests read the tree.
"""

from __future__ import annotations

import ast
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

VENDOR = REPO_ROOT / "vendor" / "scout-retrieval-agent"
OWNERSHIP = loads((REPO_ROOT / "architecture" / "chemistry_rule_ownership.yaml").read_text())
INVARIANTS = loads((REPO_ROOT / "architecture" / "invariants.yaml").read_text())
RULES = OWNERSHIP["where_each_rule_lives"]

# The guards, derived from the artifact rather than listed here, so a rule
# added to the record without a measurement cannot pass silently.
GUARDS = {
    "identity_policy_declared": ("structures/substance.py", "assert_identity_policy"),
    "no_point_identity_for_distributions": ("structures/substance.py", "assert_distribution_identity"),
    "computed_fully_specified": ("structures/method_blocks.py", "assert_method_block"),
    "applicability_domain_declared": ("structures/method_blocks.py", "assert_applicability"),
}


def _functions_in(relative: str):
    tree = ast.parse((VENDOR / relative).read_text())
    return {node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_the_record_covers_exactly_the_rows_daq_marks_absent_for_this_reason():
    """Derived from invariants.yaml, not enumerated here: a fifth row
    acquiring the same gap must not sit unrecorded."""
    absent_for_this_reason = {
        row["id"] for row in INVARIANTS["invariants"]
        if row.get("status") == "absent"
        and row.get("gap") == "no chemistry representation exists in this repository at all"
    }
    assert absent_for_this_reason == set(RULES), (
        f"the ownership record and the invariant rows disagree: {absent_for_this_reason ^ set(RULES)}"
    )


def test_every_rule_daq_records_as_absent_is_implemented_in_the_vendored_tree():
    """The discrepancy itself. `absent` is true of DAQ and false of the
    pair, and this is the measurement that makes the difference real
    rather than a reading."""
    for rule, (relative, guard) in GUARDS.items():
        assert rule in RULES, f"{rule} is not in the ownership record"
        assert (VENDOR / relative).exists(), f"{relative} is gone; re-measure rather than re-read"
        assert guard in _functions_in(relative), (
            f"{guard} is no longer defined in {relative}. The ownership record names a guard that "
            "does not exist, which is worse than recording nothing."
        )
        assert relative in RULES[rule]["ste_implementation"]
        assert guard in RULES[rule]["ste_implementation"]
        assert RULES[rule]["daq_row"] == "absent"


def test_daq_still_records_the_rows_as_absent_and_does_not_amend_them():
    """Not fixed, deliberately. A row that started describing another
    repository's state would be a worse record than a precise one plus a
    file naming the owner and the pin."""
    for rule in RULES:
        row = next(r for r in INVARIANTS["invariants"] if r["id"] == rule)
        assert row["status"] == "absent"
    assert "does_not_amend_the_invariant_rows" in OWNERSHIP["what_this_does_not_do"]
    assert "does_not_build_the_representation" in OWNERSHIP["what_this_does_not_do"]


def test_nothing_outside_the_probe_and_its_harness_calls_the_guards():
    """THE FINDING THAT MATTERS MORE THAN THE MISFILING, and the reason
    DAQ's acquisition path cannot move STE's number on its own.

    Derived by scanning the whole vendored tree for call sites, not by
    checking the two files the record happens to name."""
    guard_names = {guard for _, guard in GUARDS.values()}
    callers = {}
    for path in sorted(VENDOR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(VENDOR).as_posix()
        if relative.startswith("structures/") or relative.startswith("tests/"):
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in guard_names:
                callers.setdefault(relative, set()).add(node.func.id)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in guard_names:
                callers.setdefault(relative, set()).add(node.func.attr)

    assert set(callers) <= {"scripts/chemistry_reachability.py", "scripts/mutate_reachability_checks.py"}, (
        "a caller appeared outside the probe and its mutation harness. If it is in an admission or "
        f"acquisition path, the twenty codes may now be REACHABLE and the record needs re-measuring: {callers}"
    )


def test_the_record_does_not_claim_stes_number_moved():
    """DAQ reports; STE re-runs its own probe. The guard against DAQ
    reading its own acquisition path as evidence about STE's gates."""
    finding = OWNERSHIP["the_gates_exist_and_nothing_reaches_them"]
    assert "cannot on its own" in finding["and_it_corrects_what_daq_implied"]
    assert "CALL SITE" in finding["and_it_corrects_what_daq_implied"]
    assert "does_not_claim_stes_number_moved" in OWNERSHIP["what_this_does_not_do"]

    reachability = loads((VENDOR / "architecture" / "chemistry_reachability.yaml").read_text())
    summary = reachability["summary"]
    assert summary["reachable_from_any_entry"] == 0, (
        "STE's probe now reports a reachable code; this record's central measurement is stale"
    )
    assert summary["codes_total"] == summary["live"] == 20
    assert str(summary["codes_total"]) in finding["which_is_exactly_what_stes_own_probe_says"]

    # The field DAQ's acquisition path would move if it moved anything.
    # It is STE's to re-measure; DAQ asserts only that it has not read a
    # change into it.
    assert summary["exercised_by_real_acquisition"] == 0, (
        "STE's probe now reports acquisition reaching a chemistry gate. That is STE's finding to "
        "report, and DAQ's phase 38 conclusion needs re-measuring against it rather than assuming "
        "the acquisition path caused it"
    )


def test_the_silence_rule_is_the_one_daq_already_owns():
    """Not a new principle invented for chemistry: DAQ's own
    admission_reachability rule, applied to DAQ's own inference."""
    finding = OWNERSHIP["the_gates_exist_and_nothing_reaches_them"]
    rule = loads((REPO_ROOT / "architecture" / "admission_reachability.yaml").read_text())
    wording = str(rule)
    assert "silent, not clean" in wording
    assert "silent, not clean" in finding["the_rule_this_is_an_instance_of"]
