"""An artifact that describes its own encoding, checked against it.

THE SHAPE, which is new and is not the coverage one. Every mechanism this
pair has built verifies an artifact AGAINST ITS DIGEST. None verified an
artifact against ITS OWN CLAIMS. `daq_capabilities.yaml` carries a
`canonicalization` block describing the rules it was emitted under, and
that block went stale through TWO coordinated reissues:

  * `strings: double-quoted only where plain style would be unsafe` --
    the rule the FIRST reissue replaced;
  * a `shared_fixture_agreement` digest from before BOTH reissues.

The reason no digest check could catch it is exact and worth stating:
THE CONTENT AND THE ENCODING DISAGREED, AND THE DIGEST IS OVER THE
CONTENT. Both reissues correctly recomputed the hash. Both sidecars
matched. Every integrity check in both repositories passed, over an
artifact that was lying about how it was hashed.

THE CHECK IS DRIVEN BY THE CLAIMS, NOT BY A LIST. Each claim in the
block is bound to a verifier by name, and a claim with no verifier FAILS
-- so the next field added to the block cannot be silently unchecked.
That construction is deliberate: the enumerated form is what this
repository now records as the default failure of a check written under
time pressure, and a hand-listed set of assertions here would be one.

Wherever possible a claim is verified against THE ARTIFACT'S OWN BYTES
rather than against the emitter, because the artifact is the evidence for
its own description. `strings: double-quoted ALWAYS` is checked by
reading every scalar the artifact actually contains.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCHANGE = REPO_ROOT / "architecture" / "exchange"
sys.path.insert(0, str(EXCHANGE))
import canonical_yaml as cy  # noqa: E402

ARTIFACT = EXCHANGE / "daq_capabilities.yaml"
BYTES = ARTIFACT.read_bytes()
TEXT = ARTIFACT.read_text()
DOCUMENT = loads(TEXT)
CLAIMS = DOCUMENT["canonicalization"]


# --------------------------------------------------------------- verifiers
#
# One per claim, keyed by the claim's own field name. Each returns None on
# agreement or a string saying how the artifact's text and the fact differ.


def _v_anchors_aliases(claim):
    if "forbidden" not in claim:
        return f"claim is {claim!r}"
    for line in TEXT.splitlines():
        stripped = line.strip()
        if stripped.startswith("&") or stripped.startswith("*"):
            return f"the artifact itself contains an anchor or alias: {line!r}"
    return None


def _v_encoding(claim):
    if "UTF-8" not in claim or "LF" not in claim:
        return f"claim is {claim!r}"
    try:
        BYTES.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"the artifact is not valid UTF-8: {exc}"
    if b"\r" in BYTES:
        return "the artifact contains CR; the claim says LF line endings"
    if not BYTES.endswith(b"\n") or BYTES.endswith(b"\n\n"):
        return "the artifact does not end in exactly one newline"
    return None


def _v_floats(claim):
    # The claim describes emitter behaviour; check the emitter.
    if "1e16" not in claim.replace("|x| >= 1e16", "1e16"):
        return f"claim no longer names the exponent threshold: {claim!r}"
    if cy.canonical_dump({"k": 1.0}) != '"k": 1.0\n':
        return "the emitter does not render 1.0 as claimed"
    if "e+" not in cy.canonical_dump({"k": 1e16}):
        return "the emitter does not use exponent form at the claimed threshold"
    if "e" in cy.canonical_dump({"k": 1.5}):
        return "the emitter uses exponent form below the claimed threshold"
    return None


def _v_hash(claim):
    if "sha256" not in claim or "bytes" not in claim:
        return f"claim is {claim!r}"
    sidecar = ARTIFACT.with_suffix(".sha256").read_text().strip()
    actual = "sha256:" + hashlib.sha256(BYTES).hexdigest()
    if sidecar != actual:
        return f"the sidecar says {sidecar} and the bytes hash to {actual}"
    return None


def _v_implementation(claim):
    named = claim.split()[0]
    if not (REPO_ROOT / named).exists():
        return f"the artifact names {named!r}, which does not exist"
    return None


def _v_keys(claim):
    if "sorted" not in claim:
        return f"claim is {claim!r}"
    # Checked against the artifact's own bytes: re-emitting a document
    # parsed from them must reproduce them exactly, which can only hold if
    # the committed key order is the sorted one.
    if cy.canonical_bytes(DOCUMENT) != BYTES:
        return "the artifact is not a fixed point of the emitter it describes"
    return None


def _v_reference_format(claim):
    if "sha256:<hex>" not in claim:
        return f"claim is {claim!r}"
    # The claim states the FORMAT, so its own text contains the literal
    # `sha256:<hex>`. Excluded by value rather than by position: a
    # positional exclusion would silently stop excluding if the block's
    # key order changed.
    for line in TEXT.splitlines():
        if claim in line:
            continue
        for match in re.finditer(r"sha256:\S*", line):
            token = match.group(0).rstrip('",')
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", token):
                return f"the artifact contains a malformed reference: {token!r}"
    return None


def _v_sequence_in_sequence(claim):
    if "REFUSED" not in claim:
        return f"claim is {claim!r}"
    try:
        cy.canonical_dump({"k": [[1]]})
    except TypeError:
        return None
    return "the artifact claims the emitter refuses it; the emitter does not"


def _v_serialization(claim):
    if "block style" not in claim:
        return f"claim is {claim!r}"
    # The artifact's own bytes: no flow collection except the documented
    # empty ones.
    for number, line in enumerate(TEXT.splitlines(), 1):
        body = line.split(": ", 1)[-1].strip()
        if body in ("{}", "[]", ""):
            continue
        if body.startswith("[") or body.startswith("{"):
            return f"line {number} uses flow style: {line!r}"
    return None


def _v_shared_fixture(claim):
    if not (EXCHANGE / Path(claim).name).exists():
        return f"the artifact names {claim!r}, which does not exist"
    return None


def _v_shared_fixture_agreement(claim):
    named = re.search(r"sha256:[0-9a-f]{64}", claim)
    if not named:
        return "the agreement statement names no digest"
    recorded = (EXCHANGE / "canonicalization_fixture.sha256").read_text().strip()
    if named.group(0) != recorded:
        return f"the artifact names {named.group(0)} and the fixture is {recorded}"
    if named.group(0) != cy.canonical_sha256(cy.FIXTURE):
        return "the named digest is not what the emitter produces for the fixture"
    return None


def _v_strings(claim):
    if "ALWAYS" not in claim:
        return f"the artifact states a string rule that is not always-quote: {claim!r}"
    if cy.canonical_dump({"k": "plain"}) != '"k": "plain"\n':
        return "the emitter does not quote unconditionally"
    # ...and the artifact's own bytes: every key is quoted.
    for number, line in enumerate(TEXT.splitlines(), 1):
        stripped = line.lstrip("- ").strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        if not stripped.startswith('"'):
            return f"line {number} carries an unquoted key: {line!r}"
    return None


VERIFIERS = {
    name[len("_v_"):]: function
    for name, function in list(globals().items())
    if name.startswith("_v_")
}


# ------------------------------------------------------------------- tests


def test_every_claim_in_the_block_has_a_verifier():
    """THE ANTI-ENUMERATION PROPERTY, and the reason this file is built
    the way it is. A claim with no verifier is a claim nothing checks,
    which is exactly the state the stale `strings` rule was in for two
    reissues. Adding a field to the block without a verifier fails here
    rather than being silently trusted."""
    unverified = sorted(set(CLAIMS) - set(VERIFIERS))
    assert unverified == [], (
        f"these self-descriptive claims have no verifier, so nothing binds them to the thing they "
        f"describe: {unverified}")

    stale_verifiers = sorted(set(VERIFIERS) - set(CLAIMS))
    assert stale_verifiers == [], (
        f"these verifiers name claims the artifact no longer makes: {stale_verifiers}")


@pytest.mark.parametrize("claim_name", sorted(CLAIMS))
def test_the_artifacts_self_description_matches_the_thing_it_describes(claim_name):
    problem = VERIFIERS[claim_name](CLAIMS[claim_name])
    assert problem is None, f"canonicalization.{claim_name}: {problem}"


def test_the_two_measured_staleness_cases_are_the_ones_this_catches():
    """Both defects, replayed against the verifiers that now cover them --
    the required step for a new check is to plant the defect it claims to
    catch and watch it fail, not to trust a pass."""
    assert _v_strings("double-quoted only where plain style would be unsafe or ambiguous") is not None
    assert _v_shared_fixture_agreement(
        "both repositories independently produce "
        "sha256:5859ce6e16e2be1650b940290574a65864239a876831e747ca5e5d3d6c31429c for the shared "
        "fixture") is not None

    # ...and a third the block would have hidden the same way.
    assert _v_sequence_in_sequence("emitted as a compact nested block") is not None


def test_a_digest_check_could_never_have_caught_this():
    """The reason this shape needs its own check, demonstrated rather than
    asserted: the artifact's digest is over its CONTENT, and the stale
    claim WAS content. Both reissues recomputed the hash correctly and
    both sidecars matched while the artifact described an encoding it was
    not emitted under."""
    sidecar = ARTIFACT.with_suffix(".sha256").read_text().strip()
    assert sidecar == "sha256:" + hashlib.sha256(BYTES).hexdigest()

    # A document with a deliberately false self-description hashes and
    # verifies exactly as well as a true one.
    lying = dict(DOCUMENT)
    lying["canonicalization"] = dict(CLAIMS, strings="double-quoted only where required")
    lying_bytes = cy.canonical_bytes(lying)
    assert cy.canonical_sha256(lying) == "sha256:" + hashlib.sha256(lying_bytes).hexdigest(), (
        "a lying artifact is perfectly self-consistent under every digest check that exists")
    assert _v_strings(lying["canonicalization"]["strings"]) is not None, (
        "...and only a claim-versus-fact check separates it from a true one")


# ------------------------- the class record, checked against the substrate
#
# `architecture/proof_integrity.yaml` is itself prose about measured facts,
# which is the thing the instance below says has nothing defending it. So
# its claims are bound here rather than trusted.


PROOF_INTEGRITY = loads((REPO_ROOT / "architecture" / "proof_integrity.yaml").read_text())
INSTANCES = {entry["name"]: entry for entry in PROOF_INTEGRITY["instances"]}


def test_the_self_description_instance_names_a_check_that_exists_and_runs():
    entry = INSTANCES["a_self_describing_artifact_lying_about_its_own_encoding"]
    assert entry["enforcement"] == "tests/" + Path(__file__).name
    assert (REPO_ROOT / entry["enforcement"]).exists()
    assert "DIGEST IS OVER THE CONTENT" in entry["why_no_digest_check_could_catch_it"]


def test_the_prose_instance_states_what_each_half_actually_measured():
    """The correction that matters most in this file, because the earlier
    version of the class record said both halves recorded the same wrong
    reason. Bound to the artifact that carries the correct measurement,
    so the claim cannot drift back."""
    entry = INSTANCES["a_measured_fact_recorded_in_prose_has_nothing_defending_it"]
    assert "88248ac" in entry["what_happened"]

    defect = loads((REPO_ROOT / "architecture" / "canonicalization_defect.yaml").read_text())
    measured = defect["second_reissue"]["collection_class"]["measured"]
    assert "STRINGS" in measured, (
        "the acquisition half's original measurement of the SILENT case is the evidence for the "
        "correction; if it is no longer here, the correction rests on nothing")

    convergence = PROOF_INTEGRITY["convergence_is_not_evidence"]
    assert "not what happened" in convergence["the_counter_instance_corrected"]
    assert "the merge" in convergence["what_actually_went_wrong"].lower()


def test_the_rate_note_states_its_own_counter_evidence():
    """A class that finds its own instances quickly may be a real class or
    a lens that makes everything look like itself. The note has to say
    what would distinguish them, or it is unfalsifiable."""
    rate = PROOF_INTEGRITY["the_rate_is_itself_the_finding"]
    assert "default" in rate["what_the_rate_suggests"].lower()
    caution = rate["a_caution_against_the_obvious_reading"]
    assert "counter-evidence" in caution

    # The named non-instances are real: a closed vocabulary IS its property.
    from science.admissibility import UNCERTAINTY_KINDS
    from science.table import ABSENCE_REASONS
    assert "uncertainty_kind" in caution and "absence reasons" in caution
    assert len(UNCERTAINTY_KINDS) == 4 and len(ABSENCE_REASONS) == 5, (
        "the two named closed vocabularies changed; the caution's examples need re-checking")
