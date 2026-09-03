"""The retro-verification of the window, checked against the verdict file
it was derived from.

A record summarising a sweep can drift from the sweep. Every count and
every commit named below is re-derived from
architecture/_probes/window_verdicts.txt, which is the sweep's own output.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "unverified_window.yaml").read_text())
VERDICTS_PATH = REPO_ROOT / "architecture" / "_probes" / "window_verdicts.txt"

#: The three modules that read the sibling checkout. A verdict any of
#: them gives at a historical commit is about today's sibling.
SIBLING_COUPLED = ("test_doctrine_coverage", "test_ecosystem_census",
                   "test_kalman_preregistration_currency", "test_vacuous_evidence")


def verdicts():
    rows = {}
    for line in VERDICTS_PATH.read_text().splitlines():
        if line.count("|") < 5:
            continue
        sha, doctrine, pin, tests, mypy, summary = line.split("|", 5)
        rows[sha] = dict(doctrine=doctrine, pin=pin, tests=tests, mypy=mypy)
    return rows


def test_every_commit_in_the_window_has_an_executed_verdict():
    """D-2's first acceptance criterion. A window with a gap in it is a
    sweep that was interrupted, and reads identically to one that
    completed."""
    rows = verdicts()
    assert len(rows) == RECORD["the_window"]["commits"] == 67
    assert len(rows) == RECORD["the_result"]["measured"]
    for sha, row in rows.items():
        assert len(sha) == 40, f"{sha!r} is not a full object name"
        for gate, value in row.items():
            assert value and value != "-", f"{sha[:7]} has no verdict for {gate}"


def test_the_counts_in_the_record_are_the_counts_in_the_verdict_file():
    rows = verdicts()
    failed = {sha for sha, row in rows.items()
              if any(v != "OK" for v in row.values())}
    assert len(failed) == RECORD["the_result"]["failed"] == 7
    assert len(rows) - len(failed) == RECORD["the_result"]["passed_every_gate"] == 60

    named = set(RECORD["the_genuine_failures"]) | {
        RECORD["the_environment_coupled_verdict"]["commit"]}
    assert {sha[:7] for sha in failed} == named, (
        f"the record names {sorted(named)} and the sweep failed {sorted(s[:7] for s in failed)}"
    )


def test_the_environment_coupled_verdict_is_excluded_with_its_proof():
    """It was nearly reported as a broken state. The record must carry the
    measurement that says otherwise, not merely the claim."""
    coupled = RECORD["the_environment_coupled_verdict"]
    assert coupled["commit"] == "8aaa0e2"
    assert "a05f23c7" in coupled["why_it_is_not_a_fact_about_that_commit"]
    assert "899a0489" in coupled["why_it_is_not_a_fact_about_that_commit"]
    assert "the two repositories AGREE" in coupled["why_it_is_not_a_fact_about_that_commit"]
    assert "committed by the investigation" in coupled["it_is_an_instance_of_the_class_this_order_named"]

    import subprocess
    here = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show",
         "8aaa0e2:architecture/exchange/canonical_yaml.py"],
        capture_output=True).stdout
    now = (REPO_ROOT / "architecture" / "exchange" / "canonical_yaml.py").read_bytes()
    assert here and here != now, (
        "if the historical copy equalled today's, the time-skew explanation would be wrong and "
        "8aaa0e2 would be a genuine failure"
    )


def test_the_sibling_coupled_modules_are_named_rather_than_silently_dropped():
    """Excluding a test from a conclusion is a decision, and a decision
    left unstated is indistinguishable from an oversight."""
    reading_sibling = set()
    for path in sorted((REPO_ROOT / "tests").glob("*.py")):
        if path.stem == pathlib.Path(__file__).stem:
            continue                      # this module names the path in order to check it
        if "scientific-compute-layer-scl-" in path.read_text():
            reading_sibling.add(path.stem)
    assert reading_sibling <= set(SIBLING_COUPLED), (
        f"a module now reads the sibling checkout that this record did not account for: "
        f"{sorted(reading_sibling - set(SIBLING_COUPLED))}"
    )
    note = RECORD["the_environment_coupled_verdict"]["what_it_means_for_the_method"]
    assert f"{len(reading_sibling)} test modules read the sibling checkout" in note, (
        f"the record's count is stale: {len(reading_sibling)} modules read it -- "
        f"{sorted(reading_sibling)}"
    )
    assert "test_canonicalization_defect" in note and "no longer does" in note, (
        "the module that actually fired no longer reads the sibling, so a list derived from "
        "today's tree would miss it -- the record must say so"
    )


def test_the_record_owns_the_failure_that_belongs_to_this_session():
    """A retro-verification that found six broken states and attributed
    none of them to its own author would be worth re-reading."""
    mine = RECORD["the_genuine_failures"]["19d11d6"]
    assert "THIS_ONE_IS_MINE" in mine
    assert "landed in this session" in mine["THIS_ONE_IS_MINE"]
    assert "accurate about what was run and silent about what was not" in mine["THIS_ONE_IS_MINE"]


def test_the_record_states_the_brief_was_wrong_by_measurement_not_by_assertion():
    window = RECORD["the_window"]
    assert "sixty-one runs" in window["the_order_said_five"]
    assert window["commits"] == 67
    assert "commits and runs are not the same count" in \
        window["the_discrepancy_between_those_two_numbers"]


def test_no_history_was_rewritten():
    """The one thing the order forbade. The window's commits must still be
    reachable and unchanged."""
    import subprocess
    for short in list(RECORD["the_genuine_failures"]) + ["8aaa0e2"]:
        result = subprocess.run(["git", "-C", str(REPO_ROOT), "cat-file", "-t", short],
                                capture_output=True, text=True)
        assert result.stdout.strip() == "commit", f"{short} is no longer a commit"
