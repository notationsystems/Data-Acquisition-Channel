"""The vacuous-evidence class, bound to the instance that produced it.

Every claim in architecture/vacuous_evidence.yaml is re-measured here
against the tree rather than restated from the record.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "scout-retrieval-agent"))

import daf  # noqa: F401,E402

from epistemics._yaml import loads  # noqa: E402

RECORD = loads((REPO_ROOT / "architecture" / "vacuous_evidence.yaml").read_text())
INSTANCE = RECORD["the_measured_instance"]


def test_the_broken_invocation_still_fails_and_still_fails_silently_when_redirected():
    """THE INSTANCE, re-measured. If this ever starts succeeding the
    record is stale and the class needs a live example or none."""
    broken = subprocess.run([sys.executable, "epistemics/doctrine.py"],
                            cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert broken.returncode != 0, (
        "python epistemics/doctrine.py now succeeds; the recorded instance no longer reproduces "
        "and this record must be re-measured rather than re-read"
    )
    assert "ModuleNotFoundError" in broken.stderr

    # And the part that made it invisible: the diagnostic lives entirely
    # in stderr, so `>/dev/null 2>&1` leaves nothing behind but an exit
    # code nobody read.
    assert broken.stdout == "", (
        "the failure now says something on stdout, so redirecting stderr alone would no longer "
        "hide it -- which changes how this instance should be described"
    )
    assert "silences exactly the diagnostic" in INSTANCE["the_idiom_is_the_mechanism"]


def test_the_correct_invocation_works_and_is_the_one_the_record_names():
    correct = subprocess.run(
        [sys.executable, "-c", "import epistemics.doctrine as d; d.write()"],
        cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert correct.returncode == 0, correct.stderr
    assert "import epistemics.doctrine as d" in INSTANCE["what_the_correct_invocation_is"]


def test_the_claim_that_was_vacuously_supported_was_nonetheless_true():
    """The whole point of the class. The mechanism that was actually
    doing the work must still be doing it -- if it is not, this stops
    being an attribution error and becomes an ordinary false claim."""
    real = subprocess.run(
        [sys.executable, "-m", "pytest",
         "tests/test_doctrine_generation.py::test_committed_doctrine_matches_regeneration", "-q"],
        cwd=str(REPO_ROOT), capture_output=True, text=True)
    assert real.returncode == 0, (
        "the check that was actually holding the property is now failing, so the historical claim "
        "was not merely vacuously supported -- re-measure before citing this record"
    )
    assert "YES, throughout" in INSTANCE["was_the_claim_true"]


def test_the_record_states_the_general_repair_and_does_not_overclaim():
    assert "must independently establish that the producing step ran" in RECORD["the_general_repair"]
    assert "not that a redundant check is useless" in RECORD["what_it_does_not_say"]
    assert RECORD["status"].startswith("proposed_for_the_next_joint_reissue")


def test_the_shared_artifact_was_not_edited():
    """This class belongs in proof_integrity.yaml, which the pair holds
    byte-identically. Recorded DAQ-locally instead."""
    scl = pathlib.Path("/home/user/scientific-compute-layer-scl-/architecture/proof_integrity.yaml")
    ours = REPO_ROOT / "architecture" / "proof_integrity.yaml"
    assert "vacuous_evidence" not in ours.read_text(), (
        "the class was written into the shared artifact; that is a joint reissue, not DAQ's to take"
    )
    if scl.exists():
        import hashlib
        assert hashlib.sha256(ours.read_bytes()).digest() == hashlib.sha256(scl.read_bytes()).digest(), (
            "proof_integrity.yaml has diverged across the pair"
        )
