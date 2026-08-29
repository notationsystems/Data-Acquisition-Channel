"""The operator surface, graded before it was built.

WHAT WAS MISSING AND WHY IT MATTERED. The instrument enforced its
invariants and had no way to be USED: an operator with a queue on paper
had to write Python to reach it. That is not a small ergonomic gap. The
preconditions -- a date, a time-box, the researcher's own questions and a
stopping rule -- are supplied by a person under time pressure on the
morning of a session, and a mechanism only reachable through an import
statement will be reached by nobody. The blocked precondition was partly
a missing FORM.

WHAT THESE ASSETS ARE NOT. They do not invent a queue. The templates
carry field names and instructions and no questions; the one file that
carries questions is labelled `fabricated_example` inside its own content
and is asserted to say so, following the fixture convention this
repository already uses for the GPC report. A work order built from
questions the builder made up would measure the builder.

WHY JSON AND NOT YAML. `session/` may not import `epistemics`, which owns
the YAML subset parser, and a second parser in this package would be the
duplicate-vocabulary problem in a new place. `json` is stdlib and is not
a layer.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from session.intake import (MALFORMED_INTAKE, QUEUE_FIELD_MISSING,  # noqa: E402
                            UNKNOWN_QUEUE_FIELD, load_capture, load_queue,
                            render_order, render_session)
from session.work_order import (ABANDONED_AT_ITS_BOX, NOT_REACHED,  # noqa: E402
                                NO_ACCEPTANCE_TEST, WORKED, close_session, plan)

TEMPLATES = REPO_ROOT / "session" / "templates"


def _queue(**overrides):
    item = {
        "identifier": "q1",
        "question": "which of the corridors carries the tonnage",
        "decision_it_could_change": "whether to buy the corridor grade",
        "acceptance_test": "an answer names a corridor or refuses",
        "expected_yield": 6.0,
        "minutes": 30,
        "acceptance_test_at": 1,
    }
    item.update(overrides)
    return {"box_minutes": 120, "items": [item]}


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


# =====================================================================
# The intake refuses a malformed queue rather than guessing at it
# =====================================================================

def test_a_queue_missing_a_required_field_is_refused_by_name():
    """The field is NAMED. `invalid queue` sends an operator back to read
    the whole file; the missing key sends them to one line."""
    payload = _queue()
    del payload["items"][0]["acceptance_test"]
    with pytest.raises(ValueError) as caught:
        load_queue(json.dumps(payload))
    assert QUEUE_FIELD_MISSING in str(caught.value)
    assert "acceptance_test" in str(caught.value)
    assert "q1" in str(caught.value), "the refusal must say WHICH item"


def test_an_unknown_field_is_refused_rather_than_ignored():
    """A typo'd key silently dropped is a queue item that quietly loses
    its box or its yield -- the value the operator thought they set."""
    payload = _queue(minutes_=30)
    with pytest.raises(ValueError) as caught:
        load_queue(json.dumps(payload))
    assert UNKNOWN_QUEUE_FIELD in str(caught.value)
    assert "minutes_" in str(caught.value)


def test_text_that_is_not_json_is_refused_as_malformed_not_as_empty():
    """An unparseable file and an empty queue are different states, and
    returning an empty list for both is the class this instrument spends
    its whole surface refusing."""
    with pytest.raises(ValueError) as caught:
        load_queue("box_minutes: 120\nitems: []\n")   # YAML, not JSON
    assert MALFORMED_INTAKE in str(caught.value)


def test_a_well_formed_queue_loads_into_the_ranker_untouched():
    box_minutes, items = load_queue(json.dumps(_queue()))
    assert box_minutes == 120
    order = plan(items, box_minutes=box_minutes)
    assert [i.identifier for i in order.items] == ["q1"]
    assert order.refusals == ()
    # And the loader supplies no default the operator did not write: an
    # item with no acceptance test is refused at load, so it can never
    # arrive at the ranker as NO_ACCEPTANCE_TEST with a value invented.
    assert items[0].acceptance_test == "an answer names a corridor or refuses"


# =====================================================================
# The templates are templates, and the example says it is fabricated
# =====================================================================

def test_the_queue_template_carries_no_questions():
    """A template with a question in it becomes the question. The fields
    are there; the content is the researcher's."""
    template = json.loads((TEMPLATES / "queue.template.json").read_text())
    assert template["items"] == [], "the template must ship EMPTY of items"
    assert "how_to_fill_this" in template
    for key in ("identifier", "question", "decision_it_could_change", "acceptance_test",
                "expected_yield", "minutes", "acceptance_test_at"):
        assert key in template["field_notes"], f"{key} has no note telling the operator what it is"


def test_the_capture_template_carries_no_findings():
    template = json.loads((TEMPLATES / "capture.template.json").read_text())
    assert template["findings"] == []
    assert template["abandoned"] == []
    assert template["residue"] == [], "residue ships as an EMPTY LIST, never absent"
    assert "residue" in template, (
        "the key must be present even when empty -- an omitted residue is refused, and a "
        "template that omits it teaches the omission"
    )
    assert template["stopping_rule_met"] is None, (
        "the stopping rule is a fact of the session, not a default"
    )


def test_the_example_declares_itself_fabricated_inside_its_own_content():
    """The convention this repository already uses for the GPC fixture.
    An example queue that does not say so is a queue."""
    example = json.loads((TEMPLATES / "example.fabricated.json").read_text())
    assert example["provenance"] == "fabricated_example"
    assert "no researcher" in example["what_this_is_not"].lower()
    assert example["items"], "an example with no items demonstrates nothing"


def test_the_example_runs_end_to_end_and_exercises_every_outcome():
    """A worked example that only shows the happy path teaches half the
    instrument. This one produces all three outcomes and a drop."""
    raw = (TEMPLATES / "example.fabricated.json").read_text()
    box_minutes, items = load_queue(raw)
    order = plan(items, box_minutes=box_minutes)
    assert order.drops, "the example must show a question being dropped, in writing"
    session = close_session(order, **load_capture(
        (TEMPLATES / "example.capture.fabricated.json").read_text()))
    assert session.refusals == (), f"the worked example must be clean: {session.refusals}"
    assert session.accounting[WORKED]
    assert session.accounting[ABANDONED_AT_ITS_BOX]
    assert session.accounting[NOT_REACHED]
    assert session.complete is True


# =====================================================================
# The command line: the surface an operator actually touches
# =====================================================================

def test_plan_prints_the_order_the_drops_and_the_refusals(tmp_path):
    payload = _queue()
    payload["items"].append({**payload["items"][0], "identifier": "q2",
                             "decision_it_could_change": None})
    payload["items"].append({**payload["items"][0], "identifier": "q3",
                             "acceptance_test": None})
    path = _write(tmp_path, "queue.json", payload)
    box_minutes, items = load_queue(path.read_text())
    rendered = render_order(plan(items, box_minutes=box_minutes))
    assert "q1" in rendered
    assert "DROPPED" in rendered and "q2" in rendered
    assert NO_ACCEPTANCE_TEST in rendered and "q3" in rendered, (
        "a refused item must appear in the printed order; an operator who cannot see it "
        "will assume it was ranked"
    )


def test_the_cli_runs_and_exits_nonzero_when_the_session_is_refused(tmp_path):
    """The exit code is the operator's signal. A session whose record
    cannot be graded must not exit 0."""
    queue_path = _write(tmp_path, "queue.json", _queue())
    good = subprocess.run([sys.executable, "-m", "session", "plan", str(queue_path)],
                          cwd=REPO_ROOT, capture_output=True, text=True)
    assert good.returncode == 0, good.stderr
    assert "q1" in good.stdout

    # A capture omitting the residue is refused, and the exit code says so.
    capture_path = _write(tmp_path, "capture.json", {
        "findings": [], "abandoned": [], "stopping_rule_met": True,
    })
    bad = subprocess.run(
        [sys.executable, "-m", "session", "close", str(queue_path), str(capture_path)],
        cwd=REPO_ROOT, capture_output=True, text=True)
    assert bad.returncode != 0
    assert "RESIDUE_OMITTED" in bad.stdout + bad.stderr


def test_the_cli_refuses_a_malformed_file_by_name_rather_than_traceback(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text("not json at all")
    result = subprocess.run([sys.executable, "-m", "session", "plan", str(path)],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode != 0
    assert MALFORMED_INTAKE in result.stdout + result.stderr
    assert "Traceback" not in result.stderr, (
        "an operator reading a stack trace at the start of a session is being asked to debug "
        "the instrument instead of running it"
    )


def test_render_session_states_the_accounting_and_the_residue():
    raw = (TEMPLATES / "example.fabricated.json").read_text()
    box_minutes, items = load_queue(raw)
    order = plan(items, box_minutes=box_minutes)
    session = close_session(order, **load_capture(
        (TEMPLATES / "example.capture.fabricated.json").read_text()))
    rendered = render_session(session)
    for bucket in (WORKED, ABANDONED_AT_ITS_BOX, NOT_REACHED):
        assert bucket.upper() in rendered, f"the printed record must show the {bucket} bucket"
    assert "RESIDUE" in rendered
    assert "COMPLETE" in rendered
