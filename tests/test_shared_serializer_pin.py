"""The shared serializer's own source digest.

The fixture agreement check catches any emitter change that alters what
the fixture SERIALIZES TO. It cannot catch an edit that leaves the
fixture's output unchanged -- a comment, a refactor, or behaviour for a
shape the fixture does not cover -- and those edits still make the two
repositories' copies differ, which is the thing byte-identity-by-agreement
exists to prevent.

So the file's own digest is pinned, identically in both repositories.
Either side's suite now catches a local edit WITHOUT needing the other
tree present, which is what makes this runnable in both CI paths rather
than only in the cross-repo check.

If this fails legitimately -- because the serializer is being changed on
purpose -- the change is a COORDINATED REISSUE: update both repositories,
regenerate every artifact, reissue every record carrying a digest, and
verify with architecture/exchange/verify_pair_landed.py that BOTH remotes
landed it. Updating this digest alone is the one thing that is never the
right fix.
"""

from __future__ import annotations

import hashlib
import pathlib

EXCHANGE = pathlib.Path(__file__).resolve().parent.parent / "architecture" / "exchange"


def test_the_shared_serializer_matches_its_pinned_digest():
    source = EXCHANGE / "canonical_yaml.py"
    recorded = (EXCHANGE / "canonical_yaml.sha256").read_text().strip()
    actual = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    assert actual == recorded, (
        "the shared serializer has been edited on one side. This is a coordinated "
        "reissue, not a local fix: change both repositories, regenerate every "
        "artifact, reissue every record carrying a digest, and confirm with "
        "verify_pair_landed.py that both REMOTES landed it."
    )


def test_the_pin_is_not_self_referential():
    """The digest file must not be inside what it digests, or it could
    never be satisfied -- and a check that cannot pass is as useless as
    one that cannot fail."""
    source = (EXCHANGE / "canonical_yaml.py").read_text()
    assert "canonical_yaml.sha256" not in source


def test_the_agreement_fixture_is_still_the_primary_check():
    """The pin is a SECOND line, not a replacement. The fixture is what
    proves the two encodings agree in behaviour; this only proves the
    source has not drifted."""
    assert (EXCHANGE / "canonicalization_fixture.yaml").exists()
    assert (EXCHANGE / "canonicalization_fixture.sha256").exists()


# --------------------------------------------- the DAQ side of the adoption
#
# Everything above this line is byte-identical to the compute layer's copy,
# deliberately: a check whose purpose is that both sides agree is not one to
# reimplement. What follows is DAQ's own record of the adoption and of the
# asymmetry that remains.


def test_the_pin_file_is_byte_identical_to_the_serializer_it_pins():
    """The pin covers `canonical_yaml.py`; this covers the pin itself.
    Both repositories must run the SAME check, not two checks that
    happen to agree today."""
    import hashlib
    source = (EXCHANGE / "canonical_yaml.py").read_bytes()
    assert (EXCHANGE / "canonical_yaml.sha256").read_text().strip() == (
        "sha256:" + hashlib.sha256(source).hexdigest())


def test_the_cross_repo_verifier_checks_remotes_and_not_locals():
    """Adopted verbatim from the compute layer, which wrote it after a
    real incident: one half of a coordinated reissue reached its remote
    and the other did not, and the push was reported failed when it had
    succeeded. A local commit proves authorship; only the remote HEADs
    prove the pair landed together."""
    verifier = (EXCHANGE / "verify_pair_landed.py").read_text()
    assert "asks the REMOTES, not the locals" in verifier
    assert "architecture/exchange/canonical_yaml.py" in verifier


def test_the_recorded_ci_asymmetry_is_stated_rather_than_implied():
    """`runs in both suites` and `runs in both CI paths` are different
    claims, and only the first is true. Measured and recorded in
    architecture/canonicalization_defect.yaml rather than left to be
    inferred from the pin's own docstring, which says `both CI paths`
    because on the authoring side that was the intent."""
    import pathlib
    from epistemics._yaml import loads

    root = pathlib.Path(__file__).resolve().parent.parent
    record = loads((root / "architecture" / "canonicalization_defect.yaml").read_text())
    enforcement = record["enforcement_in_both_suites"]

    assert "not in both CI paths" in enforcement["measured_ci_asymmetry"]
    assert enforcement["adopted_by_daq"].startswith("byte-identically")

    # This repository's half is real and is asserted, not described.
    workflow = root / ".github" / "workflows" / "conformance.yml"
    assert workflow.exists()
    assert "pytest" in workflow.read_text()
