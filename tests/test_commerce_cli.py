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


# =====================================================================
# The third instance of the same class
# =====================================================================

def test_every_operator_surface_is_reachable_without_writing_python():
    """THE CLASS, THIRD INSTANCE. `record` and `form` were added when
    walking a transaction showed step 8 stopping. The morning view, the
    sheet reader and the outbound queue were then built in the same
    session by the same author and left reachable only by import.

    This test exists so a fourth surface cannot be added the same way."""
    import commerce.__main__ as cli
    for command in ("form", "sheet", "record", "read", "morning", "outbound"):
        assert command in cli.COMMANDS, f"{command} is not reachable from the shell"


def test_a_blank_sheet_header_is_printable():
    result = subprocess.run([sys.executable, "-m", "commerce", "sheet"],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.startswith("load,kind,value")
    assert result.stdout.count("\n") == 1, "a template with an example row becomes the example"


def _auth_file(tmp_path):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"authority": AUTH}))
    return path


def test_read_takes_a_sheet_and_grades_it_in_one_pass(tmp_path):
    header = subprocess.run([sys.executable, "-m", "commerce", "sheet"],
                            cwd=REPO_ROOT, capture_output=True, text=True).stdout
    sheet = tmp_path / "loads.csv"
    sheet.write_text(header
                     + "L-1,rate_quoted,2400,CAD,2026-08-25,phone,op-7,2026-08-28,,,,\n"
                     + "L-1,rate_invoiced,2550,CAD,2026-09-10,document,op-7,,,,,\n")
    result = subprocess.run([sys.executable, "-m", "commerce", "read", str(sheet),
                             str(_auth_file(tmp_path))], cwd=REPO_ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "residual" in result.stdout and "+150.00" in result.stdout


def test_a_refused_row_makes_read_exit_nonzero_and_say_it_is_not_the_whole_day(tmp_path):
    """An operator who does not see the refusal will read the shorter list
    as the whole day."""
    header = subprocess.run([sys.executable, "-m", "commerce", "sheet"],
                            cwd=REPO_ROOT, capture_output=True, text=True).stdout
    sheet = tmp_path / "loads.csv"
    sheet.write_text(header
                     + "L-1,rate_quoted,2400,CAD,2026-08-25,phone,op-7,2026-08-28,,,,\n"
                     + "L-2,rate_quoted,oops,CAD,2026-08-26,phone,op-7,2026-08-28,,,,\n")
    result = subprocess.run([sys.executable, "-m", "commerce", "read", str(sheet),
                             str(_auth_file(tmp_path))], cwd=REPO_ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "NOT THE WHOLE DAY" in result.stdout


def test_read_without_an_authority_file_exits_two(tmp_path):
    sheet = tmp_path / "loads.csv"
    sheet.write_text("load\n")
    result = subprocess.run([sys.executable, "-m", "commerce", "read", str(sheet)],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert "authority" in result.stdout


def test_the_morning_view_prints_three_lists_from_the_shell(tmp_path):
    path = tmp_path / "opps.json"
    path.write_text(json.dumps({
        "asof": "2026-08-31",
        "activity_classes": ["domestic_brokerage"],
        "credentials": {"cargo_liability_insurance": "held"},
        "opportunities": [
            {"identifier": "O-1", "activity_class": "domestic_brokerage",
             "received_at": "2026-08-31", "weight": "about 40,000 lbs"},
        ],
        "pricing": {}, "sustainable_loads_per_week": 58.3,
    }))
    result = subprocess.run([sys.executable, "-m", "commerce", "morning", str(path)],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout and "the day's work" in result.stdout
    assert "insolvency at a profit" in result.stdout


def test_the_outbound_queue_prints_what_is_waiting_for_a_person(tmp_path):
    path = tmp_path / "drafts.json"
    path.write_text(json.dumps({"drafts": [
        {"kind": "quote", "counterparty": "Acme",
         "body": "can you cover Toronto-Detroit Thursday at $2,400"},
    ]}))
    result = subprocess.run([sys.executable, "-m", "commerce", "outbound", str(path)],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[BINDING]" in result.stdout
    assert "reads as an offer to the recipient" in result.stdout


def test_a_malformed_morning_file_exits_two_without_a_traceback(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    result = subprocess.run([sys.executable, "-m", "commerce", "morning", str(path)],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
