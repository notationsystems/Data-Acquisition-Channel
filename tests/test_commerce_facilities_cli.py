"""The facility register gate: duplicates surfaced, never merged.

The measurement that shaped this surface: over the representative
register the bare similarity floor produced 51 pairs of which ONE was the
planted duplicate, because industrial addresses share street and city
tokens everywhere. The discriminating observable is a STATED
disagreement — the house number — so pairs that disagree there are listed
as distinct rather than dropped, and every pair above the floor lands in
exactly one bucket.

Exit codes: 1 suspects to work; 3 the question cannot be answered to
zero — which is EVERY clean run under the conservative normalizer,
because there the duplicate rate is unknown and is not zero; 0 only with
the statistical parser installed and nothing above the floor.
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
from commerce.facility import (CONSERVATIVE, Facility,  # noqa: E402
                               conservative_normalize, duplicate_scan)


def _fac(facility_id: str, raw: str) -> Facility:
    return Facility(facility_id=facility_id, raw=raw,
                    normalized=conservative_normalize(raw), normalizer=CONSERVATIVE)


def _facilities(path):
    return subprocess.run([sys.executable, "-m", "commerce", "facilities", str(path)],
                          cwd=REPO_ROOT, capture_output=True, text=True,
                          env=dict(os.environ))


@pytest.fixture(scope="module")
def fixture_addresses(tmp_path_factory):
    make.generate()
    path = tmp_path_factory.mktemp("facilities") / "facilities.json"
    path.write_text(json.dumps(make.FACILITY_ADDRESSES, sort_keys=True))
    return path


def test_the_planted_duplicate_is_the_unique_suspect_among_sixty_one(fixture_addresses):
    result = _facilities(fixture_addresses)
    assert result.returncode == 1, result.stdout + result.stderr
    flagged = [l for l in result.stdout.splitlines() if l.strip().startswith("?")]
    assert len(flagged) == 1, (
        f"exactly one suspect pair, or the queue drowns the operator: {flagged}"
    )
    assert make.PLANT_DUPLICATE_FACILITY[0] in flagged[0]
    assert make.PLANT_DUPLICATE_FACILITY[1] in flagged[0]
    # Both raw strings on screen: the operator judges raw, not normalized.
    assert "980 Dixie Rd, Vaughan ON" in result.stdout
    assert "980 DIXIE RD UNIT 4, Vaughan ON" in result.stdout
    assert "not merged" in result.stdout


def test_every_pair_above_the_floor_is_accounted_not_dropped(fixture_addresses):
    result = _facilities(fixture_addresses)
    line = next(l for l in result.stdout.splitlines() if "above the floor" in l and "=" in l)
    suspect, _, rest = line.strip().partition(" suspect + ")
    distinct, _, rest = rest.partition(" distinct-by-number = ")
    total = rest.split()[0]
    assert int(suspect) + int(distinct) == int(total)
    assert "stated difference" in result.stdout, (
        "the exclusion must say WHY those pairs are distinct, on the record"
    )


def test_a_clean_register_under_the_conservative_normalizer_never_exits_0(tmp_path):
    path = tmp_path / "facilities.json"
    path.write_text(json.dumps({"a": "10 First St, Guelph ON",
                                "b": "77 Ninth Ave, Halifax NS"}))
    result = _facilities(path)
    assert result.returncode == 3, (
        "under the conservative normalizer the duplicate rate is unknown and not zero"
    )
    assert "WITHOUT a statistical address parser" in result.stdout


def test_a_missing_register_exits_3_with_the_reason(tmp_path):
    result = _facilities(tmp_path / "nowhere.json")
    assert result.returncode == 3
    assert "not the same as nothing being duplicated" in result.stdout


def test_unusable_input_exits_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    assert _facilities(bad).returncode == 2
    array = tmp_path / "array.json"
    array.write_text("[1, 2]")
    assert _facilities(array).returncode == 2


def test_a_blank_address_is_refused_on_screen_and_conserved(tmp_path):
    path = tmp_path / "facilities.json"
    path.write_text(json.dumps({"a": "10 First St, Guelph ON", "b": "   "}))
    result = _facilities(path)
    assert "REFUSED b" in result.stdout
    assert "2 entr(ies): 1 scanned + 1 refused" in result.stdout


# ---------------------------------------------------------------------
# The exclusion rule itself, at the unit: a stated disagreement excuses,
# a missing statement does not.
# ---------------------------------------------------------------------

def test_conflicting_house_numbers_are_distinct_not_suspect():
    scan = duplicate_scan([_fac("x", "350 Rue Notre-Dame, Detroit MI"),
                           _fac("y", "318 Rue Notre-Dame, Detroit MI")])
    assert not scan.pairs
    assert len(scan.distinct_by_number) == 1


def test_a_compatible_number_stays_suspect():
    """`980` against `980 UNIT 4` is not a disagreement — the plant."""
    scan = duplicate_scan([_fac("x", "980 Dixie Rd, Vaughan ON"),
                           _fac("y", "980 DIXIE RD UNIT 4, Vaughan ON")])
    assert len(scan.pairs) == 1
    assert not scan.distinct_by_number


def test_a_missing_number_stays_suspect_not_distinct():
    """No number on one side is not a stated disagreement. Excusing it
    would let every incomplete address self-certify as unique."""
    scan = duplicate_scan([_fac("x", "Dixie Rd, Vaughan ON"),
                           _fac("y", "980 Dixie Rd, Vaughan ON")])
    assert len(scan.pairs) == 1
    assert not scan.distinct_by_number


def test_an_empty_register_says_which_kind_of_nothing():
    scan = duplicate_scan([])
    assert scan.empty_because is not None
    assert "not the same as nothing being duplicated" in scan.empty_because
