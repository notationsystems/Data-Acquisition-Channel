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


# =====================================================================
# The second instance, and the class it exposed
# =====================================================================

SIBLING = pathlib.Path("/home/user/scientific-compute-layer-scl-")
VERIFIER = REPO_ROOT / "architecture" / "exchange" / "verify_pair_landed.py"


def test_the_malformed_invocation_really_produces_a_zero_that_means_nothing():
    """THE MECHANISM, executed rather than described.

    Two defects, both the same family: the script was given no arguments,
    so it printed usage and returned 2; and `$?` after a pipeline is the
    LAST command's status, so a pipe to `tail` reported 0. Neither is
    about this repository's content and both are why a false claim was
    committed."""


    direct = subprocess.run([sys.executable, str(VERIFIER)], capture_output=True, text=True)
    assert direct.returncode == 2, "no arguments must be a usage error, not a pass"
    assert "Usage:" in direct.stdout, (
        "and the usage text is what scrolled past under a `tail`, reading like check output"
    )

    piped = subprocess.run(
        f'{sys.executable} {VERIFIER} 2>&1 | tail -2', shell=True,
        capture_output=True, text=True)
    assert piped.returncode == 0, (
        "the pipeline reports the LAST command's status. This zero is the one that was read as "
        "the check passing, and it is a fact about shells rather than about the pair."
    )

    instance = RECORD["the_second_instance"]
    assert "status of the LAST command" in instance["how_the_check_was_malformed_in_this_session"]
    assert "does not reconstruct" in instance["what_is_not_claimed_here"] or \
        "is not reconstructed" in instance["what_is_not_claimed_here"]


def test_the_record_does_not_claim_to_know_how_the_earlier_commit_was_run():
    """The commit that carried the false claim is outside this session's
    record. A class record that reconstructed it would be inventing the
    evidence it is filed for lacking."""
    instance = RECORD["the_second_instance"]
    assert instance["was_the_claim_true"].startswith("NO")
    assert "outside this session's record" in instance["what_is_not_claimed_here"]
    assert "false as measured today" in instance["what_is_not_claimed_here"]


def test_the_register_could_not_have_been_produced_by_the_other_side():
    """THE DISCRIMINATOR THE CHECK DOES NOT ASK FOR, measured on the half
    of it that lives here.

    The stale-mirror reading rests on the compute layer not holding the
    inputs. Half of that is checkable in this repository: the register's
    bent-zero block is derived by scanning THIS repository's phase
    reports, so a copy of it carrying those lines was produced here."""

    register = loads((REPO_ROOT / "architecture" / "exchange"
                      / "invariant_register.yaml").read_text())
    assert register["owner"] == "daf"
    occurrences = register["bent_zero_claims_held_here"]["occurrences"]
    assert occurrences, "the block must be non-empty or it discriminates nothing"
    for occurrence in occurrences:
        document = REPO_ROOT / occurrence["document"]
        assert document.exists(), (
            f"{occurrence['document']} is cited by the register and is not in this tree"
        )
        assert occurrence["document"].startswith("docs/PHASE_")

    klass = RECORD["a_diff_and_a_stale_mirror_are_the_same_observation_with_different_causes"]
    assert "could have PRODUCED its own copy" in klass["what_the_discriminator_actually_was"]
    assert "invites the wrong repair" in klass["what_its_own_docstring_already_says"]


def test_the_verifiers_own_docstring_says_byte_identity_is_not_currency():
    """The class credits the verifier with already naming half the gap.
    Quoted from the file rather than from memory."""
    text = VERIFIER.read_text()
    assert "unfinished mirror" in text, (
        "the class says the verifier's own docstring names the currency gap; if that text is "
        "gone, the credit is stale and the class must be re-argued"
    )


@pytest.mark.skipif(not SIBLING.exists(), reason="the sibling repository is not checked out here")
def test_the_stale_mirror_measurement_where_the_sibling_is_present():
    """The cross-repository half. Skipped rather than assumed when the
    sibling is absent -- a test that silently passed without it would be
    the vacuous-evidence shape this module is about."""
    theirs = SIBLING / "architecture" / "exchange" / "invariant_register.yaml"
    if not theirs.exists():
        pytest.skip("the sibling does not hold the register")

    mine = loads((REPO_ROOT / "architecture" / "exchange"
                  / "invariant_register.yaml").read_text())
    other = loads(theirs.read_text())
    assert other["bent_zero_claims_held_here"]["occurrences"] == \
        mine["bent_zero_claims_held_here"]["occurrences"], (
        "the two copies must agree on the block derived from THIS repository's documents; if "
        "they do not, the other side is generating its own and the stale-mirror reading is wrong"
    )

    theirs_own_count = 0
    for path in sorted(SIBLING.rglob("*.yaml")):
        relative = path.relative_to(SIBLING)
        if relative.parts and relative.parts[0] in ("vendor", ".git"):
            continue
        if path.name == "invariant_register.yaml":
            continue
        try:
            document = loads(path.read_text())
        except Exception:
            continue
        if isinstance(document, dict) and document.get("extends") == "core@1.0.0":
            theirs_own_count += 1
    assert theirs_own_count != other["extends_join"]["artifacts_declaring_the_core"], (
        "the other side's census matches its own tree, so its copy is independently generated "
        "and the DIFF is a genuine divergence rather than a stale mirror -- re-argue the class"
    )


def test_the_propagation_class_carries_its_measurement_and_its_inversion():
    klass = RECORD[
        "a_figure_propagated_through_a_nonlinear_function_is_not_a_measurement_of_it"]
    assert "0.07 points, not 0.69" in klass["the_measured_instance"]
    assert "the conclusion inverted" in klass["what_the_error_cost"]
    assert "MEASURE IT" in klass["the_practical_form"]
    assert "not by this repository" in klass["how_it_was_caught"], (
        "the class must attribute the catch; a record that quietly took credit for an outside "
        "correction would be the attribution failure this file already files"
    )


def test_the_propagation_class_distinguishes_itself_from_jensen():
    """A class that restated a textbook inequality would not be worth a
    record. What makes it one is that the discarded variation was
    STRUCTURED and ran against the curvature."""
    klass = RECORD[
        "a_figure_propagated_through_a_nonlinear_function_is_not_a_measurement_of_it"]
    assert "not merely Jensen" in klass["why_it_is_not_merely_jensens_inequality"] or \
        "Jensen says" in klass["why_it_is_not_merely_jensens_inequality"]
    assert "structured, not noise" in klass["why_it_is_not_merely_jensens_inequality"]
    assert "no counterpart in the data" in klass["why_it_is_not_merely_jensens_inequality"]
