"""The standing plan, checked against the tree rather than trusted.

The plan says its own section 1 must be verified before acting on it. A
plan that asserts a standing position nobody checks is archaeology waiting
to happen, and its section 7 re-read trigger fires when the tree
contradicts section 1 -- which requires something to notice.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

PLAN = (REPO_ROOT / "docs" / "STANDING_PLAN.md").read_text()
LEDGER = loads((REPO_ROOT / "architecture" / "phase_zero_ledger.yaml").read_text())


def test_every_module_the_standing_position_claims_exists():
    """Section 1's claims about `commerce/` are checkable."""
    for module in ("stores", "canadabuys", "tender", "landed_cost", "authority",
                   "vetting", "opportunity", "gate", "award", "__main__"):
        assert (REPO_ROOT / "commerce" / f"{module}.py").exists(), (
            f"the plan's standing position names {module}, which is not in the tree"
        )


def test_the_phase_zero_exit_command_the_plan_prints_actually_runs():
    """The plan tells an operator to run `python3 -m commerce form`. A plan
    that prints a command nobody tried is the same defect as a mechanism
    reachable only by import."""
    import json
    import subprocess
    assert "python3 -m commerce form" in PLAN
    result = subprocess.run([sys.executable, "-m", "commerce", "form"],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    json.loads(result.stdout)


def test_the_plan_does_not_claim_phase_zero_is_exited():
    assert LEDGER["exit_met"] == "no"
    assert "requires a real-world event" in LEDGER["what_blocks_it"]


def test_the_cycle_recorded_at_least_one_self_correction():
    """`A cycle with no self-correction is a cycle where nothing was
    probed.` The ledger must show them rather than read clean."""
    corrections = [k for k in LEDGER["cycle_1"] if k.startswith("self_correction")]
    assert len(corrections) >= 1, "a clean cycle must say so explicitly, not present as clean"


def test_the_out_of_phase_build_is_recorded_rather_than_quietly_kept():
    """Phase 0's must-not is `build integrations to avoid needing the
    transaction`, and the award adapter is an integration."""
    entry = LEDGER["cycle_1"]["self_correction_i_built_out_of_phase"]
    assert "award adapter" in entry["what_happened"]
    assert "verified subsystem" in entry["why_it_was_not_deleted"]
    assert "REMOVED unbuilt" in entry["what_was_done_instead"]


def test_the_amendment_states_the_tree_moved_rather_than_the_plan_became_inconvenient():
    """Section 7's rule about its own amendments, applied to its first one."""
    amendments = PLAN[PLAN.index("## Amendments"):]
    assert "2026-08-31" in amendments
    assert "Reason: the tree moved." in amendments
    assert "inconvenient" not in amendments.split("Reason:")[1]


def test_an_out_of_phase_proposal_is_recorded_unbuilt_with_a_validwhile():
    """Section 7: a good idea arriving mid-cycle is recorded with the
    condition under which it becomes necessary, not built because it is
    small."""
    entry = LEDGER["unbuilt_ai_dispatch_as_a_vendor_wedge"]
    assert entry["status"] == "not_built_and_not_mine_to_decide"
    assert entry["validWhile"].startswith("this stays unbuilt WHILE")
    assert "escalat" in entry["why_it_is_an_escalation_and_not_a_task"].lower()


def test_the_policy_silence_is_recorded_rather_than_read_as_permission():
    """The collection policy prohibits person-targeting and does not
    address employees. Silence in a rule is not permission."""
    gap = LEDGER["unbuilt_ai_dispatch_as_a_vendor_wedge"][
        "the_one_part_that_is_a_gap_in_an_existing_rule_rather_than_a_new_dimension"]
    assert "does not distinguish EMPLOYEES" in gap["what"]
    assert "read as permission" in gap["why_it_was_still_not_written_now"]


def test_every_phase_carries_an_entry_an_exit_and_a_must_not():
    """Phases advance on measurement, and a phase with no must-not cannot
    be built out of."""
    phases = re.findall(r"### Phase \d — [^\n]+\n(.*?)(?=\n### |\n---)", PLAN, re.S)
    assert len(phases) >= 6
    for body in phases:
        assert "**Entry:**" in body and "**Exit:**" in body
    with_must_not = [b for b in phases if "Must not" in b]
    assert len(with_must_not) >= 4, "the phases that can be built out of must say what not to build"
