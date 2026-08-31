"""Defect class 8, and the detector that catches it.

THE CLASS. A constraint correctly measured, correctly reported, and then
not carried into the design BY THE SAME AGENT THAT MEASURED IT. Distinct
from all seven already named, every one of which describes a fault in the
MEASUREMENT: here the measurement is right and the fault is in the seam
between it and the design that follows.

It recurs in multi-agent work specifically, because a single agent
producing a finding and a design in one pass has nothing between them --
no reviewer, no interval, no forcing function that re-reads the constraint
before writing the recommendation.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

from commerce.recon_lint import (CONSTRAINT_MEASURED_AND_NOT_CARRIED, constraints_of,  # noqa: E402
                                 lint, render, unheeded)

RECORD = loads((REPO_ROOT / "architecture" / "carrier_vetting_recon.yaml").read_text())

#: The verbatim recommendation that named the class, from the probe that
#: had quoted the prohibition against it a few hundred words earlier.
THE_INSTANCE = ("Build a daily snapshot-and-diff store of the four public lists so changes "
                "can be detected.")


def test_the_detector_fires_on_the_instance_that_named_the_class():
    """Plant-and-verify. A detector that has never failed proves nothing,
    and this one has an exact historical instance to be tested against."""
    planted = dict(RECORD)
    planted["quebec_is_split_and_only_the_useless_half_is_ungated"] = {
        **RECORD["quebec_is_split_and_only_the_useless_half_is_ungated"],
        "recommendation": THE_INSTANCE,
    }
    candidates = unheeded(planted)
    assert candidates, "the detector must catch the instance that named the class"
    assert candidates[0].constraint == "quebec_prohibits_storing"
    assert candidates[0].forbidden_term == "store"
    assert "daily snapshot-and-diff store" in candidates[0].sentence
    assert CONSTRAINT_MEASURED_AND_NOT_CARRIED in lint("planted", planted).empty_because


def test_the_corrected_record_is_clean():
    assert unheeded(RECORD) == (), render(lint("carrier_vetting_recon", RECORD))


def test_a_prohibition_is_not_mistaken_for_a_proposal():
    """`do not build a local mirror` contains the word `mirror` and is the
    record working correctly. A detector that flagged it would train the
    reader to dismiss the check."""
    record = {
        "constraints_measured": {"c": {"quoted": "q", "forbids": ["mirror"]}},
        "rule": "Do not build a local mirror of any of these.",
    }
    assert unheeded(record) == ()


def test_a_forbidden_term_that_is_also_domain_vocabulary_was_dropped_deliberately():
    """MEASURED ON THE FIRST RUN. `snapshot` produced three candidates and
    every one was a description of a source KIND -- `snapshot rung`,
    `snapshot surface`, `current-snapshot only` -- rather than a proposed
    act. Listing it would make the linter noisy on correct text, and a
    detector that cries wolf is worse than one that is not run.

    `store` still catches the real instance, which is what makes the drop
    a narrowing rather than a hole."""
    quebec = RECORD["constraints_measured"]["quebec_prohibits_storing"]
    assert "snapshot" not in quebec["forbids"]
    assert "store" in quebec["forbids"]
    # And the reason is on the record rather than in a commit message.
    raw = (REPO_ROOT / "architecture" / "carrier_vetting_recon.yaml").read_text()
    # Strip the comment markers before normalising, or the `#` at each
    # wrapped line becomes a token in the middle of the sentence.
    text = " ".join(line.lstrip().lstrip("#").strip() for line in raw.splitlines())
    text = " ".join(text.split())
    assert "core vocabulary in this corpus" in text, (
        "the reason for the narrowing must be on the record rather than in a commit message"
    )
    assert "trains the reader to dismiss the check" in text


def test_the_record_declares_every_constraint_the_round_actually_measured():
    names = {c.name for c in constraints_of(RECORD)}
    assert {"quebec_prohibits_storing", "ontario_is_crown_copyright",
            "carrier411_terms_prohibit_automation",
            "socrata_licence_is_null_and_terms_unfetched"} <= names


# =====================================================================
# Class 7 applied to the linter's own output
# =====================================================================

def test_no_constraints_declared_is_not_a_clean_record():
    """An unprobed terms page declares no constraint, and so does a record
    that met none. They must not read the same."""
    report = lint("empty", {"anything": "text"})
    assert "NO_CONSTRAINTS_DECLARED" in report.empty_because
    assert "not a finding that the recon met no constraints" in report.empty_because


def test_an_empty_constraints_block_is_a_third_state():
    """It looks clean and has checked nothing."""
    report = lint("blank", {"constraints_measured": {}, "plan": "build a mirror"})
    assert "NO_CONSTRAINTS_PARSED" in report.empty_because
    assert "has checked nothing" in report.empty_because


def test_the_three_clean_looking_outputs_are_distinguishable():
    sentences = {
        lint("a", {"x": "y"}).empty_because,
        lint("b", {"constraints_measured": {}}).empty_because,
        lint("c", RECORD).empty_because,
    }
    assert len(sentences) == 3


def test_the_rendered_report_names_the_constraint_the_path_and_the_sentence():
    planted = dict(RECORD)
    planted["q"] = {"recommendation": THE_INSTANCE}
    text = render(lint("planted", planted))
    assert "quebec_prohibits_storing" in text
    assert "/q/recommendation" in text
    assert "snapshot-and-diff store" in text


def test_the_detector_reports_candidates_rather_than_deciding():
    """It cannot tell a genuinely constrained proposal from a coincidence
    of words. A detector that decided would commit the class one level up:
    acting confidently on a rule it measured loosely."""
    from commerce import recon_lint
    assert "Candidate" in recon_lint.__doc__ or "CANDIDATES" in recon_lint.__doc__
    assert "flags CANDIDATES for a reader" in recon_lint.__doc__


# =====================================================================
# The class record, bound to the tree
# =====================================================================

CLASS_EIGHT = loads((REPO_ROOT / "architecture" / "defect_class_eight.yaml").read_text())


def test_the_class_record_distinguishes_it_from_all_seven_by_name():
    """A new class earns its place only by being distinguishable from each
    existing one. The record must do that individually, not in aggregate."""
    why = CLASS_EIGHT["why_it_is_not_any_of_the_seven"]
    for key in ("not_silent_filtering", "not_scoped_check_blindness", "not_a_vacuous_example",
                "not_wrong_attribution", "not_context_severance",
                "not_the_literal_that_agrees_with_itself", "not_class_seven"):
        assert key in why and why[key]
    assert "fault in the SEAM" in why["the_distinction"]


def test_the_record_says_where_the_canonical_register_lives_and_why_it_was_not_amended():
    """Sea Dog is frozen at 5a6def1. The eighth class cannot be added to
    the canonical register until that lifts, and a record that quietly
    named the class here would lose why."""
    text = (REPO_ROOT / "architecture" / "defect_class_eight.yaml").read_text()
    assert "5a6def1" in text
    assert "FROZEN" in text
    assert "cannot be added to the canonical register" in " ".join(text.split())


def test_the_record_names_the_module_and_it_exists():
    assert (REPO_ROOT / CLASS_EIGHT["the_detector"]["module"]).exists()


def test_the_class_carries_a_standing_question_like_the_others():
    """Each named class in this account carries a question a reader can
    ask of their own work. A class without one is a label."""
    question = CLASS_EIGHT["the_class"]["the_standing_question"]
    assert question.endswith("?")
    assert "measured" in question and "proposed" in question


def test_the_detectors_self_finding_is_recorded():
    finding = CLASS_EIGHT["the_finding_the_detector_produced_about_itself"]
    assert "three candidates" in finding["what_happened"]
    assert "cries wolf" in finding["the_rule_it_yields"]
    assert "cost no coverage" in finding["why_the_narrowing_is_not_a_hole"]


def test_the_record_states_what_the_linter_cannot_see():
    """A constraint nobody wrote down is invisible to it, and the round's
    biggest gaps were questions nobody asked."""
    limits = CLASS_EIGHT["what_is_not_claimed"]
    assert "invisible to it" in limits["not_a_general_solution"]
    assert "questions nobody asked" in limits["not_a_general_solution"]
