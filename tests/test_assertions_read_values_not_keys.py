"""A NAMED CHECK for the most reliably recurring construction error here.

THE ERROR. A test asserts that some text appears in a record's VALUE, and
the text it looks for is carried by the KEY that indexes it. The
assertion then proves nothing about the content: it is satisfiable by the
index it is reading through.

Committed three times in one session by one author, each time in the same
construction, each time caught only by the test failing:

    assert "success" in PREREG["what_would_make_this_phase_a_success..."]
    assert "does not describe this tree" in RECORD[...]["so_the_finding_does_not_describe_this_tree"]
    assert "not a binding" in RECORD["what_this_file_is_not"]

Three instances of one construction is a pattern worth a check rather
than a note, which is what this is.

WHAT THIS CHECK DOES AND DOES NOT CATCH -- stated, because a check
described as covering the class when it covers part of it is the
proxy-for-its-target shape this repository files.

CAUGHT: an assertion whose literal is WHOLLY CONTAINED in the key path it
indexes. That assertion cannot distinguish a correct value from any other
text sharing the key's vocabulary, so it is unsound whether or not it
passes. Two of the three instances above are this shape, and it found a
fourth, live, in tests/test_kalman_framing.py.

NOT CAUGHT: the third instance. `"not a binding"` is not contained in
`what_this_file_is_not` -- only the negation is shared -- and the rest of
the literal was genuinely absent from the value. Detecting that
statically would require knowing the value, which is what running the
test already does.

A SIBLING RULE, ADDED LATER AND EXACT. A comparison whose BOTH sides are
authored constants reads no value at all. It was added after the author
wrote `assert "does not claim" in "what_this_record_does_not_claim"` --
reaching for a record key and typing it as a string. That instance was
FALSE and failed loudly; with a key whose words matched it would have
passed forever. Swept over the corpus it found no other instance, so it
is a guard against recurrence rather than a discovery, and its detector
proof is the real line rather than an invented one.

AND A RULE THAT WAS TRIED AND REJECTED. A NEGATION rule -- flag when a
literal and its key share a negation token -- was measured against the
live corpus and produced ELEVEN false positives, every one a legitimate
assertion whose value genuinely contains the negation. It would have
caught the third instance and made the check unusable. Recorded because a
rejected rule with its measurement is worth more than a rule quietly not
tried: the reason this check covers two thirds of the class is that the
remaining third has no sound static form, not that nobody looked.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402


def _tokens(text: str) -> set:
    return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}


def assertions_satisfiable_by_their_own_key(source: str):
    """Every `<literal> in <subscript chain>` whose literal's words are a
    subset of the key path's words.

    Derived from the syntax rather than from a list of known-bad files,
    so a new instance in a new test fails on the day it is written.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Compare)
                and len(node.ops) == 1 and isinstance(node.ops[0], ast.In)
                and isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, str)):
            continue
        target, keys = node.comparators[0], []
        while isinstance(target, ast.Subscript):
            index = target.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, str):
                keys.append(index.value)
            target = target.value
        if not keys:
            continue
        literal = _tokens(node.left.value)
        if literal and literal <= _tokens(" ".join(keys)):
            found.append((node.left.value, keys, getattr(node, "lineno", 0)))
    return found


def assertions_that_read_nothing(source: str):
    """Every comparison whose BOTH sides are authored constants.

    A SIBLING OF THE CLASS ABOVE, AND A STRICTLY WORSE FORM. There the
    assertion reads a value through a key that already implies the
    answer; here it reads no value at all -- both operands were typed by
    the author, so the comparison is a fact about the source text and its
    verdict is fixed before the suite runs.

    Detection is EXACT rather than heuristic, which is why this rule can
    exist where the negation rule could not: there is no legitimate
    reason to compare two literals in an assertion, so it has no false
    positives to measure. It was added after the author wrote

        assert "does not claim" in "what_this_record_does_not_claim"

    reaching for a record key and typing it as a string. That one
    happened to be FALSE and failed loudly. Written with a key whose
    words matched, it would have passed forever."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        operands = [node.left, node.comparators[0]]
        if all(isinstance(operand, ast.Constant) for operand in operands):
            found.append((ast.unparse(node), getattr(node, "lineno", 0)))
    return found


def test_no_test_compares_two_things_the_author_typed():
    offenders = []
    for path in sorted((REPO_ROOT / "tests").glob("*.py")):
        if path.name == "test_assertions_read_values_not_keys.py":
            continue                       # this file quotes the bad forms on purpose
        for expression, line in assertions_that_read_nothing(path.read_text()):
            offenders.append(f"{path.name}:{line}  {expression}")
    assert offenders == [], (
        "a comparison whose both sides are constants reads no value; its verdict is fixed "
        "before the suite runs:\n  " + "\n  ".join(offenders)
    )


def test_the_constant_comparison_check_catches_the_instance_that_motivated_it():
    """DETECTOR PROOF, on the real line rather than an invented one."""
    caught = assertions_that_read_nothing(
        'assert "does not claim" in "what_this_record_does_not_claim"')
    assert len(caught) == 1

    assert assertions_that_read_nothing('assert "a" in RECORD["b"]') == [], (
        "an assertion that reads a value must not be flagged, or the rule catches the corpus "
        "rather than the error"
    )
    assert assertions_that_read_nothing('assert len(x) == 10') == []
    assert assertions_that_read_nothing('assert x.status == "enforced"') == []


def test_no_test_asserts_something_its_own_key_already_says():
    offenders = []
    for path in sorted((REPO_ROOT / "tests").glob("*.py")):
        if path.name == "test_assertions_read_values_not_keys.py":
            continue                       # this file quotes the bad forms on purpose
        for literal, keys, line in assertions_satisfiable_by_their_own_key(path.read_text()):
            offenders.append(f"{path.name}:{line}  {literal!r} in {keys}")
    assert offenders == [], (
        "an assertion is satisfiable by the key it reads through, so it cannot distinguish a "
        "correct value from any text sharing the key's vocabulary:\n  " + "\n  ".join(offenders)
    )


def test_the_check_catches_the_historical_instances_it_claims_to():
    """DETECTOR PROOF. A check never shown capable of failing has
    established nothing, and this one must fail on the real forms rather
    than on invented ones."""
    caught = assertions_satisfiable_by_their_own_key(
        'assert "success" in PREREG["what_would_make_this_phase_a_success_even_if_everything_fails"]')
    assert [literal for literal, _, _ in caught] == ["success"]

    caught = assertions_satisfiable_by_their_own_key(
        'assert "does not describe this tree" in R["m"]["so_the_finding_does_not_describe_this_tree"]')
    assert [literal for literal, _, _ in caught] == ["does not describe this tree"]


def test_the_check_states_the_instance_it_cannot_catch():
    """The third instance, and it must stay uncaught rather than the
    check being widened until it catches it."""
    assert assertions_satisfiable_by_their_own_key(
        'assert "not a binding" in RECORD["what_this_file_is_not"]') == [], (
        "if this is now caught, the rule was widened -- check that it did not acquire the "
        "negation rule that produced eleven false positives"
    )


def test_a_legitimate_assertion_is_not_flagged():
    """The discriminating half. A rule that flagged every assertion
    against a descriptive key would be unusable, and 'passes on the
    corpus' does not show it discriminates."""
    for legitimate in (
        'assert "MINUS 20.3%" in klass["the_measured_instance"]',
        'assert "PERMEATION LIMIT" in three["the_effect_that_was_missing"]',
        'assert "must not be offered as evidence" in RECORD["what_it_does_not_defer"]',
        'assert "biased the estimated variance DOWNWARD" in MEASURED["the_unstated_obligation"]',
    ):
        assert assertions_satisfiable_by_their_own_key(legitimate) == [], legitimate


def test_the_rejected_negation_rule_is_recorded_with_its_measurement():
    """Why the check covers two thirds and not all of it."""
    docstring = pathlib.Path(__file__).read_text()
    assert "ELEVEN false positives" in docstring
    assert "no sound static form" in docstring
