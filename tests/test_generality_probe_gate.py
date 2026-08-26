"""The generality probe's own gate, enforced.

`architecture/_probes/generality.yaml` carries one line of policy:

    gate: re-run whenever a core invariant changes

It was declared in Phase 36 and read by nothing for the whole of its
life. It failed exactly once, and silently. `generation_depth_bounded`
moved from represented_unenforced to enforced at 6f890e5 -- a core
invariant changed, with an implementation and a 36-test enforcement
suite -- and the probe's recursive_computation FAIL, measured against
the state before that commit, was never re-run. Two later commits
(7d5b7ab, 6e5c9b2) edited that very file to record two other probe runs
and left the stale FAIL standing, and
`test_the_probe_records_the_failure_rather_than_a_pass` PINNED it. Every
suite was green over a probe result that no longer described the
repository.

That is the same shape the FAIL itself had found in the invariant it was
measuring: DECLARED AND NEVER IMPLEMENTED. The probe caught it in the
substrate and then had it.

WHAT THIS FILE ASSERTS, and why in this form:

  1. THE GATE. A digest over a projection of every invariant, recomputed
     here and compared to the one the probe recorded. When a core
     invariant changes, this goes red and the re-run instruction arrives
     as a failing test rather than as a thing to remember. It reuses the
     digest mechanism the exchange artifacts already use; it is not a
     second one.

  2. THE PARTITION. Every property the probe DECLARES is accounted for
     in exactly one outcome list, and every outcome-list member has a
     result. Asserted over the declared set rather than over a list of
     property names written here -- a check specified by enumeration is
     correct until the world grows an item nobody added to the list, and
     the probe grew `recursive_computation` after it was written once
     already.

  3. THE SUPERSESSION FORM. A verdict that replaced an earlier one must
     retain the earlier one beside it. A superseded status standing
     alone is a defect this pair has already filed twice.
"""

import hashlib
import json
import pathlib
import subprocess

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCHITECTURE = REPO_ROOT / "architecture"
PROBE_PATH = ARCHITECTURE / "_probes" / "generality.yaml"
INVARIANTS_PATH = ARCHITECTURE / "invariants.yaml"

PROBE = yaml.safe_load(PROBE_PATH.read_text())


# --------------------------------------------------------- the projection


def invariant_projection(document):
    """(id, rule, status) for every invariant in the document, sorted.

    Derived by walking for the SHAPE of an invariant entry rather than by
    reading a known list of sections, so an invariant added under a new
    heading is covered without anyone remembering to extend this.
    """
    found = []

    def walk(node):
        if isinstance(node, dict):
            if "id" in node and "rule" in node and "status" in node:
                found.append([node["id"], node["rule"], node["status"]])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    return sorted(found)


def projection_digest(projection):
    payload = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_projection():
    return invariant_projection(yaml.safe_load(INVARIANTS_PATH.read_text()))


# ------------------------------------------------------------- 1. the gate


def test_the_probe_records_the_state_of_the_invariants_it_was_run_against():
    gate = PROBE["gate_enforcement"]
    projection = current_projection()

    assert gate["invariant_count"] == len(projection), (
        f"the probe records {gate['invariant_count']} invariants and "
        f"architecture/invariants.yaml now holds {len(projection)}. An invariant was "
        "added or removed since the probe was last run -- re-run it and reissue the "
        "result and outcome, then update this count. Updating the count alone is the "
        "defect gate_enforcement exists to make visible."
    )
    assert gate["invariants_projection_digest"] == projection_digest(projection), (
        "a core invariant's id, rule or status has changed since the generality probe "
        "was last run. The probe's own gate says 're-run whenever a core invariant "
        "changes'. Re-run it against the change, reissue result and outcome, and only "
        "then update invariants_projection_digest."
    )


def test_the_gate_declares_what_it_cannot_see():
    """A gate that overstates its reach is worse than a narrow one, because
    the overstatement is what gets cited."""
    gate = PROBE["gate_enforcement"]
    assert "what_it_does_not_cover" in gate
    limit = gate["what_it_does_not_cover"]
    assert "science/" in limit and "store" in limit, (
        "two of the five results rest on surfaces the declared gate does not watch; "
        "that limit must stay stated"
    )


def test_the_digest_moves_when_a_status_moves():
    """SHOWN CAPABLE OF FAILING. A check nobody has watched fail is a
    check nobody has evidence for -- `a_check_must_be_shown_capable_of_failing`
    is a core invariant of this repository."""
    projection = current_projection()
    assert projection, "no invariants found -- the projection walk is broken"

    mutated = [list(entry) for entry in projection]
    mutated[0][2] = mutated[0][2] + "_MUTATED"
    assert projection_digest(sorted(mutated)) != projection_digest(projection)

    reworded = [list(entry) for entry in projection]
    reworded[0][1] = reworded[0][1] + " (reworded)"
    assert projection_digest(sorted(reworded)) != projection_digest(projection)


def test_the_digest_would_have_caught_the_repair_that_it_missed():
    """The historical demonstration, run rather than quoted.

    6f890e5 is the commit that closed `generation_depth_bounded`. If the
    projection over the invariants BEFORE that commit equals the one the
    probe now records, this gate could not have caught the thing it was
    written for.
    """
    try:
        before = subprocess.run(
            ["git", "show", "6f890e5^:architecture/invariants.yaml"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        pytest.skip(f"git unavailable: {exc}")
    if before.returncode != 0:  # pragma: no cover
        pytest.skip("6f890e5 not reachable from this checkout")

    prior = invariant_projection(yaml.safe_load(before.stdout))
    assert projection_digest(prior) != PROBE["gate_enforcement"]["invariants_projection_digest"], (
        "the projection did not move across the commit that repaired "
        "generation_depth_bounded, so this gate would not have caught the failure it "
        "was written for"
    )

    prior_status = dict((entry[0], entry[2]) for entry in prior)
    now_status = dict((entry[0], entry[2]) for entry in current_projection())
    assert prior_status["generation_depth_bounded"] != now_status["generation_depth_bounded"], (
        "the status this gate was written about did not actually change"
    )
    assert now_status["generation_depth_bounded"] == "enforced"


# -------------------------------------------------------- 2. the partition


def declared_properties():
    return tuple(PROBE["observation_properties"]) + tuple(PROBE["computation_properties"])


OUTCOME_LISTS = (
    "qualified",
    "untested",
    "failed",
    "failed_and_since_repaired",
    "tested_since_the_verdict_below",
)


def test_every_declared_property_has_a_result():
    declared = set(declared_properties())
    recorded = set(PROBE["result"])
    assert declared == recorded, (
        f"declared but unmeasured: {sorted(declared - recorded)}; "
        f"measured but undeclared: {sorted(recorded - declared)}"
    )


def test_every_declared_property_is_accounted_for_in_exactly_one_outcome_list():
    outcome = PROBE["outcome"]
    placement = {}
    for name in OUTCOME_LISTS:
        assert name in outcome, f"outcome is missing the {name!r} list"
        for prop in outcome[name]:
            assert prop not in placement, (
                f"{prop!r} appears in both {placement[prop]!r} and {name!r}; a property "
                "in two outcome lists means the outcome cannot be read as a verdict"
            )
            placement[prop] = name

    declared = set(declared_properties())
    assert set(placement) == declared, (
        f"unaccounted for in any outcome list: {sorted(declared - set(placement))}; "
        f"listed in an outcome but never declared: {sorted(set(placement) - declared)}"
    )


def test_a_repaired_failure_is_still_recorded_as_having_failed():
    """`failed: []` must not be reachable by deleting the failure."""
    outcome = PROBE["outcome"]
    for prop in outcome["failed_and_since_repaired"]:
        result = PROBE["result"][prop]
        assert result.get("prior_verdict") == "FAIL", (
            f"{prop} is listed as repaired but its result does not record the FAIL it "
            "is repaired from"
        )
        assert "prior_detail" in result, (
            f"{prop}'s FAIL was removed rather than superseded -- the measurement that "
            "produced it must be retained"
        )
        assert result["verdict"] != "FAIL"


def test_core_invariants_modified_is_zero_and_says_why_a_repair_is_not_a_modification():
    outcome = PROBE["outcome"]
    assert outcome["core_invariants_modified"] == 0
    changes = outcome["what_the_reissue_changes"]
    assert "IMPLEMENTED, not weakened" in changes["failed_went_from_one_to_zero"], (
        "closing a FAIL by implementing the rule and closing it by relaxing the rule "
        "produce the same zero; which one happened has to be recorded"
    )


# ------------------------------------------------------ 3. the supersession


def test_a_superseded_verdict_is_retained_beside_the_current_one():
    outcome = PROBE["outcome"]
    superseded = [k for k in outcome if k.startswith("verdict_superseded")]
    assert superseded, "the reissue dropped the verdict it superseded"
    assert "verdict" in outcome
    for key in superseded:
        assert outcome[key] != outcome["verdict"]
    assert "two properties untested" not in outcome["verdict"], (
        "the current verdict still carries the stale count; untested is now empty"
    )


def _probe_at(rev):
    shown = subprocess.run(
        ["git", "show", f"{rev}:architecture/_probes/generality.yaml"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    if shown.returncode != 0:
        return None
    return yaml.safe_load(shown.stdout)


def test_every_result_that_supersedes_one_retains_the_measurement_under_it():
    """A superseded verdict standing ALONE is the defect this pair has filed
    twice. Retention is asserted against git rather than against a naming
    convention: a result may retain the earlier measurement under a
    `prior_*` key, OR by leaving `detail` exactly as it stood when the
    earlier verdict was current. What it may not do is quietly rewrite the
    measurement while claiming to supersede the verdict.
    """
    superseding = {
        name: result for name, result in PROBE["result"].items()
        if "prior_verdict" in result
    }
    assert superseding, "no result records a superseded verdict -- has the probe been reissued?"

    try:
        log = subprocess.run(
            ["git", "log", "--format=%H", "--", "architecture/_probes/generality.yaml"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        pytest.skip(f"git unavailable: {exc}")
    if log.returncode != 0:  # pragma: no cover
        pytest.skip("probe history not reachable from this checkout")
    revisions = log.stdout.split()

    for name, result in superseding.items():
        assert result["prior_verdict"] != result["verdict"]
        assert "what_changed_about_the_verdict" in result, (
            f"{name} was superseded without saying whether by a measurement, a repair "
            "or an argument"
        )

        explicit = [k for k in result if k.startswith("prior_") and k != "prior_verdict"]
        if explicit:
            continue

        # No prior_* payload: then `detail` must be the one that stood under
        # the earlier verdict, found in history rather than asserted.
        earlier = None
        for rev in revisions:
            historical = _probe_at(rev)
            if historical is None:
                continue
            entry = historical.get("result", {}).get(name)
            if entry and entry.get("verdict") == result["prior_verdict"]:
                earlier = entry
                break
        assert earlier is not None, (
            f"{name} claims prior_verdict {result['prior_verdict']!r} but no commit "
            "touching this probe ever recorded that verdict for it"
        )
        assert result.get("detail") == earlier.get("detail"), (
            f"{name} supersedes a verdict, retains no prior_* measurement, AND has "
            "rewritten `detail` since the earlier verdict stood. The measurement "
            "behind the superseded verdict is gone."
        )


def test_the_probe_is_still_paper_only():
    """The gate is enforced by a test that READS the probe. Giving the probe
    an implementation is what its own header forbids."""
    assert PROBE["status"] == "paper_only"
    source = pathlib.Path(__file__).read_text()
    assert "import" not in source.split("PROBE = ")[1].split("\n")[0]
