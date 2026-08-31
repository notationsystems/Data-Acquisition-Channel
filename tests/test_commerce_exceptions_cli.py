"""The exception queue: loads where two claims about one movement disagree.

Three states from the shell, same scheme as `vet`: 0 every load
consistent and accounted, 1 divergences to work, 3 the question cannot be
fully answered. The trap graded here is the uncaptured bill of lading —
one claim about the movement, not agreement between two — which must
never be counted as clean, because a book nobody checked would then read
as a book with nothing wrong.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

import tools.make_fixture as make  # noqa: E402
from commerce.register import (LoadRecord, append, partition,  # noqa: E402
                               read as read_register)


def _exceptions(register_path):
    env = dict(os.environ)
    env["COMMERCE_REGISTER"] = str(register_path)
    return subprocess.run([sys.executable, "-m", "commerce", "exceptions"],
                          cwd=REPO_ROOT, capture_output=True, text=True, env=env)


@pytest.fixture(scope="module")
def fixture_register(tmp_path_factory):
    path = tmp_path_factory.mktemp("register") / "register.jsonl"
    _, records = make.generate()
    append(records, path=path)
    return path


def test_the_planted_divergence_is_found_and_named_with_both_carriers(fixture_register):
    result = _exceptions(fixture_register)
    assert result.returncode == 1, result.stdout + result.stderr
    line = next(l for l in result.stdout.splitlines()
                if make.PLANT_DOUBLE_BROKERED_LOAD in l)
    assert "tendered to" in line and make.PLANT_UNEXPECTED_CARRIER in line, (
        "the queue must name both claims, not just flag the load"
    )
    assert "legitimate interline" in result.stdout, (
        "a single instance is a question, not a conviction"
    )


def test_uncaptured_bills_of_lading_are_surfaced_not_counted_clean(fixture_register):
    result = _exceptions(fixture_register)
    assert "no bill of lading captured" in result.stdout
    assert "not the same as consistent" in result.stdout


def test_the_three_buckets_conserve_on_screen(fixture_register):
    result = _exceptions(fixture_register)
    reading = read_register(path=fixture_register)
    split = partition(reading)
    assert split.conserves
    assert (f"{len(split.consistent)} consistent + {len(split.divergent)} divergent + "
            f"{len(split.unknowable)} unknowable = {split.described}") in result.stdout
    assert split.described == 400


def test_a_fully_consistent_register_exits_0(tmp_path):
    path = tmp_path / "register.jsonl"
    append([LoadRecord(load="L-1", carrier="c-1", bill_of_lading_carrier="c-1"),
            LoadRecord(load="L-2", carrier="c-2", bill_of_lading_carrier="c-2")], path=path)
    result = _exceptions(path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_unknowable_only_exits_3_not_0(tmp_path):
    """No divergence found is not the same as no divergence present."""
    path = tmp_path / "register.jsonl"
    append([LoadRecord(load="L-1", carrier="c-1", bill_of_lading_carrier=None)], path=path)
    result = _exceptions(path)
    assert result.returncode == 3, result.stdout + result.stderr


def test_a_missing_register_exits_3_with_the_reason(tmp_path):
    result = _exceptions(tmp_path / "does-not-exist.jsonl")
    assert result.returncode == 3
    assert "nothing to examine" in result.stdout


def test_a_later_entry_supersedes_and_the_exception_clears(tmp_path):
    """The read is last-entry-wins: a BOL captured later resolves the
    unknowable without editing the earlier line."""
    path = tmp_path / "register.jsonl"
    append([LoadRecord(load="L-1", carrier="c-1", bill_of_lading_carrier=None)], path=path)
    assert _exceptions(path).returncode == 3
    append([LoadRecord(load="L-1", carrier="c-1", bill_of_lading_carrier="c-1")], path=path)
    assert _exceptions(path).returncode == 0


def test_plant_removing_the_divergence_turns_the_queue_green(tmp_path):
    """The check finds the claim mismatch, not the load's name. Rewrite
    the plant's BOL to agree and the queue must stop flagging it."""
    path = tmp_path / "register.jsonl"
    _, records = make.generate()
    laundered = [
        LoadRecord(load=r.load, carrier=r.carrier, origin=r.origin,
                   destination=r.destination, month=r.month,
                   bill_of_lading_carrier=(r.carrier if r.load == make.PLANT_DOUBLE_BROKERED_LOAD
                                           and r.bill_of_lading_carrier else
                                           r.bill_of_lading_carrier),
                   recorded_at=r.recorded_at)
        for r in records]
    append(laundered, path=path)
    result = _exceptions(path)
    assert make.PLANT_DOUBLE_BROKERED_LOAD not in result.stdout
    assert result.returncode == 3, "still 24 uncaptured BOLs — not 1, and never 0"
