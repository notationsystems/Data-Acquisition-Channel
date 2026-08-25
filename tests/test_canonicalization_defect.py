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

`architecture/exchange/canonical_yaml.py` is byte-identical to the
compute layer's copy BY AGREEMENT, and that agreement is what makes any
hash meaningful, so it is NOT patched here -- the fix must land in both
repositories together and reissue every digest. These tests do two
things in the meantime:

  1. measure and lock the exact failure class, so it cannot be
     misremembered as a date bug or silently widen;
  2. enforce, over every committed artifact, that both parsers yield
     identical TYPED structures -- not merely identical bytes.
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

# The scalars measured to diverge under the CURRENT shared serializer.
DIVERGING = ("2026-08-25", "2026-08-25T12:00:00Z", "1:30:00", "0x1F", ".inf", ".nan")

# Scalars that happen to survive today, several only incidentally.
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


@pytest.mark.parametrize("scalar", DIVERGING)
def test_each_known_diverging_scalar_still_diverges(scalar):
    """A characterization lock. If one of these starts passing, the
    shared serializer changed -- which re-hashes every artifact and must
    be a coordinated reissue, not a silent improvement."""
    text = canonical_dump({"k": scalar})
    assert not _round_trips_as_a_string(text, scalar), (
        f"{scalar!r} no longer diverges -- the shared serializer changed. Every artifact digest "
        "must be reissued in the same coordinated step; update "
        "architecture/canonicalization_defect.yaml rather than this assertion."
    )


@pytest.mark.parametrize("scalar", CURRENTLY_SAFE)
def test_scalars_that_currently_survive_still_survive(scalar):
    text = canonical_dump({"k": scalar})
    assert _round_trips_as_a_string(text, scalar), f"{scalar!r} regressed into the divergence class"


def test_the_divergence_class_is_exactly_what_is_recorded():
    """The recorded count must match the measurement, so the artifact
    cannot drift away from reality."""
    measured = [s for s in DIVERGING + CURRENTLY_SAFE
                if not _round_trips_as_a_string(canonical_dump({"k": s}), s)]
    assert sorted(measured) == sorted(DIVERGING)
    assert DEFECT["measured_failure_class"]["scalars_that_diverge"] == len(DIVERGING)


def test_the_prescribed_fix_closes_the_entire_class():
    """`strings always double-quoted` -- verified against every scalar in
    both groups, compared as typed values."""

    def always_quoted(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'k: "{escaped}"\n'

    unfixed = [s for s in DIVERGING + CURRENTLY_SAFE
               if not _round_trips_as_a_string(always_quoted(s), s)]
    assert unfixed == [], f"always-quoting did not close: {unfixed}"
    assert DEFECT["fix_is_verified"]["divergences_after"] == 0


def test_it_is_recorded_as_a_class_not_as_a_date_bug():
    summary = DEFECT["summary"].lower()
    assert "class" in summary
    assert "always" in summary
    assert DEFECT["status"] == "measured_open_requires_coordination"


def test_the_shared_serializer_was_not_patched_unilaterally():
    """Editing it on one side breaks the agreement that makes every hash
    meaningful. The reason is recorded, not just the fact."""
    assert "byte-identical" in DEFECT["why_not_patched_here"]
    assert DEFECT["blast_radius_if_applied"], "a coordinated fix must state what it re-hashes"


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
