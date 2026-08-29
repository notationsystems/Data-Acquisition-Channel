"""The sea_dog_session instrument, graded before it was implemented.

THE INSTRUMENT'S THREE VALIDATIONS, from the doctrine, each written here
before the module that satisfies it:

    every queue item has a stated acceptance test and an expected-yield
        rank BEFORE the session starts
    every findings record cites its sources
    the residue list is non-empty or explicitly marked empty; it is
        never omitted

AND ITS THREE INVARIANTS, which the doctrine requires in code rather
than in prose:

    ordering is by discrimination, not openness -- a question that
        cannot change a downstream decision is DROPPED, in writing, with
        its reason, and never silently
    the acceptance test is written BEFORE the item is worked, so the
        answer is not graded by the person who produced it after seeing
        it
    the session terminates on the stopping rule, not on fatigue

WHY A SEQUENCE AND NOT A CLOCK. "Written before" is enforced against a
caller-supplied monotonic sequence position, not a timestamp. A wall
clock invites an argument about skew and about which machine's clock,
and the property being enforced is an ORDER. A stamp that cannot be
compared is not evidence of order.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from session.work_order import (ABANDONED_AND_ALSO_REPORTED,  # noqa: E402
                                ABANDONED_AT_ITS_BOX,
                                ABANDONED_ITEM_NOT_IN_THE_ORDER,
                                ABANDONED_WITHOUT_A_REASON,
                                ACCEPTANCE_TEST_POSTDATES_WORK,
                                EMPTY_BECAUSE_EVERY_ITEM_WAS_DROPPED,
                                EMPTY_BECAUSE_THE_QUEUE_WAS_EMPTY,
                                EVERY_REACHED_ITEM_WAS_ABANDONED,
                                FINDING_CITES_NO_SOURCE,
                                FINDING_DECLARES_NO_EVIDENCE_CLASS,
                                FINDING_FOR_NO_ITEM,
                                NO_ACCEPTANCE_TEST,
                                NO_DECISION_IT_COULD_CHANGE,
                                NO_ITEM_WAS_REACHED,
                                NO_TIME_BOX,
                                NOT_REACHED,
                                WORKED,
                                RESIDUE_OMITTED,
                                STOPPED_WITHOUT_THE_STOPPING_RULE,
                                Abandonment, Finding, QueueItem, close_session,
                                plan)


def _item(identifier="q1", *, decision="whether to build the allocation model",
          test="an answer names a source or it does not", yield_=6.0, minutes=30,
          test_at=1, worked_at=None):
    return QueueItem(
        identifier=identifier,
        question=f"question {identifier}",
        decision_it_could_change=decision,
        acceptance_test=test,
        expected_yield=yield_,
        minutes=minutes,
        acceptance_test_at=test_at,
        worked_at=worked_at,
    )


# =====================================================================
# Validation 1 -- every item is ranked and tested BEFORE the session
# =====================================================================

def test_the_order_is_yield_per_unit_time_and_not_yield():
    """DISCRIMINATION PER MINUTE. A high-yield item that eats the whole
    box is not the first thing to do; the ordering must be able to put a
    smaller answer first, or `per unit time` is decoration."""
    big = _item("big", yield_=9.0, minutes=120)     # 0.075 / min
    small = _item("small", yield_=4.0, minutes=20)  # 0.200 / min
    order = plan([big, small], box_minutes=180)
    assert [i.identifier for i in order.items] == ["small", "big"]
    assert order.refusals == ()
    # And the ordering is not merely alphabetical or insertion order.
    assert [i.identifier for i in plan([small, big], box_minutes=180).items] == ["small", "big"]


def test_an_item_without_an_acceptance_test_is_refused_not_ranked():
    order = plan([_item("q1"), _item("q2", test=None)], box_minutes=60)
    assert (NO_ACCEPTANCE_TEST, "q2") in order.refusals
    assert [i.identifier for i in order.items] == ["q1"], (
        "an untested item must not appear in the order at all -- ranking it would let the "
        "acceptance test be written afterwards, which is the invariant"
    )


def test_an_item_without_a_time_box_is_refused():
    """Per-item boxing is what makes an overrun a DECISION to abandon
    rather than exhaustion. An item with no box cannot overrun."""
    order = plan([_item("q1", minutes=None)], box_minutes=60)
    assert (NO_TIME_BOX, "q1") in order.refusals
    assert order.items == ()


# =====================================================================
# Invariant 1 -- dropped for a stated reason, never silently
# =====================================================================

def test_a_question_that_changes_no_decision_is_dropped_in_writing():
    order = plan([_item("keep"), _item("idle", decision=None)], box_minutes=60)
    assert [i.identifier for i in order.items] == ["keep"]
    dropped = {d.identifier: d for d in order.drops}
    assert "idle" in dropped, "an unranked question must be recorded as dropped"
    assert dropped["idle"].code == NO_DECISION_IT_COULD_CHANGE
    assert dropped["idle"].reason, "a drop without a reason is a silent drop wearing a record"
    # The dropped item is NOT also a refusal: dropping is the intended
    # handling of an open question, not a malformed one.
    assert all(identifier != "idle" for _, identifier in order.refusals)


def test_an_empty_order_says_WHICH_nothing_it_is():
    """Every item dropped and no item supplied are different facts about
    the queue, and an empty tuple states neither."""
    all_dropped = plan([_item("a", decision=None), _item("b", decision=None)], box_minutes=60)
    assert all_dropped.items == ()
    assert all_dropped.empty_because == EMPTY_BECAUSE_EVERY_ITEM_WAS_DROPPED
    assert len(all_dropped.drops) == 2

    nothing_asked = plan([], box_minutes=60)
    assert nothing_asked.items == ()
    assert nothing_asked.empty_because == EMPTY_BECAUSE_THE_QUEUE_WAS_EMPTY
    assert nothing_asked.empty_because != all_dropped.empty_because

    # And a populated order carries no such note: a warrant on every
    # result is a warrant on none.
    assert plan([_item("a")], box_minutes=60).empty_because is None


# =====================================================================
# Invariant 2 -- the test predates the work
# =====================================================================

def test_an_acceptance_test_written_after_the_item_was_worked_is_refused():
    """THE GRADING PROBLEM. If the test may be written after the answer
    is seen, it grades nothing. Enforced on the order, not remembered."""
    late = _item("late", test_at=9, worked_at=4)
    order = plan([late], box_minutes=60)
    assert (ACCEPTANCE_TEST_POSTDATES_WORK, "late") in order.refusals
    assert order.items == ()

    early = _item("early", test_at=2, worked_at=7)
    assert plan([early], box_minutes=60).refusals == ()

    # The boundary is not a preference: written AT the same position as
    # the work is not written before it.
    same = _item("same", test_at=5, worked_at=5)
    assert (ACCEPTANCE_TEST_POSTDATES_WORK, "same") in plan([same], box_minutes=60).refusals


# =====================================================================
# Validation 2 -- findings cite sources
# =====================================================================

def test_a_finding_with_no_sources_is_refused():
    order = plan([_item("q1", worked_at=5)], box_minutes=60)
    session = close_session(
        order,
        findings=[Finding(item_id="q1", statement="the researcher never opened the graph",
                          sources=(), evidence_class="asserted")],
        residue=(),
        stopping_rule_met=True,
    )
    assert (FINDING_CITES_NO_SOURCE, "q1") in session.refusals


def test_a_finding_that_belongs_to_no_queue_item_is_refused():
    """A finding attributed to nothing cannot be graded against an
    acceptance test, which is the only thing that makes it a finding
    rather than an impression."""
    order = plan([_item("q1", worked_at=5)], box_minutes=60)
    session = close_session(
        order,
        findings=[Finding(item_id="q9", statement="s", sources=("transcript 12:04",), evidence_class="asserted")],
        residue=(),
        stopping_rule_met=True,
    )
    assert (FINDING_FOR_NO_ITEM, "q9") in session.refusals


def test_a_sourced_finding_against_a_pre_registered_test_is_accepted():
    order = plan([_item("q1", test_at=1, worked_at=5)], box_minutes=60)
    session = close_session(
        order,
        findings=[Finding(item_id="q1", statement="opened the refusal queue first",
                          sources=("transcript 12:04", "session-baseline.json"),
                          evidence_class="asserted")],
        residue=("does the miss log survive a second session?",),
        stopping_rule_met=True,
    )
    assert session.refusals == ()
    assert session.findings[0].sources


# =====================================================================
# Validation 3 -- the residue is never omitted
# =====================================================================

def test_an_omitted_residue_list_is_refused_and_an_empty_one_is_not():
    """The distinction the doctrine draws explicitly: `nothing was
    raised` and `nobody wrote down what was raised` are different
    sessions, and an absent list says neither."""
    order = plan([_item("q1", worked_at=5)], box_minutes=60)
    finding = Finding(item_id="q1", statement="s", sources=("t",), evidence_class="asserted")

    omitted = close_session(order, findings=[finding], residue=None, stopping_rule_met=True)
    assert (RESIDUE_OMITTED, "session") in omitted.refusals

    explicitly_empty = close_session(order, findings=[finding], residue=(),
                                     stopping_rule_met=True)
    assert all(code != RESIDUE_OMITTED for code, _ in explicitly_empty.refusals)
    assert explicitly_empty.residue == ()
    assert explicitly_empty.residue_was_stated is True


# =====================================================================
# Invariant 3 -- terminates on the rule, not on fatigue
# =====================================================================

def test_a_session_that_stopped_without_the_stopping_rule_says_so():
    order = plan([_item("q1", worked_at=5)], box_minutes=60)
    finding = Finding(item_id="q1", statement="s", sources=("t",), evidence_class="asserted")
    tired = close_session(order, findings=[finding], residue=(), stopping_rule_met=False)
    assert (STOPPED_WITHOUT_THE_STOPPING_RULE, "session") in tired.refusals
    # It is a REFUSAL and not an exception: the session happened, and its
    # findings are still evidence. What is refused is the claim that it
    # finished.
    assert tired.findings and tired.complete is False
    assert close_session(order, findings=[finding], residue=(),
                         stopping_rule_met=True).complete is True


# =====================================================================
# The instrument is a projection, not a promoter
# =====================================================================

def test_the_module_cannot_reach_canonical_state():
    """AUTHORITY BOUNDARY, asserted structurally rather than promised.
    `Findings are observations` -- the module must not import anything
    that could promote one. Checked on the import list, because a rule
    about what a layer may touch is exactly the kind that decays into a
    comment."""
    import ast

    # SWEPT, not named. The first version read ONE file by name, which is
    # enumeration-by-location: a second module in the package inherited
    # the claim without inheriting the check. Every .py under session/ is
    # read, and the sweep asserts it found more than the file it started
    # with, so the package growing cannot quietly outrun it.
    forbidden = {"daf", "scout", "evidence", "structures", "science", "epistemics"}
    modules = sorted((REPO_ROOT / "session").rglob("*.py"))
    assert len(modules) >= 2, "the layer sweep is reading fewer files than the package holds"
    for module in modules:
        imported = set()
        for node in ast.walk(ast.parse(module.read_text())):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.add(node.module.split(".")[0])
        assert not (imported & forbidden), (
            f"{module.name} must not reach an acquisition, admission or state layer; "
            f"it imports {sorted(imported & forbidden)}"
        )


def test_every_refusal_code_is_an_observable_and_not_a_diagnosis():
    """The naming rule this program already applies to
    EVERY_RUN_DIFFERS_IN: a code asserts what was OBSERVED, never a cause
    it cannot establish. `STOPPED_WITHOUT_THE_STOPPING_RULE` says the
    rule was not met, not that anyone was tired."""
    from session import work_order

    codes = [value for name, value in vars(work_order).items()
             if name.isupper() and isinstance(value, str) and name == value]
    assert len(codes) >= 8, "the refusal vocabulary is smaller than the module's own claims"
    for code in codes:
        assert "FATIGUE" not in code and "LAZY" not in code and "BAD" not in code, (
            f"{code} names a cause rather than an observable"
        )


# =====================================================================
# The named-but-absent schema
# =====================================================================

def test_a_finding_that_declares_no_evidence_class_is_refused():
    """The doctrine says findings conform to `the research finding
    schema`. MEASURED: no such schema exists in this repository, in the
    vendored substrate at the pin, or in the instrument the session
    studies. What an acquisition layer can assert without one is that the
    finding said SOMETHING about its class rather than nothing -- the
    same resolution the GPC extractor reached when it tried to import
    UNCERTAINTY_KINDS from a layer that owns them."""
    order = plan([_item("q1", worked_at=5)], box_minutes=60)
    unclassed = Finding(item_id="q1", statement="s", sources=("t",))
    session = close_session(order, findings=[unclassed], residue=(), stopping_rule_met=True)
    assert (FINDING_DECLARES_NO_EVIDENCE_CLASS, "q1") in session.refusals
    assert unclassed.evidence_class is None, "unset must not be defaulted on the way in either"


def test_the_class_vocabulary_is_owned_elsewhere_and_not_restated_here():
    """A second copy of a closed vocabulary drifts from the first, and the
    layer rule forbids the import that would keep them in step. So
    `session/` holds NO list of classes, and the relation is bound here
    instead: the class a session finding would carry is a member of the
    set `epistemics.evidence_class` owns, measured from the artifact."""
    from epistemics._yaml import loads
    from session import work_order

    declared = loads((REPO_ROOT / "architecture" / "evidence_class.yaml").read_text())
    ingest_classes = set(declared["ingest_classes"])
    assert "asserted" in ingest_classes, (
        "a researcher's account of what they did is an ASSERTED class; if that word has left "
        "the vocabulary the refusal below is pointing at nothing"
    )

    source = (REPO_ROOT / "session" / "work_order.py").read_text()
    for name in sorted(ingest_classes):
        assert f'"{name}"' not in source, (
            f"session/work_order.py restates the class {name!r}; the vocabulary is owned by "
            "epistemics.evidence_class and a copy here would drift"
        )
    # And the module still refuses an unclassed finding, so declining to
    # hold the list is not declining to require one.
    assert hasattr(work_order, "FINDING_DECLARES_NO_EVIDENCE_CLASS")


# =====================================================================
# Deliverable 2 and 3 together: every ranked item lands in exactly one
# bucket, and an item that overran was ABANDONED rather than forgotten
# =====================================================================

def test_every_ranked_item_lands_in_exactly_one_bucket():
    """ROW ACCOUNTING, applied to the session itself.

    The doctrine asks for a findings record PER ITEM and for a per-item
    box `so an item that overruns is abandoned deliberately rather than
    by exhaustion`. Both need the same thing: an item that was ranked and
    then produced nothing must say WHICH nothing -- worked, abandoned at
    its box, or never reached. Three items, three outcomes, and the
    counts conserve."""
    order = plan([_item("a", yield_=9.0, minutes=10, worked_at=5),
                  _item("b", yield_=6.0, minutes=20, worked_at=5),
                  _item("c", yield_=1.0, minutes=30)], box_minutes=60)
    assert [i.identifier for i in order.items] == ["a", "b", "c"]

    session = close_session(
        order,
        findings=[Finding(item_id="a", statement="s", sources=("t",), evidence_class="asserted")],
        abandoned=[Abandonment(identifier="b", reason="ran past its twenty minutes with the "
                                                      "corridor grade still unresolved",
                               minutes_spent=26)],
        residue=("what the grade would have taken",),
        stopping_rule_met=True,
    )
    assert session.refusals == ()
    assert session.accounting == {WORKED: ("a",), ABANDONED_AT_ITS_BOX: ("b",),
                                  NOT_REACHED: ("c",)}
    assert sum(len(v) for v in session.accounting.values()) == len(order.items), (
        "every ranked item must be in exactly one bucket, or the session lost one"
    )


def test_an_abandonment_without_a_reason_is_refused():
    """`Abandoned deliberately` and `abandoned by exhaustion` differ only
    in whether anyone wrote down why. Without the reason the record
    cannot tell them apart, which is the whole point of the box."""
    order = plan([_item("a", worked_at=5)], box_minutes=60)
    session = close_session(order, findings=[],
                            abandoned=[Abandonment(identifier="a", reason="", minutes_spent=40)],
                            residue=(), stopping_rule_met=True)
    assert (ABANDONED_WITHOUT_A_REASON, "a") in session.refusals


def test_an_item_cannot_be_both_abandoned_and_reported():
    """Two answers to one question -- the shape `replicate_pairing`
    already refuses as CONFLICTING_VALUE_FOR_A_RUN."""
    order = plan([_item("a", worked_at=5)], box_minutes=60)
    session = close_session(
        order,
        findings=[Finding(item_id="a", statement="s", sources=("t",), evidence_class="asserted")],
        abandoned=[Abandonment(identifier="a", reason="overran", minutes_spent=40)],
        residue=(), stopping_rule_met=True)
    assert (ABANDONED_AND_ALSO_REPORTED, "a") in session.refusals
    # AND THE ACCOUNTING STILL CONSERVES. Found by a plant: refusing the
    # conflict is not the same as not double-counting it, and the first
    # version of this test asserted only the refusal. An item appearing
    # in two buckets makes the session's own row accounting untrue while
    # every refusal reads correctly -- a check correct about what it
    # examined and silent about what it handed on.
    buckets = session.accounting
    assert sum(len(v) for v in buckets.values()) == len(session.order.items)
    seen = [identifier for bucket in buckets.values() for identifier in bucket]
    assert len(seen) == len(set(seen)), f"an item is in two buckets: {seen}"


def test_an_abandonment_naming_no_ranked_item_is_refused():
    order = plan([_item("a", worked_at=5)], box_minutes=60)
    session = close_session(order, findings=[],
                            abandoned=[Abandonment(identifier="zz", reason="overran",
                                                   minutes_spent=5)],
                            residue=(), stopping_rule_met=True)
    assert (ABANDONED_ITEM_NOT_IN_THE_ORDER, "zz") in session.refusals


def test_a_session_with_no_findings_says_WHICH_no_findings():
    """The empty-collection rule, at the session. Nothing reached and
    everything abandoned are different afternoons."""
    order = plan([_item("a", minutes=30), _item("b", minutes=30)], box_minutes=60)

    nothing_reached = close_session(order, findings=[], abandoned=[], residue=(),
                                    stopping_rule_met=True)
    assert nothing_reached.findings_empty_because == NO_ITEM_WAS_REACHED

    all_abandoned = close_session(
        order, findings=[],
        abandoned=[Abandonment(identifier="a", reason="overran", minutes_spent=31),
                   Abandonment(identifier="b", reason="overran", minutes_spent=31)],
        residue=(), stopping_rule_met=True)
    assert all_abandoned.findings_empty_because == EVERY_REACHED_ITEM_WAS_ABANDONED
    assert all_abandoned.findings_empty_because != nothing_reached.findings_empty_because

    # A session that produced findings carries no such note.
    produced = close_session(
        order,
        findings=[Finding(item_id="a", statement="s", sources=("t",), evidence_class="asserted")],
        abandoned=[], residue=(), stopping_rule_met=True)
    assert produced.findings_empty_because is None


def test_the_plan_reports_an_overrun_rather_than_trimming_to_fit():
    """Which items to cut is the operator's call. A plan quietly trimmed
    to fit reads as a plan that fits."""
    order = plan([_item("a", minutes=50), _item("b", minutes=50)], box_minutes=60)
    assert len(order.items) == 2, "the plan must not silently drop the item that does not fit"
    assert order.planned_minutes == 100
    assert order.overruns_the_box is True
    assert plan([_item("a", minutes=20)], box_minutes=60).overruns_the_box is False
