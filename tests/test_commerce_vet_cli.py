"""The vetting store and the `vet` command — a verdict that replays.

Two claims are graded here, and both are about time. First, the verdict
is computed from PERSISTED observations, so the question `what would we
have decided on the fifth` is still answerable on the fifteenth. Second,
the exit code carries all three states — 0 cleared, 1 blocked, 3
undetermined — because a shell that treats nonzero as `blocked` collapses
the third state, and the third state is the one the gate exists for.

THE DISCRIMINATING PAIR. The lapsing carrier's certificate ends
2026-08-06. The same store, at the same asof, clears a same-day load on
the 5th and blocks a multi-day movement delivering the 8th. Only a
period-based check tells those apart; an `insured: yes` boolean passes
both.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

import tools.make_fixture as make  # noqa: E402
from commerce import vetting_store  # noqa: E402
from commerce.vetting import (INSURANCE_COVERAGE, REPORTED,  # noqa: E402
                              RUNG_COMMITTED_SNAPSHOT, VettingObservation,
                              VettingProvenance)

LAPSE = make.PLANT_INSURANCE_WINDOW[1]
assert LAPSE == "2026-08-06"


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    path = tmp_path_factory.mktemp("vetting") / "vetting.jsonl"
    vetting_store.append(make.vetting_observations(), path=path)
    return path


def _vet(store_path, *args):
    env = dict(os.environ)
    env["COMMERCE_VETTING"] = str(store_path)
    return subprocess.run([sys.executable, "-m", "commerce", "vet", *args],
                          cwd=REPO_ROOT, capture_output=True, text=True, env=env)


# ---------------------------------------------------------------------
# The two sides of the window — item 13's acceptance line.
# ---------------------------------------------------------------------

def test_cleared_on_the_near_side_of_the_window(store):
    """Before the lapse (and before the bulk freeze), the lapsing carrier
    is an ordinary cleared carrier. The plant is a lapse, not a villain."""
    result = _vet(store, make.PLANT_LAPSING_CARRIER,
                  "2026-05-01", "2026-05-01", "2026-05-01", "2026-05-02")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLEARED as at 2026-05-01" in result.stdout


def test_blocked_when_the_certificate_lapses_inside_the_movement(store):
    result = _vet(store, make.PLANT_LAPSING_CARRIER,
                  "2026-08-05", "2026-08-04", "2026-08-05", "2026-08-08")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout
    assert "COVERAGE_LAPSES_INSIDE_THE_MOVEMENT" in result.stdout
    # The render must say when it ends and what to do, not just `no`.
    assert LAPSE in result.stdout
    assert "renewed certificate" in result.stdout


def test_the_same_certificate_clears_the_same_day_load(store):
    """Same store, same asof, same certificate — different movement.
    Insurance clears; the verdict is UNDETERMINED only because the
    post-freeze reincarnation check honestly cannot run, and exit 3 is
    that state, distinct from blocked."""
    result = _vet(store, make.PLANT_LAPSING_CARRIER,
                  "2026-08-05", "2026-08-05", "2026-08-05", "2026-08-05")
    assert result.returncode == 3, result.stdout + result.stderr
    assert result.returncode != 1, "collapsing undetermined into blocked is the defect"
    assert "insurance_current          CLEARED" in result.stdout
    assert "NO_CHANNEL_ESTABLISHED_FOR_THIS_WINDOW" in result.stdout
    assert "UNDETERMINED is not a pass and not a failure" in result.stdout


# ---------------------------------------------------------------------
# The other kinds of nothing.
# ---------------------------------------------------------------------

def test_an_unknown_carrier_is_undetermined_not_clean(store):
    result = _vet(store, "carrier-99", "2026-08-05")
    assert result.returncode == 3
    assert "NO_OBSERVATION_OF_THIS_KIND" in result.stdout
    assert "not evidence that authority is absent" in result.stdout


def test_the_self_attested_certificate_is_undetermined_however_fresh(store):
    result = _vet(store, make.PLANT_SELF_INSURED_CARRIER,
                  "2026-08-05", "2026-08-05", "2026-08-05", "2026-08-05")
    assert result.returncode == 3
    assert "CONFIRMED_ONLY_BY_THE_CARRIER" in result.stdout
    assert "confirm the policy number directly with the named insurer" in result.stdout


def test_a_missing_store_is_undetermined_with_the_reason(tmp_path):
    result = _vet(tmp_path / "does-not-exist.jsonl", "carrier-13", "2026-08-05")
    assert result.returncode == 3
    assert "no vetting store" in result.stdout
    assert "not the same as every carrier being clean" in result.stdout


def test_too_few_arguments_exit_2(store):
    result = _vet(store, "carrier-13")
    assert result.returncode == 2


# ---------------------------------------------------------------------
# PLANT: known_at is the query. A renewal that arrived later must not
# reach back and change the earlier verdict.
# ---------------------------------------------------------------------

def test_a_later_renewal_does_not_rewrite_the_earlier_verdict(store, tmp_path):
    path = tmp_path / "vetting.jsonl"
    path.write_text(store.read_text())
    vetting_store.append([VettingObservation(
        subject=make.PLANT_LAPSING_CARRIER, kind=INSURANCE_COVERAGE,
        value=2_000_000.0, unit="CAD",
        period_start="2026-08-07", period_end="2027-08-06", known_at="2026-08-20",
        provenance=VettingProvenance("representative_fixture:insurer-call", REPORTED,
                                     RUNG_COMMITTED_SNAPSHOT, "2026-08-20"))], path=path)
    # As at the 5th the renewal was not knowable: still blocked.
    before = _vet(path, make.PLANT_LAPSING_CARRIER,
                  "2026-08-05", "2026-08-04", "2026-08-05", "2026-08-08")
    assert before.returncode == 1, (
        "a record that arrived on the 20th informed a decision taken on the 5th"
    )
    assert "COVERAGE_LAPSES_INSIDE_THE_MOVEMENT" in before.stdout
    # As at the 21st the same movement is covered; insurance clears.
    after = _vet(path, make.PLANT_LAPSING_CARRIER,
                 "2026-08-21", "2026-08-04", "2026-08-05", "2026-08-08")
    assert "insurance_current          CLEARED" in after.stdout
    assert after.returncode != 1


# ---------------------------------------------------------------------
# The store itself: append-only, conserving, and honest about bad lines.
# ---------------------------------------------------------------------

def test_the_store_round_trips_every_field(tmp_path):
    path = tmp_path / "vetting.jsonl"
    observations = make.vetting_observations()
    vetting_store.append(observations, path=path)
    book = vetting_store.read(path=path)
    assert book.observations == tuple(observations)
    assert book.bad == ()
    assert book.lines == len(observations)
    assert book.empty_because is None


def test_bad_lines_are_reported_and_conserved_not_dropped(tmp_path):
    path = tmp_path / "vetting.jsonl"
    vetting_store.append(make.vetting_observations()[:3], path=path)
    with path.open("a") as handle:
        handle.write("{ not json\n")
        handle.write(json.dumps({"subject": "carrier-00", "kind": "horoscope"}) + "\n")
    book = vetting_store.read(path=path)
    assert len(book.observations) == 3
    assert len(book.bad) == 2
    assert len(book.observations) + len(book.bad) == book.lines, (
        "every line is an observation or a named refusal; none vanish"
    )
    codes = [reason for _, reason in book.bad]
    assert any("VETTING_LINE_IS_NOT_JSON" in c for c in codes)
    assert any("VETTING_LINE_LACKS_A_KIND" in c for c in codes)


def test_for_carrier_filters_by_subject(tmp_path):
    path = tmp_path / "vetting.jsonl"
    vetting_store.append(make.vetting_observations(), path=path)
    book = vetting_store.read(path=path)
    mine = book.for_carrier(make.PLANT_LAPSING_CARRIER)
    assert mine and all(o.subject == make.PLANT_LAPSING_CARRIER for o in mine)
    assert any(o.kind == INSURANCE_COVERAGE for o in mine)
    assert not book.for_carrier("carrier-77")


def test_the_generated_store_is_deterministic():
    first = make.vetting_observations()
    again = make.vetting_observations()
    assert first == again
