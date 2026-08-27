"""The vacuous-evidence class, bound to the instance that produced it.

Every claim in architecture/vacuous_evidence.yaml is re-measured here
against the tree rather than restated from the record.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

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


# =====================================================================
# The two further classes, bound to the measurements that produced them
# =====================================================================

def test_the_direction_class_is_bound_to_the_kernel_that_produced_it():
    """Not a maxim. The instance is re-measured: the reversed kernel
    passes a sign test and fails a magnitude test."""
    import math
    import sys as _sys

    _sys.path.insert(0, str(REPO_ROOT))
    from instrument.chromatogram import Chromatogram, Column, broaden

    step, peak, n = 0.06, 100, 401
    volumes = tuple(6.0 + step * i for i in range(n))
    delta = Chromatogram(volumes, tuple(1.0 if i == peak else 0.0 for i in range(n)))

    def centroid(chromatogram):
        total = sum(chromatogram.concentrations)
        return sum(v * c for v, c in zip(chromatogram.volumes, chromatogram.concentrations)) / total

    gaussian = broaden(delta, Column("g", 10000, 300.0, 5.0))
    tailed = broaden(delta, Column("e", 10000, 300.0, 5.0, tailing_tau_over_sigma=2.0))

    # The SIGN test -- passes on the correct kernel and passed on the reversed one.
    assert centroid(tailed) > centroid(gaussian)

    # The MAGNITUDE test -- the one that discriminates.
    sigma = volumes[peak] / math.sqrt(10000)
    r = math.exp(-step / (2.0 * sigma))
    assert centroid(tailed) - centroid(gaussian) == pytest.approx((r / (1 - r)) * step, rel=0.02)

    klass = RECORD["a_direction_does_not_discriminate_when_the_property_also_has_a_magnitude"]
    assert "six times further" in klass["the_attestations"]["the_band_broadening_kernel"]
    assert "subsumes a sign check" in klass["why_it_is_not_just_the_discriminating_case_rule"]


def test_the_conservative_limit_class_states_that_the_word_is_a_measurement():
    klass = RECORD["a_stated_limit_that_inverts_a_conclusion_is_not_a_conservative_one"]
    assert "MINUS 20.3%" in klass["the_measured_instance"]
    assert "is a MEASUREMENT rather than an expectation" in klass["the_practical_form"]
    assert "effect unknown in sign and size" in klass["the_practical_form"]


def test_the_second_attestation_is_attributed_rather_than_claimed():
    """DAQ has not seen the PSD code. A class record citing an instance
    this session did not measure must say so."""
    attestations = RECORD[
        "a_direction_does_not_discriminate_when_the_property_also_has_a_magnitude"]["the_attestations"]
    assert "Attributed rather than re-measured" in attestations["the_earlier_one"]
    assert "has not seen that code" in attestations["the_earlier_one"]
