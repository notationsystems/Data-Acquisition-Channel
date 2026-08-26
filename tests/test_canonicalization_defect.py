"""Implicit YAML typing, and why byte equality is the wrong check.

The pinned encoding exists so an artifact's SHA-256 means the same thing
in both repositories. Byte-identical bytes are not sufficient for that:
YAML implicit type resolution lets two conformant parsers agree on the
bytes and disagree on the VALUE. A hash then binds a different typed
structure on each side, which is precisely the failure the pinning was
meant to prevent.

The earlier report called this an ISO-date bug. It is not -- the date is
one member of a class, and the actual defect is the spec's scalar rule:
"strings double-quoted only where required by the spec" should be
"strings double-quoted ALWAYS". See
`architecture/canonicalization_defect.yaml`.

RESOLVED. The coordinated reissue landed: the compute layer authored the
corrected emitter citing this repository's measurement, and it was adopted
here byte-identically rather than reimplemented. Every digest moved in one
step -- both artifacts, both sidecars, the agreement fixture.

These tests were characterization locks on an OPEN defect. They fired when
the serializer changed, which is what they were for, and are now inverted:
they lock the class CLOSED, so a regression would be caught the same way
the defect was.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

import daf  # noqa: F401  -- sys.path bootstrap for the vendored substrate
from epistemics._yaml import loads

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE = REPO_ROOT / "architecture"
EXCHANGE = ARCHITECTURE / "exchange"

sys.path.insert(0, str(EXCHANGE))
from canonical_yaml import canonical_dump

DEFECT = loads((ARCHITECTURE / "canonicalization_defect.yaml").read_text())

# Every committed artifact whose bytes a hash is, or will be, taken over.
HASH_BEARING = sorted(EXCHANGE.glob("*.yaml")) + sorted((ARCHITECTURE / "proposals").glob("*.yaml"))

# The scalars that diverged under the PRE-FIX serializer. They are kept by
# name because the class must stay closed for exactly these, not merely for
# whatever a future test happens to think of.
FORMERLY_DIVERGING = ("2026-08-25", "2026-08-25T12:00:00Z", "1:30:00", "0x1F", ".inf", ".nan")

# Scalars that survived even before the fix -- several only incidentally,
# which is why "they pass" was never evidence the class was closed.
CURRENTLY_SAFE = (
    "yes", "no", "on", "off", "null", "~", "0o777", "1.2", "1.2.3",
    "007", "+5", "1_000", "", "True", "12345", "3.14", "false",
)


def _round_trips_as_a_string(text, original):
    """Typed comparison, which is the whole point: identical bytes that
    parse to `str` on one side and `datetime.date` on the other are a
    failure, not a pass."""
    mine = loads(text)["k"]
    theirs = yaml.safe_load(text)["k"]
    return mine == theirs == original and isinstance(mine, str) and isinstance(theirs, str)


# ------------------------------------------- the class, measured and locked


@pytest.mark.parametrize("scalar", FORMERLY_DIVERGING)
def test_each_formerly_diverging_scalar_now_round_trips(scalar):
    """Inverted from a lock on the open defect to a lock on the closed
    class. Each of these once parsed to a different TYPE under the two
    parsers from identical bytes; under the corrected emitter each is
    quoted and each round-trips as a string."""
    text = canonical_dump({"k": scalar})
    assert _round_trips_as_a_string(text, scalar), (
        f"{scalar!r} diverges again -- the corrected emitter regressed, or this repository's "
        "serializer drifted from the compute layer's byte-identical copy"
    )
    assert '"' in text, f"{scalar!r} must be emitted quoted, not bare"


@pytest.mark.parametrize("scalar", CURRENTLY_SAFE)
def test_scalars_that_currently_survive_still_survive(scalar):
    text = canonical_dump({"k": scalar})
    assert _round_trips_as_a_string(text, scalar), f"{scalar!r} regressed into the divergence class"


def test_no_scalar_diverges_under_the_corrected_serializer():
    """The class, measured closed rather than asserted closed."""
    measured = [s for s in FORMERLY_DIVERGING + CURRENTLY_SAFE
                if not _round_trips_as_a_string(canonical_dump({"k": s}), s)]
    assert measured == [], f"still diverging: {measured}"
    assert DEFECT["resolution"]["divergences_after"] == 0


def test_the_historical_class_is_still_recorded_at_its_measured_size():
    """The defect artifact keeps what WAS measured. A resolved defect that
    forgets its own size cannot be checked for regression."""
    assert DEFECT["measured_failure_class"]["scalars_that_diverge"] == len(FORMERLY_DIVERGING)


def test_the_prescribed_fix_closes_the_entire_class():
    """`strings always double-quoted` -- verified against every scalar in
    both groups, compared as typed values."""

    def always_quoted(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'k: "{escaped}"\n'

    unfixed = [s for s in FORMERLY_DIVERGING + CURRENTLY_SAFE
               if not _round_trips_as_a_string(always_quoted(s), s)]
    assert unfixed == [], f"always-quoting did not close: {unfixed}"
    assert DEFECT["fix_is_verified"]["divergences_after"] == 0


def test_it_is_recorded_as_a_class_not_as_a_date_bug():
    summary = DEFECT["summary"].lower()
    assert "class" in summary
    assert "always" in summary
    assert DEFECT["status"] == "resolved_coordinated_reissue_landed"


def test_the_reissue_moved_every_digest_in_one_step():
    """The blast radius the artifact predicted, checked against what
    actually happened."""
    resolution = DEFECT["resolution"]
    assert len(resolution["digests_reissued"]) == 3, "artifacts and the fixture all move together"
    assert "byte-identical" in resolution["landed"]
    assert "adopted here byte-identically rather than reimplemented" in resolution["authored_by"]


def test_the_serializer_is_byte_identical_to_the_compute_layers_copy():
    """The agreement that makes any hash mean anything, re-verified after
    the reissue rather than assumed to have survived it."""
    upstream = Path("/home/user/scientific-compute-layer-scl-/architecture/exchange/canonical_yaml.py")
    if not upstream.exists():
        pytest.skip("the compute-layer checkout is not present in this environment")
    local = EXCHANGE / "canonical_yaml.py"
    assert local.read_bytes() == upstream.read_bytes(), (
        "the two repositories' serializers have drifted -- every digest on both sides is suspect"
    )


def test_the_fix_was_coordinated_rather_than_unilateral():
    """Patching one side would have broken the agreement that makes every
    hash meaningful. The record keeps why, now that the fix has landed."""
    assert "byte-identical" in DEFECT["why_not_patched_here"]
    assert DEFECT["blast_radius_if_applied"], "a coordinated fix must state what it re-hashes"
    assert len(DEFECT["blast_radius_if_applied"]) >= len(DEFECT["resolution"]["digests_reissued"])


# ------------------------------- every committed artifact, typed comparison


@pytest.mark.parametrize("path", HASH_BEARING, ids=lambda p: p.name)
def test_every_hash_bearing_artifact_agrees_across_two_parsers_by_TYPE(path):
    """The required verification step, applied where it actually matters.
    This is strictly stronger than comparing bytes."""
    text = path.read_text()
    assert loads(text) == yaml.safe_load(text), (
        f"{path.name} parses to different TYPED structures under the two parsers -- its hash does "
        "not identify one value"
    )


@pytest.mark.parametrize("path", HASH_BEARING, ids=lambda p: p.name)
def test_no_hash_bearing_artifact_uses_a_diverging_scalar_shape(path):
    """The interim mitigation, enforced rather than promised."""

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from walk(key)
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)
        elif isinstance(node, str):
            yield node

    document = loads(path.read_text())
    offenders = [
        value for value in walk(document)
        if not _round_trips_as_a_string(canonical_dump({"k": value}), value)
    ]
    assert offenders == [], (
        f"{path.name} contains scalars that emit bare and resolve differently per parser: "
        f"{offenders[:5]}"
    )


# ------------------- the two properties the fix must have, locked as tests


def test_the_fix_is_emitter_side_not_reader_normalization():
    """A reader that normalizes `datetime.date` back to `str` would make
    the round-trip pass while leaving the ARTIFACT ambiguous -- any third
    parser, and the other repository's reader, would still disagree. The
    fix has to be that the bytes are unambiguous, which is an emitter
    property."""
    rule = DEFECT["corrected_rule"]
    scalars = rule["scalars"].lower()
    assert "emitted" in scalars, "the rule must constrain the emitter"
    assert "double-quoted always" in scalars or "double-quoted ALWAYS".lower() in scalars
    assert "implicit typing is forbidden" in scalars

    blob = " ".join(str(v) for v in rule.values()).lower()
    for reader_side in ("normaliz", "coerce", "post-process", "on read", "after parsing"):
        assert reader_side not in blob, (
            f"the corrected rule mentions {reader_side!r} -- a reader-side repair hides the "
            "ambiguity rather than removing it"
        )


def test_byte_equality_alone_would_have_passed_the_date_bug():
    """Why the verification step compares typed structures. Reconstructed
    against the PRE-FIX emission, since the corrected emitter no longer
    produces it -- the demonstration has to outlive the defect."""
    pre_fix_bytes = "k: 2026-08-25\n"          # what the old emitter produced
    post_fix = canonical_dump({"k": "2026-08-25"})
    assert post_fix != pre_fix_bytes, "the corrected emitter must quote it"

    # Byte comparison against itself: satisfied then, and useless.
    assert pre_fix_bytes == "k: 2026-08-25\n"

    # Typed comparison: catches what byte comparison cannot.
    assert loads(pre_fix_bytes) != yaml.safe_load(pre_fix_bytes)
    assert _round_trips_as_a_string(post_fix, "2026-08-25"), "and the fix closes it"


def test_the_recorded_verification_step_demands_typed_structures():
    verification = DEFECT["corrected_rule"]["verification"].lower()
    assert "typed structures" in verification
    assert "not" in verification and "bytes" in verification
    assert "required step" in verification, "it must be required, not advisory"
