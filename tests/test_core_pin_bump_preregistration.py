"""architecture/core_pin_bump_preregistration.yaml -- the guard that keeps
it a preregistration.

A PREREGISTRATION HAS EXACTLY ONE FAILURE MODE WORTH DEFENDING AGAINST,
and it is not being wrong. It is being edited after the fact to match
what happened. Every prediction here is falsifiable by performing the
bump; none is checkable before it. So what this file checks is the
PROPERTY THAT MAKES SCORING POSSIBLE: that the document still describes a
state that has not yet occurred, that its predictions are intact, and
that each one says what would falsify it.

THE ONE SUBSTANTIVE CHECK. The document's whole premise is that the pin
has NOT moved. The moment it does, this file stops being a
preregistration and becomes a description -- so the pin is read from the
gitlink and compared against the recorded starting state. That fails the
day someone bumps, which is correct and is the point: the bump is when
this document has to be scored and retired rather than kept.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
PREREG = loads(
    (REPO_ROOT / "architecture" / "core_pin_bump_preregistration.yaml").read_text()
)


def _gitlink():
    result = subprocess.run(
        ["git", "ls-files", "-s", "vendor/scout-retrieval-agent"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.split()[1]


def test_the_pin_has_not_moved_so_this_is_still_a_preregistration():
    """When this fails, the document is no longer predicting anything.
    The response is to SCORE the six predictions against what the suite
    actually did and record the result in a separate artifact -- not to
    edit this one, which is the failure mode a preregistration exists to
    make impossible."""
    gitlink = _gitlink()
    if gitlink is None:
        pytest.skip("no gitlink for the vendored core in this checkout")
    recorded = PREREG["the_measured_starting_state"]["pinned_here"]
    assert gitlink == recorded, (
        f"the core pin has moved from {recorded[:12]} to {gitlink[:12]}. "
        "architecture/core_pin_bump_preregistration.yaml is now a record of "
        "predictions that can be scored, and must be scored rather than edited."
    )


def test_the_starting_state_records_both_referents_in_full():
    """Abbreviated, neither commit can be fetched back from the remote --
    the failure architecture/ecosystem_register.yaml hit twice. A
    preregistration whose subject cannot be retrieved cannot be scored."""
    state = PREREG["the_measured_starting_state"]
    for field in ("pinned_here", "remote_branch_head"):
        assert re.fullmatch(r"[0-9a-f]{40}", state[field]), (
            f"{field} is recorded as {state[field]!r}, which cannot be fetched"
        )
    assert state["pinned_here"] != state["remote_branch_head"]
    assert isinstance(state["commits_between"], int) and state["commits_between"] > 0


def test_every_prediction_states_its_basis_and_what_would_falsify_it():
    """The two fields that separate a prediction from an opinion. `basis`
    says whether it was MEASURED or is OPEN -- a prediction whose basis is
    a measurement is a different object from one that is a guess, and
    collapsing them lets a guess be scored as a confirmation.

    Falsification is required in the SAME sense: a prediction that no
    outcome could contradict has already been scored, by its author,
    before the experiment."""
    for name, prediction in PREREG["predictions"].items():
        assert prediction.get("prediction"), f"{name} states no prediction"
        assert prediction.get("basis"), f"{name} states no basis"
        falsifier = next(
            (value for key, value in prediction.items() if "falsif" in key),
            None,
        )
        assert falsifier, (
            f"{name} names nothing that would falsify it -- it cannot be "
            "scored, only agreed with"
        )


def test_a_prediction_whose_basis_is_measured_says_where_it_was_measured():
    """MEASURED is the strongest word available in this vocabulary and the
    cheapest to type. A prediction claiming it must name the artifact,
    path or file the measurement came from, so the claim can be gone back
    to rather than believed."""
    citation = re.compile(
        r"(?:architecture/[\w/.]+|materials/[\w/.]+|tests/[\w/.]+|docs/[\w/.]+|pyproject)"
    )
    for name, prediction in PREREG["predictions"].items():
        if "MEASURED" not in str(prediction["basis"]):
            continue
        blob = " ".join(str(value) for value in prediction.values())
        assert citation.search(blob), (
            f"{name} claims a MEASURED basis and names no path it was read from"
        )


def test_the_re_measurement_list_is_not_empty_and_names_artifacts_that_exist():
    """The document's operative half. A bump obliges specific files to be
    re-derived, and naming one that is not in the tree would make the
    obligation unperformable."""
    listed = PREREG["what_must_be_re_measured_if_the_pin_moves"]["the_list_this_produces"]
    assert listed
    named = []
    for entry in listed:
        for match in re.findall(r"architecture/[\w/.]+\.yaml", entry):
            named.append(match)
    assert named, "the re-measurement list names no artifact by path"
    for path in named:
        assert (REPO_ROOT / path).exists(), f"{path} is listed and is not in the tree"
