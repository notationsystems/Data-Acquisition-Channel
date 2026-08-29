"""The instrument record, bound by RE-MEASUREMENT rather than restatement.

An architecture artifact that merely repeats what a module says is a
second copy that drifts. Every claim below is re-derived: the refusal
vocabulary is read off the module, and the two `absent` claims are
re-searched across the trees that are reachable from here.

WHY THE ABSENCES ARE RE-MEASURED AND NOT TRUSTED. An `absent` row is true
and unfalsifiable at once unless something re-runs the search -- the
property this repository named when four chemistry rows read `absent`
without saying absent WHERE. If the research finding schema is ever
written, or the instrument registry ever lands here, these tests fail and
the record is corrected rather than quietly rotting into a false claim.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402
from session import work_order  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "sea_dog_session_instrument.yaml").read_text())

#: Trees the absence claims were measured over. The instrument the session
#: STUDIES is a sibling checkout and may not be present; a claim about a
#: missing repository is the vacuous pass this program has filed before,
#: so those paths are skipped rather than counted as evidence.
_SEARCH_ROOTS = (
    REPO_ROOT,
    REPO_ROOT / "vendor" / "scout-retrieval-agent",
    pathlib.Path("/home/user/Notations-OSIRIS-Overwatch-Engine"),
    pathlib.Path("/home/user/information-systems-archive"),
)

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".next"}


def _reachable_roots():
    return [root for root in _SEARCH_ROOTS if root.is_dir()]


def _grep(needles, *, exclude_paths=()):
    """Files under the reachable roots containing any needle."""
    hits = []
    excluded = {str(path) for path in exclude_paths}
    for root in _reachable_roots():
        for path in root.rglob("*"):
            if not path.is_file() or any(part in _SKIP_DIRS for part in path.parts):
                continue
            if path.suffix not in {".py", ".yaml", ".yml", ".md", ".json", ".ts", ".tsx"}:
                continue
            if str(path) in excluded:
                continue
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            if any(needle in text for needle in needles):
                hits.append(path)
    return hits


def test_the_record_names_the_refusals_the_module_actually_declares():
    """Every code the record cites is one the module exports, and the
    record does not cite a code that no longer exists. Read off the
    module, so a rename breaks the record rather than outliving it."""
    declared = {name for name, value in vars(work_order).items()
                if name.isupper() and isinstance(value, str) and name == value}
    cited = set(RECORD["invariants_in_code"].values()) | set(RECORD["validations_in_code"].values())
    assert cited, "the record cites no refusal at all"
    missing = cited - declared
    assert not missing, f"the record cites refusals the module does not declare: {sorted(missing)}"


def test_the_three_invariants_and_three_validations_are_all_covered():
    """The doctrine states three of each. A record covering five of six
    is the reading-a-subset-as-the-set shape this program has filed."""
    assert len(RECORD["invariants_in_code"]) == 3
    assert len(RECORD["validations_in_code"]) == 3


def test_the_research_finding_schema_is_STILL_absent():
    """RE-SEARCHED, not restated. If someone writes the schema the
    doctrine names, this fails and the record is corrected."""
    assert RECORD["research_finding_schema"]["measured"] == "absent"
    hits = _grep(
        ("research_finding", "research finding schema", "RESEARCH_FINDING", "finding_schema"),
        # This record and its own test say the words while asserting the
        # absence; a check that fires on its own description is the grep
        # failure mode already repaired once in this repository.
        exclude_paths=(
            REPO_ROOT / "architecture" / "sea_dog_session_instrument.yaml",
            pathlib.Path(__file__),
            REPO_ROOT / "tests" / "test_session_instrument.py",
            REPO_ROOT / "session" / "work_order.py",
        ),
    )
    assert hits == [], f"the schema now exists at {[str(h) for h in hits]}; correct the record"


def test_the_instrument_registry_is_STILL_absent_and_was_not_reconstructed():
    """The doctrine is a generated file whose source is not here. Two
    things are asserted: the source is still missing, and nobody wrote a
    plausible one to make the header true."""
    assert RECORD["instrument_registry"]["measured"] == "absent_from_every_reachable_tree"
    assert not (REPO_ROOT / "architecture" / "instruments.yaml").exists(), (
        "architecture/instruments.yaml now exists here. If it was ADDED to satisfy the "
        "doctrine header, that is the reconstruction this record refuses; if it arrived from "
        "its real owner, the record is stale and should say so."
    )
    assert not (REPO_ROOT / "generate.py").exists()
    digest_hits = _grep(
        (RECORD["instrument_registry"]["claimed_digest"],),
        exclude_paths=(
            REPO_ROOT / "architecture" / "sea_dog_session_instrument.yaml",
            pathlib.Path(__file__),
        ),
    )
    assert digest_hits == [], f"the doctrine's source digest is now reachable at {digest_hits}"


def test_the_absence_search_is_not_vacuous():
    """A search that finds nothing because it looks nowhere proves
    nothing. The roots must exist and the machinery must be able to find
    a string that IS there."""
    roots = _reachable_roots()
    assert len(roots) >= 2, f"only {len(roots)} search root(s) reachable; the absences are weak"
    control = _grep(("EVERY_RUN_DIFFERS_IN",))
    assert control, "the search machinery finds nothing at all -- the absence claims are vacuous"


def test_the_preconditions_are_recorded_unmet_and_the_module_cannot_fake_them():
    """The instrument is blocked on the calendar. The record says so, and
    the module cannot produce a populated work order out of nothing: an
    empty queue yields an empty order that says WHICH empty it is."""
    assert set(RECORD["preconditions"].values()) == {"not_supplied"}
    order = work_order.plan([], box_minutes=120)
    assert order.items == ()
    assert order.empty_because == work_order.EMPTY_BECAUSE_THE_QUEUE_WAS_EMPTY
