"""The operator surface for one load — the Phase 0 blocker.

Walking one real transaction through the tree showed steps 1 to 7 working
and step 8 stopping: nothing could be reached without writing Python. That
is the defect this account already named and fixed for the session
instrument, recurring at the shortest distance from the class that names
it. These tests grade the fix.

THE EXIT CODE IS THE POINT. The operator's next action is decided by
whether the shell said it was fine, so a record that cannot be graded must
not exit 0.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

AUTH = {"holder": "ops", "instrument": "signing_delegation",
        "valid_from": "2026-01-01", "valid_until": "2026-12-31"}


def _event(**over):
    base = {"load": "L-001", "kind": "rate_quoted", "value": 2400.0, "unit": "CAD",
            "known_at": "2026-08-25", "recorded_at": "2026-08-28", "method": "phone",
            "recorded_by": "op-7"}
    base.update(over)
    return base


def _run(tmp_path, payload, name="load.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    result = subprocess.run([sys.executable, "-m", "commerce", "record", str(path)],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    return result


def test_one_load_records_end_to_end_and_exits_zero(tmp_path):
    result = _run(tmp_path, {"authority": AUTH, "events": [
        _event(kind="rate_quoted", value=2400.0),
        _event(kind="rate_invoiced", value=2550.0, known_at="2026-09-10",
               method="document", recorded_at=None),
    ]})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "residual" in result.stdout and "+150.00" in result.stdout


def test_an_unsettled_promise_stays_visible_rather_than_being_dropped(tmp_path):
    """A promise in no bucket is one the firm has forgotten it made."""
    result = _run(tmp_path, {"authority": AUTH, "events": [
        _event(kind="pickup_promised", value=20260901.0, unit="epoch_day"),
    ]})
    assert result.returncode == 0
    assert "NOT YET SETTLED" in result.stdout
    assert "awaiting pickup_actual" in result.stdout
    assert "accounted 1 of 1" in result.stdout


def test_a_basis_mismatch_is_refused_and_exits_nonzero(tmp_path):
    """Promised in days, invoiced in dollars: the residual would be a
    number with no referent."""
    result = _run(tmp_path, {"authority": AUTH, "events": [
        _event(kind="transit_estimated", value=4.0, unit="days"),
        _event(kind="transit_realized", value=5.0, unit="hours", known_at="2026-09-02",
               method="observed", recorded_at=None),
    ]})
    assert result.returncode == 1
    assert "REFUSED" in result.stdout
    assert "NOT GRADEABLE" in result.stdout


def test_a_load_with_no_authority_is_refused_at_the_file_boundary(tmp_path):
    """A load recorded under no authority is a commitment the record
    cannot say who was entitled to make."""
    result = _run(tmp_path, {"events": [_event()]})
    assert result.returncode == 2
    assert "NO_AUTHORITY_STATED" in result.stdout


def test_an_empty_events_list_is_a_file_with_nothing_in_it(tmp_path):
    """Not a load with nothing to say about it. An empty record would read
    as the second."""
    result = _run(tmp_path, {"authority": AUTH, "events": []})
    assert result.returncode == 1
    assert "not a load with nothing to say about it" in result.stdout


def test_a_known_at_equal_to_the_typing_time_is_refused_through_the_cli(tmp_path):
    """The refusal that makes the first record worth having, reachable
    from the shell rather than only from an import."""
    result = _run(tmp_path, {"authority": AUTH, "events": [
        _event(known_at="2026-08-28", recorded_at="2026-08-28"),
    ]})
    assert result.returncode == 2
    assert "KNOWN_AT_DEFAULTED_TO_THE_TYPING_TIME" in result.stdout


def test_an_unreadable_file_exits_two_without_a_traceback(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("not json at all")
    result = subprocess.run([sys.executable, "-m", "commerce", "record", str(path)],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr, (
        "an operator reading a stack trace at the start of a load is being asked to debug the "
        "instrument instead of using it"
    )


def test_a_missing_file_exits_two():
    result = subprocess.run([sys.executable, "-m", "commerce", "record", "/tmp/does-not-exist"],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 2


def test_usage_exits_two_so_a_bare_invocation_is_not_success():
    result = subprocess.run([sys.executable, "-m", "commerce"],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert "record" in result.stdout


def test_the_form_command_emits_a_fillable_array(tmp_path):
    result = subprocess.run([sys.executable, "-m", "commerce", "form"],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0
    form = json.loads(result.stdout)
    assert isinstance(form, list) and len(form) == 1
    assert form[0]["known_at"] == ""
    assert "NOT when you are typing" in form[0]["how_to_fill_this"]["known_at"] or \
        "not when you are typing" in form[0]["how_to_fill_this"]["known_at"].lower()


def test_the_form_output_is_directly_usable_as_input(tmp_path):
    """The loop closes: what `form` prints is what `record` reads. A form
    whose output needs editing into a different shape is two formats."""
    printed = subprocess.run([sys.executable, "-m", "commerce", "form"],
                             cwd=REPO_ROOT, capture_output=True, text=True).stdout
    form = json.loads(printed)[0]
    filled = {k: v for k, v in form.items() if k != "how_to_fill_this"}
    filled.update({"load": "L-9", "kind": "rate_quoted", "value": 100.0, "unit": "CAD",
                   "known_at": "2026-08-25", "recorded_at": "2026-08-28",
                   "method": "phone", "recorded_by": "op-1"})
    filled = {k: v for k, v in filled.items() if v != ""}
    result = _run(tmp_path, {"authority": AUTH, "events": [filled]}, name="filled.json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NOT YET SETTLED" in result.stdout
